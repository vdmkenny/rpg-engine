"""
Humanoid NPC definitions.

Humanoid NPCs use the paperdoll sprite system with visible equipment
and appearance attributes (skin tone, hair style, etc.).
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List

from common.src.sprites import AppearanceData, AppearancePresets
from .entities import EntityBehavior
from .items import EquipmentSlot, ItemType
from .skills import SkillType


@dataclass(frozen=True)
class HumanoidDefinition:
    """
    Complete metadata for a humanoid NPC template.
    
    Humanoid NPCs are rendered using the paperdoll system with
    layered sprites for body, hair, and equipment. Their combat
    stats are derived from their equipped items (like players).
    
    Attributes:
        display_name: Name shown in-game
        description: Flavor text description
        behavior: AI behavior pattern
        appearance: Visual appearance (skin, hair, body type)
        equipped_items: Static equipment mapping (slot -> ItemType)
        is_attackable: Whether this NPC can be targeted in combat
        dialogue: List of dialogue lines for interaction
        shop_id: If set, NPC opens this shop on interaction
        level: NPC level (used for combat calculations)
        respawn_time: Seconds before respawning after death
    """
    # Identity
    display_name: str
    description: str
    behavior: EntityBehavior
    
    # Appearance (paperdoll rendering)
    appearance: AppearanceData = field(default_factory=AppearanceData)
    
    # Equipment (determines combat stats and visual appearance)
    # Maps EquipmentSlot -> ItemType for equipped items
    equipped_items: Dict[EquipmentSlot, ItemType] = field(default_factory=dict)
    
    # Interaction
    is_attackable: bool = True
    dialogue: Optional[List[str]] = None
    shop_id: Optional[str] = None
    
    # Stats
    level: int = 1
    respawn_time: int = 60  # Seconds to respawn
    
    # Innate skill levels (base levels before equipment bonuses)
    skills: Dict[SkillType, int] = field(default_factory=dict)

    # AI behavior settings (for AGGRESSIVE/GUARD behaviors)
    aggro_radius: int = 0  # Tiles within which entity will chase players
    disengage_radius: int = 0  # Max tiles from spawn before returning

    @property
    def max_hp(self) -> int:
        """Calculate max HP from hitpoints skill level."""
        return self.skills.get(SkillType.HITPOINTS, 10)
    
    def get_equipment_ids(self) -> Dict[str, Optional[int]]:
        """
        Get equipment as slot name -> item database ID mapping.
        
        Returns None for empty slots. Used for visibility payloads.
        """
        result = {}
        for slot in EquipmentSlot:
            item = self.equipped_items.get(slot)
            # ItemType enum members have integer values when synced to DB
            # For now, use the enum name as identifier
            result[slot.value] = item.name if item else None
        return result


class HumanoidID(Enum):
    """
    All humanoid NPCs in the game.

    Humanoid NPCs use paperdoll sprites with visible equipment.
    Their combat stats are derived from equipped items.
    """

    GOBLIN = HumanoidDefinition(
        display_name="Goblin",
        description="A small, green creature with a pointy nose.",
        behavior=EntityBehavior.AGGRESSIVE,
        appearance=AppearancePresets.GOBLIN,
        is_attackable=True,
        level=2,
        respawn_time=30,
        skills={
            SkillType.ATTACK: 5,
            SkillType.STRENGTH: 5,
            SkillType.DEFENCE: 5,
            SkillType.HITPOINTS: 10,
        },
        equipped_items={
            EquipmentSlot.WEAPON: ItemType.COPPER_DAGGER,
        },
        # AI behavior settings (required for AGGRESSIVE behavior)
        aggro_radius=5,
        disengage_radius=15,
    )

    VILLAGE_GUARD = HumanoidDefinition(
        display_name="Village Guard",
        description="Keeps the peace in the village.",
        behavior=EntityBehavior.GUARD,
        appearance=AppearancePresets.GUARD,
        is_attackable=True,  # You can try attacking them...
        level=20,
        respawn_time=120,
        skills={
            SkillType.ATTACK: 30,
            SkillType.STRENGTH: 30,
            SkillType.DEFENCE: 30,
            SkillType.HITPOINTS: 100,
        },
        equipped_items={
            EquipmentSlot.WEAPON: ItemType.IRON_SHORTSWORD,
            EquipmentSlot.BODY: ItemType.BRONZE_PLATEBODY,
            EquipmentSlot.LEGS: ItemType.BRONZE_PLATELEGS,
            EquipmentSlot.HEAD: ItemType.BRONZE_HELMET,
            EquipmentSlot.SHIELD: ItemType.BRONZE_SHIELD,
            EquipmentSlot.BOOTS: ItemType.LEATHER_BOOTS,
            EquipmentSlot.GLOVES: ItemType.LEATHER_GLOVES,
        },
        dialogue=["Move along, citizen.", "I'm watching you."],
        # Guards have moderate detection range
        aggro_radius=8,
        disengage_radius=20,
    )
    
    SHOPKEEPER_BOB = HumanoidDefinition(
        display_name="Bob",
        description="A friendly general store owner.",
        behavior=EntityBehavior.MERCHANT,
        appearance=AppearancePresets.SHOPKEEPER,
        is_attackable=False,
        level=1,
        skills={
            SkillType.HITPOINTS: 10,
        },
        dialogue=["Welcome to Bob's General Store!", "Finest wares in the land."],
        shop_id="general_store",
    )
    
    VILLAGE_ELDER = HumanoidDefinition(
        display_name="Village Elder",
        description="A wise old man standing by the fountain.",
        behavior=EntityBehavior.QUEST_GIVER,
        appearance=AppearancePresets.ELDER,
        is_attackable=False,
        level=5,
        skills={
            SkillType.HITPOINTS: 20,
        },
        dialogue=[
            "Greetings, young adventurer.",
            "Dark times are upon us...",
            "The goblins in the forest have become restless.",
        ],
    )
    
    @classmethod
    def from_name(cls, name: str) -> Optional["HumanoidID"]:
        """
        Get HumanoidID by internal name (case-insensitive).
        
        Args:
            name: The humanoid name to look up (e.g., "village_guard")
            
        Returns:
            The matching HumanoidID or None if not found
        """
        name_upper = name.upper()
        for humanoid in cls:
            if humanoid.name == name_upper:
                return humanoid
        return None
