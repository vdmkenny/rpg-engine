"""
Pydantic models for skill data.

Consolidated schemas with enums for MMORPG skill system.
Replaces LevelUpNotification and XPGainNotification with XPGain.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from enum import Enum


class SkillType(str, Enum):
    """Available skills in the game."""
    ATTACK = "attack"
    STRENGTH = "strength"
    DEFENCE = "defence"
    HITPOINTS = "hitpoints"
    MINING = "mining"
    WOODCUTTING = "woodcutting"
    FISHING = "fishing"


class SkillData(BaseModel):
    """Single skill info for UI display."""
    model_config = ConfigDict(from_attributes=True)
    
    name: str = Field(..., description="Display name of the skill")
    category: str = Field(..., description="Skill category (combat, gathering, crafting)")
    description: str = Field(..., description="Description of what the skill does")
    current_level: int = Field(..., ge=1, le=99, description="Current skill level")
    experience: int = Field(..., ge=0, description="Total experience points")
    xp_for_current_level: int = Field(..., ge=0, description="XP required to reach current level")
    xp_for_next_level: int = Field(..., ge=0, description="XP required to reach next level")
    xp_to_next_level: int = Field(..., ge=0, description="XP remaining until next level")
    xp_multiplier: float = Field(..., gt=0, description="XP scaling multiplier for this skill")
    progress_percent: float = Field(..., ge=0, le=100, description="Progress to next level as percentage")
    max_level: int = Field(..., description="Maximum achievable level")


class PlayerSkills(BaseModel):
    """Response containing all skills for a player."""
    model_config = ConfigDict(from_attributes=True)
    
    skills: List[SkillData] = Field(..., description="List of all player skills")
    total_level: int = Field(..., ge=0, description="Sum of all skill levels")


class XPGain(BaseModel):
    """
    XP gain notification - includes optional level-up info.
    Replaces both LevelUpNotification and XPGainNotification.
    """
    model_config = ConfigDict(from_attributes=True)
    
    skill: str = Field(..., description="Name of the skill")
    xp_gained: int = Field(..., gt=0, description="Amount of XP gained")
    current_xp: int = Field(..., ge=0, description="Current total XP in the skill")
    current_level: int = Field(..., ge=1, description="Current level")
    previous_level: int = Field(..., ge=1, description="Level before XP gain")
    xp_to_next_level: int = Field(..., ge=0, description="XP remaining until next level")
    leveled_up: bool = Field(..., description="Whether this XP gain caused a level up")
    levels_gained: int = Field(default=0, description="Number of levels gained (0 if no level up)")
