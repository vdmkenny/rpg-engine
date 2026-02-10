"""
Skill definitions and XP calculation formulas.

Skills are defined in Python as an enum with metadata.
XP multipliers are configured in config.yml for easy tuning.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional
from functools import lru_cache

from .config import settings


class SkillCategory(Enum):
    """Categories for organizing skills in the UI."""

    COMBAT = "combat"
    GATHERING = "gathering"
    CRAFTING = "crafting"


@dataclass(frozen=True)
class SkillDefinition:
    """Metadata for a skill definition."""

    name: str
    category: SkillCategory
    description: str


class SkillType(Enum):
    """
    All available skills in the game.

    Each skill has a name, category, and description.
    XP multipliers are configured separately in config.yml.
    """

    # Combat skills
    ATTACK = SkillDefinition("Attack", SkillCategory.COMBAT, "Melee accuracy")
    STRENGTH = SkillDefinition("Strength", SkillCategory.COMBAT, "Melee damage")
    DEFENCE = SkillDefinition("Defence", SkillCategory.COMBAT, "Damage reduction")
    RANGED = SkillDefinition("Ranged", SkillCategory.COMBAT, "Ranged combat")
    MAGIC = SkillDefinition("Magic", SkillCategory.COMBAT, "Magical combat")
    HITPOINTS = SkillDefinition("Hitpoints", SkillCategory.COMBAT, "Health points")

    # Gathering skills
    MINING = SkillDefinition(
        "Mining", SkillCategory.GATHERING, "Extract ores from rocks"
    )
    FISHING = SkillDefinition(
        "Fishing", SkillCategory.GATHERING, "Catch fish from water"
    )
    WOODCUTTING = SkillDefinition(
        "Woodcutting", SkillCategory.GATHERING, "Chop down trees"
    )

    # Crafting skills
    COOKING = SkillDefinition(
        "Cooking", SkillCategory.CRAFTING, "Prepare food for consumption"
    )
    CRAFTING = SkillDefinition(
        "Crafting", SkillCategory.CRAFTING, "Create items from materials"
    )

    @classmethod
    def from_name(cls, name: str) -> Optional["SkillType"]:
        """
        Get SkillType by name (case-insensitive).

        Args:
            name: The skill name to look up

        Returns:
            The matching SkillType or None if not found
        """
        name_lower = name.lower()
        for skill in cls:
            if skill.name.lower() == name_lower:
                return skill
        return None

    @classmethod
    def all_skill_names(cls) -> list[str]:
        """Get lowercase names of all skills."""
        return [skill.name.lower() for skill in cls]


# Default max level constant
MAX_LEVEL: int = settings.SKILL_MAX_LEVEL

# Hitpoints starts at level 10
HITPOINTS_START_LEVEL: int = 10


@lru_cache(maxsize=256)
def _base_xp_table(max_level: int = MAX_LEVEL) -> tuple[int, ...]:
    """
    Pre-compute the base XP table using standard formula.

    The formula for total XP at level L is:
    XP(L) = floor(sum(i=1 to L-1) of floor(i + 300 * 2^(i/7)) / 4)

    Returns:
        Tuple of XP values indexed by level (index 0 = level 1 = 0 XP)
    """
    xp_table = [0]  # Level 1 requires 0 XP
    total_xp = 0

    for level in range(1, max_level):
        # XP needed to go from level to level+1
        level_xp = int((level + 300 * (2 ** (level / 7))) / 4)
        total_xp += level_xp
        xp_table.append(total_xp)

    return tuple(xp_table)


def base_xp_for_level(level: int) -> int:
    """
    Calculate base XP required for a given level using standard formula.

    Args:
        level: The target level (1-99)

    Returns:
        Total XP required to reach that level (before multiplier)
    """
    if level < 1:
        return 0
    if level > MAX_LEVEL:
        level = MAX_LEVEL

    xp_table = _base_xp_table(MAX_LEVEL)
    return xp_table[level - 1]


def xp_for_level(level: int, xp_multiplier: float = 1.0) -> int:
    """
    Calculate total XP required for a given level with multiplier.

    Args:
        level: The target level (1-99)
        xp_multiplier: Scaling factor (1.0 = ~13M XP to 99)

    Returns:
        Total XP required to reach that level
    """
    return int(base_xp_for_level(level) * xp_multiplier)


def level_for_xp(xp: int, xp_multiplier: float = 1.0) -> int:
    """
    Calculate current level from XP amount.

    Args:
        xp: Current experience points
        xp_multiplier: Scaling factor for the skill

    Returns:
        Current level (1-99)
    """
    if xp <= 0:
        return 1

    xp_table = _base_xp_table(MAX_LEVEL)

    # Binary search for the level
    low, high = 1, MAX_LEVEL
    while low < high:
        mid = (low + high + 1) // 2
        required_xp = int(xp_table[mid - 1] * xp_multiplier)
        if xp >= required_xp:
            low = mid
        else:
            high = mid - 1

    return low


def xp_to_next_level(current_xp: int, xp_multiplier: float = 1.0) -> int:
    """
    Calculate XP remaining until next level.

    Args:
        current_xp: Current experience points
        xp_multiplier: Scaling factor for the skill

    Returns:
        XP needed to reach next level, or 0 if at max level
    """
    current_level = level_for_xp(current_xp, xp_multiplier)
    if current_level >= MAX_LEVEL:
        return 0

    next_level_xp = xp_for_level(current_level + 1, xp_multiplier)
    return max(0, next_level_xp - current_xp)


def xp_for_current_level(current_xp: int, xp_multiplier: float = 1.0) -> int:
    """
    Calculate the XP threshold for the current level.

    Args:
        current_xp: Current experience points
        xp_multiplier: Scaling factor for the skill

    Returns:
        XP required to have reached current level
    """
    current_level = level_for_xp(current_xp, xp_multiplier)
    return xp_for_level(current_level, xp_multiplier)


def progress_to_next_level(current_xp: int, xp_multiplier: float = 1.0) -> float:
    """
    Calculate progress percentage to next level.

    Args:
        current_xp: Current experience points
        xp_multiplier: Scaling factor for the skill

    Returns:
        Progress as percentage (0.0 - 100.0)
    """
    current_level = level_for_xp(current_xp, xp_multiplier)
    if current_level >= MAX_LEVEL:
        return 100.0

    current_level_xp = xp_for_level(current_level, xp_multiplier)
    next_level_xp = xp_for_level(current_level + 1, xp_multiplier)
    level_xp_range = next_level_xp - current_level_xp

    if level_xp_range <= 0:
        return 100.0

    xp_into_level = current_xp - current_level_xp
    return min(100.0, max(0.0, (xp_into_level / level_xp_range) * 100.0))


def get_skill_xp_multiplier(skill: SkillType) -> float:
    """
    Get XP multiplier for a skill from config.

    Args:
        skill: The skill to get multiplier for

    Returns:
        XP multiplier from config, or default if not specified
    """
    from .config import settings

    return settings.SKILL_XP_MULTIPLIERS.get(
        skill.name.lower(), settings.SKILL_DEFAULT_XP_MULTIPLIER
    )
