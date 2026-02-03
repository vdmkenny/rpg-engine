"""
Pydantic models for player data.

Consolidated schemas for MMORPG player management.
Replaces: PlayerInDB, PlayerPublic, PlayerData, etc.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from enum import Enum


class PlayerRole(str, Enum):
    """Player access roles."""
    PLAYER = "player"
    MODERATOR = "moderator"
    ADMIN = "admin"


class Direction(str, Enum):
    """Cardinal directions for player facing/movement."""
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class AnimationState(str, Enum):
    """Player animation states for client rendering."""
    IDLE = "idle"
    WALK = "walk"
    ATTACK = "attack"
    DEATH = "death"


class PlayerCreate(BaseModel):
    """Schema for creating a new player."""
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class PlayerData(BaseModel):
    """
    Complete player data - used for all player operations.
    Replaces PlayerInDB, PlayerPublic, and PlayerData.
    """
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    username: str
    x: int
    y: int
    map_id: str
    current_hp: int
    max_hp: int
    role: PlayerRole = PlayerRole.PLAYER
    is_banned: bool = False
    is_online: bool = False
    facing_direction: Direction = Direction.SOUTH
    animation_state: AnimationState = AnimationState.IDLE
    total_level: int = 0


class PlayerPosition(BaseModel):
    """
    Minimal position data for hot path updates (20 TPS).
    Used for movement and visibility calculations.
    """
    player_id: int
    x: int
    y: int
    map_id: str
    direction: Direction = Direction.SOUTH
    is_moving: bool = False


class NearbyPlayer(BaseModel):
    """
    Other players visible to client.
    Minimal data for rendering other players on screen.
    """
    player_id: int
    username: str
    x: int
    y: int
    direction: Direction
    animation_state: AnimationState
    # Client uses appearance hash to cache render data
    appearance_hash: Optional[str] = None
