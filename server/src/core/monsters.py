"""
Monster definitions.

Monsters use animated sprite sheets (idle, walk, attack, death)
rather than the paperdoll system used by humanoids.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict

from .entities import EntityBehavior
from .skills import SkillType


@dataclass(frozen=True)
class MonsterDefinition:
    """
    Complete metadata for a monster template.
    
    Monsters are rendered using animated sprite sheets with
    pre-defined animations (idle, walk, attack, death). They have
    innate combat stats rather than equipment-derived stats.
    
    Attributes:
        display_name: Name shown in-game
        description: Flavor text description
        behavior: AI behavior pattern
        sprite_sheet_id: Identifier for the monster's sprite sheet
        width: Width in tiles (for larger monsters)
        height: Height in tiles (for larger monsters)
        level: Monster level
        xp_reward: Experience points awarded on kill
        aggro_radius: Tiles within which monster will chase players
        disengage_radius: Max tiles from spawn before returning
        respawn_time: Seconds before respawning after death
        skills: Innate skill levels
        
        Combat bonuses (innate, representing natural weapons/armor):
        attack_bonus, strength_bonus, ranged_attack_bonus, etc.
    """
    # Identity
    display_name: str
    description: str
    behavior: EntityBehavior
    
    # Visuals (sprite sheet system)
    sprite_sheet_id: str = "default_monster"
    width: int = 1   # Width in tiles
    height: int = 1  # Height in tiles
    scale: float = 1.0  # Visual scaling factor
    
    # Interaction
    is_attackable: bool = True  # Monsters are attackable by default
    
    # Combat behavior
    level: int = 1
    xp_reward: int = 0
    aggro_radius: int = 0  # Tiles to spot player (if AGGRESSIVE)
    disengage_radius: int = 0  # Max tiles from spawn before returning
    respawn_time: int = 30  # Seconds to respawn
    
    # Innate skills (base levels)
    skills: Dict[SkillType, int] = field(default_factory=dict)
    
    # Combat stats (Offensive Bonuses - natural weapons)
    attack_bonus: int = 0
    strength_bonus: int = 0
    ranged_attack_bonus: int = 0
    ranged_strength_bonus: int = 0
    magic_attack_bonus: int = 0
    magic_damage_bonus: int = 0

    # Combat stats (Defensive Bonuses - natural armor/hide)
    physical_defence_bonus: int = 0
    magic_defence_bonus: int = 0
    
    # Movement
    speed_bonus: int = 0
    
    @property
    def max_hp(self) -> int:
        """Calculate max HP from hitpoints skill level."""
        return self.skills.get(SkillType.HITPOINTS, 10)


class MonsterID(Enum):
    """
    All monsters in the game.

    Monsters use sprite sheet animations and have innate combat stats.
    """

    # =========================================================================
    # LOW LEVEL MONSTERS
    # =========================================================================
    GIANT_RAT = MonsterDefinition(
        display_name="Giant Rat",
        description="An overgrown vermin with sharp teeth.",
        behavior=EntityBehavior.AGGRESSIVE,
        sprite_sheet_id="giant_rat",
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
        },
    )
    
    # =========================================================================
    # BOSS MONSTERS
    # =========================================================================
    FOREST_BEAR = MonsterDefinition(
        display_name="Forest Bear",
        description="A massive brown bear with powerful claws.",
        behavior=EntityBehavior.AGGRESSIVE,
        sprite_sheet_id="bear",
        width=2,
        height=2,
        level=15,
        xp_reward=150,
        aggro_radius=7,
        disengage_radius=25,
        respawn_time=120,  # 2 minutes
        speed_bonus=-10,  # Large and slow
        skills={
            SkillType.ATTACK: 20,
            SkillType.STRENGTH: 25,
            SkillType.DEFENCE: 15,
            SkillType.HITPOINTS: 60,
        },
        attack_bonus=10,
        strength_bonus=15,
        physical_defence_bonus=5,
    )
    
    @classmethod
    def from_name(cls, name: str) -> Optional["MonsterID"]:
        """
        Get MonsterID by internal name (case-insensitive).
        
        Args:
            name: The monster name to look up (e.g., "goblin")
            
        Returns:
            The matching MonsterID or None if not found
        """
        name_upper = name.upper()
        for monster in cls:
            if monster.name == name_upper:
                return monster
        return None
