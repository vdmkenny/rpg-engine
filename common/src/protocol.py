"""
Shared protocol definitions.
Using Pydantic models for structure and validation.
"""

from pydantic import BaseModel
from enum import Enum
from typing import Dict, Any, List, Set, Optional, Tuple


class MessageType(str, Enum):
    # Client to Server
    AUTHENTICATE = "AUTHENTICATE"
    MOVE_INTENT = "MOVE_INTENT"
    SEND_CHAT_MESSAGE = "SEND_CHAT_MESSAGE"
    REQUEST_CHUNKS = "REQUEST_CHUNKS"

    # Server to Client
    WELCOME = "WELCOME"
    GAME_STATE_UPDATE = "GAME_STATE_UPDATE"
    NEW_CHAT_MESSAGE = "NEW_CHAT_MESSAGE"
    CHUNK_DATA = "CHUNK_DATA"
    ERROR = "ERROR"
    SERVER_SHUTDOWN = "SERVER_SHUTDOWN"


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
