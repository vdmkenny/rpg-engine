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


class CombatTargetType(str, Enum):
    """Types of combat targets"""
    ENTITY = "entity"
    PLAYER = "player"


class PlayerSettingKey(str, Enum):
    """Player configuration settings"""
    AUTO_RETALIATE = "auto_retaliate"


class ChatChannel(str, Enum):
    """Chat channel types for messaging"""
    LOCAL = "local"
    GLOBAL = "global"
    DM = "dm"


class ErrorCategory(str, Enum):
    """Categories for error responses"""
    VALIDATION = "validation"
    PERMISSION = "permission"
    SYSTEM = "system"
    RATE_LIMIT = "rate_limit"


class ErrorCodes(str, Enum):
    """Error codes for response messages"""
    # System errors
    SYS_INTERNAL_ERROR = "sys_internal_error"
    SYS_SERVICE_UNAVAILABLE = "sys_service_unavailable"
    SYS_INVALID_MESSAGE = "sys_invalid_message"

    # Authentication errors
    AUTH_TOKEN_INVALID = "auth_token_invalid"
    AUTH_TOKEN_EXPIRED = "auth_token_expired"
    AUTH_PLAYER_NOT_FOUND = "auth_player_not_found"

    # Movement errors
    MOVE_RATE_LIMITED = "move_rate_limited"
    MOVE_COLLISION_DETECTED = "move_collision_detected"
    MOVE_INVALID_DIRECTION = "move_invalid_direction"
    MOVE_OUT_OF_BOUNDS = "move_out_of_bounds"

    # Inventory errors
    INV_SLOT_EMPTY = "inv_slot_empty"
    INV_SLOT_OCCUPIED = "inv_slot_occupied"
    INV_INVALID_SLOT = "inv_invalid_slot"
    INV_INVENTORY_FULL = "inv_inventory_full"
    INV_INSUFFICIENT_QUANTITY = "inv_insufficient_quantity"
    INV_CANNOT_STACK = "inv_cannot_stack"

    # Equipment errors
    EQ_ITEM_NOT_EQUIPABLE = "eq_item_not_equipable"
    EQ_REQUIREMENTS_NOT_MET = "eq_requirements_not_met"
    EQ_INVALID_SLOT = "eq_invalid_slot"
    EQ_CANNOT_UNEQUIP_FULL_INV = "eq_cannot_unequip_full_inv"

    # Ground item errors
    GROUND_ITEM_NOT_FOUND = "ground_item_not_found"
    GROUND_ITEM_TOO_FAR = "ground_item_too_far"

    # Map errors
    MAP_INVALID_COORDS = "map_invalid_coords"
    MAP_NOT_FOUND = "map_not_found"

    # Chat errors
    CHAT_MESSAGE_TOO_LONG = "chat_message_too_long"
    CHAT_PERMISSION_DENIED = "chat_permission_denied"

    # Appearance errors
    APPEARANCE_INVALID_VALUE = "appearance_invalid_value"
    APPEARANCE_UPDATE_FAILED = "appearance_update_failed"


class UpdateType(str, Enum):
    """State update types"""
    FULL = "full"
    DELTA = "delta"


class UpdateScope(str, Enum):
    """Distribution scope for state updates"""
    PERSONAL = "personal"
    NEARBY = "nearby"
    MAP = "map"
    GLOBAL = "global"


class InventorySortCriteria(str, Enum):
    """Client-facing sort criteria for inventory organization"""
    CATEGORY = "category"
    RARITY = "rarity"
    VALUE = "value"
    NAME = "name"


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
    CMD_UPDATE_APPEARANCE = "cmd_update_appearance"

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
    EVENT_CHUNK_UPDATE = "event_chunk_update"  # Map chunk data on boundary crossing
    EVENT_STATE_UPDATE = "event_state_update"
    EVENT_GAME_UPDATE = "event_game_update"
    EVENT_CHAT_MESSAGE = "event_chat_message"
    EVENT_PLAYER_JOINED = "event_player_joined"
    EVENT_PLAYER_LEFT = "event_player_left"
    EVENT_PLAYER_DIED = "event_player_died"
    EVENT_PLAYER_RESPAWN = "event_player_respawn"
    EVENT_SERVER_SHUTDOWN = "event_server_shutdown"
    EVENT_COMBAT_ACTION = "event_combat_action"
    EVENT_APPEARANCE_UPDATE = "event_appearance_update"
    



# =============================================================================
# Message Type Collections
# =============================================================================

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
    MessageType.CMD_ATTACK,
    MessageType.CMD_TOGGLE_AUTO_RETALIATE,
    MessageType.CMD_UPDATE_APPEARANCE,
}

QUERY_TYPES = {
    MessageType.QUERY_INVENTORY,
    MessageType.QUERY_EQUIPMENT,
    MessageType.QUERY_STATS,
    MessageType.QUERY_MAP_CHUNKS,
}

RESPONSE_TYPES = {
    MessageType.RESP_SUCCESS,
    MessageType.RESP_ERROR,
    MessageType.RESP_DATA,
}

EVENT_TYPES = {
    MessageType.EVENT_WELCOME,
    MessageType.EVENT_CHUNK_UPDATE,
    MessageType.EVENT_STATE_UPDATE,
    MessageType.EVENT_GAME_UPDATE,
    MessageType.EVENT_CHAT_MESSAGE,
    MessageType.EVENT_PLAYER_JOINED,
    MessageType.EVENT_PLAYER_LEFT,
    MessageType.EVENT_PLAYER_DIED,
    MessageType.EVENT_PLAYER_RESPAWN,
    MessageType.EVENT_SERVER_SHUTDOWN,
    MessageType.EVENT_COMBAT_ACTION,
    MessageType.EVENT_APPEARANCE_UPDATE,
}


# =============================================================================
# Helper Functions
# =============================================================================

def requires_correlation_id(message_type: MessageType) -> bool:
    """Check if message type requires correlation ID."""
    return message_type in COMMAND_TYPES or message_type in QUERY_TYPES


def get_expected_response_type(message_type: MessageType) -> Optional[MessageType]:
    """Get expected response type for command or query."""
    if message_type in COMMAND_TYPES:
        return MessageType.RESP_SUCCESS
    elif message_type in QUERY_TYPES:
        return MessageType.RESP_DATA
    return None


def create_success_response(correlation_id: str, data: Dict[str, Any]) -> "WSMessage":
    """Create a success response message."""
    return WSMessage(
        id=correlation_id,
        type=MessageType.RESP_SUCCESS,
        payload={"data": data}
    )


def create_error_response(
    correlation_id: str,
    error_code: str,
    message: str,
    error_category: ErrorCategory = ErrorCategory.SYSTEM,
    details: Optional[Dict[str, Any]] = None,
    retry_after: Optional[float] = None,
    suggested_action: Optional[str] = None
) -> "WSMessage":
    """Create an error response message."""
    payload: Dict[str, Any] = {
        "error": message,
        "code": error_code,
        "category": error_category.value
    }
    if details:
        payload["details"] = details
    if retry_after is not None:
        payload["retry_after"] = retry_after
    if suggested_action:
        payload["suggested_action"] = suggested_action
    
    return WSMessage(
        id=correlation_id,
        type=MessageType.RESP_ERROR,
        payload=payload
    )


def create_data_response(correlation_id: str, data: Dict[str, Any]) -> "WSMessage":
    """Create a data response message for query responses."""
    return WSMessage(
        id=correlation_id,
        type=MessageType.RESP_DATA,
        payload={"data": data}
    )


def create_event(event_type: MessageType, payload: Dict[str, Any]) -> "WSMessage":
    """Create an event message (broadcasts/notifications)."""
    return WSMessage(
        id=None,
        type=event_type,
        payload=payload
    )


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
    model_config = ConfigDict(use_enum_values=True)

    direction: Direction = Field(..., description="Movement direction")


class ChatSendPayload(BaseModel):
    """Payload for CMD_CHAT_SEND"""
    model_config = ConfigDict(use_enum_values=True)

    message: str = Field(..., max_length=500, description="Chat message content")
    channel: ChatChannel = Field(ChatChannel.LOCAL, description="Chat channel type")
    recipient: Optional[str] = Field(None, description="Recipient username for DM")


class InventoryMovePayload(BaseModel):
    """Payload for CMD_INVENTORY_MOVE"""
    from_slot: int = Field(..., ge=0, description="Source inventory slot")
    to_slot: int = Field(..., ge=0, description="Destination inventory slot")


class InventorySortPayload(BaseModel):
    """Payload for CMD_INVENTORY_SORT"""
    model_config = ConfigDict(use_enum_values=True)

    sort_by: InventorySortCriteria = Field(InventorySortCriteria.CATEGORY, description="Sort criteria")


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
    model_config = ConfigDict(use_enum_values=True)

    target_type: CombatTargetType = Field(..., description="Type of target (entity or player)")
    target_id: Union[int, str] = Field(..., description="Entity instance ID (int) or player username (str)")


class ToggleAutoRetaliatePayload(BaseModel):
    """Payload for CMD_TOGGLE_AUTO_RETALIATE"""
    enabled: bool = Field(..., description="Enable or disable auto-retaliation")


class AppearanceUpdatePayload(BaseModel):
    """Payload for CMD_UPDATE_APPEARANCE - Update player appearance (paperdoll)"""
    # Core appearance
    body_type: Optional[str] = Field(None, description="Body type (male, female, child, teen, skeleton, zombie)")
    skin_tone: Optional[str] = Field(None, description="Skin tone (light, dark, brown, etc.)")
    head_type: Optional[str] = Field(None, description="Head type (human/male, human/female, orc, etc.)")
    hair_style: Optional[str] = Field(None, description="Hair style (short, long, bald, etc.)")
    hair_color: Optional[str] = Field(None, description="Hair color (brown, blonde, black, etc.)")
    eye_color: Optional[str] = Field(None, description="Eye color (brown, blue, green, etc.)")
    
    # Facial hair
    facial_hair_style: Optional[str] = Field(None, description="Facial hair style (none, beard_black, mustache_brown, etc.)")
    facial_hair_color: Optional[str] = Field(None, description="Facial hair color")
    
    # Clothing
    shirt_style: Optional[str] = Field(None, description="Shirt style (longsleeve2, shortsleeve, tunic, etc.)")
    shirt_color: Optional[str] = Field(None, description="Shirt color")
    pants_style: Optional[str] = Field(None, description="Pants style (pants, shorts, leggings, etc.)")
    pants_color: Optional[str] = Field(None, description="Pants color")
    shoes_style: Optional[str] = Field(None, description="Shoes style (shoes/basic, boots, sandals, etc.)")
    shoes_color: Optional[str] = Field(None, description="Shoes color")


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
    center_x: int = Field(..., description="Center X coordinate")
    center_y: int = Field(..., description="Center Y coordinate")
    radius: int = Field(2, ge=1, le=5, description="Chunk radius from center")


# =============================================================================
# Response Payloads (Server → Client)
# =============================================================================

class SuccessResponsePayload(BaseModel):
    """Payload for RESP_SUCCESS"""
    message: Optional[str] = Field(None, description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional response data")


class ErrorResponsePayload(BaseModel):
    """Payload for RESP_ERROR"""
    model_config = ConfigDict(use_enum_values=True)

    error: str = Field(..., description="Error message")
    category: ErrorCategory = Field(ErrorCategory.SYSTEM, description="Error category")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


class DataResponsePayload(BaseModel):
    """Payload for RESP_DATA"""
    data_type: str = Field(..., description="Type of data being returned")
    data: Dict[str, Any] = Field(..., description="The actual data")


# =============================================================================
# Event Payloads (Server → Client)
# =============================================================================

class WelcomeEventPayload(BaseModel):
    """Payload for EVENT_WELCOME"""
    player_id: int = Field(..., description="Player's unique ID")
    username: str = Field(..., description="Player's username")
    position: Dict[str, int] = Field(..., description="Player's position {x, y}")
    map_id: str = Field(..., description="Current map ID")


class ChunkUpdateEventPayload(BaseModel):
    """Payload for EVENT_CHUNK_UPDATE - Sent when player crosses chunk boundary"""
    chunks: List[Dict[str, Any]] = Field(..., description="List of chunk data")
    player_position: Dict[str, int] = Field(..., description="Player's new position {x, y}")


class GameUpdateEventPayload(BaseModel):
    """Payload for EVENT_GAME_UPDATE - High-frequency game state updates (20 TPS)"""
    model_config = ConfigDict(use_enum_values=True)

    update_type: UpdateType = Field(UpdateType.DELTA, description="Update type (full or delta)")
    scope: UpdateScope = Field(UpdateScope.PERSONAL, description="Update distribution scope")
    sequence: int = Field(..., description="Update sequence number")
    timestamp: int = Field(..., description="Server timestamp in milliseconds")
    entities: List[Dict[str, Any]] = Field(default_factory=list, description="Visible entity updates")
    player: Optional[Dict[str, Any]] = Field(None, description="Player-specific updates (if changed)")


class ChatMessageEventPayload(BaseModel):
    """Payload for EVENT_CHAT_MESSAGE"""
    model_config = ConfigDict(use_enum_values=True)

    channel: ChatChannel = Field(..., description="Chat channel type")
    sender: str = Field(..., description="Sender's username")
    message: str = Field(..., max_length=500, description="Message content")
    timestamp: int = Field(..., description="Message timestamp in milliseconds")


class PlayerJoinedEventPayload(BaseModel):
    """Payload for EVENT_PLAYER_JOINED"""
    player_id: int = Field(..., description="Player's unique ID")
    username: str = Field(..., description="Player's username")
    position: Dict[str, int] = Field(..., description="Player's position {x, y}")


class PlayerLeftEventPayload(BaseModel):
    """Payload for EVENT_PLAYER_LEFT"""
    player_id: int = Field(..., description="Player's unique ID")
    username: str = Field(..., description="Player's username")


class PlayerDiedEventPayload(BaseModel):
    """Payload for EVENT_PLAYER_DIED"""
    player_id: int = Field(..., description="Player's unique ID")
    username: str = Field(..., description="Player's username")
    killed_by: Optional[str] = Field(None, description="Name of killer (entity or player)")


class PlayerRespawnEventPayload(BaseModel):
    """Payload for EVENT_PLAYER_RESPAWN"""
    player_id: int = Field(..., description="Player's unique ID")
    username: str = Field(..., description="Player's username")
    position: Dict[str, int] = Field(..., description="New respawn position {x, y}")


class ServerShutdownEventPayload(BaseModel):
    """Payload for EVENT_SERVER_SHUTDOWN"""
    reason: str = Field("Server maintenance", description="Shutdown reason")
    countdown_seconds: int = Field(60, ge=0, description="Seconds until shutdown")


class CombatActionEventPayload(BaseModel):
    """Payload for EVENT_COMBAT_ACTION"""
    model_config = ConfigDict(use_enum_values=True)

    action_type: str = Field(..., description="Type of combat action (attack, damage, death, etc.)")
    attacker: Optional[Dict[str, Any]] = Field(None, description="Attacker details")
    target: Optional[Dict[str, Any]] = Field(None, description="Target details")
    damage: Optional[int] = Field(None, ge=0, description="Damage amount")
    skill_xp: Optional[Dict[str, int]] = Field(None, description="Skill XP gains {skill_name: xp}")
    drops: Optional[List[Dict[str, Any]]] = Field(None, description="Items dropped")


class AppearanceUpdateEventPayload(BaseModel):
    """Payload for EVENT_APPEARANCE_UPDATE - Broadcast when player changes appearance"""
    player_id: int = Field(..., description="Player's unique ID")
    username: str = Field(..., description="Player's username")
    appearance: Dict[str, Any] = Field(..., description="Full appearance data")
    visual_hash: str = Field(..., description="Visual state hash for efficient caching")


# =============================================================================
# State Update Payloads (High-Frequency Updates)
# =============================================================================

class EntityState(BaseModel):
    """Entity state within a state update"""
    id: Union[int, str] = Field(..., description="Entity ID")
    type: str = Field(..., description="Entity type")
    x: int = Field(..., description="X coordinate")
    y: int = Field(..., description="Y coordinate")
    direction: Optional[str] = Field(None, description="Facing direction")
    animation: Optional[str] = Field(None, description="Current animation state")
    visual_hash: Optional[str] = Field(None, description="Visual appearance hash")
    hp_percent: Optional[float] = Field(None, ge=0, le=100, description="HP percentage")


class PlayerStateUpdate(BaseModel):
    """Player-specific state update"""
    position: Optional[Dict[str, int]] = Field(None, description="Position {x, y}")
    current_hp: Optional[int] = Field(None, ge=0, description="Current HP")
    max_hp: Optional[int] = Field(None, ge=1, description="Maximum HP")
    visual_hash: Optional[str] = Field(None, description="Visual state hash")
    equipment_hash: Optional[str] = Field(None, description="Equipment state hash")


class StateUpdateEventPayload(BaseModel):
    """Payload for EVENT_STATE_UPDATE - Mid-frequency state updates (5 TPS)"""
    timestamp: int = Field(..., description="Server timestamp in milliseconds")
    sequence: int = Field(..., description="Update sequence number")
    entities: List[EntityState] = Field(default_factory=list, description="Entity state updates")
    player: Optional[PlayerStateUpdate] = Field(None, description="Player-specific updates")


# =============================================================================
# Inventory System Payloads
# =============================================================================

class InventoryItemData(BaseModel):
    """Item data for inventory responses"""
    slot: int = Field(..., ge=0, description="Inventory slot index")
    item_id: str = Field(..., description="Item type ID")
    name: str = Field(..., description="Item display name")
    quantity: int = Field(1, ge=1, description="Stack quantity")
    category: str = Field(..., description="Item category")
    rarity: str = Field(..., description="Item rarity")
    is_stackable: bool = Field(False, description="Whether item can stack")
    is_equippable: bool = Field(False, description="Whether item can be equipped")
    icon_sprite: Optional[str] = Field(None, description="Icon sprite ID")
    equipped_sprite: Optional[str] = Field(None, description="Equipped sprite ID for paperdoll")
    description: Optional[str] = Field(None, description="Item description")


class InventoryDataPayload(BaseModel):
    """Payload for inventory data responses"""
    items: List[InventoryItemData] = Field(default_factory=list, description="List of inventory items")
    gold: int = Field(0, ge=0, description="Player's gold amount")
    capacity: int = Field(28, description="Inventory capacity")


class EquipmentSlotData(BaseModel):
    """Equipment slot data"""
    slot: str = Field(..., description="Equipment slot name")
    item: Optional[InventoryItemData] = Field(None, description="Equipped item, or None if empty")


class EquipmentDataPayload(BaseModel):
    """Payload for equipment data responses"""
    slots: List[EquipmentSlotData] = Field(default_factory=list, description="List of equipment slots")


# =============================================================================
# Stats System Payloads
# =============================================================================

class SkillData(BaseModel):
    """Skill data for stats"""
    name: str = Field(..., description="Skill name")
    level: int = Field(..., ge=1, description="Current level")
    xp: int = Field(..., ge=0, description="Current XP")
    xp_to_next: int = Field(..., ge=0, description="XP needed for next level")


class StatsDataPayload(BaseModel):
    """Payload for stats data responses"""
    combat_level: int = Field(..., ge=1, description="Combat level")
    total_level: int = Field(..., ge=1, description="Total skill levels")
    total_xp: int = Field(..., ge=0, description="Total XP across all skills")
    skills: List[SkillData] = Field(default_factory=list, description="List of skills")
    max_hp: int = Field(..., ge=1, description="Maximum hitpoints")


# =============================================================================
# Map System Payloads
# =============================================================================

class MapChunkData(BaseModel):
    """Map chunk data"""
    chunk_x: int = Field(..., description="Chunk X coordinate")
    chunk_y: int = Field(..., description="Chunk Y coordinate")
    tiles: List[List[int]] = Field(..., description="2D array of tile IDs")


class MapChunksDataPayload(BaseModel):
    """Payload for map chunk data responses"""
    chunks: List[MapChunkData] = Field(default_factory=list, description="List of chunk data")
    player_chunk_x: int = Field(..., description="Player's chunk X coordinate")
    player_chunk_y: int = Field(..., description="Player's chunk Y coordinate")
