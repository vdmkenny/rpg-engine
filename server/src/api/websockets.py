"""
WebSocket Protocol Handler

This module implements the WebSocket protocol with:
- Correlation ID support for request/response pairing
- Consistent message patterns (Commands/Queries -> Responses, Events)
- Structured error handling with actionable error codes
- Enhanced broadcasting with targeting (Personal/Nearby/Map/Global)
- Rate limiting with per-operation cooldowns

The handler is composed from domain-specific mixins for maintainability.
"""

import time
import traceback
from typing import Optional, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from jose import JWTError
import msgpack
from glide import GlideClient

from server.src.api.connection_manager import ConnectionManager
from server.src.core.database import get_valkey
from server.src.core.logging_config import get_logger
from server.src.core.metrics import (
    metrics,
    websocket_connections_active,
    players_online,
    websocket_connection_duration_seconds,
)

from server.src.services.game_state import get_player_state_manager
from server.src.services.map_service import map_manager
from server.src.services.player_service import PlayerService
from server.src.services.equipment_service import EquipmentService
from server.src.services.connection_service import ConnectionService

from common.src.protocol import (
    WSMessage,
    MessageType,
    ErrorCodes,
    ErrorCategory,
    PROTOCOL_VERSION,
    AuthenticatePayload,
    ErrorPayload,
)

from common.src.websocket_utils import (
    CorrelationManager,
    StateUpdateManager,
    MessageValidator,
    RateLimiter,
    MessageRouter,
    BroadcastManager,
    rate_limit_configs,
)

from server.src.game.game_loop import register_player_login

from server.src.api.handlers import (
    BaseHandlerMixin,
    MovementHandlerMixin,
    ChatHandlerMixin,
    InventoryHandlerMixin,
    GroundItemHandlerMixin,
    EquipmentHandlerMixin,
    CombatHandlerMixin,
    QueryHandlerMixin,
)

from server.src.api.helpers import (
    OperationRateLimiter,
    receive_auth_message,
    authenticate_player,
    initialize_player_connection,
    send_welcome_message,
    handle_player_join_broadcast,
    broadcast_player_left,
)

router = APIRouter()
logger = get_logger(__name__)

manager = ConnectionManager()
correlation_manager = CorrelationManager()
state_manager = StateUpdateManager()
message_validator = MessageValidator()
rate_limiter = RateLimiter(rate_limit_configs)
broadcast_manager = BroadcastManager(manager)


class WebSocketHandler(
    MovementHandlerMixin,
    ChatHandlerMixin,
    InventoryHandlerMixin,
    GroundItemHandlerMixin,
    EquipmentHandlerMixin,
    CombatHandlerMixin,
    QueryHandlerMixin,
    BaseHandlerMixin,
):
    """
    Unified WebSocket handler implementing Protocol unified patterns.
    
    Composed from domain-specific mixins for maintainability.
    Handles all message types with consistent request/response correlation
    and structured error handling.
    """
    
    def __init__(
        self,
        websocket: WebSocket,
        username: str,
        player_id: int,
        valkey: GlideClient,
    ):
        self.websocket = websocket
        self.username = username
        self.player_id = player_id
        self.valkey = valkey
        self.router = MessageRouter()
        self._setup_message_handlers()
    
    def _setup_message_handlers(self):
        """Register all message type handlers."""
        # Command handlers (state-changing operations)
        self.router.register_handler(MessageType.CMD_AUTHENTICATE, self._handle_cmd_authenticate)
        self.router.register_handler(MessageType.CMD_MOVE, self._handle_cmd_move)
        self.router.register_handler(MessageType.CMD_CHAT_SEND, self._handle_cmd_chat_send)
        self.router.register_handler(MessageType.CMD_INVENTORY_MOVE, self._handle_cmd_inventory_move)
        self.router.register_handler(MessageType.CMD_INVENTORY_SORT, self._handle_cmd_inventory_sort)
        self.router.register_handler(MessageType.CMD_ITEM_DROP, self._handle_cmd_item_drop)
        self.router.register_handler(MessageType.CMD_ITEM_PICKUP, self._handle_cmd_item_pickup)
        self.router.register_handler(MessageType.CMD_ITEM_EQUIP, self._handle_cmd_item_equip)
        self.router.register_handler(MessageType.CMD_ITEM_UNEQUIP, self._handle_cmd_item_unequip)
        self.router.register_handler(MessageType.CMD_ATTACK, self._handle_cmd_attack)
        self.router.register_handler(MessageType.CMD_TOGGLE_AUTO_RETALIATE, self._handle_cmd_toggle_auto_retaliate)
        
        # Query handlers (data retrieval operations)
        self.router.register_handler(MessageType.QUERY_INVENTORY, self._handle_query_inventory)
        self.router.register_handler(MessageType.QUERY_EQUIPMENT, self._handle_query_equipment)
        self.router.register_handler(MessageType.QUERY_STATS, self._handle_query_stats)
        self.router.register_handler(MessageType.QUERY_MAP_CHUNKS, self._handle_query_map_chunks)
    
    async def process_message(self, message: WSMessage) -> None:
        """
        Process incoming WebSocket message using the unified router.
        
        Handles correlation ID tracking, rate limiting, and error responses.
        """
        try:
            raw_message = msgpack.packb(message.model_dump(), use_bin_type=True)
            await self.router.route_message(self.websocket, raw_message, self.player_id)
            
        except Exception as e:
            logger.error(
                "Error processing WebSocket message",
                extra={
                    "username": self.username,
                    "message_type": message.type,
                    "correlation_id": message.id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                ErrorCategory.SYSTEM,
                "Internal server error occurred",
                suggested_action="Please retry the operation"
            )
    
    async def _handle_cmd_authenticate(self, message: WSMessage) -> None:
        """Handle CMD_AUTHENTICATE - should not be called after initial auth."""
        await self._send_error_response(
            message.id,
            ErrorCodes.AUTH_PLAYER_NOT_FOUND,
            ErrorCategory.PERMISSION,
            "Already authenticated"
        )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    valkey: GlideClient = Depends(get_valkey),
):
    """
    WebSocket handler implementing structured message patterns.
    
    Provides comprehensive request/response handling with correlation IDs,
    structured error responses, and enhanced broadcasting capabilities.
    """
    username: Optional[str] = None
    player_id: Optional[int] = None
    connection_start_time = None
    handler: Optional[WebSocketHandler] = None
    
    try:
        await websocket.accept()
        metrics.track_websocket_connection("accepted")
        connection_start_time = time.time()
        
        # Wait for authentication message
        auth_message = await receive_auth_message(websocket)
        username, player_id = await authenticate_player(auth_message)
        
        # Initialize player connection and load into GSM
        await initialize_player_connection(username, player_id, valkey)
        
        # Create handler instance for this connection
        handler = WebSocketHandler(websocket, username, player_id, valkey)
        
        # Send welcome message
        await send_welcome_message(websocket, username, player_id)
        
        # Handle player join broadcasting
        await handle_player_join_broadcast(websocket, username, player_id, manager)
        
        # Register connection with manager
        player_mgr = get_player_state_manager()
        position = await player_mgr.get_position(player_id)
        if not position:
            raise WebSocketDisconnect(
                code=status.WS_1011_INTERNAL_ERROR,
                reason="Could not get player position"
            )
        await manager.connect(websocket, player_id, position["map_id"])
        
        # Register for game loop
        await register_player_login(player_id)
        
        # Update metrics
        _update_connection_metrics()
        
        logger.info(
            "Player connected",
            extra={
                "username": username,
                "player_id": player_id,
            }
        )
        
        # Main message processing loop
        while True:
            try:
                data = await websocket.receive_bytes()
                await handler.router.route_message(websocket, data, player_id)
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(
                    "Error in message processing loop",
                    extra={
                        "username": username,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "traceback": traceback.format_exc()
                    }
                )
                continue
                
    except WebSocketDisconnect as e:
        logger.debug(
            "Player disconnected",
            extra={"username": username, "reason": e.reason or "Normal disconnect"}
        )
        metrics.track_websocket_connection("disconnected")
        
    except JWTError:
        logger.warning("JWT validation failed")
        metrics.track_websocket_connection("auth_failed")
        try:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION, 
                reason="Invalid token"
            )
        except Exception:
            pass
            
    except Exception as e:
        logger.error(
            "WebSocket error",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }
        )
        metrics.track_websocket_connection("error")
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
            
    finally:
        if connection_start_time:
            duration = time.time() - connection_start_time
            websocket_connection_duration_seconds.observe(duration)
        
        if username:
            await _handle_player_disconnect(username, player_id)
            _update_connection_metrics()


async def _handle_player_disconnect(username: str, player_id: Optional[int]) -> None:
    """Handle player disconnection cleanup."""
    try:
        # Get map from player_id (not username)
        player_map = manager.player_to_map.get(player_id) if player_id else None
        
        await ConnectionService.handle_player_disconnect(
            username, player_map, manager, rate_limiter
        )
        
        # Disconnect from connection manager using player_id
        if player_id:
            await manager.disconnect(player_id)
        
        if player_map:
            await broadcast_player_left(username, player_id, player_map, manager)
        
        logger.debug(
            "Player disconnection handled",
            extra={"username": username, "player_id": player_id}
        )
        
    except Exception as e:
        logger.error(
            "Error handling player disconnect",
            extra={
                "username": username,
                "player_id": player_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }
        )


def _update_connection_metrics() -> None:
    """Update connection metrics after connect/disconnect."""
    total_connections = sum(
        len(conns) for conns in manager.connections_by_map.values()
    )
    websocket_connections_active.set(total_connections)
    players_online.set(total_connections)
