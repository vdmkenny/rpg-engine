"""
SQLAlchemy models for players.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, Enum as SAEnum
from sqlalchemy.orm import relationship
from .base import Base
from ..schemas.player import PlayerRole


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # Permissions and Status
    role = Column(
        SAEnum(PlayerRole, name="playerrole", create_type=False),
        default=PlayerRole.PLAYER,
        nullable=False,
    )
    is_banned = Column(Boolean, default=False, nullable=False)
    timeout_until = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Position (will also be in Valkey for hot access)
    x_coord = Column(Integer, default=5)  # Default spawn x coordinate
    y_coord = Column(Integer, default=5)  # Default spawn y coordinate
    map_id = Column(String, default="test_map")  # Map filename without .tmx extension

    # Relationships
    skills = relationship(
        "PlayerSkill", back_populates="player", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        defaults = {
            "role": PlayerRole.PLAYER,
            "is_banned": False,
            "x_coord": 5,
            "y_coord": 5,
            "map_id": "test_map",
        }
        for key, value in defaults.items():
            kwargs.setdefault(key, value)
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<Player(id={self.id}, username='{self.username}')>"

    __table_args__ = {"extend_existing": True}
