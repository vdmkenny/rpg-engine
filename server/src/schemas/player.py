"""
Pydantic models (schemas) for player data.
Used for API validation and serialization.
"""

from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
from typing import Annotated


class PlayerRole(str, Enum):
    """
    Defines the roles a player can have.
    """

    PLAYER = "player"
    MODERATOR = "moderator"
    ADMIN = "admin"


class PlayerBase(BaseModel):
    """
    Base schema for a player.
    """

    username: Annotated[str, Field(min_length=3, max_length=50)]


class PlayerCreate(PlayerBase):
    """
    Schema for creating a new player.
    """

    password: str


class PlayerInDB(PlayerBase):
    """
    Schema for a player as stored in the database.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: PlayerRole
    is_banned: bool


class PlayerPublic(BaseModel):
    """
    Schema for returning public player data.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: PlayerRole
