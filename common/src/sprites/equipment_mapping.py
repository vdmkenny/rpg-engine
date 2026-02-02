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
    """
    base_path: str
    variant: str
    tint: Optional[str] = None
    has_layers: bool = False
    
    def get_path(self, animation: str = "walk", layer: str = "fg") -> str:
        """
        Get the full sprite path for a specific animation.
        
        Args:
            animation: Animation name (walk, slash, hurt, etc.)
            layer: Layer name for layered sprites (fg, bg)
            
        Returns:
            Full path like "weapon/sword/arming/universal/fg/walk/copper.png"
        """
        if self.has_layers:
            return f"{self.base_path}/universal/{layer}/{animation}/{self.variant}.png"
        else:
            return f"{self.base_path}/{animation}/{self.variant}.png"


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
        base_path="weapon/blunt/club",
        variant="club",
        tint=METAL_TINT_COLORS[MetalTier.WOOD],
    ),
    
    # =========================================================================
    # WEAPONS - Shortswords (Native LPC metal variants via arming sword)
    # =========================================================================
    "equip_copper_shortsword": EquipmentSprite(
        base_path="weapon/sword/arming",
        variant="copper",
        has_layers=True,
    ),
    "equip_bronze_shortsword": EquipmentSprite(
        base_path="weapon/sword/arming",
        variant="bronze",
        has_layers=True,
    ),
    "equip_iron_shortsword": EquipmentSprite(
        base_path="weapon/sword/arming",
        variant="iron",
        has_layers=True,
    ),
    "equip_steel_shortsword": EquipmentSprite(
        base_path="weapon/sword/arming",
        variant="steel",
        has_layers=True,
    ),
    
    # =========================================================================
    # WEAPONS - Daggers (Single sprite + tint)
    # =========================================================================
    "equip_copper_dagger": EquipmentSprite(
        base_path="weapon/sword/dagger",
        variant="dagger",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
    ),
    "equip_bronze_dagger": EquipmentSprite(
        base_path="weapon/sword/dagger",
        variant="dagger",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
    ),
    "equip_iron_dagger": EquipmentSprite(
        base_path="weapon/sword/dagger",
        variant="dagger",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
    ),
    "equip_steel_dagger": EquipmentSprite(
        base_path="weapon/sword/dagger",
        variant="dagger",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
    ),
    
    # =========================================================================
    # WEAPONS - Longswords (Single sprite + tint)
    # =========================================================================
    "equip_copper_longsword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
    ),
    "equip_bronze_longsword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
    ),
    "equip_iron_longsword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
    ),
    "equip_steel_longsword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
    ),
    
    # =========================================================================
    # WEAPONS - Maces (Single sprite + tint)
    # =========================================================================
    "equip_copper_mace": EquipmentSprite(
        base_path="weapon/blunt/mace",
        variant="mace",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
    ),
    "equip_bronze_mace": EquipmentSprite(
        base_path="weapon/blunt/mace",
        variant="mace",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
    ),
    "equip_iron_mace": EquipmentSprite(
        base_path="weapon/blunt/mace",
        variant="mace",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
    ),
    "equip_steel_mace": EquipmentSprite(
        base_path="weapon/blunt/mace",
        variant="mace",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
    ),
    
    # =========================================================================
    # WEAPONS - Battleaxes (waraxe in LPC, single sprite + tint)
    # =========================================================================
    "equip_copper_battleaxe": EquipmentSprite(
        base_path="weapon/blunt/waraxe",
        variant="waraxe",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
    ),
    "equip_bronze_battleaxe": EquipmentSprite(
        base_path="weapon/blunt/waraxe",
        variant="waraxe",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
    ),
    "equip_iron_battleaxe": EquipmentSprite(
        base_path="weapon/blunt/waraxe",
        variant="waraxe",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
    ),
    "equip_steel_battleaxe": EquipmentSprite(
        base_path="weapon/blunt/waraxe",
        variant="waraxe",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
    ),
    
    # =========================================================================
    # WEAPONS - 2H Swords (use longsword sprite + tint)
    # =========================================================================
    "equip_copper_2h_sword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
    ),
    "equip_bronze_2h_sword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
    ),
    "equip_iron_2h_sword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
    ),
    "equip_steel_2h_sword": EquipmentSprite(
        base_path="weapon/sword/longsword",
        variant="longsword",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
    ),
    
    # =========================================================================
    # WEAPONS - Ranged (Bows)
    # =========================================================================
    "equip_shortbow": EquipmentSprite(
        base_path="weapon/ranged/bow",
        variant="shortbow",
    ),
    "equip_oak_shortbow": EquipmentSprite(
        base_path="weapon/ranged/bow",
        variant="shortbow",
        tint="#8B4513",  # Oak brown tint
    ),
    
    # =========================================================================
    # SHIELDS - Round style
    # =========================================================================
    "equip_wooden_shield": EquipmentSprite(
        base_path="shield/round",
        variant="brown",
    ),
    "equip_copper_shield": EquipmentSprite(
        base_path="shield/round",
        variant="gold",
        tint=METAL_TINT_COLORS[MetalTier.COPPER],
    ),
    "equip_bronze_shield": EquipmentSprite(
        base_path="shield/round",
        variant="gold",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
    ),
    "equip_iron_shield": EquipmentSprite(
        base_path="shield/round",
        variant="silver",
    ),
    "equip_steel_shield": EquipmentSprite(
        base_path="shield/round",
        variant="silver",
        tint=METAL_TINT_COLORS[MetalTier.STEEL],
    ),
    
    # =========================================================================
    # ARMOR - Helmets (Native LPC metal variants via barbarian helmet)
    # =========================================================================
    "equip_copper_helmet": EquipmentSprite(
        base_path="hat/helmet/barbarian",
        variant="copper",
    ),
    "equip_bronze_helmet": EquipmentSprite(
        base_path="hat/helmet/barbarian",
        variant="bronze",
    ),
    "equip_iron_helmet": EquipmentSprite(
        base_path="hat/helmet/barbarian",
        variant="iron",
    ),
    "equip_steel_helmet": EquipmentSprite(
        base_path="hat/helmet/barbarian",
        variant="steel",
    ),
    
    # =========================================================================
    # ARMOR - Platebodies (Native LPC metal variants)
    # =========================================================================
    "equip_copper_platebody": EquipmentSprite(
        base_path="torso/armour/plate",
        variant="copper",
    ),
    "equip_bronze_platebody": EquipmentSprite(
        base_path="torso/armour/plate",
        variant="bronze",
    ),
    "equip_iron_platebody": EquipmentSprite(
        base_path="torso/armour/plate",
        variant="iron",
    ),
    "equip_steel_platebody": EquipmentSprite(
        base_path="torso/armour/plate",
        variant="steel",
    ),
    
    # =========================================================================
    # ARMOR - Platelegs (Native LPC metal variants)
    # =========================================================================
    "equip_copper_platelegs": EquipmentSprite(
        base_path="legs/armour/plate",
        variant="copper",
    ),
    "equip_bronze_platelegs": EquipmentSprite(
        base_path="legs/armour/plate",
        variant="bronze",
    ),
    "equip_iron_platelegs": EquipmentSprite(
        base_path="legs/armour/plate",
        variant="iron",
    ),
    "equip_steel_platelegs": EquipmentSprite(
        base_path="legs/armour/plate",
        variant="steel",
    ),
    
    # =========================================================================
    # ARMOR - Leather (leather color variants)
    # =========================================================================
    "equip_leather_body": EquipmentSprite(
        base_path="torso/leather/chest",
        variant="leather",
    ),
    "equip_leather_chaps": EquipmentSprite(
        base_path="legs/leather/pants",
        variant="leather",
    ),
    "equip_leather_boots": EquipmentSprite(
        base_path="feet/boots/basic",
        variant="leather",
    ),
    "equip_leather_gloves": EquipmentSprite(
        base_path="hands/gloves/leather",
        variant="leather",
    ),
    
    # =========================================================================
    # ARMOR - Hard Leather
    # =========================================================================
    "equip_hard_leather_body": EquipmentSprite(
        base_path="torso/leather/chest",
        variant="brown",
    ),
    "equip_hard_leather_chaps": EquipmentSprite(
        base_path="legs/leather/pants",
        variant="brown",
    ),
    "equip_hard_leather_boots": EquipmentSprite(
        base_path="feet/boots/basic",
        variant="brown",
    ),
    "equip_hard_leather_gloves": EquipmentSprite(
        base_path="hands/gloves/leather",
        variant="brown",
    ),
    
    # =========================================================================
    # ARMOR - Studded Leather
    # =========================================================================
    "equip_studded_leather_body": EquipmentSprite(
        base_path="torso/leather/chest",
        variant="black",
    ),
    "equip_studded_leather_chaps": EquipmentSprite(
        base_path="legs/leather/pants",
        variant="black",
    ),
    "equip_studded_leather_boots": EquipmentSprite(
        base_path="feet/boots/basic",
        variant="black",
    ),
    "equip_studded_leather_gloves": EquipmentSprite(
        base_path="hands/gloves/leather",
        variant="black",
    ),
    
    # =========================================================================
    # TOOLS - Mining (pickaxe)
    # =========================================================================
    "equip_bronze_pickaxe": EquipmentSprite(
        base_path="tools/smash/universal/male",
        variant="pickaxe",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
    ),
    "equip_iron_pickaxe": EquipmentSprite(
        base_path="tools/smash/universal/male",
        variant="pickaxe",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
    ),
    
    # =========================================================================
    # TOOLS - Woodcutting (axe)
    # =========================================================================
    "equip_bronze_axe": EquipmentSprite(
        base_path="tools/smash/universal/male",
        variant="axe",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
    ),
    "equip_iron_axe": EquipmentSprite(
        base_path="tools/smash/universal/male",
        variant="axe",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
    ),
    
    # =========================================================================
    # TOOLS - Fishing
    # =========================================================================
    "equip_fishing_net": EquipmentSprite(
        base_path="tools/fishing",
        variant="net",
    ),
    "equip_fishing_rod": EquipmentSprite(
        base_path="tools/rod",
        variant="rod",
    ),
    
    # =========================================================================
    # AMMUNITION (equipped in ammo slot, may need quiver sprite)
    # =========================================================================
    "equip_bronze_arrows": EquipmentSprite(
        base_path="back/quiver",
        variant="arrows",
        tint=METAL_TINT_COLORS[MetalTier.BRONZE],
    ),
    "equip_iron_arrows": EquipmentSprite(
        base_path="back/quiver",
        variant="arrows",
        tint=METAL_TINT_COLORS[MetalTier.IRON],
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
