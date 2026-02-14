"""
Pydantic models for player data.

Consolidated schemas for MMORPG player management.
Replaces: PlayerInDB, PlayerPublic, PlayerData, etc.
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

from common.src.sprites import AppearanceData
from ..core.constants import PlayerRole


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
    password: str = Field(min_length=8, max_length=72)
    
    @field_validator("password", mode="after")
    @classmethod
    def validate_password_bytes(cls, v: str) -> str:
        """
        Validate that password is within bcrypt 5.0.0+ limit of 72 bytes.
        bcrypt truncates passwords longer than 72 bytes, which is a security concern.
        """
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 bytes or less (UTF-8 encoded)")
        return v


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
    timeout_until: Optional[datetime] = None  # UTC datetime or None
    appearance: Optional[AppearanceData] = None
    
    @field_validator("appearance", mode="before")
    @classmethod
    def validate_appearance(cls, v):
        """
        Convert dict or AppearanceData to AppearanceData using lenient parsing.
        
        This handles:
        - Dict from database (JSON column) -> AppearanceData via from_dict()
        - None -> None
        - Existing AppearanceData -> passed through
        
        Using from_dict() ensures invalid enum values fallback to defaults
        rather than causing validation errors that block player login.
        """
        if v is None:
            return None
        if isinstance(v, AppearanceData):
            return v
        if isinstance(v, dict):
            return AppearanceData.from_dict(v)
        # Fallback: try to treat as dict-like
        try:
            return AppearanceData.from_dict(dict(v))
        except Exception:
            return None


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
