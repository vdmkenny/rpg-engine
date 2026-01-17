"""
Shared protocol definitions.
Using Pydantic models for structure and validation.
"""

from pydantic import BaseModel
from enum import Enum
from typing import Dict, Any, List, Set, Optional, Tuple


class MessageType(str, Enum):
    # Client to Server - Authentication & Movement
    AUTHENTICATE = "AUTHENTICATE"
    MOVE_INTENT = "MOVE_INTENT"
    SEND_CHAT_MESSAGE = "SEND_CHAT_MESSAGE"
    REQUEST_CHUNKS = "REQUEST_CHUNKS"

    # Client to Server - Inventory
    REQUEST_INVENTORY = "REQUEST_INVENTORY"
    MOVE_INVENTORY_ITEM = "MOVE_INVENTORY_ITEM"
    SORT_INVENTORY = "SORT_INVENTORY"
    DROP_ITEM = "DROP_ITEM"

    # Client to Server - Equipment
    REQUEST_EQUIPMENT = "REQUEST_EQUIPMENT"
    EQUIP_ITEM = "EQUIP_ITEM"
    UNEQUIP_ITEM = "UNEQUIP_ITEM"
    REQUEST_STATS = "REQUEST_STATS"

    # Client to Server - Ground Items
    PICKUP_ITEM = "PICKUP_ITEM"

    # Server to Client - Core
    WELCOME = "WELCOME"
    GAME_STATE_UPDATE = "GAME_STATE_UPDATE"
    NEW_CHAT_MESSAGE = "NEW_CHAT_MESSAGE"
    CHUNK_DATA = "CHUNK_DATA"
    ERROR = "ERROR"
    SERVER_SHUTDOWN = "SERVER_SHUTDOWN"
    PLAYER_DISCONNECT = "PLAYER_DISCONNECT"

    # Server to Client - Inventory
    INVENTORY_UPDATE = "INVENTORY_UPDATE"

    # Server to Client - Equipment
    EQUIPMENT_UPDATE = "EQUIPMENT_UPDATE"
    STATS_UPDATE = "STATS_UPDATE"

    # Server to Client - Ground Items
    GROUND_ITEMS_UPDATE = "GROUND_ITEMS_UPDATE"

    # Server to Client - Operation Results
    OPERATION_RESULT = "OPERATION_RESULT"


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class GameMessage(BaseModel):
    type: MessageType
    payload: Dict[str, Any]


# --- Specific Payload Schemas ---


class MoveIntentPayload(BaseModel):
    direction: Direction


class GameStateUpdatePayload(BaseModel):
    entities: List[Dict[str, Any]]  # e.g., [{"id": 1, "x": 10, "y": 15}]


class ChunkRequestPayload(BaseModel):
    map_id: str
    center_x: int  # Player's current tile x position
    center_y: int  # Player's current tile y position
    radius: int = 1  # Number of chunks around center (1 = 3x3 grid of chunks)


class TileData(BaseModel):
    gid: int  # Global tile ID (for backward compatibility)
    properties: Dict[str, Any] = {}  # Tile properties like walkable, etc.
    layers: List[Dict[str, Any]] = []  # Multi-layer support: [{"gid": 577, "layer_name": "ground"}, ...]


class ChunkData(BaseModel):
    chunk_x: int  # Chunk coordinate X (in chunk units)
    chunk_y: int  # Chunk coordinate Y (in chunk units)
    tiles: List[List[TileData]]  # 16x16 grid of tiles
    width: int = 16
    height: int = 16


class ChunkDataPayload(BaseModel):
    map_id: str
    chunks: List[Dict[str, Any]]  # List of chunk data


class PlayerDisconnectPayload(BaseModel):
    """Payload for PLAYER_DISCONNECT messages."""
    username: str


class MovementValidator:
    """Simple movement validator for testing collision detection logic."""

    def __init__(self, obstacles: Optional[Set[Tuple[int, int]]] = None):
        """Initialize with a set of obstacle coordinates."""
        self.obstacles = obstacles or set()

    def is_valid_move(self, x: int, y: int) -> bool:
        """Check if movement to position (x, y) is valid."""
        # Basic validation
        if x < 0 or y < 0:
            return False

        # Check if position has an obstacle
        return (x, y) not in self.obstacles


# --- Inventory Payload Schemas ---


class MoveInventoryItemPayload(BaseModel):
    """Payload for MOVE_INVENTORY_ITEM messages."""
    from_slot: int
    to_slot: int


class SortInventoryPayload(BaseModel):
    """Payload for SORT_INVENTORY messages."""
    sort_type: str  # InventorySortType value


class DropItemPayload(BaseModel):
    """Payload for DROP_ITEM messages."""
    inventory_slot: int
    quantity: Optional[int] = None  # None = drop entire stack


# --- Equipment Payload Schemas ---


class EquipItemPayload(BaseModel):
    """Payload for EQUIP_ITEM messages."""
    inventory_slot: int  # Inventory slot to equip from


class UnequipItemPayload(BaseModel):
    """Payload for UNEQUIP_ITEM messages."""
    equipment_slot: str  # EquipmentSlot value


# --- Ground Item Payload Schemas ---


class PickupItemPayload(BaseModel):
    """Payload for PICKUP_ITEM messages."""
    ground_item_id: int


# --- Operation Result Payload ---


class OperationResultPayload(BaseModel):
    """
    Generic operation result payload.

    Sent in response to client operations like equip, drop, pickup, etc.
    """
    operation: str  # e.g., "equip", "drop", "pickup", "sort"
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None  # Additional operation-specific data
