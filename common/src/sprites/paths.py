"""
Sprite path builders for LPC assets.

Constructs file paths for sprite sheets based on enum values.
Matches the directory structure created by setup_lpc_sprites.py.

License: Part of the LPC sprite integration.
See server/sprites/CREDITS.csv for sprite attribution.
"""

from typing import Optional, List

from .enums import (
    BodyType,
    SkinTone,
    HeadType,
    HairStyle,
    HairColor,
    EyeColor,
    EyeAgeGroup,
    EquipmentSlot,
    get_eye_age_group,
)
from .appearance import AppearanceData


class SpritePaths:
    """
    Utility class for constructing sprite file paths.
    
    All paths are relative to the sprites/lpc/ directory.
    """
    
    # Base directory for LPC sprites (relative to server/sprites/)
    LPC_BASE = "lpc"
    
    @staticmethod
    def body(body_type: BodyType, skin_tone: SkinTone) -> str:
        """
        Get the path for a body sprite sheet.
        
        Args:
            body_type: Body type (male, female, child, etc.)
            skin_tone: Skin color variant
            
        Returns:
            Path like "body/bodies/male/light.png"
        """
        return f"body/bodies/{body_type.value}/{skin_tone.value}.png"
    
    @staticmethod
    def head(head_type: HeadType, skin_tone: SkinTone) -> str:
        """
        Get the path for a head sprite sheet.
        
        Args:
            head_type: Head type (includes race, e.g., "human/male")
            skin_tone: Skin color variant
            
        Returns:
            Path like "head/human/male/light.png"
        """
        return f"head/{head_type.value}/{skin_tone.value}.png"
    
    @staticmethod
    def eyes(
        eye_color: EyeColor,
        age_group: EyeAgeGroup = EyeAgeGroup.ADULT,
    ) -> str:
        """
        Get the path for an eyes sprite sheet.
        
        Args:
            eye_color: Eye color
            age_group: Age variant (adult, child, elderly)
            
        Returns:
            Path like "eyes/human/adult/blue.png"
        """
        return f"eyes/human/{age_group.value}/{eye_color.value}.png"
    
    @staticmethod
    def hair(hair_style: HairStyle, hair_color: HairColor) -> str:
        """
        Get the path for a hair sprite sheet.
        
        Args:
            hair_style: Hair style
            hair_color: Hair color
            
        Returns:
            Path like "hair/short/brown.png"
        """
        # Handle "bald" specially - no sprite needed
        if hair_style == HairStyle.BALD:
            return ""
        
        return f"hair/{hair_style.value}/{hair_color.value}.png"
    
    @staticmethod
    def equipment(
        slot: EquipmentSlot,
        sprite_id: str,
        body_type: BodyType = BodyType.MALE,
    ) -> str:
        """
        Get the path for an equipment sprite sheet.
        
        Args:
            slot: Equipment slot (determines subdirectory)
            sprite_id: The equipment's sprite identifier
            body_type: Body type for body-specific equipment
            
        Returns:
            Path like "equipment/armor/chainmail/male.png"
        """
        # Map slots to directory names
        slot_dirs = {
            EquipmentSlot.HEAD: "head",
            EquipmentSlot.BODY: "torso",
            EquipmentSlot.LEGS: "legs",
            EquipmentSlot.FEET: "feet",
            EquipmentSlot.HANDS: "hands",
            EquipmentSlot.MAIN_HAND: "weapons",
            EquipmentSlot.OFF_HAND: "shield",
            EquipmentSlot.BACK: "back",
            EquipmentSlot.BELT: "belt",
        }
        
        slot_dir = slot_dirs.get(slot, "misc")
        
        # Weapons don't typically have body type variants
        if slot in {EquipmentSlot.MAIN_HAND, EquipmentSlot.OFF_HAND}:
            return f"equipment/{slot_dir}/{sprite_id}.png"
        
        # Body equipment has body type variants
        return f"equipment/{slot_dir}/{sprite_id}/{body_type.value}.png"
    
    @classmethod
    def get_appearance_paths(cls, appearance: AppearanceData) -> List[str]:
        """
        Get all sprite paths needed to render an appearance.
        
        Args:
            appearance: The character's appearance data.
            
        Returns:
            List of sprite paths (excluding empty paths like bald hair).
        """
        paths = []
        
        # Body sprite
        paths.append(cls.body(appearance.body_type, appearance.skin_tone))
        
        # Head sprite
        paths.append(cls.head(appearance.head_type, appearance.skin_tone))
        
        # Eyes sprite
        eye_age = get_eye_age_group(appearance.body_type, appearance.head_type)
        paths.append(cls.eyes(appearance.eye_color, eye_age))
        
        # Hair sprite (skip if bald)
        hair_path = cls.hair(appearance.hair_style, appearance.hair_color)
        if hair_path:
            paths.append(hair_path)
        
        return paths
    
    @classmethod
    def get_full_path(cls, relative_path: str) -> str:
        """
        Get the full path including the LPC base directory.
        
        Args:
            relative_path: Path relative to lpc/ directory.
            
        Returns:
            Full path like "lpc/body/bodies/male/light.png"
        """
        if not relative_path:
            return ""
        return f"{cls.LPC_BASE}/{relative_path}"


# =============================================================================
# Convenience Functions
# =============================================================================

def get_sprite_paths_for_appearance(appearance: AppearanceData) -> List[str]:
    """
    Get all sprite file paths needed to render a character appearance.
    
    Convenience function wrapping SpritePaths.get_appearance_paths().
    
    Args:
        appearance: The character's appearance data.
        
    Returns:
        List of sprite paths relative to sprites/ directory.
    """
    relative_paths = SpritePaths.get_appearance_paths(appearance)
    return [SpritePaths.get_full_path(p) for p in relative_paths if p]


def get_body_sprite_path(body_type: BodyType, skin_tone: SkinTone) -> str:
    """Get full path for a body sprite."""
    return SpritePaths.get_full_path(SpritePaths.body(body_type, skin_tone))


def get_head_sprite_path(head_type: HeadType, skin_tone: SkinTone) -> str:
    """Get full path for a head sprite."""
    return SpritePaths.get_full_path(SpritePaths.head(head_type, skin_tone))


def get_eyes_sprite_path(
    eye_color: EyeColor,
    age_group: EyeAgeGroup = EyeAgeGroup.ADULT,
) -> str:
    """Get full path for an eyes sprite."""
    return SpritePaths.get_full_path(SpritePaths.eyes(eye_color, age_group))


def get_hair_sprite_path(hair_style: HairStyle, hair_color: HairColor) -> str:
    """Get full path for a hair sprite."""
    path = SpritePaths.hair(hair_style, hair_color)
    return SpritePaths.get_full_path(path) if path else ""


def get_equipment_sprite_path(
    slot: EquipmentSlot,
    sprite_id: str,
    body_type: BodyType = BodyType.MALE,
) -> str:
    """Get full path for an equipment sprite."""
    return SpritePaths.get_full_path(
        SpritePaths.equipment(slot, sprite_id, body_type)
    )


def resolve_equipment_sprite(
    sprite_id: str,
    animation: str = "walk",
) -> tuple[str, str | None]:
    """
    Resolve an equipment sprite ID to an LPC path and optional tint.
    
    This uses the equipment mapping to convert game item sprite IDs
    to actual LPC sprite paths, with tint colors for items that
    don't have native metal variants.
    
    Args:
        sprite_id: The equipped_sprite_id from ItemDefinition
        animation: Animation name (walk, slash, hurt, etc.)
        
    Returns:
        Tuple of (full_sprite_path, tint_color_or_none)
        If sprite_id is not found in mapping, returns (fallback_path, None)
    """
    from .equipment_mapping import get_equipment_sprite
    
    sprite_info = get_equipment_sprite(sprite_id)
    if sprite_info is None:
        # Fallback: use the sprite_id as a simple path
        fallback_path = f"equipment/unknown/{sprite_id}.png"
        return (SpritePaths.get_full_path(fallback_path), None)
    
    path = sprite_info.get_path(animation=animation)
    return (SpritePaths.get_full_path(path), sprite_info.tint)
