"""
SQLAlchemy models for players.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, DateTime, func, Enum as SAEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from ..schemas.player import PlayerRole


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)

    # Permissions and Status
    role: Mapped[PlayerRole] = mapped_column(
        SAEnum(PlayerRole, name="playerrole", create_type=False),
        default=PlayerRole.PLAYER,
    )
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    timeout_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Position (will also be in Valkey for hot access)
    x: Mapped[int] = mapped_column()
    y: Mapped[int] = mapped_column()
    map_id: Mapped[str] = mapped_column(String)

    # Hitpoints (current HP, persisted - max HP derived from Hitpoints skill + equipment)
    current_hp: Mapped[int] = mapped_column(default=10)

    # Appearance (paperdoll rendering data)
    # JSON structure: {"skin_tone": str, "hair_style": str, "hair_color": str, "body_type": str}
    appearance: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationships
    skills: Mapped[List["PlayerSkill"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    inventory: Mapped[List["PlayerInventory"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    equipment: Mapped[List["PlayerEquipment"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    dropped_items: Mapped[List["GroundItem"]] = relationship(
        back_populates="dropped_by_player", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        defaults = {
            "role": PlayerRole.PLAYER,
            "is_banned": False,
        }
        for key, value in defaults.items():
            kwargs.setdefault(key, value)
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<Player(id={self.id}, username='{self.username}')>"

    __table_args__ = {"extend_existing": True}
