"""
WebSocket Protocol Handler

This module implements the WebSocket protocol with:
- Correlation ID support for request/response pairing
- Consistent message patterns (Commands/Queries → Responses, Events)
- Structured error handling with actionable error codes
- Enhanced broadcasting with targeting (Personal/Nearby/Map/Global)
- Rate limiting with per-operation cooldowns
"""

import asyncio
import json
import time
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from jose import JWTError, jwt
from pydantic import ValidationError
import msgpack
from sqlalchemy.future import select
from glide import GlideClient

# Core dependencies
from server.src.api.connection_manager import ConnectionManager
from server.src.core.config import settings
from server.src.core.database import get_valkey
from server.src.core.logging_config import get_logger
from server.src.core.metrics import (
    metrics,
    websocket_connections_active,
    players_online,
    websocket_connection_duration_seconds,
)

# Models and schemas
from server.src.core.items import InventorySortType, EquipmentSlot

# Services
from server.src.services.map_service import map_manager, get_map_manager
from server.src.services.inventory_service import InventoryService
from server.src.services.equipment_service import EquipmentService
from server.src.services.ground_item_service import GroundItemService
from server.src.services.game_state_manager import get_game_state_manager
from server.src.services.authentication_service import AuthenticationService
from server.src.services.connection_service import ConnectionService
from server.src.services.movement_service import MovementService
from server.src.services.chat_service import ChatService
from server.src.services.player_service import PlayerService

# WebSocket Protocol implementation
from common.src.protocol import (
    WSMessage,
    MessageType,
    ErrorCodes,
    PROTOCOL_VERSION,
    AuthenticatePayload,
    MovePayload,
    ChatSendPayload,
    InventoryMovePayload,
    InventorySortPayload,
    ItemDropPayload,
    ItemPickupPayload,
    ItemEquipPayload,
    ItemUnequipPayload,
    InventoryQueryPayload,
    EquipmentQueryPayload,
    StatsQueryPayload,
    MapChunksQueryPayload,
    SuccessPayload,
    ErrorPayload,
    DataPayload,
    WelcomeEventPayload,
    StateUpdateEventPayload,
    GameUpdateEventPayload,
    ChatMessageEventPayload,
    PlayerJoinedEventPayload,
    PlayerLeftEventPayload,
)

# WebSocket utilities (now the unified utilities)
from common.src.websocket_utils import (
    CorrelationManager,
    StateUpdateManager,
    MessageValidator,
    RateLimiter,
    MessageRouter,
    BroadcastManager,
    BroadcastTarget,
    rate_limit_configs,
)

# Game loop integration
from server.src.game.game_loop import cleanup_disconnected_player, register_player_login

router = APIRouter()
logger = get_logger(__name__)

# Global instances for WebSocket protocol
manager = ConnectionManager()  # Reuse existing connection manager
correlation_manager = CorrelationManager()
state_manager = StateUpdateManager()
message_validator = MessageValidator()
rate_limiter = RateLimiter(rate_limit_configs)
broadcast_manager = BroadcastManager(manager)


class OperationRateLimiter:
    """
    Rate limiting wrapper for specific WebSocket operations.
    Delegates to the unified RateLimiter from websocket_utils.
    """
    
    def __init__(self):
        from common.src.websocket_utils import RateLimit
        # For testing purposes, we maintain our own rate limiting state
        # that can handle dynamic cooldowns
        self._player_last_operation = {}  # {player_id: {operation: timestamp}}
    
    def check_rate_limit(self, user_id: str, operation: str, cooldown: float) -> bool:
        """
        Check if operation is allowed for user.
        
        Args:
            user_id: Player username or ID  
            operation: Operation name
            cooldown: Cooldown in seconds
            
        Returns:
            True if allowed, False if rate limited
        """
        import time
        
        # Convert user_id to int if it's a string
        try:
            player_id = int(user_id)
        except (ValueError, TypeError):
            # If conversion fails, use hash of string as player ID
            player_id = hash(user_id) % 1000000
        
        current_time = time.time()
        
        # Initialize player tracking if not exists
        if player_id not in self._player_last_operation:
            self._player_last_operation[player_id] = {}
        
        # Special case: zero cooldown always allows operations
        if cooldown == 0:
            self._player_last_operation[player_id][operation] = current_time
            return True
        
        # Check if operation was performed recently
        last_operation_time = self._player_last_operation[player_id].get(operation, 0)
        time_since_last = current_time - last_operation_time
        
        if time_since_last >= cooldown:
            # Operation is allowed, update timestamp
            self._player_last_operation[player_id][operation] = current_time
            return True
        else:
            # Operation is rate limited
            return False
    
    def cleanup_player(self, user_id: str) -> None:
        """
        Clean up rate limiting data for disconnected player.
        
        Args:
            user_id: Player username or ID to clean up
        """
        # Convert user_id to int using same logic as check_rate_limit
        try:
            player_id = int(user_id)
        except (ValueError, TypeError):
            # If conversion fails, use hash of string as player ID
            player_id = hash(user_id) % 1000000
        
        # Remove player's rate limiting state
        self._player_last_operation.pop(player_id, None)


class WebSocketHandler:
    """
    Unified WebSocket handler implementing Protocol unified patterns.
    
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
        """Register all message type handlers"""
        
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
            # Use the message router to handle validation, rate limiting, and routing
            # The router expects raw bytes, so we need to pack the message back to bytes
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
                "system",
                "Internal server error occurred",
                suggested_action="Please retry the operation"
            )
    
    # =================================================================
    # Command Handlers (State-changing operations)
    # =================================================================
    
    async def _handle_cmd_authenticate(self, message: WSMessage) -> None:
        """Handle CMD_AUTHENTICATE - should not be called after initial auth"""
        await self._send_error_response(
            message.id,
            ErrorCodes.AUTH_PLAYER_NOT_FOUND,
            "permission",
            "Already authenticated"
        )
    
    async def _handle_cmd_move(self, message: WSMessage) -> None:
        """Handle CMD_MOVE - player movement with collision detection"""
        try:
            # Early validation - ensure player is properly initialized
            from server.src.services.game_state_manager import get_game_state_manager
            gsm = get_game_state_manager()
            
            if not gsm.is_online(self.player_id):
                logger.warning(
                    "Player attempted movement while not online",
                    extra={
                        "player_id": self.player_id,
                        "username": getattr(self, 'username', 'unknown'),
                        "message_id": message.id
                    }
                )
                await self._send_error_response(
                    message.id,
                    ErrorCodes.MOVE_RATE_LIMITED,
                    "system",
                    "Player not properly initialized - please reconnect"
                )
                return
            
            payload = MovePayload(**message.payload)
            
            # Execute movement using service layer
            movement_result = await MovementService.execute_movement(
                self.player_id, payload.direction
            )
            
            if movement_result["success"]:
                # Send success response
                await self._send_success_response(
                    message.id,
                    {
                        "new_position": movement_result["new_position"],
                        "old_position": movement_result["old_position"]
                    }
                )
                
                # Track movement metrics
                metrics.track_player_movement(payload.direction)
                
                logger.debug(
                    "Player movement executed",
                    extra={
                        "username": self.username,
                        "direction": payload.direction,
                        "from_position": movement_result["old_position"],
                        "to_position": movement_result["new_position"]
                    }
                )
                
            else:
                # Movement failed (blocked or rate limited)
                reason = movement_result.get("reason", "unknown")
                
                # Map reasons to appropriate error codes
                if reason == "rate_limited":
                    error_code = ErrorCodes.MOVE_RATE_LIMITED
                    error_category = "rate_limit"
                    error_message = f"Movement cooldown active"
                    details = {
                        "current_position": movement_result.get("current_position"),
                        "cooldown_remaining": movement_result.get("cooldown_remaining", 0)
                    }
                    suggested_action = "Wait before moving again"
                elif reason == "blocked":
                    error_code = ErrorCodes.MOVE_COLLISION_DETECTED  
                    error_category = "validation"
                    error_message = "Movement blocked by obstacle"
                    details = {"current_position": movement_result.get("current_position")}
                    suggested_action = None
                elif reason == "invalid_direction":
                    error_code = ErrorCodes.MOVE_INVALID_DIRECTION
                    error_category = "validation"
                    error_message = "Invalid movement direction"
                    details = {"current_position": movement_result.get("current_position")}
                    suggested_action = None
                else:
                    error_code = ErrorCodes.MOVE_RATE_LIMITED
                    error_category = "system"
                    error_message = f"Movement failed: {reason}"
                    details = {"current_position": movement_result.get("current_position")}
                    suggested_action = None
                
                await self._send_error_response(
                    message.id,
                    error_code,
                    error_category,
                    error_message,
                    details=details,
                    suggested_action=suggested_action
                )
                
        except Exception as e:
            import traceback
            
            logger.error(
                "Movement command processing failed - comprehensive diagnostic",
                extra={
                    "username": self.username,
                    "player_id": self.player_id,
                    "message_payload": message.payload,
                    "message_id": message.id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                    "websocket_state": getattr(self.websocket, 'client_state', 'unknown')
                }
            )
            
            # Try to get current player position for additional context
            try:
                from server.src.services.game_state_manager import get_game_state_manager
                gsm = get_game_state_manager()
                current_pos = await gsm.get_player_position(self.player_id)
                
                logger.info(
                    "Player position context during movement failure",
                    extra={
                        "username": self.username,
                        "player_id": self.player_id,
                        "current_position": current_pos
                    }
                )
            except Exception as pos_error:
                logger.warning(
                    "Could not retrieve player position for movement error context",
                    extra={
                        "username": self.username,
                        "error": str(pos_error)
                    }
                )
            
            await self._send_error_response(
                message.id,
                ErrorCodes.MOVE_RATE_LIMITED,
                "system",
                "Movement processing failed"
            )
    
    async def _handle_cmd_chat_send(self, message: WSMessage) -> None:
        """Handle CMD_CHAT_SEND - chat message processing"""
        try:
            payload = ChatSendPayload(**message.payload)
            
            # Access the global connection manager
            global manager
            
            # Process chat message using service
            chat_result = await ChatService.handle_chat_message(
                self.player_id, self.username, payload.model_dump(), manager
            )
            
            if chat_result["success"]:
                await self._send_success_response(
                    message.id,
                    {
                        "channel": chat_result["channel"],
                        "message": chat_result["message_data"]["payload"]["message"] if "message_data" in chat_result else ""
                    }
                )
                
                # Chat broadcasting is handled by the ChatService directly
                logger.info(
                    "Chat message processed",
                    extra={
                        "username": self.username,
                        "channel": chat_result["channel"],
                        "recipient_count": len(chat_result.get("recipients", [])),
                        "message_id": chat_result.get("message_id")
                    }
                )
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.CHAT_MESSAGE_TOO_LONG,
                    "validation",
                    chat_result.get("reason", "Chat message rejected"),
                    details={"channel": payload.channel}
                )
        except ValidationError as e:
            # Handle Pydantic validation errors (e.g., message too long)
            logger.info(
                "Chat message validation failed",
                extra={
                    "username": self.username,
                    "validation_errors": str(e),
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.CHAT_MESSAGE_TOO_LONG,
                "validation",
                "Message validation failed"
            )
        except Exception as e:
            logger.error(
                "Error handling chat command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.CHAT_PERMISSION_DENIED,
                "system",
                "Chat processing failed"
            )
            
        except Exception as e:
            logger.error(
                "Error handling chat command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.CHAT_PERMISSION_DENIED,
                "system",
                "Chat processing failed"
            )
    
    async def _handle_cmd_inventory_move(self, message: WSMessage) -> None:
        """Handle CMD_INVENTORY_MOVE - move items within inventory"""
        try:
            payload = InventoryMovePayload(**message.payload)
            
            result = await InventoryService.move_item(
                self.player_id, payload.from_slot, payload.to_slot
            )
            
            if result.success:
                await self._send_success_response(
                    message.id,
                    {"message": result.message}
                )
                
                # Send updated inventory state
                await self._send_inventory_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.INV_SLOT_EMPTY,
                    "validation",
                    result.message,
                    details={"from_slot": payload.from_slot, "to_slot": payload.to_slot}
                )
                
        except Exception as e:
            logger.error(
                "Error handling inventory move command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.INV_INVENTORY_FULL,
                "system",
                "Inventory move failed"
            )
    
    async def _handle_cmd_inventory_sort(self, message: WSMessage) -> None:
        """Handle CMD_INVENTORY_SORT - sort inventory by criteria"""
        try:
            payload = InventorySortPayload(**message.payload)
            
            # Validate sort type
            try:
                sort_type = InventorySortType(payload.sort_by)
            except ValueError:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.INV_INVALID_SLOT,
                    "validation",
                    f"Invalid sort type: {payload.sort_by}"
                )
                return
            
            result = await InventoryService.sort_inventory(self.player_id, sort_type)
            
            if result.success:
                await self._send_success_response(
                    message.id,
                    {
                        "message": result.message,
                        "items_moved": result.items_moved,
                        "stacks_merged": result.stacks_merged
                    }
                )
                
                # Send updated inventory state
                await self._send_inventory_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.INV_SLOT_EMPTY,
                    "validation",
                    result.message
                )
                
        except Exception as e:
            logger.error(
                "Error handling inventory sort command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.INV_INVENTORY_FULL,
                "system",
                "Inventory sort failed"
            )
    
    async def _handle_cmd_item_drop(self, message: WSMessage) -> None:
        """Handle CMD_ITEM_DROP - drop items to ground"""
        try:
            payload = ItemDropPayload(**message.payload)
            
            # Get player position
            gsm = get_game_state_manager()
            position = await gsm.get_player_position(self.player_id)
            if not position:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.INV_CANNOT_STACK,
                    "system",
                    "Could not determine player position"
                )
                return
            
            result = await GroundItemService.drop_from_inventory(
                player_id=self.player_id,
                inventory_slot=payload.inventory_slot,
                map_id=position["map_id"],
                x=position["x"],
                y=position["y"],
                quantity=payload.quantity,
            )
            
            if result.success:
                await self._send_success_response(
                    message.id,
                    {
                        "message": result.message,
                        "ground_item_id": result.ground_item_id
                    }
                )
                
                # Send updated inventory state
                await self._send_inventory_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.INV_INSUFFICIENT_QUANTITY,
                    "validation",
                    result.message,
                    details={"inventory_slot": payload.inventory_slot}
                )
                
        except Exception as e:
            logger.error(
                "Error handling item drop command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                "system",
                "Item drop failed"
            )
    
    async def _handle_cmd_item_pickup(self, message: WSMessage) -> None:
        """Handle CMD_ITEM_PICKUP - pickup ground items"""
        try:
            payload = ItemPickupPayload(**message.payload)
            
            # Get player position
            gsm = get_game_state_manager()
            position = await gsm.get_player_position(self.player_id)
            if not position:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.SYS_INTERNAL_ERROR,
                    "system",
                    "Could not determine player position"
                )
                return
            
            result = await GroundItemService.pickup_item(
                player_id=self.player_id,
                ground_item_id=int(payload.ground_item_id),
                player_x=position["x"],
                player_y=position["y"],
                player_map_id=position["map_id"],
            )
            
            if result.success:
                await self._send_success_response(
                    message.id,
                    {"message": result.message}
                )
                
                # Send updated inventory state
                await self._send_inventory_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.GROUND_ITEM_NOT_FOUND,
                    "validation",
                    result.message,
                    details={"ground_item_id": payload.ground_item_id}
                )
                
        except Exception as e:
            logger.error(
                "Error handling item pickup command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                "system",
                "Item pickup failed"
            )
    
    async def _handle_cmd_item_equip(self, message: WSMessage) -> None:
        """Handle CMD_ITEM_EQUIP - equip items from inventory"""
        try:
            payload = ItemEquipPayload(**message.payload)
            
            result = await EquipmentService.equip_from_inventory(
                self.player_id, payload.inventory_slot
            )
            
            if result.success:
                await self._send_success_response(
                    message.id,
                    {"message": result.message}
                )
                
                # Send consolidated state update (inventory + equipment + stats)
                await self._send_equipment_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.EQ_ITEM_NOT_EQUIPABLE,
                    "validation",
                    result.message,
                    details={"inventory_slot": payload.inventory_slot}
                )
                
        except Exception as e:
            logger.error(
                "Error handling item equip command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.EQ_REQUIREMENTS_NOT_MET,
                "system",
                "Item equip failed"
            )
    
    async def _handle_cmd_item_unequip(self, message: WSMessage) -> None:
        """Handle CMD_ITEM_UNEQUIP - unequip items to inventory"""
        try:
            payload = ItemUnequipPayload(**message.payload)
            
            # Validate equipment slot
            try:
                slot = EquipmentSlot(payload.equipment_slot)
            except ValueError:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.EQ_INVALID_SLOT,
                    "validation",
                    f"Invalid equipment slot: {payload.equipment_slot}"
                )
                return
            
            result = await EquipmentService.unequip_to_inventory(
                self.player_id, slot
            )
            
            if result.success:
                await self._send_success_response(
                    message.id,
                    {"message": result.message}
                )
                
                # Send consolidated state update (inventory + equipment + stats)
                await self._send_equipment_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.EQ_CANNOT_UNEQUIP_FULL_INV,
                    "validation",
                    result.message,
                    details={"equipment_slot": payload.equipment_slot}
                )
                
        except Exception as e:
            logger.error(
                "Error handling item unequip command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                "system",
                "Item unequip failed"
            )
    
    # =================================================================
    # Query Handlers (Data retrieval operations)
    # =================================================================
    
    async def _handle_query_inventory(self, message: WSMessage) -> None:
        """Handle QUERY_INVENTORY - retrieve current inventory state"""
        try:
            inventory_data = await InventoryService.get_inventory_response(self.player_id)
            
            await self._send_data_response(
                message.id,
                {
                    "inventory": inventory_data.model_dump(),
                    "query_type": "inventory"
                }
            )
            
        except Exception as e:
            logger.error(
                "Error handling inventory query",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                "system",
                "Inventory query failed"
            )
    
    async def _handle_query_equipment(self, message: WSMessage) -> None:
        """
        Handle QUERY_EQUIPMENT - retrieve current equipment state.
        
        This is the critical handler that fixes the hanging equipment test issue.
        Uses RESP_DATA with proper correlation ID tracking for request/response pairing.
        """
        try:
            equipment_data = await EquipmentService.get_equipment_response(self.player_id)
            
            await self._send_data_response(
                message.id,
                {
                    "equipment": equipment_data.model_dump(),
                    "query_type": "equipment"
                }
            )
            
            logger.debug(
                "Equipment query processed",
                extra={
                    "username": self.username,
                    "correlation_id": message.id,
                    "equipment_slots": len(equipment_data.model_dump().get("slots", {}))
                }
            )
            
        except Exception as e:
            logger.error(
                "Error handling equipment query", 
                extra={
                    "username": self.username,
                    "correlation_id": message.id,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                "system",
                "Equipment query failed"
            )
    
    async def _handle_query_stats(self, message: WSMessage) -> None:
        """Handle QUERY_STATS - retrieve aggregated player stats"""
        try:
            stats_data = await EquipmentService.get_total_stats(self.player_id)
            
            await self._send_data_response(
                message.id,
                {
                    "stats": stats_data.model_dump(),
                    "query_type": "stats"
                }
            )
            
        except Exception as e:
            logger.error(
                "Error handling stats query",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                "system",
                "Stats query failed"
            )
    
    async def _handle_query_map_chunks(self, message: WSMessage) -> None:
        """Handle QUERY_MAP_CHUNKS - retrieve map chunk data"""
        try:
            payload = MapChunksQueryPayload(**message.payload)
            
            # Validate chunk request using MapManager
            map_manager = get_map_manager()
            is_valid = await map_manager.validate_chunk_request_security(
                self.player_id,
                payload.map_id,
                payload.center_x,
                payload.center_y,
                payload.radius
            )
            
            if not is_valid:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.MAP_INVALID_COORDS,
                    "validation",
                    "Invalid chunk request parameters",
                    details={
                        "map_id": payload.map_id,
                        "center": (payload.center_x, payload.center_y),
                        "radius": payload.radius
                    }
                )
                return
            
            # Get chunk data
            chunk_data = await map_manager.get_chunks_for_player(
                payload.map_id,
                payload.center_x,
                payload.center_y,
                payload.radius
            )
            
            await self._send_data_response(
                message.id,
                {
                    "chunks": chunk_data or [],
                    "map_id": payload.map_id,
                    "center": {"x": payload.center_x, "y": payload.center_y},
                    "radius": payload.radius,
                    "query_type": "map_chunks"
                }
            )
            
            logger.debug(
                "Map chunks query processed",
                extra={
                    "username": self.username,
                    "map_id": payload.map_id,
                    "center": (payload.center_x, payload.center_y),
                    "radius": payload.radius,
                    "chunks_count": len(chunk_data) if chunk_data else 0
                }
            )
            
        except Exception as e:
            logger.error(
                "Error handling map chunks query",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.MAP_NOT_FOUND,
                "system",
                "Map chunks query failed"
            )
    
    # =================================================================
    # Response Helpers
    # =================================================================
    
    async def _send_success_response(self, correlation_id: Optional[str], data: Dict[str, Any] = None) -> None:
        """Send RESP_SUCCESS with correlation ID"""
        response = WSMessage(
            id=correlation_id,
            type=MessageType.RESP_SUCCESS,
            payload=data or {},
            version=PROTOCOL_VERSION
        )
        await self._send_message(response)
    
    async def _send_error_response(
        self, 
        correlation_id: Optional[str], 
        error_code: str,
        error_category: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        retry_after: Optional[float] = None,
        suggested_action: Optional[str] = None
    ) -> None:
        """Send RESP_ERROR with structured error information"""
        error_payload = ErrorPayload(
            error_code=error_code,
            error_category=error_category,
            message=message,
            details=details,
            retry_after=retry_after,
            suggested_action=suggested_action
        )
        
        response = WSMessage(
            id=correlation_id,
            type=MessageType.RESP_ERROR,
            payload=error_payload.model_dump(),
            version=PROTOCOL_VERSION
        )
        await self._send_message(response)
    
    async def _send_data_response(self, correlation_id: Optional[str], data: Dict[str, Any]) -> None:
        """Send RESP_DATA with query results"""
        response = WSMessage(
            id=correlation_id,
            type=MessageType.RESP_DATA,
            payload=data,
            version=PROTOCOL_VERSION
        )
        await self._send_message(response)
    
    async def _send_message(self, message: WSMessage) -> None:
        """
        Send message with comprehensive error handling
        """
        try:
            # Log message structure before serialization for debugging
            logger.debug(
                "Attempting to send WebSocket message",
                extra={
                    "username": self.username,
                    "message_type": message.type,
                    "payload_keys": list(message.payload.keys()) if message.payload else None,
                    "correlation_id": message.id,
                    "payload_size": len(str(message.payload)) if message.payload else 0
                }
            )
            
            # Separate serialization from sending to isolate failure point
            try:
                message_dump = message.model_dump()
                packed_message = msgpack.packb(message_dump, use_bin_type=True)
                
                logger.debug(
                    "Message serialization successful",
                    extra={
                        "username": self.username,
                        "message_type": message.type,
                        "serialized_size": len(packed_message),
                        "correlation_id": message.id
                    }
                )
                
            except Exception as serialize_error:
                logger.error(
                    "Message serialization failed",
                    extra={
                        "username": self.username,
                        "message_type": message.type,
                        "correlation_id": message.id,
                        "error": str(serialize_error),
                        "error_type": type(serialize_error).__name__,
                        "message_dump": str(message_dump)[:500]  # Truncate for logging
                    }
                )
                raise
            
            # Attempt WebSocket sending with connection health check
            try:
                # Check connection state before attempting to send
                if hasattr(self.websocket, 'client_state'):
                    # WebSocket states: 0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED
                    if self.websocket.client_state == 3:  # CLOSED
                        logger.warning(
                            "Attempted to send message on closed WebSocket",
                            extra={
                                "username": self.username,
                                "message_type": message.type,
                                "correlation_id": message.id
                            }
                        )
                        # Clean up connection from manager
                        manager.disconnect(self.username)
                        raise ConnectionError("WebSocket connection is closed")
                    elif self.websocket.client_state == 2:  # CLOSING
                        logger.warning(
                            "Attempted to send message on closing WebSocket",
                            extra={
                                "username": self.username,
                                "message_type": message.type,
                                "correlation_id": message.id
                            }
                        )
                        raise ConnectionError("WebSocket connection is closing")
                
                await self.websocket.send_bytes(packed_message)
                
                logger.debug(
                    "WebSocket message sent successfully",
                    extra={
                        "username": self.username,
                        "message_type": message.type,
                        "correlation_id": message.id
                    }
                )
                
            except Exception as send_error:
                logger.error(
                    "WebSocket sending failed",
                    extra={
                        "username": self.username,
                        "message_type": message.type,
                        "correlation_id": message.id,
                        "error": str(send_error),
                        "error_type": type(send_error).__name__,
                        "websocket_state": getattr(self.websocket, 'client_state', 'unknown')
                    }
                )
                
                # Clean up connection on send failure
                manager.disconnect(self.username)
                raise
            
            # Track outbound message
            # message.type is already a string value, not an enum
            metrics.track_websocket_message(str(message.type), "outbound")
            
        except Exception as e:
            logger.error(
                "Error sending WebSocket message - outer catch",
                extra={
                    "username": self.username,
                    "message_type": message.type,
                    "correlation_id": message.id,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
    
    # =================================================================
    # State Update Helpers
    # =================================================================
    
    async def _send_inventory_state_update(self) -> None:
        """Send personal inventory state update"""
        try:
            inventory_data = await InventoryService.get_inventory_response(self.player_id)
            
            state_update = WSMessage(
                id=None,
                type=MessageType.EVENT_STATE_UPDATE,
                payload={
                    "update_type": "full",
                    "target": "personal",
                    "systems": {
                        "inventory": inventory_data.model_dump()
                    }
                },
                version=PROTOCOL_VERSION
            )
            await self._send_message(state_update)
            
        except Exception as e:
            logger.error(
                "Error sending inventory state update",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
    
    async def _send_equipment_state_update(self) -> None:
        """Send consolidated equipment-related state update (inventory + equipment + stats)"""
        try:
            # Get all related data
            inventory_data = await InventoryService.get_inventory_response(self.player_id)
            equipment_data = await EquipmentService.get_equipment_response(self.player_id)
            stats_data = await EquipmentService.get_total_stats(self.player_id)
            
            # Send consolidated state update
            state_update = WSMessage(
                id=None,
                type=MessageType.EVENT_STATE_UPDATE,
                payload={
                    "update_type": "full",
                    "target": "personal",
                    "systems": {
                        "inventory": inventory_data.model_dump(),
                        "equipment": equipment_data.model_dump(),
                        "stats": stats_data.model_dump()
                    }
                },
                version=PROTOCOL_VERSION
            )
            await self._send_message(state_update)
            
        except Exception as e:
            logger.error(
                "Error sending equipment state update",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )


# =============================================================================
# WebSocket Endpoint  
# =============================================================================

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
        # Accept WebSocket connection
        await websocket.accept()
        metrics.track_websocket_connection("accepted")
        connection_start_time = time.time()
        
        logger.info("WebSocket unified connection accepted")
        
        # Wait for authentication message
        auth_message = await _receive_auth_message(websocket)
        username, player_id = await _authenticate_player(auth_message)
        
        # Initialize player connection and load into GSM
        await _initialize_player_connection(username, player_id, valkey)
        
        # Create handler instance for this connection
        handler = WebSocketHandler(websocket, username, player_id, valkey)
        
        # Send welcome message
        await _send_welcome_message(websocket, username, player_id)
        
        # Handle player join broadcasting
        await _handle_player_join_broadcast(websocket, username, player_id)
        
        # Register connection with manager
        gsm = get_game_state_manager()
        position = await gsm.get_player_position(player_id)
        if not position:
            raise WebSocketDisconnect(
                code=status.WS_1011_INTERNAL_ERROR,
                reason="Could not get player position"
            )
        await manager.connect(websocket, username, position["map_id"])
        
        # Register for game loop
        register_player_login(username)
        
        # Update metrics
        _update_connection_metrics()
        
        logger.info(
            "Player connected to WebSocket unified",
            extra={
                "username": username,
                "player_id": player_id,
                "initial_position": position
            }
        )
        
        # Main message processing loop
        while True:
            try:
                # Receive raw message bytes
                data = await websocket.receive_bytes()
                
                # Use the message router to handle validation, rate limiting, and routing
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
                # Continue processing other messages
                continue
                
    except WebSocketDisconnect as e:
        logger.info(
            "Client disconnected from WebSocket unified",
            extra={"username": username, "reason": e.reason or "Normal disconnect"}
        )
        metrics.track_websocket_connection("disconnected")
        
    except JWTError:
        logger.warning("JWT validation failed for WebSocket unified connection")
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
            "Unexpected error in WebSocket unified handler",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
        )
        metrics.track_websocket_connection("error")
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
            
    finally:
        # Track connection duration
        if connection_start_time:
            duration = time.time() - connection_start_time
            websocket_connection_duration_seconds.observe(duration)
        
        if username:
            # Handle player disconnection
            await _handle_player_disconnect(username, player_id, valkey)
            
            # Update metrics
            _update_connection_metrics()


# =============================================================================
# Authentication and Connection Helpers
# =============================================================================

async def _receive_auth_message(websocket: WebSocket) -> WSMessage:
    """Receive and validate authentication message"""
    try:
        auth_bytes = await websocket.receive_bytes()
        auth_data = msgpack.unpackb(auth_bytes, raw=False)
        auth_message = WSMessage(**auth_data)
        
        if auth_message.type != MessageType.CMD_AUTHENTICATE:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Authentication message expected"
            )
        
        return auth_message
        
    except (msgpack.exceptions.UnpackException, ValueError) as e:
        raise WebSocketDisconnect(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=f"Invalid authentication message: {str(e)}"
        )


async def _authenticate_player(auth_message: WSMessage) -> tuple[str, int]:
    """Authenticate player and return username and player_id"""
    try:
        # Validate authentication payload
        auth_payload = AuthenticatePayload(**auth_message.payload)
        
        # Use authentication service to validate token and get player
        auth_service = AuthenticationService()
        player_data = await auth_service.validate_jwt_token(auth_payload.token)
        
        if not player_data:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid token"
            )
        
        username = player_data.get("username")
        player_id = player_data.get("player_id")
        
        if not username or not player_id:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid token: player data missing"
            )
        
        # Get player details using service layer
        player_service = PlayerService()
        player = await player_service.get_player_by_username(username)
        
        if not player:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Player not found"
            )
        
        # Check ban status
        if player.is_banned:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Account is banned"
            )
        
        # Check timeout status
        if player.timeout_until:
            timeout_until = player.timeout_until
            if timeout_until.tzinfo is None:
                timeout_until = timeout_until.replace(tzinfo=timezone.utc)
            if timeout_until > datetime.now(timezone.utc):
                raise WebSocketDisconnect(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason=f"Account is timed out until {player.timeout_until.isoformat()}"
                )
        
        return username, player.id
        
    except ValidationError:
        # Handle Pydantic validation errors (missing/invalid fields)
        raise WebSocketDisconnect(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid authentication payload"
        )
    except JWTError:
        # Handle JWT decoding/validation errors
        raise WebSocketDisconnect(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid authentication token"
        )


async def _initialize_player_connection(username: str, player_id: int, valkey: GlideClient) -> None:
    """Initialize player connection state in GSM and services"""
    try:
        # Get player data using service layer
        player_service = PlayerService()
        player = await player_service.get_player_by_id(player_id)
        
        if not player:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Player not found during initialization"
            )
        
        # Validate and correct player position if needed
        validated_map, validated_x, validated_y = map_manager.validate_player_position(
            player.map_id, player.x_coord, player.y_coord
        )
        
        # Calculate max HP and validate current HP
        max_hp = await EquipmentService.get_max_hp(player.id)
        current_hp = min(player.current_hp, max_hp)
        
        # Initialize player in service layer and GSM
        await PlayerService.login_player(player)
        await ConnectionService.initialize_player_connection(
            player.id, username, validated_x, validated_y, validated_map, current_hp, max_hp
        )
        
        logger.info(
            "Player connection initialized successfully",
            extra={
                "username": username,
                "player_id": player_id,
                "position": {"x": validated_x, "y": validated_y, "map_id": validated_map},
                "hp": {"current": current_hp, "max": max_hp}
            }
        )
        
    except Exception as e:
        logger.error(
            "Error initializing player connection",
            extra={
                "username": username,
                "player_id": player_id,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise WebSocketDisconnect(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Failed to initialize player connection"
        )


async def _send_welcome_message(websocket: WebSocket, username: str, player_id: int) -> None:
    """Send EVENT_WELCOME message to newly connected player"""
    try:
        # Get current player state
        gsm = get_game_state_manager()
        position = await gsm.get_player_position(player_id)
        hp_data = await gsm.get_player_hp(player_id)
        
        welcome_event = WSMessage(
            id=None,
            type=MessageType.EVENT_WELCOME,
            payload={
                "message": f"Welcome to RPG Engine, {username}!",
                "motd": "WebSocket Protocol unified - Enhanced with correlation IDs and structured responses",
                "player": {
                    "id": player_id,
                    "username": username,
                    "position": position,
                    "hp": hp_data,
                },
                "config": {
                    "move_cooldown": settings.MOVE_COOLDOWN,
                    "animation_duration": settings.ANIMATION_DURATION,
                    "protocol_version": PROTOCOL_VERSION
                }
            },
            version=PROTOCOL_VERSION
        )
        
        packed_message = msgpack.packb(welcome_event.model_dump(), use_bin_type=True)
        await websocket.send_bytes(packed_message)
        
        # Send welcome chat message
        welcome_chat = WSMessage(
            id=None,
            type=MessageType.EVENT_CHAT_MESSAGE,
            payload={
                "sender": "Server",
                "message": f"Welcome, {username}! Protocol unified is now active. You can chat by typing in the chat window.",
                "channel": "system",
                "sender_position": None
            },
            version=PROTOCOL_VERSION
        )
        
        packed_chat = msgpack.packb(welcome_chat.model_dump(), use_bin_type=True)
        await websocket.send_bytes(packed_chat)
        
        logger.info(
            "Welcome messages sent via Protocol unified",
            extra={"username": username, "player_id": player_id}
        )
        
    except Exception as e:
        logger.error(
            "Error sending welcome message",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )


async def _handle_player_join_broadcast(websocket: WebSocket, username: str, player_id: int) -> None:
    """Handle player join broadcasting to existing players"""
    try:
        gsm = get_game_state_manager()
        position = await gsm.get_player_position(player_id)
        if not position:
            logger.error("Could not get player position for join broadcast", extra={"player_id": player_id})
            return
        map_id = position["map_id"]
        
        # Get existing players on this map
        existing_players_data = await ConnectionService.get_existing_players_on_map(
            map_id, username
        )
        
        if existing_players_data:
            # Send existing players to new player
            game_update = WSMessage(
                id=None,
                type=MessageType.EVENT_STATE_UPDATE,
                payload={
                    "entities": existing_players_data,
                    "removed_entities": [],
                    "map_id": map_id
                },
                version=PROTOCOL_VERSION
            )
            
            packed_update = msgpack.packb(game_update.model_dump(), use_bin_type=True)
            await websocket.send_bytes(packed_update)
        
        # Broadcast new player join to existing players
        player_joined = WSMessage(
            id=None,
            type=MessageType.EVENT_PLAYER_JOINED,
            payload={
                "player": {
                    "username": username,
                    "position": position,
                    "type": "player"
                }
            },
            version=PROTOCOL_VERSION
        )
        
        packed_join = msgpack.packb(player_joined.model_dump(), use_bin_type=True)
        
        # Get all connections on this map and filter out the joining player
        all_connections = await manager.get_all_connections()
        other_players = [
            conn['username'] for conn in all_connections 
            if conn['map_id'] == map_id and conn['username'] != username
        ]
        
        if other_players:
            await manager.broadcast_to_users(other_players, packed_join)
        
        logger.info(
            "Player join broadcast completed",
            extra={
                "username": username,
                "map_id": map_id,
                "existing_players": len(existing_players_data) if existing_players_data else 0
            }
        )
        
    except Exception as e:
        logger.error(
            "Error handling player join broadcast",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
        )


async def _handle_player_disconnect(username: str, player_id: Optional[int], valkey: GlideClient) -> None:
    """Handle player disconnection cleanup"""
    try:
        if username:
            # Get player's map before disconnection
            player_map = manager.client_to_map.get(username)
            
            # Use ConnectionService to handle disconnection
            await ConnectionService.handle_player_disconnect(
                username, player_map, manager, rate_limiter
            )
            
            # Broadcast player left event to remaining players
            if player_map:
                player_left = WSMessage(
                    id=None,
                    type=MessageType.EVENT_PLAYER_LEFT,
                    payload={
                        "username": username,
                        "reason": "Disconnected"
                    },
                    version=PROTOCOL_VERSION
                )
                
                packed_left = msgpack.packb(player_left.model_dump(), use_bin_type=True)
                
                # Get all connections on this map and filter out the disconnecting player
                all_connections = await manager.get_all_connections()
                other_players = [
                    conn['username'] for conn in all_connections 
                    if conn['map_id'] == player_map and conn['username'] != username
                ]
                
                if other_players:
                    await manager.broadcast_to_users(other_players, packed_left)
            
            logger.info(
                "Player disconnection handled",
                extra={"username": username, "player_map": player_map}
            )
            
    except Exception as e:
        logger.error(
            "Error handling player disconnect",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )


def _update_connection_metrics() -> None:
    """Update connection metrics after connect/disconnect"""
    total_connections = sum(
        len(conns) for conns in manager.connections_by_map.values()
    )
    websocket_connections_active.set(total_connections)
    players_online.set(total_connections)