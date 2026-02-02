"""
Entity base enums and utilities.

Contains shared enums for entity behavior and state that are used by
both humanoid NPCs and monsters.
"""

from enum import Enum
from typing import Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .humanoids import HumanoidID, HumanoidDefinition
    from .monsters import MonsterID, MonsterDefinition


class EntityBehavior(Enum):
    """
    Defines the AI behavior pattern for an entity.
    """
    PASSIVE = "passive"          # Wanders, flees if attacked
    NEUTRAL = "neutral"          # Wanders, attacks back if provoked
    AGGRESSIVE = "aggressive"    # Chases and attacks players within range
    GUARD = "guard"              # Stationary/Patrols, attacks AGGRESSIVE mobs or PKers
    MERCHANT = "merchant"        # Stationary, offers trade
    QUEST_GIVER = "quest_giver"  # Stationary, offers dialogue


class EntityState(str, Enum):
    """
    Runtime state of an entity instance.
    """
    IDLE = "idle"              # Default state, not doing anything
    WANDER = "wander"          # Roaming around spawn area
    COMBAT = "combat"          # Engaged in combat
    RETURNING = "returning"    # Returning to spawn point after disengaging
    DYING = "dying"            # Playing death animation
    DEAD = "dead"              # Fully dead, awaiting respawn


class EntityType(str, Enum):
    """
    Type of entity for protocol messages and visibility system.
    """
    PLAYER = "player"
    HUMANOID_NPC = "humanoid_npc"
    MONSTER = "monster"


def get_entity_by_name(
    name: str,
) -> Optional[Union["HumanoidID", "MonsterID"]]:
    """
    Look up an entity (humanoid or monster) by name.
    
    Searches both HumanoidID and MonsterID enums for a match.
    
    Args:
        name: Entity name (case-insensitive, e.g., "GOBLIN", "VILLAGE_GUARD")
        
    Returns:
        The matching HumanoidID or MonsterID, or None if not found
    """
    from .humanoids import HumanoidID
    from .monsters import MonsterID
    
    # Try humanoid first
    humanoid = HumanoidID.from_name(name)
    if humanoid:
        return humanoid
    
    # Try monster
    monster = MonsterID.from_name(name)
    if monster:
        return monster
    
    return None


def is_humanoid(name: str) -> bool:
    """Check if entity name refers to a humanoid NPC."""
    from .humanoids import HumanoidID
    return HumanoidID.from_name(name) is not None


def is_monster(name: str) -> bool:
    """Check if entity name refers to a monster."""
    from .monsters import MonsterID
    return MonsterID.from_name(name) is not None
