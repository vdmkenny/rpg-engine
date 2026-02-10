"""
SQLAlchemy models for skills.
"""

from typing import List
from sqlalchemy import String, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class Skill(Base):
    """
    Static definition of a skill.

    Skill metadata (category, description, xp_multiplier) is defined in
    server/src/core/skills.py and config.yml. This table just stores
    the skill names for foreign key relationships.
    """

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)

    player_skills: Mapped[List["PlayerSkill"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, name='{self.name}')>"

    __table_args__ = {"extend_existing": True}


class PlayerSkill(Base):
    """
    Junction table linking a player to a skill and their progress.

    The current_level is computed from experience using the XP formula
    in server/src/core/skills.py with multipliers from config.yml.
    It's stored here for query efficiency but should be recalculated
    when experience changes.
    """

    __tablename__ = "player_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), index=True)

    current_level: Mapped[int] = mapped_column(default=1)
    experience: Mapped[int] = mapped_column(BigInteger, default=0)

    player: Mapped["Player"] = relationship(back_populates="skills")
    skill: Mapped["Skill"] = relationship(back_populates="player_skills")

    __table_args__ = (
        UniqueConstraint("player_id", "skill_id", name="_player_skill_uc"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return f"<PlayerSkill(player_id={self.player_id}, skill_id={self.skill_id}, level={self.current_level}, xp={self.experience})>"
