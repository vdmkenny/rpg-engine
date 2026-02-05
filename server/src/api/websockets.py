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
    ErrorResponsePayload,
    PROTOCOL_VERSION,
    AuthenticatePayload,
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
    AppearanceHandlerMixin,
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
    AppearanceHandlerMixin,
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
        self.router.register_handler(MessageType.CMD_UPDATE_APPEARANCE, self._handle_cmd_update_appearance)
        
        # Query handlers (data retrieval operations)
        self.router.register_handler(MessageType.QUERY_INVENTORY, self._handle_query_inventory)
        self.router.register_handler(MessageType.QUERY_EQUIPMENT, self._handle_query_equipment)
        self.router.register_handler(MessageType.QUERY_STATS, self._handle_query_stats)
        self.router.register_handler(MessageType.QUERY_MAP_CHUNKS, self._handle_query_map_chunks)
    
    async def process_message(self, message: WSMessage) -> None:
        """
        Process incoming WebSocket message using the unified router.
        
        Handles correlation ID tracking, rate limiting, and error responses.
        
        Args:
            message: Parsed WebSocket message
        """
        # Track correlation ID
        if message.id:
            correlation_manager.track_request(message.id, message.type)
        
        # Check rate limits
        rate_limit_key = f"{self.player_id}:{message.type}"
        if not rate_limiter.check_rate_limit(rate_limit_key, message.type):
            await self._send_error_response(
                message.id,
                ErrorCodes.MOVE_RATE_LIMITED,
                ErrorCategory.RATE_LIMIT,
                "Rate limit exceeded - please slow down",
                retry_after=rate_limiter.get_retry_after(rate_limit_key, message.type)
            )
            return
        
        # Route message to handler
        try:
            handler = self.router.get_handler(message.type)
            if handler:
                await handler(message)
            else:
                logger.warning(
                    "No handler registered for message type",
                    extra={"type": message.type, "player_id": self.player_id}
                )
                await self._send_error_response(
                    message.id,
                    ErrorCodes.SYS_INVALID_MESSAGE,
                    ErrorCategory.SYSTEM,
                    f"Unknown message type: {message.type}"
                )
        except Exception as e:
            logger.error(
                "Error processing message",
                extra={
                    "type": message.type,
                    "player_id": self.player_id,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                ErrorCategory.SYSTEM,
                "Internal server error"
            )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    valkey: GlideClient = Depends(get_valkey)
):
    """
    WebSocket endpoint for real-time game communication.
    
    Handles:
    - Authentication and session management
    - Message routing and processing
    - Connection lifecycle management
    - Graceful disconnection handling
    """
    await websocket.accept()
    
    handler: Optional[WebSocketHandler] = None
    username: Optional[str] = None
    player_id: Optional[int] = None
    
    start_time = time.time()
    websocket_connections_active.inc()
    
    try:
        # Receive and validate authentication message
        auth_data = await receive_auth_message(websocket)
        if not auth_data:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Authenticate player
        auth_result = await authenticate_player(auth_data)
        if not auth_result["success"]:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        username = auth_result["username"]
        player_id = auth_result["player_id"]
        
        # Initialize connection
        init_result = await initialize_player_connection(player_id, username)
        if not init_result["success"]:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return
        
        # Create handler
        handler = WebSocketHandler(websocket, username, player_id, valkey)
        await manager.connect(websocket, player_id)
        players_online.inc()
        
        # Send welcome message
        await send_welcome_message(websocket, player_id, username, init_result["position"])
        
        # Broadcast player join to others
        await handle_player_join_broadcast(player_id, username, init_result["position"])
        
        # Register with game loop
        await register_player_login(player_id)
        
        # Message processing loop
        while True:
            try:
                # Receive and parse message
                raw_data = await websocket.receive_bytes()
                message_data = msgpack.unpackb(raw_data, raw=False)
                
                # Validate message structure
                validation = message_validator.validate_message(message_data)
                if not validation["valid"]:
                    await handler._send_error_response(
                        message_data.get("id"),
                        ErrorCodes.SYS_INVALID_MESSAGE,
                        ErrorCategory.VALIDATION,
                        validation["error"]
                    )
                    continue
                
                # Create message object
                message = WSMessage(**message_data)
                
                # Process message
                await handler.process_message(message)
                
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.error(
                    "Error in message loop",
                    extra={
                        "player_id": player_id,
                        "error": str(e),
                        "traceback": traceback.format_exc()
                    }
                )
                
    except WebSocketDisconnect:
        logger.info(
            "Client disconnected",
            extra={"player_id": player_id, "username": username}
        )
    except Exception as e:
        logger.error(
            "WebSocket error",
            extra={
                "player_id": player_id,
                "username": username,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        )
    finally:
        # Cleanup
        if player_id:
            await manager.disconnect(player_id)
            players_online.dec()
            await broadcast_player_left(player_id)
            
            if handler:
                await ConnectionService.disconnect(player_id)
        
        # Record metrics
        duration = time.time() - start_time
        websocket_connection_duration_seconds.observe(duration)
        websocket_connections_active.dec()


@router.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown - disconnect all players."""
    logger.info("Shutting down WebSocket connections")
    await manager.disconnect_all()
