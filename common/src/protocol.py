"""
RPG WebSocket Protocol

Unified protocol specification for RPG WebSocket communications
with correlation ID support and structured message patterns.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import Enum
from typing import Dict, Any, List, Optional, Literal, Union
import time


# =============================================================================
# Protocol Constants
# =============================================================================

PROTOCOL_VERSION = "2.0"
"""Current WebSocket protocol version"""


# =============================================================================
# Enums
# =============================================================================

class Direction(str, Enum):
    """Movement directions for player movement commands"""
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"


# =============================================================================
# Message Types
# =============================================================================

class MessageType(str, Enum):
    """All WebSocket message types for RPG Protocol"""
    
    # Client → Server: Commands (State-Changing Operations)
    CMD_AUTHENTICATE = "cmd_authenticate"
    CMD_MOVE = "cmd_move"  
    CMD_CHAT_SEND = "cmd_chat_send"
    CMD_INVENTORY_MOVE = "cmd_inventory_move"
    CMD_INVENTORY_SORT = "cmd_inventory_sort"
    CMD_ITEM_DROP = "cmd_item_drop"
    CMD_ITEM_PICKUP = "cmd_item_pickup"
    CMD_ITEM_EQUIP = "cmd_item_equip"
    CMD_ITEM_UNEQUIP = "cmd_item_unequip"
    CMD_ATTACK = "cmd_attack"
    CMD_TOGGLE_AUTO_RETALIATE = "cmd_toggle_auto_retaliate"
    
    # Client → Server: Queries (Data Retrieval)
    QUERY_INVENTORY = "query_inventory"
    QUERY_EQUIPMENT = "query_equipment"
    QUERY_STATS = "query_stats" 
    QUERY_MAP_CHUNKS = "query_map_chunks"
    
    # Server → Client: Responses (Direct Replies)
    RESP_SUCCESS = "resp_success"
    RESP_ERROR = "resp_error"
    RESP_DATA = "resp_data"
    
    # Server → Client: Events (Broadcasts/Notifications)
    EVENT_WELCOME = "event_welcome"
    EVENT_STATE_UPDATE = "event_state_update"
    EVENT_GAME_UPDATE = "event_game_update"
    EVENT_CHAT_MESSAGE = "event_chat_message"
    EVENT_PLAYER_JOINED = "event_player_joined"
    EVENT_PLAYER_LEFT = "event_player_left"
    EVENT_PLAYER_DIED = "event_player_died"
    EVENT_PLAYER_RESPAWN = "event_player_respawn"
    EVENT_GAME_STATE_UPDATE = "event_game_state_update"
    EVENT_SERVER_SHUTDOWN = "event_server_shutdown"
    EVENT_COMBAT_ACTION = "event_combat_action"
    



# =============================================================================
# Core Message Structure
# =============================================================================

class WSMessage(BaseModel):
    """Universal WebSocket message envelope for all communications"""
    
    id: Optional[str] = Field(None, description="Correlation ID for commands/queries")
    type: MessageType = Field(..., description="Message type from enum")
    payload: Dict[str, Any] = Field(..., description="Type-specific payload data")
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000), description="UTC timestamp in milliseconds")
    version: Literal["2.0"] = Field(PROTOCOL_VERSION, description="Protocol version")

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# Command Payloads (Client → Server)  
# =============================================================================

class AuthenticatePayload(BaseModel):
    """Payload for CMD_AUTHENTICATE"""
    token: str = Field(..., description="JWT authentication token")


class MovePayload(BaseModel):
    """Payload for CMD_MOVE"""
    direction: Direction = Field(..., description="Movement direction")


class ChatSendPayload(BaseModel):
    """Payload for CMD_CHAT_SEND"""
    message: str = Field(..., max_length=500, description="Chat message content")
    channel: Literal["local", "global", "dm"] = Field("local", description="Chat channel type")
    recipient: Optional[str] = Field(None, description="Recipient username for DM")


class InventoryMovePayload(BaseModel):
    """Payload for CMD_INVENTORY_MOVE"""
    from_slot: int = Field(..., ge=0, description="Source inventory slot")
    to_slot: int = Field(..., ge=0, description="Destination inventory slot")


class InventorySortPayload(BaseModel):
    """Payload for CMD_INVENTORY_SORT"""
    sort_by: Literal["category", "rarity", "value", "name"] = Field("category", description="Sort criteria")


class ItemDropPayload(BaseModel):
    """Payload for CMD_ITEM_DROP"""
    inventory_slot: int = Field(..., ge=0, description="Inventory slot to drop from")
    quantity: int = Field(1, ge=1, description="Quantity to drop")


class ItemPickupPayload(BaseModel):
    """Payload for CMD_ITEM_PICKUP"""
    ground_item_id: str = Field(..., description="Ground item ID to pickup")


class ItemEquipPayload(BaseModel):
    """Payload for CMD_ITEM_EQUIP"""
    inventory_slot: int = Field(..., ge=0, description="Inventory slot containing item to equip")


class ItemUnequipPayload(BaseModel):
    """Payload for CMD_ITEM_UNEQUIP"""
    equipment_slot: str = Field(..., description="Equipment slot to unequip from")


class AttackPayload(BaseModel):
    """Payload for CMD_ATTACK"""
    target_type: Literal["entity", "player"] = Field(..., description="Type of target (entity or player)")
    target_id: Union[int, str] = Field(..., description="Entity instance ID (int) or player username (str)")


class ToggleAutoRetaliatePayload(BaseModel):
    """Payload for CMD_TOGGLE_AUTO_RETALIATE"""
    enabled: bool = Field(..., description="Enable or disable auto-retaliation")


# =============================================================================
# Query Payloads (Client → Server)
# =============================================================================

class InventoryQueryPayload(BaseModel):
    """Payload for QUERY_INVENTORY (empty payload)"""
    pass


class EquipmentQueryPayload(BaseModel):
    """Payload for QUERY_EQUIPMENT (empty payload)"""
    pass


class StatsQueryPayload(BaseModel):
    """Payload for QUERY_STATS (empty payload)"""
    pass


class MapChunksQueryPayload(BaseModel):
    """Payload for QUERY_MAP_CHUNKS"""
    map_id: str = Field(..., description="Map identifier")
    center_x: int = Field(..., description="Center tile X coordinate")
    center_y: int = Field(..., description="Center tile Y coordinate")
    radius: int = Field(1, ge=1, le=5, description="Chunk radius (max 5)")


# =============================================================================
# Response Payloads (Server → Client)
# =============================================================================

class SuccessPayload(BaseModel):
    """Payload for RESP_SUCCESS - flexible success response"""
    # Dynamic payload - can contain any success data
    pass


class ErrorPayload(BaseModel):
    """Payload for RESP_ERROR - structured error information"""
    error_code: str = Field(..., description="Structured error code (e.g., CHAT_MESSAGE_TOO_LONG)")
    error_category: Literal["validation", "permission", "system", "rate_limit"] = Field(..., description="Error category")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error context")
    retry_after: Optional[float] = Field(None, description="Seconds to wait before retry (rate limiting)")
    suggested_action: Optional[str] = Field(None, description="Suggested client action")


class DataPayload(BaseModel):
    """Payload for RESP_DATA - query response data"""
    # Dynamic payload - can contain any query result data
    pass


# =============================================================================
# Event Payloads (Server → Client)
# =============================================================================

class WelcomeEventPayload(BaseModel):
    """Payload for EVENT_WELCOME"""
    message: str = Field(..., description="Welcome message")
    motd: Optional[str] = Field(None, description="Message of the day")


class StateUpdateEventPayload(BaseModel):
    """Payload for EVENT_STATE_UPDATE - consolidated state changes"""
    update_type: Literal["full", "delta"] = Field("full", description="Full state or changes only")
    target: Literal["personal", "nearby", "map", "global"] = Field("personal", description="Update distribution scope")
    systems: Dict[str, Any] = Field(..., description="Updated game systems")
    
    class SystemData(BaseModel):
        """Nested data structures for different game systems"""
        player: Optional[Dict[str, Any]] = None      # Position, HP, basic info
        inventory: Optional[Dict[str, Any]] = None   # Items, capacity  
        equipment: Optional[Dict[str, Any]] = None   # Equipped items
        stats: Optional[Dict[str, Any]] = None       # Aggregated stats
        entities: Optional[Dict[str, Any]] = None    # Visible game entities


class GameUpdateEventPayload(BaseModel):
    """Payload for EVENT_GAME_UPDATE - real-time game entity updates"""
    entities: List[Dict[str, Any]] = Field(..., description="Visible game entities")
    removed_entities: List[str] = Field(default_factory=list, description="Removed entity IDs")
    map_id: str = Field(..., description="Map identifier")


class ChatMessageEventPayload(BaseModel):
    """Payload for EVENT_CHAT_MESSAGE"""
    sender: str = Field(..., description="Sender username")
    message: str = Field(..., description="Chat message content")
    channel: str = Field(..., description="Chat channel")
    sender_position: Optional[Dict[str, Any]] = Field(None, description="Sender position data")


class PlayerJoinedEventPayload(BaseModel):
    """Payload for EVENT_PLAYER_JOINED"""
    player: Dict[str, Any] = Field(..., description="Joined player data")
    

class PlayerLeftEventPayload(BaseModel):
    """Payload for EVENT_PLAYER_LEFT"""
    username: str = Field(..., description="Username of player who left")
    reason: Optional[str] = Field(None, description="Disconnect reason")


class ServerShutdownEventPayload(BaseModel):
    """Payload for EVENT_SERVER_SHUTDOWN"""
    message: str = Field(..., description="Shutdown message")
    countdown_seconds: Optional[int] = Field(None, description="Seconds until shutdown")


# =============================================================================
# Error Codes
# =============================================================================

class ErrorCodes:
    """Structured error codes for all game systems"""
    
    # Authentication errors
    AUTH_INVALID_TOKEN = "AUTH_INVALID_TOKEN"
    AUTH_EXPIRED_TOKEN = "AUTH_EXPIRED_TOKEN" 
    AUTH_PLAYER_NOT_FOUND = "AUTH_PLAYER_NOT_FOUND"
    AUTH_PLAYER_BANNED = "AUTH_PLAYER_BANNED"
    AUTH_PLAYER_TIMEOUT = "AUTH_PLAYER_TIMEOUT"
    
    # Movement errors
    MOVE_INVALID_DIRECTION = "MOVE_INVALID_DIRECTION"
    MOVE_COLLISION_DETECTED = "MOVE_COLLISION_DETECTED"
    MOVE_RATE_LIMITED = "MOVE_RATE_LIMITED"
    MOVE_INVALID_POSITION = "MOVE_INVALID_POSITION"
    
    # Chat errors
    CHAT_MESSAGE_TOO_LONG = "CHAT_MESSAGE_TOO_LONG"
    CHAT_PERMISSION_DENIED = "CHAT_PERMISSION_DENIED"
    CHAT_RATE_LIMITED = "CHAT_RATE_LIMITED"
    CHAT_RECIPIENT_NOT_FOUND = "CHAT_RECIPIENT_NOT_FOUND"
    
    # Inventory errors
    INV_INVALID_SLOT = "INV_INVALID_SLOT"
    INV_SLOT_EMPTY = "INV_SLOT_EMPTY" 
    INV_INVENTORY_FULL = "INV_INVENTORY_FULL"
    INV_CANNOT_STACK = "INV_CANNOT_STACK"
    INV_INSUFFICIENT_QUANTITY = "INV_INSUFFICIENT_QUANTITY"
    
    # Equipment errors
    EQ_ITEM_NOT_EQUIPABLE = "EQ_ITEM_NOT_EQUIPABLE"
    EQ_REQUIREMENTS_NOT_MET = "EQ_REQUIREMENTS_NOT_MET"
    EQ_INVALID_SLOT = "EQ_INVALID_SLOT"
    EQ_CANNOT_UNEQUIP_FULL_INV = "EQ_CANNOT_UNEQUIP_FULL_INV"
    
    # Ground Items errors
    GROUND_TOO_FAR = "GROUND_TOO_FAR"
    GROUND_PROTECTED_LOOT = "GROUND_PROTECTED_LOOT"
    GROUND_ITEM_NOT_FOUND = "GROUND_ITEM_NOT_FOUND"
    
    # Map errors
    MAP_INVALID_COORDS = "MAP_INVALID_COORDS"
    MAP_CHUNK_LIMIT_EXCEEDED = "MAP_CHUNK_LIMIT_EXCEEDED"
    MAP_NOT_FOUND = "MAP_NOT_FOUND"
    
    # System errors
    SYS_DATABASE_ERROR = "SYS_DATABASE_ERROR"
    SYS_SERVICE_UNAVAILABLE = "SYS_SERVICE_UNAVAILABLE"
    SYS_INTERNAL_ERROR = "SYS_INTERNAL_ERROR"


# =============================================================================
# Protocol Utilities
# =============================================================================

def create_message(
    message_type: MessageType,
    payload: Dict[str, Any],
    correlation_id: Optional[str] = None
) -> WSMessage:
    """Create a properly formatted WebSocket message"""
    return WSMessage(
        id=correlation_id,
        type=message_type,
        payload=payload
    )


def create_success_response(
    correlation_id: str,
    data: Dict[str, Any]
) -> WSMessage:
    """Create a success response message"""
    return WSMessage(
        id=correlation_id,
        type=MessageType.RESP_SUCCESS,
        payload=data
    )


def create_error_response(
    correlation_id: str,
    error_code: str,
    message: str,
    error_category: str = "system",
    details: Optional[Dict[str, Any]] = None,
    retry_after: Optional[float] = None,
    suggested_action: Optional[str] = None
) -> WSMessage:
    """Create an error response message"""
    return WSMessage(
        id=correlation_id,
        type=MessageType.RESP_ERROR,
        payload={
            "error_code": error_code,
            "error_category": error_category,
            "message": message,
            "details": details,
            "retry_after": retry_after,
            "suggested_action": suggested_action
        }
    )


def create_data_response(
    correlation_id: str,
    data: Dict[str, Any]
) -> WSMessage:
    """Create a data response message for queries"""
    return WSMessage(
        id=correlation_id,
        type=MessageType.RESP_DATA,
        payload=data
    )


def create_event(
    event_type: MessageType,
    payload: Dict[str, Any]
) -> WSMessage:
    """Create an event message (no correlation ID)"""
    return WSMessage(
        type=event_type,
        payload=payload
    )


# =============================================================================
# Request/Response Pattern Mapping
# =============================================================================

# Commands that expect RESP_SUCCESS responses
COMMAND_TYPES = {
    MessageType.CMD_AUTHENTICATE,
    MessageType.CMD_MOVE,
    MessageType.CMD_CHAT_SEND,
    MessageType.CMD_INVENTORY_MOVE,
    MessageType.CMD_INVENTORY_SORT,
    MessageType.CMD_ITEM_DROP,
    MessageType.CMD_ITEM_PICKUP,
    MessageType.CMD_ITEM_EQUIP,
    MessageType.CMD_ITEM_UNEQUIP,
    MessageType.CMD_ATTACK
}

# Queries that expect RESP_DATA responses  
QUERY_TYPES = {
    MessageType.QUERY_INVENTORY,
    MessageType.QUERY_EQUIPMENT,
    MessageType.QUERY_STATS,
    MessageType.QUERY_MAP_CHUNKS
}

# Events (no correlation ID required)
EVENT_TYPES = {
    MessageType.EVENT_WELCOME,
    MessageType.EVENT_STATE_UPDATE,
    MessageType.EVENT_GAME_UPDATE,
    MessageType.EVENT_CHAT_MESSAGE,
    MessageType.EVENT_PLAYER_JOINED,
    MessageType.EVENT_PLAYER_LEFT,
    MessageType.EVENT_SERVER_SHUTDOWN,
    MessageType.EVENT_COMBAT_ACTION
}

# Response types (server only)
RESPONSE_TYPES = {
    MessageType.RESP_SUCCESS,
    MessageType.RESP_ERROR,
    MessageType.RESP_DATA
}


def get_expected_response_type(message_type: MessageType) -> MessageType:
    """Get the expected response type for a client message"""
    if message_type in COMMAND_TYPES:
        return MessageType.RESP_SUCCESS
    elif message_type in QUERY_TYPES:
        return MessageType.RESP_DATA
    else:
        raise ValueError(f"No expected response for message type: {message_type}")


def requires_correlation_id(message_type: MessageType) -> bool:
    """Check if a message type requires a correlation ID"""
    return message_type in (COMMAND_TYPES | QUERY_TYPES)