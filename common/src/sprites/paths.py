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
    FacialHairStyle,
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

    # Body type directory mapping: female -> thin for most clothing categories
    # LPC assets use "thin" as the female body type for most items, not "female"
    _BODY_TYPE_MAP = {
        "feet": "thin",
        "legs": "thin",
        "torso_clothes": "female",
    }

    # Hair styles that use bg/fg subdirectories for multi-layer rendering
    # These styles have hair behind and in front of the head
    _MULTILAYER_HAIR_STYLES = {
        "bangslong2", "braid", "braid2", "bunches", "curls_large",
        "curls_large_xlong", "high_ponytail", "long_band", "long_center_part",
        "long_tied", "ponytail", "ponytail2", "princess", "relm_ponytail",
        "relm_xlong", "sara", "shoulderl", "shoulderr", "single", "wavy",
        "xlong", "xlong_wavy",
    }

    # Clothing items that lack IDLE animation (fall back to WALK)
    _CLOTHING_NO_IDLE = {
        # Format: (style, body_type): True
        # Female shirt styles without idle
        ("corset", "female"),
        ("blouse", "female"),
        ("tunic", "female"),
        ("robe", "female"),
        ("sleeveless", "female"),
        # Male shirt styles without idle
        ("sleeveless", "male"),
        # Leg styles without idle
        ("skirts", "male"),      # Skirts lack idle for both genders
        ("skirts", "female"),
        ("pants", "female"),     # Female pants lack idle
    }

    @classmethod
    def _get_body_dir(cls, category: str, body_type: BodyType) -> str:
        """
        Get the correct body type directory name for a category.

        Most LPC assets use "thin" for female body types, not "female".
        """
        if body_type == BodyType.FEMALE:
            return cls._BODY_TYPE_MAP.get(category, "female")
        return body_type.value

    @classmethod
    def _get_clothing_animation(cls, style: str, body_type: BodyType, animation: str) -> str:
        """
        Get the correct animation for clothing, with fallback for missing IDLE.

        Some clothing styles don't have idle animations - fall back to walk.
        """
        if animation == "idle":
            # Check if this clothing+body combination lacks idle
            if (style, body_type.value) in cls._CLOTHING_NO_IDLE:
                return "walk"
        return animation
    
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

    @classmethod
    def hair_layers(
        cls,
        hair_style: HairStyle,
        hair_color: HairColor,
        age_group: str = "adult",
        animation: str = "walk",
    ) -> List[str]:
        """
        Get the path(s) for hair sprite sheet(s).
        
        For multi-layer styles (ponytail, braid, etc.), returns both bg and fg paths.
        For direct styles, returns a single path.
        For bald, returns an empty list.
        
        Args:
            hair_style: Hair style
            hair_color: Hair color
            age_group: Age group (adult, child, elderly)
            animation: Animation type (walk, idle, slash, etc.)
            
        Returns:
            List of sprite paths (empty for bald, 1 for direct styles, 2 for multi-layer)
        """
        # Handle "bald" specially - no sprite needed
        if hair_style == HairStyle.BALD:
            return []

        style_value = hair_style.value
        if style_value in cls._MULTILAYER_HAIR_STYLES:
            # Multi-layer style: bg layer (behind head) and fg layer (in front of head)
            bg_path = f"hair/{style_value}/{age_group}/bg/{animation}/{hair_color.value}.png"
            fg_path = f"hair/{style_value}/{age_group}/fg/{animation}/{hair_color.value}.png"
            return [bg_path, fg_path]
        else:
            # Direct style: single path
            return [f"hair/{style_value}/{age_group}/{animation}/{hair_color.value}.png"]

    @staticmethod
    def facial_hair(
        facial_hair_style: FacialHairStyle,
        facial_hair_color: HairColor,
        animation: str = "walk",
    ) -> str:
        """
        Get the path for a facial hair (beard/mustache) sprite sheet.

        Args:
            facial_hair_style: Facial hair style (beards, mustaches)
            facial_hair_color: Facial hair color
            animation: Animation type (walk, idle, slash, etc.)

        Returns:
            Path like "beards/beard/basic/walk/black.png" or "beards/mustache/basic/walk/black.png"
        """
        # Handle "none" specially - no sprite needed
        if facial_hair_style == FacialHairStyle.NONE:
            return ""

        # Handle "stubble" - falls under beard directory
        if facial_hair_style == FacialHairStyle.STUBBLE:
            return f"beards/beard/5oclock_shadow/{animation}/{facial_hair_color.value}.png"

        # Map FacialHairStyle enum values to actual directory names
        # Color is controlled separately via facial_hair_color parameter
        if facial_hair_style == FacialHairStyle.BEARD:
            return f"beards/beard/basic/{animation}/{facial_hair_color.value}.png"
        elif facial_hair_style == FacialHairStyle.MUSTACHE:
            return f"beards/mustache/basic/{animation}/{facial_hair_color.value}.png"
        elif facial_hair_style == FacialHairStyle.GOATEE:
            return f"beards/beard/trimmed/{animation}/{facial_hair_color.value}.png"

        # Default fallback (should never reach here)
        return ""

    @classmethod
    def clothing_shirt(
        cls,
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

        # Handle animation fallback for missing idle
        style_name = shirt_style.value
        actual_animation = cls._get_clothing_animation(style_name, body_type, animation)

        # Handle vest - no female/thin variant exists, only male
        if shirt_style == ClothingStyle.VEST:
            if body_type == BodyType.FEMALE:
                return ""  # Skip vest layer for female body type
            return f"torso/clothes/vest/{body_type.value}/{actual_animation}/{shirt_color.value}.png"

        # Handle nested directory structure for longsleeve variants
        # longsleeve2, longsleeve2_buttoned, etc. are inside longsleeve/ parent directory
        if shirt_style.value.startswith("longsleeve"):
            return f"torso/clothes/longsleeve/{shirt_style.value}/{body_type.value}/{actual_animation}/{shirt_color.value}.png"

        # Handle nested directory for shortsleeve: shortsleeve/shortsleeve/
        if shirt_style == ClothingStyle.SHORTSLEEVE:
            return f"torso/clothes/shortsleeve/shortsleeve/{body_type.value}/{actual_animation}/{shirt_color.value}.png"

        # Handle nested directory for sleeveless: sleeveless/sleeveless/
        if shirt_style == ClothingStyle.SLEEVELESS:
            return f"torso/clothes/sleeveless/sleeveless/{body_type.value}/{actual_animation}/{shirt_color.value}.png"

        return f"torso/clothes/{style_name}/{body_type.value}/{actual_animation}/{shirt_color.value}.png"

    @classmethod
    def clothing_pants(
        cls,
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

        # Handle animation fallback for missing idle
        style_name = pants_style.value
        actual_animation = cls._get_clothing_animation(style_name, body_type, animation)

        # Get correct body type directory
        # Note: pants uses "female" but leggings, shorts, and pantaloons use "thin" for female body type
        if pants_style in {PantsStyle.LEGGINGS, PantsStyle.SHORTS, PantsStyle.PANTALOONS}:
            body_dir = cls._get_body_dir("legs", body_type)
        else:
            body_dir = body_type.value

        # Handle shorts nested directory: shorts/shorts/
        if pants_style == PantsStyle.SHORTS:
            return f"legs/shorts/shorts/{body_dir}/{actual_animation}/{pants_color.value}.png"

        # Handle skirts sub-style: default to "plain" (supports both male/female)
        if pants_style == PantsStyle.SKIRT:
            return f"legs/skirts/plain/{body_dir}/{actual_animation}/{pants_color.value}.png"

        return f"legs/{style_name}/{body_dir}/{actual_animation}/{pants_color.value}.png"

    @classmethod
    def clothing_shoes(
        cls,
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

        # Get correct body type directory
        body_dir = cls._get_body_dir("feet", body_type)

        # Handle boots - requires "basic/" subdirectory
        if shoes_style == ShoesStyle.BOOTS:
            return f"feet/boots/basic/{body_dir}/{animation}/{shoes_color.value}.png"

        return f"feet/{shoes_style.value}/{body_dir}/{animation}/{shoes_color.value}.png"

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

        # Hair sprite(s) - may return 1 path (direct) or 2 paths (bg+fg for multi-layer)
        hair_paths = cls.hair_layers(appearance.hair_style, appearance.hair_color)
        paths.extend(hair_paths)

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
