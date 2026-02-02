"""
AppearanceData - Visual appearance attributes for humanoid entities.

Defines the base visual characteristics of a character (body, skin, head, hair, eyes).
This does NOT include equipment - see VisualState for the complete visual representation.

License: Part of the LPC sprite integration.
See server/sprites/CREDITS.csv for sprite attribution.
"""

from dataclasses import dataclass
from typing import Optional
import hashlib
import json

from .enums import (
    BodyType,
    SkinTone,
    HeadType,
    HairStyle,
    HairColor,
    EyeColor,
)


@dataclass(frozen=True)
class AppearanceData:
    """
    Visual appearance attributes for humanoid entities.
    
    Represents the "natural" appearance of a character - body type, skin,
    head shape, hair, and eyes. Equipment is handled separately.
    
    This class is immutable (frozen=True) to ensure hash stability.
    
    Attributes:
        body_type: Base body shape (male, female, child, etc.)
        skin_tone: Skin color variant
        head_type: Head shape and race
        hair_style: Hair style
        hair_color: Hair color
        eye_color: Eye color
    """
    body_type: BodyType = BodyType.MALE
    skin_tone: SkinTone = SkinTone.LIGHT
    head_type: HeadType = HeadType.HUMAN_MALE
    hair_style: HairStyle = HairStyle.SHORT
    hair_color: HairColor = HairColor.BROWN
    eye_color: EyeColor = EyeColor.BROWN
    
    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON/network serialization.
        
        Returns:
            Dictionary with all appearance fields as string values.
        """
        return {
            "body_type": self.body_type.value,
            "skin_tone": self.skin_tone.value,
            "head_type": self.head_type.value,
            "hair_style": self.hair_style.value,
            "hair_color": self.hair_color.value,
            "eye_color": self.eye_color.value,
        }
    
    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "AppearanceData":
        """
        Create AppearanceData from a dictionary.
        
        Handles missing fields gracefully with defaults.
        Handles both enum values (strings) and enum members.
        
        Args:
            data: Dictionary with appearance fields, or None for defaults.
            
        Returns:
            AppearanceData instance with provided or default values.
        """
        if data is None:
            return cls()
        
        def get_enum(enum_cls, value, default):
            """Safely get enum value, handling both strings and enum members."""
            if value is None:
                return default
            if isinstance(value, enum_cls):
                return value
            try:
                return enum_cls(value)
            except (ValueError, KeyError):
                return default
        
        return cls(
            body_type=get_enum(BodyType, data.get("body_type"), BodyType.MALE),
            skin_tone=get_enum(SkinTone, data.get("skin_tone"), SkinTone.LIGHT),
            head_type=get_enum(HeadType, data.get("head_type"), HeadType.HUMAN_MALE),
            hair_style=get_enum(HairStyle, data.get("hair_style"), HairStyle.SHORT),
            hair_color=get_enum(HairColor, data.get("hair_color"), HairColor.BROWN),
            eye_color=get_enum(EyeColor, data.get("eye_color"), EyeColor.BROWN),
        )
    
    def compute_hash(self) -> str:
        """
        Compute a stable hash for this appearance configuration.
        
        The hash is deterministic - same appearance always produces same hash.
        Used for efficient network broadcasting (send hash instead of full data).
        
        Returns:
            12-character hexadecimal hash string.
        """
        data_str = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()[:12]
    
    def with_changes(self, **kwargs) -> "AppearanceData":
        """
        Create a new AppearanceData with some fields changed.
        
        Since AppearanceData is immutable, this returns a new instance.
        
        Args:
            **kwargs: Fields to change (body_type, skin_tone, etc.)
            
        Returns:
            New AppearanceData with the specified changes.
            
        Example:
            new_appearance = appearance.with_changes(hair_color=HairColor.BLONDE)
        """
        current = self.to_dict()
        
        # Convert enum values to their value strings if needed
        for key, value in kwargs.items():
            if hasattr(value, 'value'):
                current[key] = value.value
            else:
                current[key] = value
        
        return AppearanceData.from_dict(current)


# =============================================================================
# Presets - Common appearance configurations
# =============================================================================

class AppearancePresets:
    """
    Common appearance presets for NPCs and testing.
    
    These provide sensible defaults for various character archetypes.
    """
    
    # Human male defaults
    HUMAN_MALE = AppearanceData(
        body_type=BodyType.MALE,
        skin_tone=SkinTone.LIGHT,
        head_type=HeadType.HUMAN_MALE,
        hair_style=HairStyle.SHORT,
        hair_color=HairColor.BROWN,
        eye_color=EyeColor.BROWN,
    )
    
    # Human female defaults
    HUMAN_FEMALE = AppearanceData(
        body_type=BodyType.FEMALE,
        skin_tone=SkinTone.LIGHT,
        head_type=HeadType.HUMAN_FEMALE,
        hair_style=HairStyle.LONG,
        hair_color=HairColor.BRUNETTE,
        eye_color=EyeColor.GREEN,
    )
    
    # Guard NPC
    GUARD = AppearanceData(
        body_type=BodyType.MALE,
        skin_tone=SkinTone.OLIVE,
        head_type=HeadType.HUMAN_MALE,
        hair_style=HairStyle.SHORT,
        hair_color=HairColor.BLACK,
        eye_color=EyeColor.BROWN,
    )
    
    # Elder NPC
    ELDER = AppearanceData(
        body_type=BodyType.MALE,
        skin_tone=SkinTone.LIGHT,
        head_type=HeadType.HUMAN_MALE_ELDERLY,
        hair_style=HairStyle.BALD,
        hair_color=HairColor.GRAY,
        eye_color=EyeColor.GRAY,
    )
    
    # Shopkeeper NPC
    SHOPKEEPER = AppearanceData(
        body_type=BodyType.MALE,
        skin_tone=SkinTone.BROWN,
        head_type=HeadType.HUMAN_MALE,
        hair_style=HairStyle.PARTED,
        hair_color=HairColor.BROWN,
        eye_color=EyeColor.BROWN,
    )
    
    # Orc
    ORC = AppearanceData(
        body_type=BodyType.MALE,
        skin_tone=SkinTone.GREEN,
        head_type=HeadType.ORC,
        hair_style=HairStyle.MOHAWK,
        hair_color=HairColor.BLACK,
        eye_color=EyeColor.RED,
    )
    
    # Skeleton
    SKELETON = AppearanceData(
        body_type=BodyType.SKELETON,
        skin_tone=SkinTone.LIGHT,  # Not visible for skeleton
        head_type=HeadType.SKELETON,
        hair_style=HairStyle.BALD,
        hair_color=HairColor.BLACK,  # Not visible
        eye_color=EyeColor.RED,  # Glowing eyes
    )
    
    # Zombie
    ZOMBIE = AppearanceData(
        body_type=BodyType.ZOMBIE,
        skin_tone=SkinTone.ZOMBIE_GREEN,
        head_type=HeadType.ZOMBIE,
        hair_style=HairStyle.MESSY1,
        hair_color=HairColor.GRAY,
        eye_color=EyeColor.YELLOW,
    )
    
    # Child NPC
    CHILD = AppearanceData(
        body_type=BodyType.CHILD,
        skin_tone=SkinTone.LIGHT,
        head_type=HeadType.HUMAN_CHILD,
        hair_style=HairStyle.MESSY1,
        hair_color=HairColor.BLONDE,
        eye_color=EyeColor.BLUE,
    )
