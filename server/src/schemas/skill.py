"""
Pydantic schemas for skill-related API responses.
"""

from pydantic import BaseModel, Field


class SkillInfo(BaseModel):
    """Detailed information about a single skill for a player."""

    name: str = Field(..., description="Display name of the skill")
    category: str = Field(..., description="Skill category (combat, gathering, crafting)")
    description: str = Field(..., description="Description of what the skill does")
    current_level: int = Field(..., ge=1, le=99, description="Current skill level")
    experience: int = Field(..., ge=0, description="Total experience points")
    xp_for_current_level: int = Field(
        ..., ge=0, description="XP required to reach current level"
    )
    xp_for_next_level: int = Field(
        ..., ge=0, description="XP required to reach next level"
    )
    xp_to_next_level: int = Field(
        ..., ge=0, description="XP remaining until next level"
    )
    xp_multiplier: float = Field(
        ..., gt=0, description="XP scaling multiplier for this skill"
    )
    progress_percent: float = Field(
        ..., ge=0, le=100, description="Progress to next level as percentage"
    )
    max_level: int = Field(..., description="Maximum achievable level")

    model_config = {"from_attributes": True}


class PlayerSkillsResponse(BaseModel):
    """Response containing all skills for a player."""

    skills: list[SkillInfo] = Field(..., description="List of all player skills")
    total_level: int = Field(..., ge=0, description="Sum of all skill levels")

    model_config = {"from_attributes": True}


class LevelUpNotification(BaseModel):
    """Notification sent when a player levels up a skill."""

    skill_name: str = Field(..., description="Name of the skill that leveled up")
    previous_level: int = Field(..., ge=1, description="Level before the XP gain")
    new_level: int = Field(..., ge=1, description="New level after XP gain")
    levels_gained: int = Field(..., ge=1, description="Number of levels gained")
    current_xp: int = Field(..., ge=0, description="Current total XP in the skill")
    xp_to_next_level: int = Field(
        ..., ge=0, description="XP remaining until next level"
    )

    model_config = {"from_attributes": True}


class XPGainNotification(BaseModel):
    """Notification sent when a player gains experience."""

    skill_name: str = Field(..., description="Name of the skill")
    xp_gained: int = Field(..., gt=0, description="Amount of XP gained")
    current_xp: int = Field(..., ge=0, description="Current total XP in the skill")
    current_level: int = Field(..., ge=1, description="Current level")
    xp_to_next_level: int = Field(
        ..., ge=0, description="XP remaining until next level"
    )
    leveled_up: bool = Field(..., description="Whether this XP gain caused a level up")

    model_config = {"from_attributes": True}
