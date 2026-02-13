"""
Equipment Sprite Mapping - Maps equipped_sprite_id to LPC paths.

This module resolves equipment sprite IDs (e.g., "equip_copper_longsword")
to actual LPC sprite paths, with optional tint colors for items that
don't have native metal variants in the LPC asset pack.

LPC Asset Structure:
- Some items (arming sword, plate armor) have native metal variants
  (copper, bronze, iron, steel, etc.)
- Other items (dagger, longsword, mace) only have a single sprite,
  so we provide a tint color for client-side recoloring.

License: Part of the LPC sprite integration.
See server/sprites/CREDITS.csv for sprite attribution.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from enum import Enum


class MetalTier(str, Enum):
    """
    Metal tiers for tiered equipment.
    
    These represent our game's progression tiers, which may or may not
    have native LPC sprite variants.
    """
    WOOD = "wood"
    COPPER = "copper"
    BRONZE = "bronze"
    IRON = "iron"
    STEEL = "steel"


# Tint colors for client-side recoloring
# Used when LPC doesn't provide native metal variants
METAL_TINT_COLORS: Dict[MetalTier, str] = {
    MetalTier.WOOD: "#8B4513",     # Saddle brown (wood)
    MetalTier.COPPER: "#B87333",   # Copper orange
    MetalTier.BRONZE: "#CD7F32",   # Bronze tan
    MetalTier.IRON: "#71797E",     # Iron gray
    MetalTier.STEEL: "#B4C4D0",    # Steel blue-gray
}


# Maps (equipment_category, character_body_type) → directory name on disk
# Used to generate correct body type directories for equipment sprites
EQUIPMENT_BODY_TYPE_MAP: Dict[Tuple[str, str], str] = {
    # Armor body (torso/armour/plate, torso/armour/leather)
    ("armor_body", "male"): "male",
    ("armor_body", "female"): "female",
    ("armor_body", "child"): "teen",
    ("armor_body", "teen"): "teen",
    # Armor legs (legs/armour/plate)
    ("armor_legs", "male"): "male",
    ("armor_legs", "female"): "thin",
    ("armor_legs", "child"): "male",
    ("armor_legs", "teen"): "male",
    # Helmet (hat/helmet/*)
    ("helmet", "male"): "adult",
    ("helmet", "female"): "adult",
    ("helmet", "child"): "adult",
    ("helmet", "teen"): "adult",
    # Gloves (arms/gloves)
    ("gloves", "male"): "male",
    ("gloves", "female"): "female",
    ("gloves", "child"): "male",
    ("gloves", "teen"): "male",
    # Boots (feet/boots/*)
    ("boots", "male"): "male",
    ("boots", "female"): "thin",
    ("boots", "child"): "thin",
    ("boots", "teen"): "thin",
    # Shoulders
    ("shoulders", "male"): "male",
    ("shoulders", "female"): "female",
    ("shoulders", "child"): "male",
    ("shoulders", "teen"): "male",
    # Shields
    ("shield", "male"): "male",
    ("shield", "female"): "female",
    ("shield", "child"): "male",
    ("shield", "teen"): "male",
}


@dataclass(frozen=True)
class EquipmentSprite:
    """
    Resolved LPC sprite information for an equipment item.

    Attributes:
        base_path: Base LPC path (e.g., "weapon/sword/arming")
        variant: LPC variant name (e.g., "copper", "dagger")
        tint: Optional hex color for client-side tinting (e.g., "#B87333")
              None if native variant exists, hex string if tinting needed.
        has_layers: True if sprite has fg/bg layers (some weapons do)
        body_type_category: Category for body type mapping (e.g., "armor_body", "helmet")
                            None for items without body type dirs (weapons)
        has_idle: False if this equipment has no idle animation on disk
                  (idle will fall back to walk). Default True.
        flat_path: Override path that bypasses the standard formula.
                   Used for items with unique directory structures (bows).
    """
    base_path: str
    variant: str
    tint: Optional[str] = None
    has_layers: bool = False
    body_type_category: Optional[str] = None
    has_idle: bool = True
    flat_path: Optional[str] = None

    def get_path(self, animation: str = "walk", layer: str = "fg", body_type: str = "male") -> str:
        """
        Get the full sprite path for a specific animation.

        Args:
            animation: Animation name (walk, slash, hurt, idle, etc.)
            layer: Layer name for layered sprites (fg, bg)
            body_type: Character body type for body type directory selection

        Returns:
            Full path like "torso/armour/plate/male/walk/copper.png"
            or "weapon/sword/arming/universal/fg/walk/copper.png" for layered
        """
        if self.flat_path:
            return self.flat_path

        if animation == "idle" and not self.has_idle:
            animation = "walk"

        body_dir = ""
        if self.body_type_category:
            dir_name = EQUIPMENT_BODY_TYPE_MAP.get((self.body_type_category, body_type), body_type)
            body_dir = f"{dir_name}/"

        if self.has_layers:
            return f"{self.base_path}/universal/{layer}/{animation}/{self.variant}.png"
        else:
            return f"{self.base_path}/{body_dir}{animation}/{self.variant}.png"


# =============================================================================
# Equipment Sprite Mappings
# =============================================================================

# Keys are equipped_sprite_id values from ItemDefinition
# Values are EquipmentSprite instances

EQUIPMENT_SPRITES: Dict[str, EquipmentSprite] = {
    # =========================================================================
    # WEAPONS - Wood Tier
    # =========================================================================
    "equip_wooden_club": EquipmentSprite(
        base_path="weapon/blunt/mace",  # Club sprite doesn't exist, use mace
        variant="mace",
        tint=METAL_TINT_COLORS[MetalTier.WOOD],
        has_idle=False,
    ),
    
    # =========================================================================
    # WEAPONS - Shortswords (Native LPC metal variants via arming sword)
    # =========================================================================
    "equip_copper_shortsword": EquipmentSprite(
        base_path="weapon/sword/arming",
        variant="copper",
        has_layers=True,
        has_idle=True,
    ),
    "equip_bronze_shortsword": EquipmentSprite(
        base_path="weapon/sword/arming",
        variant="bronze",
        has_layers=True,
        has_idle=True,
    ),
    "equip_iron_shortsword": EquipmentSprite(
        base_path="weapon/sword/arming",
        variant="iron",
        has_layers=True,
        has_idle=True,
    ),
    "equip_steel_shortsword": EquipmentSprite(
        base_path="weapon/sword/arming",
        variant="steel",
        has_layers=True,
        has_idle=True,
    ),
    
    # =========================================================================
    # WEAPONS - Daggers (Single sprite + tint)
    # =========================================================================
    "equip_copper_dagger": EquipmentSprite(
        base_path="weapon/sword/dagger",
        variant="dagger",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
        has_idle=False,
    ),
    "equip_bronze_dagger": EquipmentSprite(
        base_path="weapon/sword/dagger",
        variant="dagger",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
        has_idle=False,
    ),
    "equip_iron_dagger": EquipmentSprite(
        base_path="weapon/sword/dagger",
        variant="dagger",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
        has_idle=False,
    ),
    "equip_steel_dagger": EquipmentSprite(
        base_path="weapon/sword/dagger",
        variant="dagger",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
        has_idle=False,
    ),
    
    # =========================================================================
    # WEAPONS - Longswords (Single sprite + tint)
    # =========================================================================
    "equip_copper_longsword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
        has_idle=False,
    ),
    "equip_bronze_longsword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
        has_idle=False,
    ),
    "equip_iron_longsword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
        has_idle=False,
    ),
    "equip_steel_longsword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
        has_idle=False,
    ),
    
    # =========================================================================
    # WEAPONS - Maces (Single sprite + tint)
    # =========================================================================
    "equip_copper_mace": EquipmentSprite(
        base_path="weapon/blunt/mace",
        variant="mace",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
        has_idle=False,
    ),
    "equip_bronze_mace": EquipmentSprite(
        base_path="weapon/blunt/mace",
        variant="mace",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
        has_idle=False,
    ),
    "equip_iron_mace": EquipmentSprite(
        base_path="weapon/blunt/mace",
        variant="mace",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
        has_idle=False,
    ),
    "equip_steel_mace": EquipmentSprite(
        base_path="weapon/blunt/mace",
        variant="mace",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
        has_idle=False,
    ),
    
    # =========================================================================
    # WEAPONS - Battleaxes (waraxe in LPC, single sprite + tint)
    # =========================================================================
    "equip_copper_battleaxe": EquipmentSprite(
        base_path="weapon/blunt/waraxe",
        variant="waraxe",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
        has_idle=False,
    ),
    "equip_bronze_battleaxe": EquipmentSprite(
        base_path="weapon/blunt/waraxe",
        variant="waraxe",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
        has_idle=False,
    ),
    "equip_iron_battleaxe": EquipmentSprite(
        base_path="weapon/blunt/waraxe",
        variant="waraxe",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
        has_idle=False,
    ),
    "equip_steel_battleaxe": EquipmentSprite(
        base_path="weapon/blunt/waraxe",
        variant="waraxe",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
        has_idle=False,
    ),
    
    # =========================================================================
    # WEAPONS - 2H Swords (use longsword sprite + tint)
    # =========================================================================
    "equip_copper_2h_sword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
        has_idle=False,
    ),
    "equip_bronze_2h_sword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
        has_idle=False,
    ),
    "equip_iron_2h_sword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
        has_idle=False,
    ),
    "equip_steel_2h_sword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
        has_idle=False,
    ),
    
    # =========================================================================
    # WEAPONS - Ranged (Bows)
    # =========================================================================
    "equip_shortbow": EquipmentSprite(
        base_path="weapon/ranged/bow/normal",  # For documentation/reference
        variant="normal",
        has_idle=False,
        flat_path="weapon/ranged/bow/normal/walk/foreground/normal.png",
    ),
    "equip_oak_shortbow": EquipmentSprite(
        base_path="weapon/ranged/bow/normal",
        variant="normal",
        tint="#8B4513",  # Oak brown tint
        has_idle=False,
        flat_path="weapon/ranged/bow/normal/walk/foreground/normal.png",
    ),
    
    # =========================================================================
    # SHIELDS - Kite style (body type based: male/female)
    # =========================================================================
    "equip_wooden_shield": EquipmentSprite(
        base_path="shield/kite",
        variant="kite_gray",
        body_type_category="shield",
        has_idle=False,
    ),
    "equip_copper_shield": EquipmentSprite(
        base_path="shield/kite",
        variant="kite_orange",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
        body_type_category="shield",
        has_idle=False,
    ),
    "equip_bronze_shield": EquipmentSprite(
        base_path="shield/kite",
        variant="kite_orange",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
        body_type_category="shield",
        has_idle=False,
    ),
    "equip_iron_shield": EquipmentSprite(
        base_path="shield/kite",
        variant="kite_gray",
        body_type_category="shield",
        has_idle=False,
    ),
    "equip_steel_shield": EquipmentSprite(
        base_path="shield/kite",
        variant="kite_gray_blue",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
        body_type_category="shield",
        has_idle=False,
    ),
    
    # =========================================================================
    # ARMOR - Helmets (Native LPC metal variants via barbarian helmet)
    # =========================================================================
    "equip_copper_helmet": EquipmentSprite(
        base_path="hat/helmet/barbarian",
        variant="copper",
        body_type_category="helmet",
    ),
    "equip_bronze_helmet": EquipmentSprite(
        base_path="hat/helmet/barbarian",
        variant="bronze",
        body_type_category="helmet",
    ),
    "equip_iron_helmet": EquipmentSprite(
        base_path="hat/helmet/barbarian",
        variant="iron",
        body_type_category="helmet",
    ),
    "equip_steel_helmet": EquipmentSprite(
        base_path="hat/helmet/barbarian",
        variant="steel",
        body_type_category="helmet",
    ),
    
    # =========================================================================
    # ARMOR - Platebodies (Native LPC metal variants)
    # =========================================================================
    "equip_copper_platebody": EquipmentSprite(
        base_path="torso/armour/plate",
        variant="copper",
        body_type_category="armor_body",
    ),
    "equip_bronze_platebody": EquipmentSprite(
        base_path="torso/armour/plate",
        variant="bronze",
        body_type_category="armor_body",
    ),
    "equip_iron_platebody": EquipmentSprite(
        base_path="torso/armour/plate",
        variant="iron",
        body_type_category="armor_body",
    ),
    "equip_steel_platebody": EquipmentSprite(
        base_path="torso/armour/plate",
        variant="steel",
        body_type_category="armor_body",
    ),
    
    # =========================================================================
    # ARMOR - Platelegs (Native LPC metal variants)
    # =========================================================================
    "equip_copper_platelegs": EquipmentSprite(
        base_path="legs/armour/plate",
        variant="copper",
        body_type_category="armor_legs",
    ),
    "equip_bronze_platelegs": EquipmentSprite(
        base_path="legs/armour/plate",
        variant="bronze",
        body_type_category="armor_legs",
    ),
    "equip_iron_platelegs": EquipmentSprite(
        base_path="legs/armour/plate",
        variant="iron",
        body_type_category="armor_legs",
    ),
    "equip_steel_platelegs": EquipmentSprite(
        base_path="legs/armour/plate",
        variant="steel",
        body_type_category="armor_legs",
    ),
    
    # =========================================================================
    # ARMOR - Leather (leather color variants)
    # =========================================================================
    "equip_leather_body": EquipmentSprite(
        base_path="torso/armour/leather",
        variant="leather",
        body_type_category="armor_body",
        has_idle=False,
    ),
    "equip_leather_chaps": EquipmentSprite(
        base_path="legs/pants",
        variant="leather",
        body_type_category="armor_legs",
        has_idle=True,
    ),
    "equip_leather_boots": EquipmentSprite(
        base_path="feet/boots/basic",
        variant="leather",
        body_type_category="boots",
    ),
    "equip_leather_gloves": EquipmentSprite(
        base_path="arms/gloves",
        variant="leather",
        body_type_category="gloves",
    ),

    # =========================================================================
    # ARMOR - Hard Leather
    # =========================================================================
    "equip_hard_leather_body": EquipmentSprite(
        base_path="torso/armour/leather",
        variant="brown",
        body_type_category="armor_body",
        has_idle=False,
    ),
    "equip_hard_leather_chaps": EquipmentSprite(
        base_path="legs/pants",
        variant="brown",
        body_type_category="armor_legs",
        has_idle=True,
    ),
    "equip_hard_leather_boots": EquipmentSprite(
        base_path="feet/boots/basic",
        variant="brown",
        body_type_category="boots",
    ),
    "equip_hard_leather_gloves": EquipmentSprite(
        base_path="arms/gloves",
        variant="brown",
        body_type_category="gloves",
    ),
    
    # =========================================================================
    # ARMOR - Studded Leather
    # =========================================================================
    "equip_studded_leather_body": EquipmentSprite(
        base_path="torso/armour/leather",
        variant="black",
        body_type_category="armor_body",
        has_idle=False,
    ),
    "equip_studded_leather_chaps": EquipmentSprite(
        base_path="legs/pants",
        variant="black",
        body_type_category="armor_legs",
        has_idle=True,
    ),
    "equip_studded_leather_boots": EquipmentSprite(
        base_path="feet/boots/basic",
        variant="black",
        body_type_category="boots",
    ),
    "equip_studded_leather_gloves": EquipmentSprite(
        base_path="arms/gloves",
        variant="black",
        body_type_category="gloves",
    ),
    
    # =========================================================================
    # TOOLS - Mining (pickaxe)
    # =========================================================================
    "equip_bronze_pickaxe": EquipmentSprite(
        base_path="tools/smash/universal/male",
        variant="pickaxe",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
        has_idle=False,
    ),
    "equip_iron_pickaxe": EquipmentSprite(
        base_path="tools/smash/universal/male",
        variant="pickaxe",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
        has_idle=False,
    ),
    
    # =========================================================================
    # TOOLS - Woodcutting (axe)
    # =========================================================================
    "equip_bronze_axe": EquipmentSprite(
        base_path="tools/smash/universal/male",
        variant="axe",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
        has_idle=False,
    ),
    "equip_iron_axe": EquipmentSprite(
        base_path="tools/smash/universal/male",
        variant="axe",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
        has_idle=False,
    ),
    
    # =========================================================================
    # TOOLS - Fishing
    # =========================================================================
    "equip_fishing_net": EquipmentSprite(
        base_path="tools/fishing",
        variant="net",
        has_idle=False,
        flat_path="tools/fishing/walk/fishing.png",
    ),
    "equip_fishing_rod": EquipmentSprite(
        base_path="tools/rod",
        variant="rod",
        has_idle=False,
        has_layers=True,
        flat_path="tools/rod/foreground/rod.png",
    ),
    
    # =========================================================================
    # AMMUNITION (equipped in ammo slot, may need quiver sprite)
    # =========================================================================
    "equip_bronze_arrows": EquipmentSprite(
        base_path="quiver",
        variant="arrows",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
        has_idle=False,
        flat_path="quiver/walk/quiver.png",
    ),
    "equip_iron_arrows": EquipmentSprite(
        base_path="quiver",
        variant="arrows",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
        has_idle=False,
        flat_path="quiver/walk/quiver.png",
    ),
}


# =============================================================================
# Lookup Functions
# =============================================================================

def get_equipment_sprite(sprite_id: str) -> Optional[EquipmentSprite]:
    """
    Look up equipment sprite info by sprite ID.
    
    Args:
        sprite_id: The equipped_sprite_id from ItemDefinition
        
    Returns:
        EquipmentSprite instance, or None if not found
    """
    return EQUIPMENT_SPRITES.get(sprite_id)


def resolve_equipment(sprite_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve sprite ID to (path, tint) tuple.
    
    Convenience function for quick lookups.
    
    Args:
        sprite_id: The equipped_sprite_id from ItemDefinition
        
    Returns:
        Tuple of (sprite_path, tint_color) or (None, None) if not found
    """
    sprite = get_equipment_sprite(sprite_id)
    if sprite is None:
        return (None, None)
    return (sprite.get_path(), sprite.tint)


def get_all_sprite_ids() -> list[str]:
    """Get all registered equipment sprite IDs."""
    return list(EQUIPMENT_SPRITES.keys())


def validate_sprite_id(sprite_id: str) -> bool:
    """Check if a sprite ID has a valid mapping."""
    return sprite_id in EQUIPMENT_SPRITES
