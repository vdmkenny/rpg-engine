"""
Item definitions and related enums.

Items are defined in Python as an enum with metadata.
Configuration for inventory, equipment, and ground items is in config.yml.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional

# Import enums from schemas to ensure single source of truth with modern str, Enum pattern
from server.src.schemas.item import EquipmentSlot, ItemRarity, ItemCategory


class AmmoType(Enum):
    """Types of ammunition for ranged combat."""

    ARROWS = "arrows"
    BOLTS = "bolts"
    THROWN = "thrown"
    RUNES = "runes"


class RequiredSkill(Enum):
    """Skills that items can require to equip or use."""

    ATTACK = "attack"  # Melee weapons
    DEFENCE = "defence"  # Armor
    RANGED = "ranged"  # Ranged weapons/armor
    MAGIC = "magic"  # Magic weapons/armor
    MINING = "mining"  # Pickaxes
    WOODCUTTING = "woodcutting"  # Axes
    FISHING = "fishing"  # Fishing rods


class InventorySortType(Enum):
    """
    Sort types for inventory organization.

    All sorts compact items to the front (slots 0-N, empty slots at end).
    Secondary sort is by rarity (descending), then by name (alphabetical).
    """

    BY_CATEGORY = "category"  # currency -> equipment -> ammo -> consumables -> materials -> quest -> normal
    BY_RARITY = "rarity"  # legendary -> poor (descending)
    BY_VALUE = "value"  # highest value first
    BY_NAME = "name"  # alphabetical
    STACK_MERGE = "stack_merge"  # merge split stacks only, no reordering
    BY_EQUIPMENT_SLOT = "equipment_slot"  # equipable items first, ordered by slot


# Category sort order (lower = earlier in sorted inventory)
CATEGORY_SORT_ORDER = {
    ItemCategory.CURRENCY: 0,
    ItemCategory.WEAPON: 1,
    ItemCategory.ARMOR: 2,
    ItemCategory.TOOL: 3,
    ItemCategory.AMMUNITION: 4,
    ItemCategory.CONSUMABLE: 5,
    ItemCategory.MATERIAL: 6,
    ItemCategory.QUEST: 7,
    ItemCategory.NORMAL: 8,
}

# Rarity sort order (lower = rarer = earlier in sorted inventory)
RARITY_SORT_ORDER = {
    ItemRarity.LEGENDARY: 0,
    ItemRarity.EPIC: 1,
    ItemRarity.RARE: 2,
    ItemRarity.UNCOMMON: 3,
    ItemRarity.COMMON: 4,
    ItemRarity.POOR: 5,
}

# Equipment slot sort order (for BY_EQUIPMENT_SLOT sorting)
EQUIPMENT_SLOT_SORT_ORDER = {
    EquipmentSlot.HEAD: 0,
    EquipmentSlot.CAPE: 1,
    EquipmentSlot.AMULET: 2,
    EquipmentSlot.WEAPON: 3,
    EquipmentSlot.BODY: 4,
    EquipmentSlot.SHIELD: 5,
    EquipmentSlot.LEGS: 6,
    EquipmentSlot.GLOVES: 7,
    EquipmentSlot.BOOTS: 8,
    EquipmentSlot.RING: 9,
    EquipmentSlot.AMMO: 10,
}


# Stack size constants (base-2)
STACK_SIZE_SINGLE = 1
STACK_SIZE_MATERIALS = 64  # 2^6
STACK_SIZE_CONSUMABLES = 64  # 2^6
STACK_SIZE_AMMUNITION = 8192  # 2^13
STACK_SIZE_CURRENCY = 2147483647  # int max


@dataclass(frozen=True)
class ItemDefinition:
    """
    Complete metadata for an item definition.

    All stat bonuses default to 0 and can be negative for balance tradeoffs.
    For example, heavy metal armor may have negative magic attack bonus.
    
    Sprite IDs:
        icon_sprite_id: Sprite for inventory/ground display (all items should have this)
        equipped_sprite_id: Sprite layer for paperdoll rendering (equipable items only)
    """

    display_name: str
    description: str
    category: ItemCategory
    rarity: ItemRarity = ItemRarity.COMMON
    equipment_slot: Optional[EquipmentSlot] = None
    max_stack_size: int = 1  # 1 = not stackable, >1 = stackable up to this amount
    is_two_handed: bool = False
    max_durability: Optional[int] = None
    is_indestructible: bool = False
    required_skill: Optional[RequiredSkill] = None
    required_level: int = 1
    ammo_type: Optional[AmmoType] = None
    value: int = 0
    is_tradeable: bool = True
    
    # Sprite identifiers for rendering
    icon_sprite_id: Optional[str] = None  # Inventory/ground icon sprite
    equipped_sprite_id: Optional[str] = None  # Paperdoll layer sprite (equipable items only)

    # Combat stats (offensive)
    attack_bonus: int = 0
    strength_bonus: int = 0
    ranged_attack_bonus: int = 0
    ranged_strength_bonus: int = 0
    magic_attack_bonus: int = 0
    magic_damage_bonus: int = 0

    # Combat stats (defensive)
    physical_defence_bonus: int = 0
    magic_defence_bonus: int = 0

    # Other stats
    health_bonus: int = 0
    speed_bonus: int = 0
    attack_speed: float = 3.0  # Seconds between attacks (default: standard speed)

    # Gathering stats
    mining_bonus: int = 0
    woodcutting_bonus: int = 0
    fishing_bonus: int = 0

    @property
    def is_stackable(self) -> bool:
        """Returns True if item can stack (max_stack_size > 1)."""
        return self.max_stack_size > 1


class ItemType(Enum):
    """
    All items in the game, defined as enum with metadata.

    Each item has complete stats and properties defined in its ItemDefinition.
    Items are synced to the database on server startup.
    """

    # =========================================================================
    # WEAPONS - Melee (Wood Tier - Level 1, Poor rarity)
    # =========================================================================
    WOODEN_CLUB = ItemDefinition(
        display_name="Wooden Club",
        description="A crude wooden club. Better than nothing.",
        category=ItemCategory.WEAPON,
        rarity=ItemRarity.POOR,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=200,
        required_skill=RequiredSkill.ATTACK,
        required_level=1,
        value=5,
        attack_bonus=1,
        strength_bonus=1,
        attack_speed=3.0,
        icon_sprite_id="icon_wooden_club",
        equipped_sprite_id="equip_wooden_club",
    )

    # =========================================================================
    # WEAPONS - Melee (Copper Tier - Level 1, Common rarity)
    # Attack: 3, Strength: 2, Durability: 350, Value: 12
    # =========================================================================
    COPPER_DAGGER = ItemDefinition(
        display_name="Copper Dagger",
        description="A small copper dagger. Fast but weak.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=350,
        required_skill=RequiredSkill.ATTACK,
        required_level=1,
        value=8,
        attack_bonus=2,
        strength_bonus=1,
        attack_speed=2.4,
        icon_sprite_id="icon_copper_dagger",
        equipped_sprite_id="equip_copper_dagger",
    )

    COPPER_SHORTSWORD = ItemDefinition(
        display_name="Copper Shortsword",
        description="A basic copper shortsword.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=350,
        required_skill=RequiredSkill.ATTACK,
        required_level=1,
        value=12,
        attack_bonus=2,
        strength_bonus=2,
        attack_speed=3.0,
        icon_sprite_id="icon_copper_shortsword",
        equipped_sprite_id="equip_copper_shortsword",
    )

    COPPER_LONGSWORD = ItemDefinition(
        display_name="Copper Longsword",
        description="A copper longsword with decent reach.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=350,
        required_skill=RequiredSkill.ATTACK,
        required_level=1,
        value=15,
        attack_bonus=3,
        strength_bonus=2,
        attack_speed=3.0,
        icon_sprite_id="icon_copper_longsword",
        equipped_sprite_id="equip_copper_longsword",
    )

    COPPER_MACE = ItemDefinition(
        display_name="Copper Mace",
        description="A copper mace. Good for crushing.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=350,
        required_skill=RequiredSkill.ATTACK,
        required_level=1,
        value=12,
        attack_bonus=2,
        strength_bonus=3,
        attack_speed=3.0,
        icon_sprite_id="icon_copper_mace",
        equipped_sprite_id="equip_copper_mace",
    )

    COPPER_BATTLEAXE = ItemDefinition(
        display_name="Copper Battleaxe",
        description="A heavy copper battleaxe.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=350,
        required_skill=RequiredSkill.ATTACK,
        required_level=1,
        value=18,
        attack_bonus=3,
        strength_bonus=4,
        attack_speed=3.6,
        icon_sprite_id="icon_copper_battleaxe",
        equipped_sprite_id="equip_copper_battleaxe",
    )

    COPPER_2H_SWORD = ItemDefinition(
        display_name="Copper Zweihander",
        description="A large copper sword requiring two hands.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        is_two_handed=True,
        max_durability=400,
        required_skill=RequiredSkill.ATTACK,
        required_level=1,
        value=24,
        attack_bonus=4,
        strength_bonus=3,
        attack_speed=4.2,
        icon_sprite_id="icon_copper_2h_sword",
        equipped_sprite_id="equip_copper_2h_sword",
    )

    # =========================================================================
    # WEAPONS - Melee (Bronze Tier - Level 5, Common rarity)
    # Attack: 5, Strength: 4, Durability: 500, Value: 20
    # =========================================================================
    BRONZE_DAGGER = ItemDefinition(
        display_name="Bronze Dagger",
        description="A small bronze dagger. Fast but weak.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=500,
        required_skill=RequiredSkill.ATTACK,
        required_level=5,
        value=14,
        attack_bonus=3,
        strength_bonus=2,
        attack_speed=2.4,
        icon_sprite_id="icon_bronze_dagger",
        equipped_sprite_id="equip_bronze_dagger",
    )

    BRONZE_SHORTSWORD = ItemDefinition(
        display_name="Bronze Shortsword",
        description="A basic bronze shortsword.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=500,
        required_skill=RequiredSkill.ATTACK,
        required_level=5,
        value=20,
        attack_bonus=4,
        strength_bonus=3,
        attack_speed=3.0,
        icon_sprite_id="icon_bronze_shortsword",
        equipped_sprite_id="equip_bronze_shortsword",
    )

    BRONZE_LONGSWORD = ItemDefinition(
        display_name="Bronze Longsword",
        description="A bronze longsword with decent reach.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=500,
        required_skill=RequiredSkill.ATTACK,
        required_level=5,
        value=25,
        attack_bonus=5,
        strength_bonus=4,
        attack_speed=3.0,
        icon_sprite_id="icon_bronze_longsword",
        equipped_sprite_id="equip_bronze_longsword",
    )

    BRONZE_MACE = ItemDefinition(
        display_name="Bronze Mace",
        description="A bronze mace. Good for crushing.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=500,
        required_skill=RequiredSkill.ATTACK,
        required_level=5,
        value=20,
        attack_bonus=4,
        strength_bonus=5,
        attack_speed=3.0,
        icon_sprite_id="icon_bronze_mace",
        equipped_sprite_id="equip_bronze_mace",
    )

    BRONZE_BATTLEAXE = ItemDefinition(
        display_name="Bronze Battleaxe",
        description="A heavy bronze battleaxe.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=500,
        required_skill=RequiredSkill.ATTACK,
        required_level=5,
        value=30,
        attack_bonus=5,
        strength_bonus=6,
        attack_speed=3.6,
        icon_sprite_id="icon_bronze_battleaxe",
        equipped_sprite_id="equip_bronze_battleaxe",
    )

    BRONZE_2H_SWORD = ItemDefinition(
        display_name="Bronze Zweihander",
        description="A large bronze sword requiring two hands.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        is_two_handed=True,
        max_durability=600,
        required_skill=RequiredSkill.ATTACK,
        required_level=5,
        value=40,
        attack_bonus=7,
        strength_bonus=6,
        attack_speed=4.2,
        icon_sprite_id="icon_bronze_2h_sword",
        equipped_sprite_id="equip_bronze_2h_sword",
    )

    # =========================================================================
    # WEAPONS - Melee (Iron Tier - Level 10, Common rarity)
    # Attack: 8, Strength: 6, Durability: 750, Value: 50
    # =========================================================================
    IRON_DAGGER = ItemDefinition(
        display_name="Iron Dagger",
        description="A small iron dagger. Fast but weak.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=750,
        required_skill=RequiredSkill.ATTACK,
        required_level=10,
        value=35,
        attack_bonus=5,
        strength_bonus=3,
        attack_speed=2.4,
        icon_sprite_id="icon_iron_dagger",
        equipped_sprite_id="equip_iron_dagger",
    )

    IRON_SHORTSWORD = ItemDefinition(
        display_name="Iron Shortsword",
        description="A sturdy iron shortsword.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=750,
        required_skill=RequiredSkill.ATTACK,
        required_level=10,
        value=50,
        attack_bonus=6,
        strength_bonus=5,
        attack_speed=3.0,
        icon_sprite_id="icon_iron_shortsword",
        equipped_sprite_id="equip_iron_shortsword",
    )

    IRON_LONGSWORD = ItemDefinition(
        display_name="Iron Longsword",
        description="An iron longsword with good reach.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=750,
        required_skill=RequiredSkill.ATTACK,
        required_level=10,
        value=60,
        attack_bonus=8,
        strength_bonus=6,
        attack_speed=3.0,
        icon_sprite_id="icon_iron_longsword",
        equipped_sprite_id="equip_iron_longsword",
    )

    IRON_MACE = ItemDefinition(
        display_name="Iron Mace",
        description="An iron mace. Effective at crushing.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=750,
        required_skill=RequiredSkill.ATTACK,
        required_level=10,
        value=50,
        attack_bonus=6,
        strength_bonus=7,
        attack_speed=3.0,
        icon_sprite_id="icon_iron_mace",
        equipped_sprite_id="equip_iron_mace",
    )

    IRON_BATTLEAXE = ItemDefinition(
        display_name="Iron Battleaxe",
        description="A heavy iron battleaxe.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=750,
        required_skill=RequiredSkill.ATTACK,
        required_level=10,
        value=75,
        attack_bonus=8,
        strength_bonus=9,
        attack_speed=3.6,
        icon_sprite_id="icon_iron_battleaxe",
        equipped_sprite_id="equip_iron_battleaxe",
    )

    IRON_2H_SWORD = ItemDefinition(
        display_name="Iron Zweihander",
        description="A large iron sword requiring two hands.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        is_two_handed=True,
        max_durability=900,
        required_skill=RequiredSkill.ATTACK,
        required_level=10,
        value=100,
        attack_bonus=11,
        strength_bonus=9,
        attack_speed=4.2,
        icon_sprite_id="icon_iron_2h_sword",
        equipped_sprite_id="equip_iron_2h_sword",
    )

    # =========================================================================
    # WEAPONS - Melee (Steel Tier - Level 20, Uncommon rarity)
    # Attack: 12, Strength: 9, Durability: 1000, Value: 100
    # =========================================================================
    STEEL_DAGGER = ItemDefinition(
        display_name="Steel Dagger",
        description="A sharp steel dagger. Fast and deadly.",
        category=ItemCategory.WEAPON,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=1000,
        required_skill=RequiredSkill.ATTACK,
        required_level=20,
        value=70,
        attack_bonus=7,
        strength_bonus=5,
        attack_speed=2.4,
        icon_sprite_id="icon_steel_dagger",
        equipped_sprite_id="equip_steel_dagger",
    )

    STEEL_SHORTSWORD = ItemDefinition(
        display_name="Steel Shortsword",
        description="A well-crafted steel shortsword.",
        category=ItemCategory.WEAPON,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=1000,
        required_skill=RequiredSkill.ATTACK,
        required_level=20,
        value=100,
        attack_bonus=9,
        strength_bonus=7,
        attack_speed=3.0,
        icon_sprite_id="icon_steel_shortsword",
        equipped_sprite_id="equip_steel_shortsword",
    )

    STEEL_LONGSWORD = ItemDefinition(
        display_name="Steel Longsword",
        description="A fine steel longsword with excellent reach.",
        category=ItemCategory.WEAPON,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=1000,
        required_skill=RequiredSkill.ATTACK,
        required_level=20,
        value=120,
        attack_bonus=12,
        strength_bonus=9,
        attack_speed=3.0,
        icon_sprite_id="icon_steel_longsword",
        equipped_sprite_id="equip_steel_longsword",
    )

    STEEL_MACE = ItemDefinition(
        display_name="Steel Mace",
        description="A steel mace. Devastating crushing power.",
        category=ItemCategory.WEAPON,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=1000,
        required_skill=RequiredSkill.ATTACK,
        required_level=20,
        value=100,
        attack_bonus=9,
        strength_bonus=11,
        attack_speed=3.0,
        icon_sprite_id="icon_steel_mace",
        equipped_sprite_id="equip_steel_mace",
    )

    STEEL_BATTLEAXE = ItemDefinition(
        display_name="Steel Battleaxe",
        description="A massive steel battleaxe.",
        category=ItemCategory.WEAPON,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=1000,
        required_skill=RequiredSkill.ATTACK,
        required_level=20,
        value=150,
        attack_bonus=12,
        strength_bonus=14,
        attack_speed=3.6,
        icon_sprite_id="icon_steel_battleaxe",
        equipped_sprite_id="equip_steel_battleaxe",
    )

    STEEL_2H_SWORD = ItemDefinition(
        display_name="Steel Zweihander",
        description="A massive steel sword requiring two hands.",
        category=ItemCategory.WEAPON,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.WEAPON,
        is_two_handed=True,
        max_durability=1200,
        required_skill=RequiredSkill.ATTACK,
        required_level=20,
        value=200,
        attack_bonus=17,
        strength_bonus=14,
        attack_speed=4.2,
        icon_sprite_id="icon_steel_2h_sword",
        equipped_sprite_id="equip_steel_2h_sword",
    )

    # =========================================================================
    # WEAPONS - Ranged
    # =========================================================================
    SHORTBOW = ItemDefinition(
        display_name="Shortbow",
        description="A basic wooden shortbow.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        is_two_handed=True,
        max_durability=500,
        required_skill=RequiredSkill.RANGED,
        required_level=1,
        value=25,
        ranged_attack_bonus=4,
        ranged_strength_bonus=3,
        attack_speed=2.4,
        icon_sprite_id="icon_shortbow",
        equipped_sprite_id="equip_shortbow",
    )

    OAK_SHORTBOW = ItemDefinition(
        display_name="Oak Shortbow",
        description="A shortbow made from oak wood.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        is_two_handed=True,
        max_durability=650,
        required_skill=RequiredSkill.RANGED,
        required_level=10,
        value=60,
        ranged_attack_bonus=10,
        ranged_strength_bonus=6,
        attack_speed=2.4,
        icon_sprite_id="icon_oak_shortbow",
        equipped_sprite_id="equip_oak_shortbow",
    )

    # =========================================================================
    # ARMOR - Wood (Level 1, Poor rarity)
    # =========================================================================
    WOODEN_SHIELD = ItemDefinition(
        display_name="Wooden Shield",
        description="A crude wooden shield. Offers minimal protection.",
        category=ItemCategory.ARMOR,
        rarity=ItemRarity.POOR,
        equipment_slot=EquipmentSlot.SHIELD,
        max_durability=150,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=5,
        physical_defence_bonus=1,
        magic_defence_bonus=0,
        icon_sprite_id="icon_wooden_shield",
        equipped_sprite_id="equip_wooden_shield",
    )

    # =========================================================================
    # ARMOR - Copper (Level 1, Common rarity)
    # Defence: 2, Durability: 300, Value: ~10
    # =========================================================================
    COPPER_HELMET = ItemDefinition(
        display_name="Copper Helmet",
        description="Basic head protection made of copper.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.HEAD,
        max_durability=300,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=10,
        physical_defence_bonus=2,
        magic_defence_bonus=0,
        magic_attack_bonus=-1,  # Metal interferes with magic
        icon_sprite_id="icon_copper_helmet",
        equipped_sprite_id="equip_copper_helmet",
    )

    COPPER_PLATEBODY = ItemDefinition(
        display_name="Copper Platebody",
        description="Heavy copper chest armor.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.BODY,
        max_durability=450,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=28,
        physical_defence_bonus=5,
        magic_defence_bonus=1,
        health_bonus=3,
        magic_attack_bonus=-2,  # Heavy metal reduces magic ability
        speed_bonus=-1,  # Heavy armor slows movement
        icon_sprite_id="icon_copper_platebody",
        equipped_sprite_id="equip_copper_platebody",
    )

    COPPER_PLATELEGS = ItemDefinition(
        display_name="Copper Platelegs",
        description="Heavy copper leg armor.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.LEGS,
        max_durability=400,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=20,
        physical_defence_bonus=3,
        magic_defence_bonus=0,
        magic_attack_bonus=-1,  # Metal interferes with magic
        icon_sprite_id="icon_copper_platelegs",
        equipped_sprite_id="equip_copper_platelegs",
    )

    COPPER_SHIELD = ItemDefinition(
        display_name="Copper Shield",
        description="A basic copper shield.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.SHIELD,
        max_durability=350,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=18,
        physical_defence_bonus=3,
        magic_defence_bonus=0,
        magic_attack_bonus=-1,  # Metal interferes with magic
        icon_sprite_id="icon_copper_shield",
        equipped_sprite_id="equip_copper_shield",
    )

    # =========================================================================
    # ARMOR - Bronze (Level 5, Common rarity)
    # Defence: 4, Durability: 500, Value: ~25
    # =========================================================================
    BRONZE_HELMET = ItemDefinition(
        display_name="Bronze Helmet",
        description="Basic head protection made of bronze.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.HEAD,
        max_durability=400,
        required_skill=RequiredSkill.DEFENCE,
        required_level=5,
        value=15,
        physical_defence_bonus=3,
        magic_defence_bonus=1,
        magic_attack_bonus=-1,  # Metal interferes with magic
        icon_sprite_id="icon_bronze_helmet",
        equipped_sprite_id="equip_bronze_helmet",
    )

    BRONZE_PLATEBODY = ItemDefinition(
        display_name="Bronze Platebody",
        description="Heavy bronze chest armor.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.BODY,
        max_durability=600,
        required_skill=RequiredSkill.DEFENCE,
        required_level=5,
        value=40,
        physical_defence_bonus=8,
        magic_defence_bonus=2,
        health_bonus=5,
        magic_attack_bonus=-3,  # Heavy metal reduces magic ability
        speed_bonus=-1,  # Heavy armor slows movement
        icon_sprite_id="icon_bronze_platebody",
        equipped_sprite_id="equip_bronze_platebody",
    )

    BRONZE_PLATELEGS = ItemDefinition(
        display_name="Bronze Platelegs",
        description="Heavy bronze leg armor.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.LEGS,
        max_durability=500,
        required_skill=RequiredSkill.DEFENCE,
        required_level=5,
        value=30,
        physical_defence_bonus=5,
        magic_defence_bonus=1,
        magic_attack_bonus=-2,  # Metal interferes with magic
        icon_sprite_id="icon_bronze_platelegs",
        equipped_sprite_id="equip_bronze_platelegs",
    )

    BRONZE_SHIELD = ItemDefinition(
        display_name="Bronze Shield",
        description="A basic bronze shield.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.SHIELD,
        max_durability=450,
        required_skill=RequiredSkill.DEFENCE,
        required_level=5,
        value=25,
        physical_defence_bonus=4,
        magic_defence_bonus=1,
        magic_attack_bonus=-2,  # Metal interferes with magic
        icon_sprite_id="icon_bronze_shield",
        equipped_sprite_id="equip_bronze_shield",
    )

    # =========================================================================
    # ARMOR - Iron (Level 10, Common rarity)
    # Defence: 6, Durability: 700, Value: ~50
    # =========================================================================
    IRON_HELMET = ItemDefinition(
        display_name="Iron Helmet",
        description="Sturdy head protection made of iron.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.HEAD,
        max_durability=600,
        required_skill=RequiredSkill.DEFENCE,
        required_level=10,
        value=40,
        physical_defence_bonus=5,
        magic_defence_bonus=1,
        magic_attack_bonus=-2,  # Metal interferes with magic
        icon_sprite_id="icon_iron_helmet",
        equipped_sprite_id="equip_iron_helmet",
    )

    IRON_PLATEBODY = ItemDefinition(
        display_name="Iron Platebody",
        description="Heavy iron chest armor.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.BODY,
        max_durability=900,
        required_skill=RequiredSkill.DEFENCE,
        required_level=10,
        value=100,
        physical_defence_bonus=12,
        magic_defence_bonus=3,
        health_bonus=8,
        magic_attack_bonus=-4,  # Heavy metal reduces magic ability
        speed_bonus=-1,  # Heavy armor slows movement
        icon_sprite_id="icon_iron_platebody",
        equipped_sprite_id="equip_iron_platebody",
    )

    IRON_PLATELEGS = ItemDefinition(
        display_name="Iron Platelegs",
        description="Heavy iron leg armor.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.LEGS,
        max_durability=750,
        required_skill=RequiredSkill.DEFENCE,
        required_level=10,
        value=75,
        physical_defence_bonus=8,
        magic_defence_bonus=2,
        magic_attack_bonus=-3,  # Metal interferes with magic
        icon_sprite_id="icon_iron_platelegs",
        equipped_sprite_id="equip_iron_platelegs",
    )

    IRON_SHIELD = ItemDefinition(
        display_name="Iron Shield",
        description="A sturdy iron shield.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.SHIELD,
        max_durability=700,
        required_skill=RequiredSkill.DEFENCE,
        required_level=10,
        value=60,
        physical_defence_bonus=6,
        magic_defence_bonus=2,
        magic_attack_bonus=-2,  # Metal interferes with magic
        icon_sprite_id="icon_iron_shield",
        equipped_sprite_id="equip_iron_shield",
    )

    # =========================================================================
    # ARMOR - Steel (Level 20, Uncommon rarity)
    # Defence: 9, Durability: 1000, Value: ~100
    # =========================================================================
    STEEL_HELMET = ItemDefinition(
        display_name="Steel Helmet",
        description="Fine head protection made of steel.",
        category=ItemCategory.ARMOR,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.HEAD,
        max_durability=900,
        required_skill=RequiredSkill.DEFENCE,
        required_level=20,
        value=80,
        physical_defence_bonus=8,
        magic_defence_bonus=2,
        magic_attack_bonus=-2,  # Metal interferes with magic
        icon_sprite_id="icon_steel_helmet",
        equipped_sprite_id="equip_steel_helmet",
    )

    STEEL_PLATEBODY = ItemDefinition(
        display_name="Steel Platebody",
        description="Heavy steel chest armor.",
        category=ItemCategory.ARMOR,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.BODY,
        max_durability=1200,
        required_skill=RequiredSkill.DEFENCE,
        required_level=20,
        value=200,
        physical_defence_bonus=18,
        magic_defence_bonus=4,
        health_bonus=12,
        magic_attack_bonus=-5,  # Heavy metal reduces magic ability
        speed_bonus=-1,  # Heavy armor slows movement
        icon_sprite_id="icon_steel_platebody",
        equipped_sprite_id="equip_steel_platebody",
    )

    STEEL_PLATELEGS = ItemDefinition(
        display_name="Steel Platelegs",
        description="Heavy steel leg armor.",
        category=ItemCategory.ARMOR,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.LEGS,
        max_durability=1000,
        required_skill=RequiredSkill.DEFENCE,
        required_level=20,
        value=150,
        physical_defence_bonus=12,
        magic_defence_bonus=3,
        magic_attack_bonus=-4,  # Metal interferes with magic
        icon_sprite_id="icon_steel_platelegs",
        equipped_sprite_id="equip_steel_platelegs",
    )

    STEEL_SHIELD = ItemDefinition(
        display_name="Steel Shield",
        description="A well-crafted steel shield.",
        category=ItemCategory.ARMOR,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.SHIELD,
        max_durability=950,
        required_skill=RequiredSkill.DEFENCE,
        required_level=20,
        value=120,
        physical_defence_bonus=9,
        magic_defence_bonus=3,
        magic_attack_bonus=-3,  # Metal interferes with magic
        icon_sprite_id="icon_steel_shield",
        equipped_sprite_id="equip_steel_shield",
    )

    # =========================================================================
    # ARMOR - Leather (balanced, no magic penalty)
    # =========================================================================
    LEATHER_BODY = ItemDefinition(
        display_name="Leather Body",
        description="Light leather chest armor.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.BODY,
        max_durability=400,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=25,
        physical_defence_bonus=4,
        magic_defence_bonus=4,
        ranged_attack_bonus=2,  # Good for archers
        icon_sprite_id="icon_leather_body",
        equipped_sprite_id="equip_leather_body",
    )

    LEATHER_CHAPS = ItemDefinition(
        display_name="Leather Chaps",
        description="Light leather leg armor.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.LEGS,
        max_durability=350,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=18,
        physical_defence_bonus=2,
        magic_defence_bonus=2,
        ranged_attack_bonus=1,  # Good for archers
        icon_sprite_id="icon_leather_chaps",
        equipped_sprite_id="equip_leather_chaps",
    )

    LEATHER_BOOTS = ItemDefinition(
        display_name="Leather Boots",
        description="Light leather boots.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.BOOTS,
        max_durability=250,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=12,
        physical_defence_bonus=1,
        magic_defence_bonus=1,
        icon_sprite_id="icon_leather_boots",
        equipped_sprite_id="equip_leather_boots",
    )

    LEATHER_GLOVES = ItemDefinition(
        display_name="Leather Gloves",
        description="Light leather gloves.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.GLOVES,
        max_durability=250,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=10,
        physical_defence_bonus=1,
        magic_defence_bonus=1,
        icon_sprite_id="icon_leather_gloves",
        equipped_sprite_id="equip_leather_gloves",
    )

    # =========================================================================
    # ARMOR - Hard Leather (Level 10, balanced, no magic penalty)
    # =========================================================================
    HARD_LEATHER_BODY = ItemDefinition(
        display_name="Hard Leather Body",
        description="Hardened leather chest armor.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.BODY,
        max_durability=550,
        required_skill=RequiredSkill.DEFENCE,
        required_level=10,
        value=60,
        physical_defence_bonus=6,
        magic_defence_bonus=5,
        ranged_attack_bonus=3,  # Good for archers
        icon_sprite_id="icon_hard_leather_body",
        equipped_sprite_id="equip_hard_leather_body",
    )

    HARD_LEATHER_CHAPS = ItemDefinition(
        display_name="Hard Leather Chaps",
        description="Hardened leather leg armor.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.LEGS,
        max_durability=500,
        required_skill=RequiredSkill.DEFENCE,
        required_level=10,
        value=45,
        physical_defence_bonus=4,
        magic_defence_bonus=3,
        ranged_attack_bonus=2,  # Good for archers
        icon_sprite_id="icon_hard_leather_chaps",
        equipped_sprite_id="equip_hard_leather_chaps",
    )

    HARD_LEATHER_BOOTS = ItemDefinition(
        display_name="Hard Leather Boots",
        description="Hardened leather boots.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.BOOTS,
        max_durability=400,
        required_skill=RequiredSkill.DEFENCE,
        required_level=10,
        value=35,
        physical_defence_bonus=2,
        magic_defence_bonus=2,
        icon_sprite_id="icon_hard_leather_boots",
        equipped_sprite_id="equip_hard_leather_boots",
    )

    HARD_LEATHER_GLOVES = ItemDefinition(
        display_name="Hard Leather Gloves",
        description="Hardened leather gloves.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.GLOVES,
        max_durability=400,
        required_skill=RequiredSkill.DEFENCE,
        required_level=10,
        value=30,
        physical_defence_bonus=2,
        magic_defence_bonus=2,
        icon_sprite_id="icon_hard_leather_gloves",
        equipped_sprite_id="equip_hard_leather_gloves",
    )

    # =========================================================================
    # ARMOR - Studded Leather (Level 20, Uncommon, balanced)
    # =========================================================================
    STUDDED_LEATHER_BODY = ItemDefinition(
        display_name="Studded Leather Body",
        description="Leather chest armor reinforced with metal studs.",
        category=ItemCategory.ARMOR,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.BODY,
        max_durability=700,
        required_skill=RequiredSkill.DEFENCE,
        required_level=20,
        value=120,
        physical_defence_bonus=9,
        magic_defence_bonus=6,
        ranged_attack_bonus=4,  # Good for archers
        icon_sprite_id="icon_studded_leather_body",
        equipped_sprite_id="equip_studded_leather_body",
    )

    STUDDED_LEATHER_CHAPS = ItemDefinition(
        display_name="Studded Leather Chaps",
        description="Leather leg armor reinforced with metal studs.",
        category=ItemCategory.ARMOR,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.LEGS,
        max_durability=650,
        required_skill=RequiredSkill.DEFENCE,
        required_level=20,
        value=90,
        physical_defence_bonus=6,
        magic_defence_bonus=4,
        ranged_attack_bonus=3,  # Good for archers
        icon_sprite_id="icon_studded_leather_chaps",
        equipped_sprite_id="equip_studded_leather_chaps",
    )

    STUDDED_LEATHER_BOOTS = ItemDefinition(
        display_name="Studded Leather Boots",
        description="Leather boots reinforced with metal studs.",
        category=ItemCategory.ARMOR,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.BOOTS,
        max_durability=550,
        required_skill=RequiredSkill.DEFENCE,
        required_level=20,
        value=70,
        physical_defence_bonus=3,
        magic_defence_bonus=3,
        icon_sprite_id="icon_studded_leather_boots",
        equipped_sprite_id="equip_studded_leather_boots",
    )

    STUDDED_LEATHER_GLOVES = ItemDefinition(
        display_name="Studded Leather Gloves",
        description="Leather gloves reinforced with metal studs.",
        category=ItemCategory.ARMOR,
        rarity=ItemRarity.UNCOMMON,
        equipment_slot=EquipmentSlot.GLOVES,
        max_durability=550,
        required_skill=RequiredSkill.DEFENCE,
        required_level=20,
        value=60,
        physical_defence_bonus=3,
        magic_defence_bonus=3,
        icon_sprite_id="icon_studded_leather_gloves",
        equipped_sprite_id="equip_studded_leather_gloves",
    )

    # =========================================================================
    # TOOLS (equipped in weapon slot, gathering bonuses)
    # =========================================================================
    BRONZE_PICKAXE = ItemDefinition(
        display_name="Bronze Pickaxe",
        description="A basic pickaxe for mining ores.",
        category=ItemCategory.TOOL,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=500,
        required_skill=RequiredSkill.MINING,
        required_level=1,
        value=20,
        mining_bonus=5,
        attack_bonus=2,  # Can be used as weak weapon
        strength_bonus=1,
        attack_speed=3.6,
        icon_sprite_id="icon_bronze_pickaxe",
        equipped_sprite_id="equip_bronze_pickaxe",
    )

    IRON_PICKAXE = ItemDefinition(
        display_name="Iron Pickaxe",
        description="A sturdy iron pickaxe.",
        category=ItemCategory.TOOL,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=750,
        required_skill=RequiredSkill.MINING,
        required_level=10,
        value=50,
        mining_bonus=10,
        attack_bonus=4,
        strength_bonus=2,
        attack_speed=3.6,
        icon_sprite_id="icon_iron_pickaxe",
        equipped_sprite_id="equip_iron_pickaxe",
    )

    BRONZE_AXE = ItemDefinition(
        display_name="Bronze Axe",
        description="A basic axe for chopping trees.",
        category=ItemCategory.TOOL,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=500,
        required_skill=RequiredSkill.WOODCUTTING,
        required_level=1,
        value=20,
        woodcutting_bonus=5,
        attack_bonus=3,  # Better weapon than pickaxe
        strength_bonus=2,
        attack_speed=3.6,
        icon_sprite_id="icon_bronze_axe",
        equipped_sprite_id="equip_bronze_axe",
    )

    IRON_AXE = ItemDefinition(
        display_name="Iron Axe",
        description="A sturdy iron axe.",
        category=ItemCategory.TOOL,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=750,
        required_skill=RequiredSkill.WOODCUTTING,
        required_level=10,
        value=50,
        woodcutting_bonus=10,
        attack_bonus=6,
        strength_bonus=4,
        attack_speed=3.6,
        icon_sprite_id="icon_iron_axe",
        equipped_sprite_id="equip_iron_axe",
    )

    FISHING_NET = ItemDefinition(
        display_name="Fishing Net",
        description="A net for catching small fish.",
        category=ItemCategory.TOOL,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=300,
        required_skill=RequiredSkill.FISHING,
        required_level=1,
        value=10,
        fishing_bonus=3,
        icon_sprite_id="icon_fishing_net",
        equipped_sprite_id="equip_fishing_net",
    )

    FISHING_ROD = ItemDefinition(
        display_name="Fishing Rod",
        description="A rod for catching fish with bait.",
        category=ItemCategory.TOOL,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=400,
        required_skill=RequiredSkill.FISHING,
        required_level=5,
        value=20,
        fishing_bonus=5,
        icon_sprite_id="icon_fishing_rod",
        equipped_sprite_id="equip_fishing_rod",
    )

    # =========================================================================
    # MATERIALS (stackable to 64, gathered from skills)
    # =========================================================================
    COPPER_ORE = ItemDefinition(
        display_name="Copper Ore",
        description="Raw copper ore, used in smelting.",
        category=ItemCategory.MATERIAL,
        max_stack_size=STACK_SIZE_MATERIALS,
        value=5,
        icon_sprite_id="icon_copper_ore",
    )

    TIN_ORE = ItemDefinition(
        display_name="Tin Ore",
        description="Raw tin ore, used in smelting.",
        category=ItemCategory.MATERIAL,
        max_stack_size=STACK_SIZE_MATERIALS,
        value=5,
        icon_sprite_id="icon_tin_ore",
    )

    BRONZE_BAR = ItemDefinition(
        display_name="Bronze Bar",
        description="A bar of bronze, made from copper and tin.",
        category=ItemCategory.MATERIAL,
        max_stack_size=STACK_SIZE_MATERIALS,
        value=15,
        icon_sprite_id="icon_bronze_bar",
    )

    IRON_ORE = ItemDefinition(
        display_name="Iron Ore",
        description="Raw iron ore, used in smelting.",
        category=ItemCategory.MATERIAL,
        max_stack_size=STACK_SIZE_MATERIALS,
        value=12,
        icon_sprite_id="icon_iron_ore",
    )

    IRON_BAR = ItemDefinition(
        display_name="Iron Bar",
        description="A bar of iron.",
        category=ItemCategory.MATERIAL,
        max_stack_size=STACK_SIZE_MATERIALS,
        value=30,
        icon_sprite_id="icon_iron_bar",
    )

    OAK_LOGS = ItemDefinition(
        display_name="Oak Logs",
        description="Logs from an oak tree.",
        category=ItemCategory.MATERIAL,
        max_stack_size=STACK_SIZE_MATERIALS,
        value=10,
        icon_sprite_id="icon_oak_logs",
    )

    WILLOW_LOGS = ItemDefinition(
        display_name="Willow Logs",
        description="Logs from a willow tree.",
        category=ItemCategory.MATERIAL,
        max_stack_size=STACK_SIZE_MATERIALS,
        value=20,
        icon_sprite_id="icon_willow_logs",
    )

    RAW_SHRIMP = ItemDefinition(
        display_name="Raw Shrimp",
        description="A raw shrimp, needs cooking.",
        category=ItemCategory.MATERIAL,
        rarity=ItemRarity.POOR,
        max_stack_size=STACK_SIZE_MATERIALS,
        value=3,
        icon_sprite_id="icon_raw_shrimp",
    )

    RAW_TROUT = ItemDefinition(
        display_name="Raw Trout",
        description="A raw trout, needs cooking.",
        category=ItemCategory.MATERIAL,
        max_stack_size=STACK_SIZE_MATERIALS,
        value=15,
        icon_sprite_id="icon_raw_trout",
    )

    # =========================================================================
    # CONSUMABLES (stackable to 64, food and potions)
    # =========================================================================
    COOKED_SHRIMP = ItemDefinition(
        display_name="Cooked Shrimp",
        description="A tasty cooked shrimp. Heals a small amount.",
        category=ItemCategory.CONSUMABLE,
        rarity=ItemRarity.POOR,
        max_stack_size=STACK_SIZE_CONSUMABLES,
        value=5,
        icon_sprite_id="icon_cooked_shrimp",
    )

    COOKED_TROUT = ItemDefinition(
        display_name="Cooked Trout",
        description="A delicious cooked trout. Heals a moderate amount.",
        category=ItemCategory.CONSUMABLE,
        max_stack_size=STACK_SIZE_CONSUMABLES,
        value=25,
        icon_sprite_id="icon_cooked_trout",
    )

    BREAD = ItemDefinition(
        display_name="Bread",
        description="A loaf of bread. Heals a small amount.",
        category=ItemCategory.CONSUMABLE,
        rarity=ItemRarity.POOR,
        max_stack_size=STACK_SIZE_CONSUMABLES,
        value=8,
        icon_sprite_id="icon_bread",
    )

    # =========================================================================
    # AMMUNITION (stackable to 8192, for ranged combat)
    # =========================================================================
    BRONZE_ARROWS = ItemDefinition(
        display_name="Bronze Arrows",
        description="Basic arrows with bronze tips.",
        category=ItemCategory.AMMUNITION,
        equipment_slot=EquipmentSlot.AMMO,
        max_stack_size=STACK_SIZE_AMMUNITION,
        ammo_type=AmmoType.ARROWS,
        value=1,
        ranged_strength_bonus=1,
        icon_sprite_id="icon_bronze_arrows",
        equipped_sprite_id="equip_bronze_arrows",
    )

    IRON_ARROWS = ItemDefinition(
        display_name="Iron Arrows",
        description="Arrows with iron tips.",
        category=ItemCategory.AMMUNITION,
        equipment_slot=EquipmentSlot.AMMO,
        max_stack_size=STACK_SIZE_AMMUNITION,
        ammo_type=AmmoType.ARROWS,
        value=3,
        ranged_strength_bonus=3,
        icon_sprite_id="icon_iron_arrows",
        equipped_sprite_id="equip_iron_arrows",
    )

    # =========================================================================
    # CURRENCY (stackable to int max)
    # =========================================================================
    GOLD_COINS = ItemDefinition(
        display_name="Gold Coins",
        description="The standard currency.",
        category=ItemCategory.CURRENCY,
        max_stack_size=STACK_SIZE_CURRENCY,
        value=1,
        icon_sprite_id="icon_gold_coins",
    )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    @classmethod
    def from_name(cls, name: str) -> Optional["ItemType"]:
        """
        Get ItemType by internal name (case-insensitive).

        Args:
            name: The item name to look up (e.g., "bronze_sword")

        Returns:
            The matching ItemType or None if not found
        """
        name_upper = name.upper()
        for item in cls:
            if item.name == name_upper:
                return item
        return None

    @classmethod
    def all_item_names(cls) -> list[str]:
        """Get lowercase names of all items."""
        return [item.name.lower() for item in cls]

    @classmethod
    def get_by_category(cls, category: ItemCategory) -> list["ItemType"]:
        """Get all items in a specific category."""
        return [item for item in cls if item.value.category == category]

    @classmethod
    def get_equipable_items(cls) -> list["ItemType"]:
        """Get all items that can be equipped."""
        return [item for item in cls if item.value.equipment_slot is not None]
