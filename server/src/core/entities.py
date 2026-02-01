"""
Entity definitions and related enums.

This file acts as the source of truth for all non-player entities (NPCs, Monsters).
Similar to items.py, entities are defined as an enum with metadata.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List

from .skills import SkillType


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


@dataclass(frozen=True)
class EntityDefinition:
    """
    Complete metadata for an entity template.
    
    Includes identity, base stats, innate skills, and combat bonuses
    (representing 'natural' equipment like claws or hide).
    """
    # Identity
    display_name: str
    description: str
    behavior: EntityBehavior
    is_attackable: bool = True  # Can this entity be targeted for combat?
    
    # Visuals
    sprite_name: str = "default"
    width: int = 1   # Width in tiles
    height: int = 1  # Height in tiles
    scale: float = 1.0 # Visual scaling factor
    
    # Interaction
    # Simple list of strings for chained dialogue.
    # Advanced dialogue trees should be handled by a dedicated service/DB system later.
    dialogue: Optional[List[str]] = None
    shop_id: Optional[str] = None # If set, interaction opens this shop
    
    # Base Stats
    level: int = 1
    xp_reward: int = 0
    aggro_radius: int = 0  # Tiles to spot player (if AGGRESSIVE)
    disengage_radius: int = 0  # Max tiles from spawn before returning home
    respawn_time: int = 30 # Default seconds to respawn
    
    # Innate Skills (Base levels)
    # e.g., {SkillType.ATTACK: 10, SkillType.HITPOINTS: 20}
    skills: Dict[SkillType, int] = field(default_factory=dict)
    
    # Combat stats (Offensive Bonuses - akin to equipment)
    attack_bonus: int = 0
    strength_bonus: int = 0
    ranged_attack_bonus: int = 0
    ranged_strength_bonus: int = 0
    magic_attack_bonus: int = 0
    magic_damage_bonus: int = 0

    # Combat stats (Defensive Bonuses - akin to armor)
    physical_defence_bonus: int = 0
    magic_defence_bonus: int = 0
    
    # Other stats
    speed_bonus: int = 0
    
    @property
    def max_hp(self) -> int:
        """Calculate max HP from hitpoints skill level."""
        return self.skills.get(SkillType.HITPOINTS, 10)


class EntityID(Enum):
    """
    All entities in the game, defined as enum with metadata.
    
    These definitions are synced to the 'entities' table on server startup.
    """
    
    # =========================================================================
    # MONSTERS - Low Level
    # =========================================================================
    GOBLIN = EntityDefinition(
        display_name="Goblin",
        description="A small, green creature with a pointy nose.",
        behavior=EntityBehavior.AGGRESSIVE,
        sprite_name="goblin",
        level=2,
        xp_reward=15,
        aggro_radius=5,
        disengage_radius=15,
        speed_bonus=5,
        skills={
            SkillType.ATTACK: 5,
            SkillType.STRENGTH: 5,
            SkillType.DEFENCE: 5,
            SkillType.HITPOINTS: 10,
        },
        # Slight bonuses representing a small dagger
        attack_bonus=2,
        strength_bonus=1
    )
    
    GIANT_RAT = EntityDefinition(
        display_name="Giant Rat",
        description="An overgrown vermin.",
        behavior=EntityBehavior.AGGRESSIVE,
        sprite_name="giant_rat",
        level=1,
        xp_reward=10,
        aggro_radius=4,
        disengage_radius=12,
        speed_bonus=10,
        skills={
            SkillType.ATTACK: 3,
            SkillType.STRENGTH: 3,
            SkillType.DEFENCE: 2,
            SkillType.HITPOINTS: 8,
        }
    )
    
    # =========================================================================
    # MONSTERS - Bosses
    # =========================================================================
    FOREST_BEAR = EntityDefinition(
        display_name="Forest Bear",
        description="A massive brown bear.",
        behavior=EntityBehavior.AGGRESSIVE,
        sprite_name="bear",
        width=2,
        height=2,
        level=15,
        xp_reward=150,
        aggro_radius=7,
        disengage_radius=25,
        respawn_time=120, # 2 minutes
        speed_bonus=-10,
        skills={
            SkillType.ATTACK: 20,
            SkillType.STRENGTH: 25,
            SkillType.DEFENCE: 15,
            SkillType.HITPOINTS: 60,
        },
        attack_bonus=10,
        strength_bonus=15,
        physical_defence_bonus=5
    )
    
    # =========================================================================
    # NPCS
    # =========================================================================
    VILLAGE_GUARD = EntityDefinition(
        display_name="Village Guard",
        description="Keeps the peace.",
        behavior=EntityBehavior.GUARD,
        is_attackable=True, # You can try...
        sprite_name="guard",
        level=20,
        xp_reward=0,
        speed_bonus=0,
        skills={
            SkillType.ATTACK: 30,
            SkillType.STRENGTH: 30,
            SkillType.DEFENCE: 30,
            SkillType.HITPOINTS: 100,
        },
        # Equipped with Iron equivalent
        attack_bonus=10,
        strength_bonus=7,
        physical_defence_bonus=15,
        dialogue=["Move along, citizen.", "I'm watching you."]
    )
    
    SHOPKEEPER_BOB = EntityDefinition(
        display_name="Bob",
        description="A friendly general store owner.",
        behavior=EntityBehavior.MERCHANT,
        is_attackable=False,
        sprite_name="shopkeeper",
        level=1,
        speed_bonus=0,
        skills={
            SkillType.HITPOINTS: 10,
        },
        dialogue=["Welcome to Bob's General Store!", "Finest wares in the land."],
        shop_id="general_store"
    )
    
    VILLAGE_ELDER = EntityDefinition(
        display_name="Village Elder",
        description="A wise old man standing by the fountain.",
        behavior=EntityBehavior.QUEST_GIVER,
        is_attackable=False,
        sprite_name="elder",
        level=5,
        speed_bonus=0,
        skills={
             SkillType.HITPOINTS: 20
        },
        dialogue=[
            "Greetings, young adventurer.", 
            "Dark times are upon us...", 
            "The goblins in the forest have become restless."
        ]
    )

    @classmethod
    def from_name(cls, name: str) -> Optional["EntityID"]:
        """
        Get EntityID by internal name (case-insensitive).
        """
        name_upper = name.upper()
        for entity in cls:
            if entity.name == name_upper:
                return entity
        return None
