"""
Icon Sprite Mapping - Maps icon_sprite_id to Idylwild icon paths.

This module resolves inventory/ground icon sprite IDs (e.g., "icon_copper_dagger")
to actual icon file paths from the Idylwild icon packs, with optional tint colors
for items that use the same base icon with different colors.

All icons are 32x32 pixels from Idylwild's CC0 packs:
- inventory: materials, tools, food, containers
- arsenal: melee weapons
- armory: armor, shields, jewelry
- arcanum: arcane items, potions, scrolls
- aerial_arsenal: ranged weapons, ammo

License: CC0 (public domain) - Idylwild
See server/icons/ATTRIBUTION.md for full details.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from enum import Enum


class MetalTier(str, Enum):
    """Metal tiers for tiered equipment tinting."""
    WOOD = "wood"
    COPPER = "copper"
    BRONZE = "bronze"
    IRON = "iron"
    STEEL = "steel"


# Tint colors for client-side recoloring
# Used when the same base icon is tinted for different tiers
METAL_TINT_COLORS: Dict[MetalTier, str] = {
    MetalTier.WOOD: "#8B4513",     # Saddle brown (wood)
    MetalTier.COPPER: "#B87333",   # Copper orange
    MetalTier.BRONZE: "#CD7F32",   # Bronze tan
    MetalTier.IRON: "#71797E",     # Iron gray
    MetalTier.STEEL: "#B4C4D0",    # Steel blue-gray
}


@dataclass(frozen=True)
class IconSprite:
    """
    Resolved icon sprite information.

    Attributes:
        pack: Icon pack name (inventory, arsenal, armory, arcanum, aerial_arsenal)
        filename: The .png filename in the pack directory
        tint: Optional hex color for client-side tinting (e.g., "#B87333")
              None if the icon has its own color already.
    """
    pack: str
    filename: str
    tint: Optional[str] = None

    def get_path(self) -> str:
        """Get the full icon path relative to idylwild/ directory."""
        return f"{self.pack}/{self.filename}"


# =============================================================================
# Icon Sprite Mappings
# =============================================================================

# Weapons from arsenal pack (many use tinting for metal tiers)
ARSENAL_ICONS: Dict[str, IconSprite] = {
    # Daggers - use dagger1.png with tints
    "icon_copper_dagger": IconSprite("arsenal", "dagger1.png", tint=METAL_TINT_COLORS[MetalTier.COPPER]),
    "icon_bronze_dagger": IconSprite("arsenal", "dagger1.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_dagger": IconSprite("arsenal", "dagger1.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    "icon_steel_dagger": IconSprite("arsenal", "dagger1.png", tint=METAL_TINT_COLORS[MetalTier.STEEL]),
    
    # Shortswords - use sword1.png with tints
    "icon_copper_shortsword": IconSprite("arsenal", "sword1.png", tint=METAL_TINT_COLORS[MetalTier.COPPER]),
    "icon_bronze_shortsword": IconSprite("arsenal", "sword1.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_shortsword": IconSprite("arsenal", "sword1.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    "icon_steel_shortsword": IconSprite("arsenal", "sword1.png", tint=METAL_TINT_COLORS[MetalTier.STEEL]),
    
    # Longswords - use sword2.png with tints
    "icon_copper_longsword": IconSprite("arsenal", "sword2.png", tint=METAL_TINT_COLORS[MetalTier.COPPER]),
    "icon_bronze_longsword": IconSprite("arsenal", "sword2.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_longsword": IconSprite("arsenal", "sword2.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    "icon_steel_longsword": IconSprite("arsenal", "sword2.png", tint=METAL_TINT_COLORS[MetalTier.STEEL]),
    
    # Maces - use mace1.png with tints
    "icon_copper_mace": IconSprite("arsenal", "mace1.png", tint=METAL_TINT_COLORS[MetalTier.COPPER]),
    "icon_bronze_mace": IconSprite("arsenal", "mace1.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_mace": IconSprite("arsenal", "mace1.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    "icon_steel_mace": IconSprite("arsenal", "mace1.png", tint=METAL_TINT_COLORS[MetalTier.STEEL]),
    
    # Battleaxes - use axe1.png with tints
    "icon_copper_battleaxe": IconSprite("arsenal", "axe1.png", tint=METAL_TINT_COLORS[MetalTier.COPPER]),
    "icon_bronze_battleaxe": IconSprite("arsenal", "axe1.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_battleaxe": IconSprite("arsenal", "axe1.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    "icon_steel_battleaxe": IconSprite("arsenal", "axe1.png", tint=METAL_TINT_COLORS[MetalTier.STEEL]),
    
    # 2H Swords - use sword3.png with tints (larger 2h sword)
    "icon_copper_2h_sword": IconSprite("arsenal", "sword3.png", tint=METAL_TINT_COLORS[MetalTier.COPPER]),
    "icon_bronze_2h_sword": IconSprite("arsenal", "sword3.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_2h_sword": IconSprite("arsenal", "sword3.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    "icon_steel_2h_sword": IconSprite("arsenal", "sword3.png", tint=METAL_TINT_COLORS[MetalTier.STEEL]),
    
    # Wooden club - no tint
    "icon_wooden_club": IconSprite("arsenal", "club1.png"),
    
    # Shortbows - wood colored
    "icon_shortbow": IconSprite("arsenal", "bow1.png", tint=METAL_TINT_COLORS[MetalTier.WOOD]),
    "icon_oak_shortbow": IconSprite("arsenal", "bow2.png", tint=METAL_TINT_COLORS[MetalTier.WOOD]),
}

# Armor and shields from armory pack
ARMORY_ICONS: Dict[str, IconSprite] = {
    # Shields - use wooden buckler for wood, iron buckler for metals
    "icon_wooden_shield": IconSprite("armory", "wooden_buckler.png"),
    "icon_copper_shield": IconSprite("armory", "iron_buckler.png", tint=METAL_TINT_COLORS[MetalTier.COPPER]),
    "icon_bronze_shield": IconSprite("armory", "iron_buckler.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_shield": IconSprite("armory", "iron_buckler.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    "icon_steel_shield": IconSprite("armory", "iron_buckler.png", tint=METAL_TINT_COLORS[MetalTier.STEEL]),
    
    # Helmets - use close_helmet.png for plate
    "icon_copper_helmet": IconSprite("armory", "close_helmet.png", tint=METAL_TINT_COLORS[MetalTier.COPPER]),
    "icon_bronze_helmet": IconSprite("armory", "close_helmet.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_helmet": IconSprite("armory", "close_helmet.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    "icon_steel_helmet": IconSprite("armory", "close_helmet.png", tint=METAL_TINT_COLORS[MetalTier.STEEL]),
    
    # Plate bodies - use breastplate.png
    "icon_copper_platebody": IconSprite("armory", "breastplate.png", tint=METAL_TINT_COLORS[MetalTier.COPPER]),
    "icon_bronze_platebody": IconSprite("armory", "breastplate.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_platebody": IconSprite("armory", "breastplate.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    "icon_steel_platebody": IconSprite("armory", "breastplate.png", tint=METAL_TINT_COLORS[MetalTier.STEEL]),
    
    # Plate legs - use greaves.png
    "icon_copper_platelegs": IconSprite("armory", "greaves.png", tint=METAL_TINT_COLORS[MetalTier.COPPER]),
    "icon_bronze_platelegs": IconSprite("armory", "greaves.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_platelegs": IconSprite("armory", "greaves.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    "icon_steel_platelegs": IconSprite("armory", "greaves.png", tint=METAL_TINT_COLORS[MetalTier.STEEL]),
    
    # Leather armor - no tint (has its own colors)
    "icon_leather_body": IconSprite("armory", "leather_jacket.png"),
    "icon_leather_chaps": IconSprite("armory", "leather_pants.png"),
    "icon_leather_boots": IconSprite("armory", "leather_boots.png"),
    "icon_leather_gloves": IconSprite("armory", "leather_gloves.png"),
    
    # Hard leather armor - tint the leather gear darker
    "icon_hard_leather_body": IconSprite("armory", "leather_jacket_alt.png"),
    "icon_hard_leather_chaps": IconSprite("armory", "leather_pants.png", tint="#5C4033"),
    "icon_hard_leather_boots": IconSprite("armory", "leather_boots.png", tint="#5C4033"),
    "icon_hard_leather_gloves": IconSprite("armory", "leather_gloves.png", tint="#5C4033"),
    
    # Studded leather armor
    "icon_studded_leather_body": IconSprite("armory", "studded_jacket.png"),
    "icon_studded_leather_chaps": IconSprite("armory", "studded_pants.png"),
    "icon_studded_leather_boots": IconSprite("armory", "studded_boots.png"),
    "icon_studded_leather_gloves": IconSprite("armory", "studded_gloves.png"),
}

# Materials and tools from inventory pack
INVENTORY_ICONS: Dict[str, IconSprite] = {
    # Ores - use the ore icons directly
    "icon_copper_ore": IconSprite("inventory", "copper_ore.png"),
    "icon_tin_ore": IconSprite("inventory", "copper_ore.png", tint="#A0A0A0"),  # Tin is gray-ish
    "icon_iron_ore": IconSprite("inventory", "iron_ore.png"),
    
    # Bars/Ingots
    "icon_bronze_bar": IconSprite("inventory", "copper_ingot.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_bar": IconSprite("inventory", "iron_ingot.png"),
    
    # Tools
    "icon_bronze_pickaxe": IconSprite("inventory", "iron_pickaxe.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),
    "icon_iron_pickaxe": IconSprite("inventory", "iron_pickaxe.png"),
    "icon_bronze_axe": IconSprite("inventory", "iron_pickaxe.png", tint=METAL_TINT_COLORS[MetalTier.BRONZE]),  # Reuse pickaxe with tint
    "icon_iron_axe": IconSprite("inventory", "iron_pickaxe.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    "icon_fishing_rod": IconSprite("inventory", "copper_rod.png", tint=METAL_TINT_COLORS[MetalTier.WOOD]),
    
    # Fishing net - use basket with tint
    "icon_fishing_net": IconSprite("inventory", "basket.png", tint="#4A3728"),
    
    # Logs - wood colored
    "icon_oak_logs": IconSprite("inventory", "log.png"),
    "icon_willow_logs": IconSprite("inventory", "log.png", tint="#5C4033"),
    
    # Food - use the actual food icons
    "icon_raw_shrimp": IconSprite("inventory", "rawhide.png", tint="#FF6B6B"),
    "icon_raw_trout": IconSprite("inventory", "rawhide.png", tint="#4A90E2"),
    "icon_cooked_shrimp": IconSprite("inventory", "steak.png", tint="#FF8C42"),
    "icon_cooked_trout": IconSprite("inventory", "steak.png", tint="#E8A87C"),
    "icon_bread": IconSprite("inventory", "bread.png"),
    
    # Arrows - use arrow icon from inventory
    "icon_bronze_arrows": IconSprite("inventory", "arrow.png"),
    "icon_iron_arrows": IconSprite("inventory", "arrow.png", tint=METAL_TINT_COLORS[MetalTier.IRON]),
    
    # Gold coins - use gold ingot with tint
    "icon_gold_coins": IconSprite("inventory", "gold_ingot.png"),
}

# Combined icon sprites dictionary
ICON_SPRITES: Dict[str, IconSprite] = {}
ICON_SPRITES.update(ARSENAL_ICONS)
ICON_SPRITES.update(ARMORY_ICONS)
ICON_SPRITES.update(INVENTORY_ICONS)


def resolve_icon(icon_sprite_id: str) -> Optional[Tuple[str, Optional[str]]]:
    """
    Resolve an icon sprite ID to (icon_path, tint_or_none).

    Args:
        icon_sprite_id: The icon sprite ID (e.g., "icon_copper_dagger")

    Returns:
        Tuple of (path relative to idylwild/, tint_color_or_none) or None if not found
    """
    if icon_sprite_id not in ICON_SPRITES:
        return None
    
    icon = ICON_SPRITES[icon_sprite_id]
    return (icon.get_path(), icon.tint)


def get_icon_info(icon_sprite_id: str) -> Optional[IconSprite]:
    """
    Get the IconSprite info for an icon sprite ID.

    Args:
        icon_sprite_id: The icon sprite ID

    Returns:
        IconSprite dataclass or None if not found
    """
    return ICON_SPRITES.get(icon_sprite_id)


def list_all_icons() -> Dict[str, IconSprite]:
    """Return a copy of all icon sprite mappings."""
    return ICON_SPRITES.copy()
