"""
WebSocket Protocol Utilities

Provides correlation management, message routing, and utility functions
for the WebSocket protocol.
"""

import uuid
import asyncio
import time
import msgpack
from typing import Dict, Any, Optional, Callable, Awaitable, Union
from dataclasses import dataclass
from collections import defaultdict
import logging

from .protocol import (
    WSMessage, MessageType, ErrorCodes,
    COMMAND_TYPES, QUERY_TYPES, EVENT_TYPES, RESPONSE_TYPES,
    get_expected_response_type, requires_correlation_id,
    create_success_response, create_error_response, create_data_response, create_event
)

logger = logging.getLogger(__name__)


# =============================================================================
# Correlation Management
# =============================================================================

@dataclass
class PendingRequest:
    """Information about a pending request awaiting response"""
    correlation_id: str
    message_type: MessageType
    player_id: Optional[int]
    timestamp: float
    timeout_task: Optional[asyncio.Task] = None


class CorrelationManager:
    """Manages correlation IDs for request/response pairing"""
    
    def __init__(self, default_timeout: float = 30.0):
        self.pending_requests: Dict[str, PendingRequest] = {}
        self.default_timeout = default_timeout
        
    def create_correlation_id(self) -> str:
        """Generate a new correlation ID"""
        return str(uuid.uuid4())
        
    def register_request(
        self, 
        correlation_id: str, 
        message_type: MessageType,
        player_id: Optional[int] = None,
        timeout: Optional[float] = None
    ) -> None:
        """Register a pending request"""
        timeout = timeout or self.default_timeout
        
        # Create timeout task
        timeout_task = asyncio.create_task(
            self._handle_timeout(correlation_id, timeout)
        )
        
        request = PendingRequest(
            correlation_id=correlation_id,
            message_type=message_type,
            player_id=player_id,
            timestamp=time.time(),
            timeout_task=timeout_task
        )
        
        self.pending_requests[correlation_id] = request
        
    async def _handle_timeout(self, correlation_id: str, timeout: float) -> None:
        """Handle request timeout"""
        await asyncio.sleep(timeout)
        
        if correlation_id in self.pending_requests:
            request = self.pending_requests.pop(correlation_id)
            logger.warning(
                f"Request timed out: {request.message_type} "
                f"for player {request.player_id}"
            )
            
    def resolve_request(self, correlation_id: str) -> Optional[PendingRequest]:
        """Mark a request as resolved and return its info"""
        request = self.pending_requests.pop(correlation_id, None)
        if request and request.timeout_task:
            request.timeout_task.cancel()
        return request
        
    def get_pending_count(self) -> int:
        """Get number of pending requests"""
        return len(self.pending_requests)
        
    def cleanup_expired(self, max_age_seconds: float = 60.0) -> int:
        """Clean up expired requests and return count cleaned"""
        now = time.time()
        expired = [
            correlation_id for correlation_id, request in self.pending_requests.items()
            if now - request.timestamp > max_age_seconds
        ]
        
        for correlation_id in expired:
            request = self.pending_requests.pop(correlation_id)
            if request.timeout_task:
                request.timeout_task.cancel()
                
        return len(expired)


# =============================================================================
# Broadcasting and Message Distribution
# =============================================================================

from enum import Enum

class BroadcastTarget(str, Enum):
    """Message distribution targets"""
    PERSONAL = "personal"        # Only to the specific player
    NEARBY = "nearby"           # To players in visible range
    MAP = "map"                 # To all players on the same map  
    GLOBAL = "global"           # To all connected players


class StateUpdateManager:
    """Manages consolidated state updates with proper broadcast targeting"""
    
    @staticmethod
    def create_personal_update(
        systems: Dict[str, Any],
        update_type: str = "full"
    ) -> WSMessage:
        """Create a personal state update (only to the player)"""
        return create_event(
            MessageType.EVENT_STATE_UPDATE,
            {
                "update_type": update_type,
                "target": BroadcastTarget.PERSONAL,
                "systems": systems
            }
        )
        
    @staticmethod  
    def create_nearby_update(
        systems: Dict[str, Any],
        update_type: str = "delta"
    ) -> WSMessage:
        """Create an update for nearby players (visible range)"""
        return create_event(
            MessageType.EVENT_STATE_UPDATE,
            {
                "update_type": update_type,
                "target": BroadcastTarget.NEARBY, 
                "systems": systems
            }
        )
        
    @staticmethod  
    def create_map_update(
        systems: Dict[str, Any],
        update_type: str = "delta"
    ) -> WSMessage:
        """Create an update for all players on the map"""
        return create_event(
            MessageType.EVENT_STATE_UPDATE,
            {
                "update_type": update_type,
                "target": BroadcastTarget.MAP, 
                "systems": systems
            }
        )
        
    @staticmethod  
    def create_global_update(
        systems: Dict[str, Any],
        update_type: str = "delta"
    ) -> WSMessage:
        """Create an update for all connected players"""
        return create_event(
            MessageType.EVENT_STATE_UPDATE,
            {
                "update_type": update_type,
                "target": BroadcastTarget.GLOBAL, 
                "systems": systems
            }
        )
        
    @staticmethod
    def create_game_update(
        entities: list,
        removed_entities: list,
        map_id: str
    ) -> WSMessage:
        """Create a real-time game entity update (always nearby broadcast)"""
        return create_event(
            MessageType.EVENT_GAME_UPDATE,
            {
                "entities": entities,
                "removed_entities": removed_entities,
                "map_id": map_id
            }
        )


# =============================================================================
# Message Validation and Parsing
# =============================================================================

class MessageValidator:
    """Validates incoming WebSocket messages"""
    
    @staticmethod
    def validate_message_structure(raw_data: bytes) -> Dict[str, Any]:
        """Validate basic message structure and deserialize"""
        try:
            # Deserialize msgpack
            message_data = msgpack.unpackb(raw_data, raw=False)
            
            if not isinstance(message_data, dict):
                raise ValueError("Message must be a dictionary")
                
            # Check required fields
            if "type" not in message_data:
                raise ValueError("Message missing required 'type' field")
                
            if "payload" not in message_data:
                raise ValueError("Message missing required 'payload' field")
                
            return message_data
            
        except (msgpack.exceptions.ExtraData, msgpack.exceptions.FormatError) as e:
            raise ValueError(f"Invalid msgpack format: {e}")
        except Exception as e:
            raise ValueError(f"Message validation failed: {e}")
            
    @staticmethod
    def validate_correlation_id(message_data: Dict[str, Any]) -> None:
        """Validate correlation ID requirements"""
        message_type_str = message_data.get("type")
        correlation_id = message_data.get("id")
        
        try:
            message_type = MessageType(message_type_str)
        except ValueError:
            raise ValueError(f"Unknown message type: {message_type_str}")
            
        # Check if correlation ID is required
        if requires_correlation_id(message_type):
            if not correlation_id:
                raise ValueError(f"Message type {message_type} requires correlation ID")
        else:
            if correlation_id:
                raise ValueError(f"Message type {message_type} should not have correlation ID")
                
    @staticmethod
    def create_ws_message(message_data: Dict[str, Any]) -> WSMessage:
        """Create and validate WSMessage from raw data"""
        try:
            return WSMessage(**message_data)
        except Exception as e:
            raise ValueError(f"Invalid message format: {e}")


# =============================================================================  
# Rate Limiting
# =============================================================================

@dataclass
class RateLimit:
    """Rate limit configuration"""
    max_requests: int
    window_seconds: float
    cooldown_seconds: float = 0.0


# Rate limit configurations for different message types
rate_limit_configs = {
    MessageType.CMD_MOVE: RateLimit(1, 0.5, 0.5),
    MessageType.CMD_INVENTORY_MOVE: RateLimit(1, 0.5, 0.5),
    MessageType.CMD_INVENTORY_SORT: RateLimit(1, 0.5, 0.5), 
    MessageType.CMD_ITEM_EQUIP: RateLimit(1, 0.5, 0.5),
    MessageType.CMD_ITEM_UNEQUIP: RateLimit(1, 0.5, 0.5),
    MessageType.CMD_ITEM_DROP: RateLimit(1, 0.2, 0.2),
    MessageType.CMD_ITEM_PICKUP: RateLimit(1, 0.2, 0.2),
    MessageType.CMD_CHAT_SEND: RateLimit(1, 1.0, 1.0),  # Different for channels
}


class RateLimiter:
    """Rate limiting for WebSocket operations"""
    
    def __init__(self, rate_configs: Optional[Dict[MessageType, RateLimit]] = None):
        self.player_requests: Dict[int, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self.player_cooldowns: Dict[int, Dict[str, float]] = defaultdict(dict)
        self.rate_limits = rate_configs or rate_limit_configs
        
    def check_rate_limit(self, player_id: int, message_type: Union[MessageType, str]) -> Optional[float]:
        """
        Check if player is rate limited for message type.
        Returns None if allowed, or retry_after seconds if rate limited.
        """
        now = time.time()
        
        # Handle both MessageType enum and string values
        if isinstance(message_type, str):
            type_value = message_type
            try:
                type_enum = MessageType(message_type)
            except ValueError:
                return None  # Invalid type, no rate limit
        else:
            type_value = message_type.value
            type_enum = message_type
        
        # Check cooldown first
        cooldown_key = f"{type_value}_cooldown"
        if cooldown_key in self.player_cooldowns[player_id]:
            cooldown_expires = self.player_cooldowns[player_id][cooldown_key]
            if now < cooldown_expires:
                return cooldown_expires - now
                
        # Check rate limit
        if type_enum not in self.rate_limits:
            return None  # No rate limit configured
            
        rate_limit = self.rate_limits[type_enum]
        request_key = type_value
        
        # Clean old requests outside window
        requests = self.player_requests[player_id][request_key]
        window_start = now - rate_limit.window_seconds
        requests[:] = [req_time for req_time in requests if req_time > window_start]
        
        # Check if at limit
        if len(requests) >= rate_limit.max_requests:
            oldest_request = min(requests)
            retry_after = oldest_request + rate_limit.window_seconds - now
            return max(0.0, retry_after)
            
        # Allow request - add to tracking
        requests.append(now)
        
        # Set cooldown if configured
        if rate_limit.cooldown_seconds > 0:
            self.player_cooldowns[player_id][cooldown_key] = now + rate_limit.cooldown_seconds
            
        return None
        
    def cleanup_player(self, player_id: int) -> None:
        """Clean up rate limiting data for disconnected player"""
        self.player_requests.pop(player_id, None)
        self.player_cooldowns.pop(player_id, None)


# =============================================================================
# Message Router
# =============================================================================

MessageHandler = Callable[[WSMessage], Awaitable[None]]

class MessageRouter:
    """Routes WebSocket messages to appropriate handlers"""
    
    def __init__(self):
        self.handlers: Dict[MessageType, MessageHandler] = {}
        self.correlation_manager = CorrelationManager()
        self.rate_limiter = RateLimiter()
        
    def register_handler(self, message_type: MessageType, handler: MessageHandler) -> None:
        """Register a message handler"""
        self.handlers[message_type] = handler
        
    async def route_message(
        self, 
        websocket: Any, 
        raw_message: bytes, 
        player_id: Optional[int] = None
    ) -> None:
        """Route an incoming message to the appropriate handler"""
        try:
            # Validate and parse message
            message_data = MessageValidator.validate_message_structure(raw_message)
            MessageValidator.validate_correlation_id(message_data)
            ws_message = MessageValidator.create_ws_message(message_data)
            
            # Check if handler exists
            if ws_message.type not in self.handlers:
                await self._send_error_response(
                    websocket, 
                    ws_message.id,
                    ErrorCodes.SYS_SERVICE_UNAVAILABLE,
                    f"No handler for message type: {ws_message.type}"
                )
                return
                
            # Check rate limiting for commands and queries
            if player_id and ws_message.type in (COMMAND_TYPES | QUERY_TYPES):
                retry_after = self.rate_limiter.check_rate_limit(player_id, ws_message.type)
                if retry_after is not None:
                    await self._send_error_response(
                        websocket,
                        ws_message.id, 
                        ErrorCodes.MOVE_RATE_LIMITED,  # Generic rate limit error
                        "Operation rate limited",
                        error_category="rate_limit",
                        retry_after=retry_after
                    )
                    return
                    
            # Register correlation for tracking (commands/queries only)
            if ws_message.id:
                self.correlation_manager.register_request(
                    ws_message.id,
                    ws_message.type,
                    player_id
                )
                
            # Route to handler  
            handler = self.handlers[ws_message.type]
            await handler(ws_message)
            
        except ValueError as e:
            # Message validation error
            logger.warning(f"Invalid message from player {player_id}: {e}")
            await self._send_error_response(
                websocket,
                None,
                ErrorCodes.SYS_INTERNAL_ERROR,
                f"Invalid message format: {e}",
                error_category="validation"
            )
        except Exception as e:
            # Unexpected error
            logger.error(f"Error routing message from player {player_id}: {e}", exc_info=True)
            await self._send_error_response(
                websocket,
                message_data.get("id") if 'message_data' in locals() else None,
                ErrorCodes.SYS_INTERNAL_ERROR,
                "Internal server error",
                error_category="system"
            )
            
    async def _send_error_response(
        self,
        websocket: Any,
        correlation_id: Optional[str],
        error_code: str,
        message: str,
        error_category: str = "system",
        retry_after: Optional[float] = None
    ) -> None:
        """Send an error response"""
        try:
            error_msg = create_error_response(
                correlation_id or "unknown",
                error_code,
                message,
                error_category=error_category,
                retry_after=retry_after
            )
            await websocket.send_bytes(msgpack.packb(error_msg.model_dump()))
        except Exception as e:
            logger.error(f"Failed to send error response: {e}")
            
    def cleanup_player(self, player_id: int) -> None:
        """Clean up resources for disconnected player"""
        self.rate_limiter.cleanup_player(player_id)


# =============================================================================
# Message Sending Utilities with Broadcasting Support
# =============================================================================

async def send_success_response(
    websocket: Any,
    correlation_id: str, 
    data: Dict[str, Any]
) -> None:
    """Send a success response"""
    message = create_success_response(correlation_id, data)
    await websocket.send_bytes(msgpack.packb(message.model_dump()))


async def send_data_response(
    websocket: Any,
    correlation_id: str,
    data: Dict[str, Any] 
) -> None:
    """Send a data response for queries"""
    message = create_data_response(correlation_id, data)
    await websocket.send_bytes(msgpack.packb(message.model_dump()))
    

async def send_error_response(
    websocket: Any,
    correlation_id: str,
    error_code: str,
    message: str,
    error_category: str = "system",
    details: Optional[Dict[str, Any]] = None,
    retry_after: Optional[float] = None,
    suggested_action: Optional[str] = None
) -> None:
    """Send an error response"""
    error_msg = create_error_response(
        correlation_id,
        error_code, 
        message,
        error_category=error_category,
        details=details,
        retry_after=retry_after,
        suggested_action=suggested_action
    )
    await websocket.send_bytes(msgpack.packb(error_msg.model_dump()))


async def send_personal_event(
    websocket: Any,
    event_type: MessageType,
    payload: Dict[str, Any]
) -> None:
    """Send an event message to a specific player"""
    event_msg = create_event(event_type, payload)
    await websocket.send_bytes(msgpack.packb(event_msg.model_dump()))


async def send_personal_state_update(
    websocket: Any,
    systems: Dict[str, Any],
    update_type: str = "full"
) -> None:
    """Send a personal state update to a specific player"""
    update_msg = StateUpdateManager.create_personal_update(systems, update_type)
    await websocket.send_bytes(msgpack.packb(update_msg.model_dump()))


# =============================================================================
# Broadcasting Utilities
# =============================================================================

class BroadcastManager:
    """Manages message broadcasting to different target groups"""
    
    def __init__(self, connection_manager):
        """Initialize with connection manager for player/map lookups"""
        self.connection_manager = connection_manager
        
    async def broadcast_to_nearby(
        self,
        origin_player: str,
        event_type: MessageType,
        payload: Dict[str, Any],
        include_origin: bool = False
    ) -> list:
        """Broadcast to players in visible range of origin player"""
        try:
            # Get nearby connections from connection manager
            nearby_connections = self.connection_manager.get_nearby_connections(
                origin_player, 
                include_self=include_origin
            )
            
            if not nearby_connections:
                return []
                
            event_msg = create_event(event_type, payload)
            message_data = msgpack.packb(event_msg.model_dump())
            
            failed_sends = []
            for websocket in nearby_connections:
                try:
                    await websocket.send_bytes(message_data)
                except Exception as e:
                    logger.warning(f"Failed to broadcast to nearby player: {e}")
                    failed_sends.append(websocket)
                    
            return failed_sends
            
        except Exception as e:
            logger.error(f"Error in broadcast_to_nearby: {e}")
            return []
    
    async def broadcast_to_map(
        self,
        map_id: str,
        event_type: MessageType,
        payload: Dict[str, Any],
        exclude_players: Optional[list] = None
    ) -> list:
        """Broadcast to all players on a specific map"""
        try:
            map_connections = self.connection_manager.get_map_connections(map_id)
            
            if exclude_players:
                map_connections = [
                    conn for conn in map_connections 
                    if conn.username not in exclude_players
                ]
                
            if not map_connections:
                return []
                
            event_msg = create_event(event_type, payload)
            message_data = msgpack.packb(event_msg.model_dump())
            
            failed_sends = []
            for conn in map_connections:
                try:
                    await conn.websocket.send_bytes(message_data)
                except Exception as e:
                    logger.warning(f"Failed to broadcast to map player {conn.username}: {e}")
                    failed_sends.append(conn.websocket)
                    
            return failed_sends
            
        except Exception as e:
            logger.error(f"Error in broadcast_to_map: {e}")
            return []
            
    async def broadcast_globally(
        self,
        event_type: MessageType,
        payload: Dict[str, Any],
        exclude_players: Optional[list] = None
    ) -> list:
        """Broadcast to all connected players"""
        try:
            all_connections = self.connection_manager.get_all_connections()
            
            if exclude_players:
                all_connections = [
                    conn for conn in all_connections 
                    if conn.username not in exclude_players
                ]
                
            if not all_connections:
                return []
                
            event_msg = create_event(event_type, payload)
            message_data = msgpack.packb(event_msg.model_dump())
            
            failed_sends = []
            for conn in all_connections:
                try:
                    await conn.websocket.send_bytes(message_data)
                except Exception as e:
                    logger.warning(f"Failed to broadcast globally to {conn.username}: {e}")
                    failed_sends.append(conn.websocket)
                    
            return failed_sends
            
        except Exception as e:
            logger.error(f"Error in broadcast_globally: {e}")
            return []
            
    async def broadcast_state_update(
        self,
        systems: Dict[str, Any],
        target: BroadcastTarget,
        origin_player: Optional[str] = None,
        map_id: Optional[str] = None,
        update_type: str = "delta",
        exclude_players: Optional[list] = None
    ) -> list:
        """Broadcast a state update with appropriate targeting"""
        
        # Create the appropriate update message
        update_msg: WSMessage
        if target == BroadcastTarget.PERSONAL:
            # Personal updates should use send_personal_state_update instead
            raise ValueError("Use send_personal_state_update for personal updates")
        elif target == BroadcastTarget.NEARBY:
            if not origin_player:
                raise ValueError("origin_player required for nearby broadcasts")
            update_msg = StateUpdateManager.create_nearby_update(systems, update_type)
        elif target == BroadcastTarget.MAP:
            if not map_id:
                raise ValueError("map_id required for map broadcasts")
            update_msg = StateUpdateManager.create_map_update(systems, update_type)
        elif target == BroadcastTarget.GLOBAL:
            update_msg = StateUpdateManager.create_global_update(systems, update_type)
        else:
            raise ValueError(f"Unknown broadcast target: {target}")
            
            # Send via appropriate broadcast method
            if target == BroadcastTarget.NEARBY:
                if not origin_player:
                    raise ValueError("origin_player required for nearby broadcasts")
                return await self.broadcast_to_nearby(
                    origin_player, 
                    MessageType.EVENT_STATE_UPDATE, 
                    update_msg.payload,
                    include_origin=False
                )
            elif target == BroadcastTarget.MAP:
                if not map_id:
                    raise ValueError("map_id required for map broadcasts")
                return await self.broadcast_to_map(
                    map_id,
                    MessageType.EVENT_STATE_UPDATE,
                    update_msg.payload,
                    exclude_players=exclude_players
                )
            elif target == BroadcastTarget.GLOBAL:
                return await self.broadcast_globally(
                    MessageType.EVENT_STATE_UPDATE,
                    update_msg.payload,
                    exclude_players=exclude_players
                )
            else:
                return []  # Should never reach here due to earlier validation
            
    async def broadcast_chat_message(
        self,
        sender: str,
        message: str,
        channel: str,
        sender_position: Optional[Dict[str, Any]] = None
    ) -> list:
        """Broadcast a chat message with appropriate targeting based on channel"""
        
        chat_payload = {
            "sender": sender,
            "message": message,
            "channel": channel,
            "sender_position": sender_position
        }
        
        if channel == "local":
            # Local chat broadcasts to nearby players
            return await self.broadcast_to_nearby(
                sender,
                MessageType.EVENT_CHAT_MESSAGE,
                chat_payload,
                include_origin=True  # Sender sees their own message
            )
        elif channel == "global":
            # Global chat broadcasts to everyone
            return await self.broadcast_globally(
                MessageType.EVENT_CHAT_MESSAGE,
                chat_payload
            )
        elif channel == "dm":
            # DM should be handled separately by the chat service
            raise ValueError("DM messages should be handled directly, not broadcasted")
        else:
            raise ValueError(f"Unknown chat channel: {channel}")


async def broadcast_event(
    websockets: list,
    event_type: MessageType,
    payload: Dict[str, Any]
) -> list:
    """Broadcast an event to multiple WebSockets"""
    if not websockets:
        return []
        
    event_msg = create_event(event_type, payload)
    message_data = msgpack.packb(event_msg.model_dump())
    
    # Send to all websockets, handle failures gracefully
    failed_sends = []
    for ws in websockets:
        try:
            await ws.send(message_data)
        except Exception as e:
            logger.warning(f"Failed to broadcast event to websocket: {e}")
            failed_sends.append(ws)
            
    return failed_sends  # Return failed websockets for cleanup


# End of websocket_utils.py