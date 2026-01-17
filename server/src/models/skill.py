"""
SQLAlchemy models for skills.
"""

from sqlalchemy import Column, Integer, String, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import Base


class Skill(Base):
    """
    Static definition of a skill.

    Skill metadata (category, description, xp_multiplier) is defined in
    server/src/core/skills.py and config.yml. This table just stores
    the skill names for foreign key relationships.
    """

    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)

    player_skills = relationship(
        "PlayerSkill", back_populates="skill", cascade="all, delete-orphan"
    )

    def __repr__(self):
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

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False, index=True)

    current_level = Column(Integer, default=1, nullable=False)
    experience = Column(BigInteger, default=0, nullable=False)

    player = relationship("Player", back_populates="skills")
    skill = relationship("Skill", back_populates="player_skills")

    __table_args__ = (
        UniqueConstraint("player_id", "skill_id", name="_player_skill_uc"),
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<PlayerSkill(player_id={self.player_id}, skill_id={self.skill_id}, level={self.current_level}, xp={self.experience})>"
