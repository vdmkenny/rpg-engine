"""
Comprehensive validation tests for equipment sprite paths.

Validates that all equipment items generate valid paths with correct
body type directories and idle animation fallbacks.
"""

import os
from pathlib import Path
import pytest

from common.src.sprites import (
    EquipmentSprite,
    EQUIPMENT_SPRITES,
    EQUIPMENT_BODY_TYPE_MAP,
    get_equipment_sprite,
    MetalTier,
)


SPRITES_DIR = Path(__file__).parent.parent.parent.parent.parent.parent / "server" / "sprites" / "lpc"

BODY_TYPES = ["male", "female", "child", "teen"]
ANIMATIONS = ["idle", "walk", "slash"]
LAYERS = ["fg", "bg"]


def get_full_path(relative_path: str) -> Path:
    """Convert relative sprite path to full filesystem path."""
    return SPRITES_DIR / relative_path


class TestEquipmentPathGeneration:
    """Test that all equipment items generate valid paths."""

    def test_all_items_have_valid_paths(self):
        """Every equipment item should generate valid paths."""
        errors = []
        
        for sprite_id, sprite in EQUIPMENT_SPRITES.items():
            for animation in ANIMATIONS:
                if animation == "slash" and not sprite.has_layers:
                    continue
                    
                for body_type in BODY_TYPES:
                    try:
                        if sprite.has_layers:
                            for layer in LAYERS:
                                path = sprite.get_path(
                                    animation=animation,
                                    layer=layer,
                                    body_type=body_type
                                )
                                self._validate_path(path, sprite_id, animation, body_type, layer)
                        else:
                            path = sprite.get_path(
                                animation=animation,
                                body_type=body_type
                            )
                            self._validate_path(path, sprite_id, animation, body_type)
                    except Exception as e:
                        errors.append(f"{sprite_id} ({animation}/{body_type}): {str(e)}")
        
        if errors:
            pytest.fail("Path generation errors:\n" + "\n".join(errors[:20]))

    def _validate_path(self, path: str, sprite_id: str, animation: str, body_type: str, layer: str = None):
        """Validate a generated path has no obvious errors."""
        assert path.endswith(".png"), f"Path must end with .png: {path}"
        assert "//" not in path, f"Path has double slashes: {path}"
        assert not path.startswith("/"), f"Path must be relative: {path}"


class TestEquipmentIdleFallback:
    """Test idle animation fallback behavior."""

    def test_items_without_idle_use_walk_fallback(self):
        """Items with has_idle=False should use walk in path."""
        for sprite_id, sprite in EQUIPMENT_SPRITES.items():
            if not sprite.has_idle:
                path = sprite.get_path(animation="idle", body_type="male")
                assert "walk" in path, \
                    f"{sprite_id}: has_idle=False but idle path doesn't use walk: {path}"
                assert "idle" not in path, \
                    f"{sprite_id}: has_idle=False but path contains 'idle': {path}"

    def test_items_with_idle_use_idle_in_path(self):
        """Items with has_idle=True should use idle in path."""
        for sprite_id, sprite in EQUIPMENT_SPRITES.items():
            if sprite.has_idle:
                path = sprite.get_path(animation="idle", body_type="male")
                assert "idle" in path, \
                    f"{sprite_id}: has_idle=True but path doesn't contain 'idle': {path}"


class TestEquipmentBodyTypeInsertion:
    """Test body type directory insertion."""

    def test_armor_body_items_insert_body_type(self):
        """Armor body items should have body type in path."""
        armor_items = [
            "equip_copper_platebody", "equip_bronze_platebody",
            "equip_iron_platebody", "equip_steel_platebody",
            "equip_leather_body", "equip_hard_leather_body", "equip_studded_leather_body",
        ]
        
        for sprite_id in armor_items:
            sprite = get_equipment_sprite(sprite_id)
            assert sprite is not None, f"Missing sprite: {sprite_id}"
            assert sprite.body_type_category is not None, \
                f"{sprite_id}: Missing body_type_category"
            
            path = sprite.get_path(animation="walk", body_type="male")
            assert sprite.body_type_category == "armor_body", \
                f"{sprite_id}: Expected armor_body category"
            assert "male" in path, f"{sprite_id}: Missing body type in path: {path}"

    def test_armor_legs_items_insert_body_type(self):
        """Armor legs items should have body type in path."""
        legs_items = [
            "equip_copper_platelegs", "equip_bronze_platelegs",
            "equip_iron_platelegs", "equip_steel_platelegs",
            "equip_leather_chaps", "equip_hard_leather_chaps", "equip_studded_leather_chaps",
        ]
        
        for sprite_id in legs_items:
            sprite = get_equipment_sprite(sprite_id)
            assert sprite is not None, f"Missing sprite: {sprite_id}"
            assert sprite.body_type_category is not None, \
                f"{sprite_id}: Missing body_type_category"
            
            path = sprite.get_path(animation="walk", body_type="male")
            assert sprite.body_type_category == "armor_legs", \
                f"{sprite_id}: Expected armor_legs category"
            assert "male" in path, f"{sprite_id}: Missing body type in path: {path}"

    def test_helmet_items_use_adult_directory(self):
        """Helmet items should use adult body type directory."""
        helmets = [
            "equip_copper_helmet", "equip_bronze_helmet",
            "equip_iron_helmet", "equip_steel_helmet",
        ]
        
        for sprite_id in helmets:
            sprite = get_equipment_sprite(sprite_id)
            path = sprite.get_path(animation="walk", body_type="male")
            assert "adult" in path, f"{sprite_id}: Should use adult directory: {path}"

    def test_shield_items_insert_body_type(self):
        """Shield items should have body type in path."""
        shields = [
            "equip_wooden_shield", "equip_copper_shield",
            "equip_bronze_shield", "equip_iron_shield", "equip_steel_shield",
        ]
        
        for sprite_id in shields:
            sprite = get_equipment_sprite(sprite_id)
            assert sprite.body_type_category == "shield", \
                f"{sprite_id}: Expected shield category"
            
            path = sprite.get_path(animation="walk", body_type="male")
            assert "male" in path, f"{sprite_id}: Missing body type in path: {path}"

    def test_gloves_items_insert_body_type(self):
        """Gloves items should have body type in path."""
        gloves = [
            "equip_leather_gloves", "equip_hard_leather_gloves", "equip_studded_leather_gloves",
        ]
        
        for sprite_id in gloves:
            sprite = get_equipment_sprite(sprite_id)
            assert sprite.body_type_category == "gloves", \
                f"{sprite_id}: Expected gloves category"
            
            path = sprite.get_path(animation="walk", body_type="male")
            assert "male" in path, f"{sprite_id}: Missing body type in path: {path}"

    def test_boots_items_insert_body_type(self):
        """Boots items should have body type in path."""
        boots = [
            "equip_leather_boots", "equip_hard_leather_boots", "equip_studded_leather_boots",
        ]
        
        for sprite_id in boots:
            sprite = get_equipment_sprite(sprite_id)
            assert sprite.body_type_category == "boots", \
                f"{sprite_id}: Expected boots category"
            
            path = sprite.get_path(animation="walk", body_type="male")
            assert "male" in path or "thin" in path, \
                f"{sprite_id}: Missing body type in path: {path}"


class TestEquipmentLeatherArmor:
    """Test leather armor configuration."""

    def test_leather_body_has_no_idle(self):
        """Leather body should not have idle animations."""
        sprite = get_equipment_sprite("equip_leather_body")
        assert sprite.has_idle is False, \
            "Leather body has no idle sprites on disk"
        
        path = sprite.get_path(animation="idle", body_type="male")
        assert "walk" in path, "Leather body should fallback to walk for idle"

    def test_leather_body_has_body_type_category(self):
        """Leather body should have armor_body category."""
        sprite = get_equipment_sprite("equip_leather_body")
        assert sprite.body_type_category == "armor_body", \
            "Leather body missing armor_body category"

    def test_all_leather_armor_items_categorized(self):
        """All leather armor items should have body_type_category."""
        leather_items = [
            "equip_leather_body", "equip_leather_chaps",
            "equip_hard_leather_body", "equip_hard_leather_chaps",
            "equip_studded_leather_body", "equip_studded_leather_chaps",
            "equip_leather_gloves", "equip_hard_leather_gloves", "equip_studded_leather_gloves",
            "equip_leather_boots", "equip_hard_leather_boots", "equip_studded_leather_boots",
        ]
        
        for sprite_id in leather_items:
            sprite = get_equipment_sprite(sprite_id)
            assert sprite.body_type_category is not None, \
                f"{sprite_id}: Missing body_type_category"


class TestEquipmentSpecificPaths:
    """Test specific path generation for key items."""

    def test_shortsword_paths_use_idle(self):
        """Shortswords (arming sword) should use idle animations."""
        sprite = get_equipment_sprite("equip_copper_shortsword")
        assert sprite.has_idle is True, "Shortsword should have idle (arming sword has idle)"
        
        idle_path = sprite.get_path(animation="idle", layer="fg")
        assert "idle" in idle_path, f"Shortsword idle path wrong: {idle_path}"
        assert "arming" in idle_path, f"Shortsword should use arming sword base: {idle_path}"

    def test_plate_armor_paths_with_body_type(self):
        """Plate armor paths should include body type directory."""
        sprite = get_equipment_sprite("equip_copper_platebody")
        path = sprite.get_path(animation="walk", body_type="male")
        expected = "torso/armour/plate/male/walk/copper.png"
        assert path == expected, f"Platebody path wrong: {path}"

    def test_helmet_paths_use_adult(self):
        """Helmet paths should use adult directory."""
        sprite = get_equipment_sprite("equip_copper_helmet")
        path = sprite.get_path(animation="walk", body_type="male")
        expected = "hat/helmet/barbarian/adult/walk/copper.png"
        assert path == expected, f"Helmet path wrong: {path}"

    def test_shield_paths_with_body_type(self):
        """Shield paths should include body type directory."""
        sprite = get_equipment_sprite("equip_wooden_shield")
        path = sprite.get_path(animation="walk", body_type="female")
        assert "female" in path, f"Shield path missing body type: {path}"
        assert "shield/kite" in path, f"Shield path wrong: {path}"

    def test_dagger_paths_no_idle(self):
        """Dagger paths should fallback to walk for idle."""
        sprite = get_equipment_sprite("equip_copper_dagger")
        idle_path = sprite.get_path(animation="idle")
        assert "walk" in idle_path, f"Dagger idle should fallback: {idle_path}"


class TestDiskValidationOptional:
    """Optional disk validation - skipped if sprites not downloaded."""

    @pytest.mark.skipif(not SPRITES_DIR.exists(), reason="LPC sprites not downloaded")
    def test_key_sprites_exist_on_disk(self):
        """Verify key sprite paths exist on disk."""
        key_items = [
            ("equip_copper_platebody", "male", "idle"),
            ("equip_copper_platebody", "male", "walk"),
            ("equip_copper_helmet", "male", "idle"),
            ("equip_copper_shortsword", None, "idle"),
            ("equip_leather_body", "male", "walk"),
        ]
        
        missing = []
        for sprite_id, body_type, animation in key_items:
            sprite = get_equipment_sprite(sprite_id)
            if sprite.has_layers and animation != "slash":
                for layer in ["fg", "bg"]:
                    path = sprite.get_path(
                        animation=animation,
                        body_type=body_type or "male",
                        layer=layer
                    )
                    full_path = get_full_path(path)
                    if not full_path.exists():
                        missing.append(f"{path}")
            else:
                path = sprite.get_path(
                    animation=animation,
                    body_type=body_type or "male"
                )
                full_path = get_full_path(path)
                if not full_path.exists():
                    missing.append(f"{path}")
        
        if missing:
            pytest.fail(f"Missing sprite files:\n" + "\n".join(missing))


class TestEquipmentMappingCompleteness:
    """Verify the equipment mapping is complete and consistent."""

    def test_all_sprites_have_required_fields(self):
        """All equipment sprites should have base_path and variant."""
        for sprite_id, sprite in EQUIPMENT_SPRITES.items():
            assert sprite.base_path, f"{sprite_id}: Missing base_path"
            assert sprite.variant, f"{sprite_id}: Missing variant"

    def test_armor_items_have_body_type_category(self):
        """Armor items should have body_type_category."""
        armor_keywords = ["plate", "leather", "chain", "helmet"]
        
        for sprite_id, sprite in EQUIPMENT_SPRITES.items():
            if any(kw in sprite_id for kw in armor_keywords):
                if "shield" in sprite_id:
                    continue
                assert sprite.body_type_category is not None, \
                    f"{sprite_id}: Armor item missing body_type_category"

    def test_weapons_do_not_have_body_type_category(self):
        """Weapons should not have body_type_category."""
        weapon_keywords = ["sword", "dagger", "mace", "axe", "bow", "club"]
        
        for sprite_id, sprite in EQUIPMENT_SPRITES.items():
            if any(kw in sprite_id for kw in weapon_keywords):
                assert sprite.body_type_category is None, \
                    f"{sprite_id}: Weapon should not have body_type_category"
