"""
SQLAlchemy model for entity definitions (NPCs and Monsters).
"""

from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, Integer, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Entity(Base):
    """
    Database mirror of HumanoidDefinition and MonsterDefinition.
    
    This table acts as a queryable reference for entity templates.
    The source of truth is the code (HumanoidID/MonsterID enums), which are synced
    to this table on server startup.
    
    entity_type distinguishes between:
    - "humanoid_npc": Uses paperdoll rendering with appearance + equipment
    - "monster": Uses sprite sheet animations with innate combat stats
    """
    
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)  # Enum name (e.g., "GOBLIN", "VILLAGE_GUARD")
    entity_type: Mapped[str] = mapped_column(String, default="monster")  # "humanoid_npc" or "monster"
    
    # Identity
    display_name: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    behavior: Mapped[str] = mapped_column(String)  # EntityBehavior value
    is_attackable: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Visuals - Monster sprite sheets
    sprite_sheet_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Monster sprite sheet identifier
    width: Mapped[int] = mapped_column(Integer, default=1)
    height: Mapped[int] = mapped_column(Integer, default=1)
    scale: Mapped[float] = mapped_column(Float, default=1.0)
    
    # Visuals - Humanoid paperdoll (JSON for appearance data)
    appearance: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # AppearanceData as JSON
    equipped_items: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON, nullable=True)  # {slot: item_name}
    
    # Stats
    level: Mapped[int] = mapped_column(Integer, default=1)
    max_hp: Mapped[int] = mapped_column(Integer, default=10)
    xp_reward: Mapped[int] = mapped_column(Integer, default=0)
    aggro_radius: Mapped[int] = mapped_column(Integer, default=0)
    disengage_radius: Mapped[int] = mapped_column(Integer, default=0)
    respawn_time: Mapped[int] = mapped_column(Integer, default=30)
    
    # Complex Data
    skills: Mapped[Dict[str, int]] = mapped_column(JSON, default=dict)
    dialogue: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    shop_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Combat Bonuses (Offensive)
    attack_bonus: Mapped[int] = mapped_column(Integer, default=0)
    strength_bonus: Mapped[int] = mapped_column(Integer, default=0)
    ranged_attack_bonus: Mapped[int] = mapped_column(Integer, default=0)
    ranged_strength_bonus: Mapped[int] = mapped_column(Integer, default=0)
    magic_attack_bonus: Mapped[int] = mapped_column(Integer, default=0)
    magic_damage_bonus: Mapped[int] = mapped_column(Integer, default=0)

    # Combat Bonuses (Defensive)
    physical_defence_bonus: Mapped[int] = mapped_column(Integer, default=0)
    magic_defence_bonus: Mapped[int] = mapped_column(Integer, default=0)
    
    # Other Bonuses
    speed_bonus: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<Entity(name='{self.name}', display_name='{self.display_name}')>"
