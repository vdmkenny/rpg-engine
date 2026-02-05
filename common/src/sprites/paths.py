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
    ClothingStyle,
    PantsStyle,
    ShoesStyle,
    ClothingColor,
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
    def body(body_type: BodyType, skin_tone: SkinTone, animation: str = "walk") -> str:
        """
        Get the path for a body sprite sheet.
        
        Args:
            body_type: Body type (male, female, child, etc.)
            skin_tone: Skin color variant
            animation: Animation type (walk, idle, slash, etc.). Defaults to "walk".
            
        Returns:
            Path like "body/bodies/male/walk/light.png"
        """
        return f"body/bodies/{body_type.value}/{animation}/{skin_tone.value}.png"
    
    @staticmethod
    def head(head_type: HeadType, skin_tone: SkinTone, animation: str = "walk") -> str:
        """
        Get the path for a head sprite sheet.
        
        Args:
            head_type: Head type (includes race, e.g., "human/male")
            skin_tone: Skin color variant
            animation: Animation type (walk, idle, slash, etc.). Defaults to "walk".
            
        Returns:
            Path like "head/heads/human/male/walk/light.png"
        """
        return f"head/heads/{head_type.value}/{animation}/{skin_tone.value}.png"
    
    @staticmethod
    def eyes(
        eye_color: EyeColor,
        age_group: EyeAgeGroup = EyeAgeGroup.ADULT,
        expression: str = "default",
        animation: str = "walk",
    ) -> str:
        """
        Get the path for an eyes sprite sheet.
        
        Args:
            eye_color: Eye color
            age_group: Age variant (adult, child, elderly)
            expression: Eye expression (default, anger, sad, etc.)
            animation: Animation type (walk, idle, slash, etc.)
            
        Returns:
            Path like "eyes/human/adult/default/walk/blue.png"
        """
        return f"eyes/human/{age_group.value}/{expression}/{animation}/{eye_color.value}.png"
    
    @staticmethod
    def hair(
        hair_style: HairStyle,
        hair_color: HairColor,
        age_group: str = "adult",
        animation: str = "walk",
    ) -> str:
        """
        Get the path for a hair sprite sheet.
        
        Args:
            hair_style: Hair style
            hair_color: Hair color
            age_group: Age group (adult, child, elderly)
            animation: Animation type (walk, idle, slash, etc.)
            
        Returns:
            Path like "hair/parted/adult/walk/brown.png"
        """
        # Handle "bald" specially - no sprite needed
        if hair_style == HairStyle.BALD:
            return ""
        
        return f"hair/{hair_style.value}/{age_group}/{animation}/{hair_color.value}.png"

    @staticmethod
    def clothing_shirt(
        shirt_style: ClothingStyle,
        shirt_color: ClothingColor,
        body_type: BodyType = BodyType.MALE,
        animation: str = "walk",
    ) -> str:
        """
        Get the path for a clothing shirt/top sprite sheet.

        Args:
            shirt_style: Shirt style (longsleeve, shortsleeve, etc.)
            shirt_color: Shirt color
            body_type: Body type for body-specific sprites
            animation: Animation type (walk, idle, slash, etc.)

        Returns:
            Path like "torso/clothes/longsleeve/longsleeve2/male/walk/white.png"
        """
        # Handle "none" specially - no sprite needed
        if shirt_style == ClothingStyle.NONE:
            return ""

        return f"torso/clothes/{shirt_style.value}/{body_type.value}/{animation}/{shirt_color.value}.png"

    @staticmethod
    def clothing_pants(
        pants_style: PantsStyle,
        pants_color: ClothingColor,
        body_type: BodyType = BodyType.MALE,
        animation: str = "walk",
    ) -> str:
        """
        Get the path for clothing pants/legs sprite sheet.

        Args:
            pants_style: Pants style (pants, shorts, leggings, etc.)
            pants_color: Pants color
            body_type: Body type for body-specific sprites
            animation: Animation type (walk, idle, slash, etc.)

        Returns:
            Path like "legs/pants/male/walk/brown.png" or "legs/shorts/male/walk/blue.png"
        """
        # Handle "none" specially - no sprite needed
        if pants_style == PantsStyle.NONE:
            return ""

        return f"legs/{pants_style.value}/{body_type.value}/{animation}/{pants_color.value}.png"

    @staticmethod
    def clothing_shoes(
        shoes_style: ShoesStyle,
        shoes_color: ClothingColor,
        body_type: BodyType = BodyType.MALE,
        animation: str = "walk",
    ) -> str:
        """
        Get the path for clothing shoes/footwear sprite sheet.

        Args:
            shoes_style: Shoes style (shoes, sandals, etc.)
            shoes_color: Shoes color
            body_type: Body type for body-specific sprites
            animation: Animation type (walk, idle, slash, etc.)

        Returns:
            Path like "feet/shoes/basic/male/walk/brown.png"
        """
        # Handle "none" specially - no sprite needed
        if shoes_style == ShoesStyle.NONE:
            return ""

        return f"feet/{shoes_style.value}/{body_type.value}/{animation}/{shoes_color.value}.png"

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
            EquipmentSlot.BOOTS: "feet",
            EquipmentSlot.GLOVES: "hands",
            EquipmentSlot.WEAPON: "weapons",
            EquipmentSlot.SHIELD: "shield",
            EquipmentSlot.CAPE: "back",
            EquipmentSlot.AMMO: "back",  # Quiver renders on back
        }

        slot_dir = slot_dirs.get(slot, "misc")

        # Weapons don't typically have body type variants
        if slot in {EquipmentSlot.WEAPON, EquipmentSlot.SHIELD}:
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

        # Clothing - pants (under armor)
        pants_path = cls.clothing_pants(
            appearance.pants_style,
            appearance.pants_color,
            appearance.body_type,
        )
        if pants_path:
            paths.append(pants_path)

        # Clothing - shoes (under boots)
        shoes_path = cls.clothing_shoes(
            appearance.shoes_style,
            appearance.shoes_color,
            appearance.body_type,
        )
        if shoes_path:
            paths.append(shoes_path)

        # Clothing - shirt (under body armor)
        shirt_path = cls.clothing_shirt(
            appearance.shirt_style,
            appearance.shirt_color,
            appearance.body_type,
        )
        if shirt_path:
            paths.append(shirt_path)

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


def get_clothing_shirt_path(
    shirt_style: ClothingStyle,
    shirt_color: ClothingColor,
    body_type: BodyType = BodyType.MALE,
    animation: str = "walk",
) -> str:
    """Get full path for a clothing shirt sprite."""
    return SpritePaths.get_full_path(
        SpritePaths.clothing_shirt(shirt_style, shirt_color, body_type, animation)
    )


def get_clothing_pants_path(
    pants_style: PantsStyle,
    pants_color: ClothingColor,
    body_type: BodyType = BodyType.MALE,
    animation: str = "walk",
) -> str:
    """Get full path for clothing pants sprite."""
    return SpritePaths.get_full_path(
        SpritePaths.clothing_pants(pants_style, pants_color, body_type, animation)
    )


def get_clothing_shoes_path(
    shoes_style: ShoesStyle,
    shoes_color: ClothingColor,
    body_type: BodyType = BodyType.MALE,
    animation: str = "walk",
) -> str:
    """Get full path for clothing shoes sprite."""
    return SpritePaths.get_full_path(
        SpritePaths.clothing_shoes(shoes_style, shoes_color, body_type, animation)
    )
