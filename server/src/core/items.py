"""
Item definitions and related enums.

Items are defined in Python as an enum with metadata.
Configuration for inventory, equipment, and ground items is in config.yml.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ItemRarity(Enum):
    """Item rarity with display colors.

    Each rarity has a value and associated hex color for UI display.
    """

    POOR = ("poor", "#9d9d9d")  # Gray - vendor trash
    COMMON = ("common", "#ffffff")  # White - basic items
    UNCOMMON = ("uncommon", "#1eff00")  # Green - slightly better
    RARE = ("rare", "#0070dd")  # Blue - good items
    EPIC = ("epic", "#a335ee")  # Purple - excellent items
    LEGENDARY = ("legendary", "#ff8000")  # Orange - best items

    def __init__(self, value: str, color: str):
        self._value_ = value
        self.color = color

    @classmethod
    def from_value(cls, value: str) -> "ItemRarity":
        """
        Look up ItemRarity by its string value.

        Args:
            value: The rarity string (e.g., "common", "rare")

        Returns:
            The matching ItemRarity enum member

        Raises:
            ValueError: If no matching rarity is found
        """
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"'{value}' is not a valid ItemRarity")

    @classmethod
    def get_color(cls, rarity_value: str, default: str = "#ffffff") -> str:
        """
        Get the color for a rarity value with a safe fallback.
        
        This is a convenience method that handles missing/invalid rarity values
        gracefully without raising exceptions.
        
        Args:
            rarity_value: The rarity string (e.g., "common", "rare")
            default: Default color to return if rarity is invalid
            
        Returns:
            Hex color string for the rarity
        """
        if not rarity_value:
            return default
        try:
            rarity_enum = cls.from_value(rarity_value)
            return rarity_enum.color
        except ValueError:
            return default


class ItemCategory(Enum):
    """Categories for organizing items."""

    NORMAL = "normal"  # Generic items
    TOOL = "tool"  # Pickaxe, axe, fishing rod
    WEAPON = "weapon"  # Swords, bows, staffs
    ARMOR = "armor"  # Defensive equipment
    CONSUMABLE = "consumable"  # Food, potions
    QUEST = "quest"  # Quest items (non-tradeable)
    MATERIAL = "material"  # Ores, logs, fish
    CURRENCY = "currency"  # Gold coins, tokens
    AMMUNITION = "ammunition"  # Arrows, bolts, runes


class EquipmentSlot(Enum):
    """Equipment slots (11 total)."""

    HEAD = "head"
    CAPE = "cape"
    AMULET = "amulet"
    WEAPON = "weapon"
    BODY = "body"
    SHIELD = "shield"
    LEGS = "legs"
    GLOVES = "gloves"
    BOOTS = "boots"
    RING = "ring"
    AMMO = "ammo"


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
    # WEAPONS - Melee
    # =========================================================================
    BRONZE_SWORD = ItemDefinition(
        display_name="Bronze Sword",
        description="A basic bronze sword.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=500,
        required_skill=RequiredSkill.ATTACK,
        required_level=1,
        value=20,
        attack_bonus=4,
        strength_bonus=3,
        attack_speed=3.0,
        icon_sprite_id="icon_bronze_sword",
        equipped_sprite_id="equip_bronze_sword",
    )

    IRON_SWORD = ItemDefinition(
        display_name="Iron Sword",
        description="A sturdy iron sword.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        max_durability=750,
        required_skill=RequiredSkill.ATTACK,
        required_level=10,
        value=50,
        attack_bonus=10,
        strength_bonus=7,
        attack_speed=3.0,
        icon_sprite_id="icon_iron_sword",
        equipped_sprite_id="equip_iron_sword",
    )

    BRONZE_2H_SWORD = ItemDefinition(
        display_name="Bronze Two-Handed Sword",
        description="A large bronze sword requiring two hands.",
        category=ItemCategory.WEAPON,
        equipment_slot=EquipmentSlot.WEAPON,
        is_two_handed=True,
        max_durability=600,
        required_skill=RequiredSkill.ATTACK,
        required_level=1,
        value=30,
        attack_bonus=6,
        strength_bonus=8,
        attack_speed=3.6,
        icon_sprite_id="icon_bronze_2h_sword",
        equipped_sprite_id="equip_bronze_2h_sword",
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
    # ARMOR - Bronze (heavy, negative magic stats)
    # =========================================================================
    BRONZE_HELMET = ItemDefinition(
        display_name="Bronze Helmet",
        description="Basic head protection made of bronze.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.HEAD,
        max_durability=400,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
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
        required_level=1,
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
        required_level=1,
        value=30,
        physical_defence_bonus=5,
        magic_defence_bonus=1,
        magic_attack_bonus=-2,  # Metal interferes with magic
        icon_sprite_id="icon_bronze_platelegs",
        equipped_sprite_id="equip_bronze_platelegs",
    )

    BRONZE_BOOTS = ItemDefinition(
        display_name="Bronze Boots",
        description="Heavy bronze boots.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.BOOTS,
        max_durability=300,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=12,
        physical_defence_bonus=1,
        magic_attack_bonus=-1,  # Metal interferes with magic
        icon_sprite_id="icon_bronze_boots",
        equipped_sprite_id="equip_bronze_boots",
    )

    BRONZE_GLOVES = ItemDefinition(
        display_name="Bronze Gloves",
        description="Heavy bronze gauntlets.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.GLOVES,
        max_durability=300,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=10,
        physical_defence_bonus=1,
        magic_attack_bonus=-1,  # Metal interferes with magic
        icon_sprite_id="icon_bronze_gloves",
        equipped_sprite_id="equip_bronze_gloves",
    )

    BRONZE_SHIELD = ItemDefinition(
        display_name="Bronze Shield",
        description="A basic bronze shield.",
        category=ItemCategory.ARMOR,
        equipment_slot=EquipmentSlot.SHIELD,
        max_durability=450,
        required_skill=RequiredSkill.DEFENCE,
        required_level=1,
        value=25,
        physical_defence_bonus=4,
        magic_defence_bonus=1,
        magic_attack_bonus=-2,  # Metal interferes with magic
        icon_sprite_id="icon_bronze_shield",
        equipped_sprite_id="equip_bronze_shield",
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
