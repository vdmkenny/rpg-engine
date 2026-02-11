"""
Unit tests for appearance system components.

Tests the core appearance data structures and validation logic.
"""

import pytest
from common.src.sprites import AppearanceData, AppearancePresets
from common.src.sprites.enums import (
    BodyType, SkinTone, HeadType, HairStyle, HairColor, EyeColor,
    ClothingStyle, PantsStyle, ShoesStyle, ClothingColor, FacialHairStyle
)


class TestAppearanceData:
    """Tests for AppearanceData dataclass."""

    def test_default_appearance_creation(self):
        """Default appearance should have sensible defaults."""
        appearance = AppearanceData()
        
        assert appearance.body_type == BodyType.MALE
        assert appearance.skin_tone == SkinTone.LIGHT
        assert appearance.head_type == HeadType.HUMAN_MALE
        assert appearance.hair_style == HairStyle.BUZZCUT
        assert appearance.hair_color == HairColor.DARK_BROWN
        assert appearance.eye_color == EyeColor.BROWN
        
        # Clothing defaults
        assert appearance.shirt_style == ClothingStyle.LONGSLEEVE
        assert appearance.shirt_color == ClothingColor.WHITE
        assert appearance.pants_style == PantsStyle.PANTS
        assert appearance.pants_color == ClothingColor.BROWN
        assert appearance.shoes_style == ShoesStyle.SHOES
        assert appearance.shoes_color == ClothingColor.BROWN
        
        # Facial hair defaults
        assert appearance.facial_hair_style == FacialHairStyle.NONE
        assert appearance.facial_hair_color == HairColor.DARK_BROWN

    def test_appearance_serialization(self):
        """Appearance should serialize to dict correctly."""
        appearance = AppearanceData(
            body_type=BodyType.FEMALE,
            skin_tone=SkinTone.BLACK,
            hair_style=HairStyle.LONG,
            hair_color=HairColor.BLONDE,
            shirt_style=ClothingStyle.BLOUSE,
            shirt_color=ClothingColor.BLUE,
        )
        
        data = appearance.to_dict()
        
        assert data["body_type"] == "female"
        assert data["skin_tone"] == "black"
        assert data["hair_style"] == "long"
        assert data["hair_color"] == "blonde"
        assert data["shirt_style"] == "blouse"
        assert data["shirt_color"] == "blue"

    def test_appearance_deserialization(self):
        """Appearance should deserialize from dict correctly."""
        data = {
            "body_type": "female",
            "skin_tone": "olive",
            "head_type": "human/female",
            "hair_style": "long",
            "hair_color": "black",
            "eye_color": "green",
            "facial_hair_style": "none",
            "facial_hair_color": "brown",
            "shirt_style": "tunic",
            "shirt_color": "red",
            "pants_style": "leggings",
            "pants_color": "black",
            "shoes_style": "boots",
            "shoes_color": "brown",
        }
        
        appearance = AppearanceData.from_dict(data)
        
        assert appearance.body_type == BodyType.FEMALE
        assert appearance.skin_tone == SkinTone.OLIVE
        assert appearance.head_type == HeadType.HUMAN_FEMALE
        assert appearance.hair_style == HairStyle.LONG
        assert appearance.hair_color == HairColor.BLACK
        assert appearance.eye_color == EyeColor.GREEN
        assert appearance.shirt_style == ClothingStyle.TUNIC
        assert appearance.shirt_color == ClothingColor.RED
        assert appearance.pants_style == PantsStyle.LEGGINGS
        assert appearance.pants_color == ClothingColor.BLACK
        assert appearance.shoes_style == ShoesStyle.BOOTS
        assert appearance.shoes_color == ClothingColor.BROWN

    def test_appearance_with_changes(self):
        """Appearance.with_changes should create modified copy."""
        base = AppearanceData()
        modified = base.with_changes(
            hair_color=HairColor.RED,
            shirt_color=ClothingColor.BLUE
        )
        
        # Original unchanged
        assert base.hair_color == HairColor.DARK_BROWN
        assert base.shirt_color == ClothingColor.WHITE
        
        # Modified has new values
        assert modified.hair_color == HairColor.RED
        assert modified.shirt_color == ClothingColor.BLUE
        
        # Other fields unchanged
        assert modified.body_type == base.body_type

    def test_appearance_hash_consistency(self):
        """Same appearance should produce same hash."""
        appearance1 = AppearanceData(body_type=BodyType.MALE)
        appearance2 = AppearanceData(body_type=BodyType.MALE)
        
        assert appearance1.compute_hash() == appearance2.compute_hash()

    def test_appearance_hash_uniqueness(self):
        """Different appearances should produce different hashes."""
        appearance1 = AppearanceData(body_type=BodyType.MALE)
        appearance2 = AppearanceData(body_type=BodyType.FEMALE)
        
        assert appearance1.compute_hash() != appearance2.compute_hash()

    def test_appearance_partial_dict(self):
        """from_dict should handle partial data with defaults."""
        data = {"body_type": "female"}
        appearance = AppearanceData.from_dict(data)
        
        assert appearance.body_type == BodyType.FEMALE
        assert appearance.skin_tone == SkinTone.LIGHT  # Default
        assert appearance.hair_style == HairStyle.BUZZCUT  # Default

    def test_appearance_none_dict(self):
        """from_dict should handle None with defaults."""
        appearance = AppearanceData.from_dict(None)
        
        assert appearance.body_type == BodyType.MALE
        assert appearance.skin_tone == SkinTone.LIGHT

    def test_appearance_invalid_enum_value(self):
        """from_dict should gracefully handle invalid enum values."""
        data = {
            "body_type": "invalid_body_type",
            "skin_tone": "light"
        }
        appearance = AppearanceData.from_dict(data)
        
        # Invalid values fall back to defaults
        assert appearance.body_type == BodyType.MALE  # Default fallback
        assert appearance.skin_tone == SkinTone.LIGHT


class TestAppearancePresets:
    """Tests for AppearancePresets."""

    def test_human_male_preset(self):
        """HUMAN_MALE preset should be valid."""
        preset = AppearancePresets.HUMAN_MALE
        
        assert preset.body_type == BodyType.MALE
        assert preset.skin_tone == SkinTone.LIGHT
        assert preset.head_type == HeadType.HUMAN_MALE
        assert preset.shirt_style == ClothingStyle.LONGSLEEVE
        assert preset.shirt_color == ClothingColor.WHITE
        assert preset.pants_style == PantsStyle.PANTS
        assert preset.pants_color == ClothingColor.BROWN

    def test_human_female_preset(self):
        """HUMAN_FEMALE preset should be valid."""
        preset = AppearancePresets.HUMAN_FEMALE
        
        assert preset.body_type == BodyType.FEMALE
        assert preset.head_type == HeadType.HUMAN_FEMALE
        assert preset.hair_style == HairStyle.LONG
        assert preset.shirt_style == ClothingStyle.BLOUSE

    def test_guard_preset(self):
        """GUARD preset should have appropriate clothing."""
        preset = AppearancePresets.GUARD
        
        assert preset.shirt_style == ClothingStyle.TUNIC
        assert preset.shirt_color == ClothingColor.NAVY
        assert preset.shoes_style == ShoesStyle.BOOTS
        assert preset.shoes_color == ClothingColor.BLACK

    def test_elder_preset(self):
        """ELDER preset should have gray hair and beard."""
        preset = AppearancePresets.ELDER
        
        assert preset.hair_style == HairStyle.BALD
        assert preset.hair_color == HairColor.GRAY
        assert preset.eye_color == EyeColor.GRAY
        assert preset.facial_hair_style == FacialHairStyle.BEARD

    def test_child_preset(self):
        """CHILD preset should have child body type."""
        preset = AppearancePresets.CHILD
        
        assert preset.body_type == BodyType.CHILD
        assert preset.head_type == HeadType.HUMAN_CHILD
        assert preset.shirt_style == ClothingStyle.SHORTSLEEVE
        assert preset.pants_style == PantsStyle.SHORTS

    def test_orc_preset(self):
        """ORC preset should have no shirt."""
        preset = AppearancePresets.ORC
        
        assert preset.skin_tone == SkinTone.GREEN
        assert preset.head_type == HeadType.ORC
        assert preset.shirt_style == ClothingStyle.NONE
        assert preset.facial_hair_style == FacialHairStyle.NONE

    def test_all_presets_valid(self):
        """All presets should produce valid serializable data."""
        presets = [
            AppearancePresets.HUMAN_MALE,
            AppearancePresets.HUMAN_FEMALE,
            AppearancePresets.GUARD,
            AppearancePresets.ELDER,
            AppearancePresets.SHOPKEEPER,
            AppearancePresets.ORC,
            AppearancePresets.SKELETON,
            AppearancePresets.ZOMBIE,
            AppearancePresets.CHILD,
        ]
        
        for preset in presets:
            # Should serialize without error
            data = preset.to_dict()
            assert isinstance(data, dict)
            
            # Should deserialize back
            restored = AppearanceData.from_dict(data)
            assert isinstance(restored, AppearanceData)


class TestClothingEnums:
    """Tests for clothing-related enums."""

    def test_clothing_style_values(self):
        """ClothingStyle should have expected values."""
        assert ClothingStyle.NONE.value == "none"
        assert ClothingStyle.LONGSLEEVE.value == "longsleeve2"
        assert ClothingStyle.SHORTSLEEVE.value == "shortsleeve"
        assert ClothingStyle.TUNIC.value == "tunic"
        assert ClothingStyle.BLOUSE.value == "blouse"

    def test_pants_style_values(self):
        """PantsStyle should have expected values."""
        assert PantsStyle.NONE.value == "none"
        assert PantsStyle.PANTS.value == "pants"
        assert PantsStyle.SHORTS.value == "shorts"
        assert PantsStyle.LEGGINGS.value == "leggings"

    def test_shoes_style_values(self):
        """ShoesStyle should have expected values."""
        assert ShoesStyle.NONE.value == "none"
        assert ShoesStyle.SHOES.value == "shoes/basic"
        assert ShoesStyle.BOOTS.value == "boots"
        assert ShoesStyle.SANDALS.value == "sandals"

    def test_clothing_color_values(self):
        """ClothingColor should have expected values."""
        colors = [
            ClothingColor.WHITE, ClothingColor.BLACK, ClothingColor.BROWN,
            ClothingColor.BLUE, ClothingColor.RED, ClothingColor.GREEN,
        ]
        for color in colors:
            assert isinstance(color.value, str)
            assert len(color.value) > 0


class TestFacialHairEnums:
    """Tests for facial hair enums."""

    def test_facial_hair_style_values(self):
        """FacialHairStyle should have expected values."""
        assert FacialHairStyle.NONE.value == "none"
        assert FacialHairStyle.STUBBLE.value == "stubble"
        assert FacialHairStyle.BEARD.value == "beard"
        assert FacialHairStyle.MUSTACHE.value == "mustache"
        assert FacialHairStyle.GOATEE.value == "goatee"
