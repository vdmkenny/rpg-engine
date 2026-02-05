"""
Tests for equipment sprite mapping system.

Tests the mapping from equipped_sprite_id to LPC paths and tint colors.
"""

import re
import pytest

from common.src.sprites import (
    EquipmentSprite,
    MetalTier,
    METAL_TINT_COLORS,
    EQUIPMENT_SPRITES,
    get_equipment_sprite,
    resolve_equipment,
    get_all_sprite_ids,
    validate_sprite_id,
    resolve_equipment_sprite,
)
from common.src.sprites.visual_state import EquippedVisuals


class TestMetalTiers:
    """Tests for MetalTier enum and tint colors."""
    
    def test_all_tiers_have_tint_colors(self):
        """Every metal tier should have a defined tint color."""
        for tier in MetalTier:
            assert tier in METAL_TINT_COLORS, f"Missing tint color for {tier}"
    
    def test_tint_colors_are_valid_hex(self):
        """All tint colors should be valid hex color codes."""
        hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        for tier, color in METAL_TINT_COLORS.items():
            assert hex_pattern.match(color), f"Invalid hex color for {tier}: {color}"


class TestEquipmentSprite:
    """Tests for EquipmentSprite dataclass."""
    
    def test_get_path_simple(self):
        """Simple sprites generate correct paths."""
        sprite = EquipmentSprite(
            base_path="weapon/sword/dagger",
            variant="dagger",
        )
        path = sprite.get_path(animation="walk")
        assert path == "weapon/sword/dagger/walk/dagger.png"
    
    def test_get_path_with_layers(self):
        """Layered sprites generate correct paths with layer subdirectory."""
        sprite = EquipmentSprite(
            base_path="weapon/sword/arming",
            variant="copper",
            has_layers=True,
        )
        path = sprite.get_path(animation="walk", layer="fg")
        assert path == "weapon/sword/arming/universal/fg/walk/copper.png"
        
        bg_path = sprite.get_path(animation="slash", layer="bg")
        assert bg_path == "weapon/sword/arming/universal/bg/slash/copper.png"
    
    def test_get_path_different_animations(self):
        """Paths change correctly for different animations."""
        sprite = EquipmentSprite(
            base_path="weapon/blunt/mace",
            variant="mace",
        )
        assert sprite.get_path(animation="walk") == "weapon/blunt/mace/walk/mace.png"
        assert sprite.get_path(animation="slash") == "weapon/blunt/mace/slash/mace.png"
        assert sprite.get_path(animation="hurt") == "weapon/blunt/mace/hurt/mace.png"


class TestEquipmentMapping:
    """Tests for the equipment sprite mapping."""
    
    def test_mapping_not_empty(self):
        """The equipment mapping should contain entries."""
        assert len(EQUIPMENT_SPRITES) > 0
    
    def test_all_shortswords_have_native_variants(self):
        """Shortswords should use LPC arming sword with native metal variants."""
        shortswords = [
            "equip_copper_shortsword",
            "equip_bronze_shortsword",
            "equip_iron_shortsword",
            "equip_steel_shortsword",
        ]
        for sprite_id in shortswords:
            sprite = get_equipment_sprite(sprite_id)
            assert sprite is not None, f"Missing mapping for {sprite_id}"
            assert "arming" in sprite.base_path, f"{sprite_id} should use arming sword"
            assert sprite.tint is None, f"{sprite_id} has native variant, should not have tint"
    
    def test_daggers_have_tints(self):
        """Daggers should have tint colors since LPC has no metal variants."""
        daggers = [
            "equip_copper_dagger",
            "equip_bronze_dagger",
            "equip_iron_dagger",
            "equip_steel_dagger",
        ]
        for sprite_id in daggers:
            sprite = get_equipment_sprite(sprite_id)
            assert sprite is not None, f"Missing mapping for {sprite_id}"
            assert sprite.tint is not None, f"{sprite_id} should have a tint color"
            assert sprite.tint.startswith("#"), f"{sprite_id} tint should be hex color"
    
    def test_different_tiers_have_different_tints(self):
        """Different metal tiers should have different tint colors."""
        copper = get_equipment_sprite("equip_copper_dagger")
        iron = get_equipment_sprite("equip_iron_dagger")
        
        assert copper is not None and iron is not None
        assert copper.tint != iron.tint, "Copper and iron should have different tints"
    
    def test_armor_with_native_variants(self):
        """Plate armor should use native LPC metal variants."""
        armor_pieces = [
            "equip_copper_helmet",
            "equip_bronze_platebody",
            "equip_iron_platelegs",
            "equip_steel_helmet",
        ]
        for sprite_id in armor_pieces:
            sprite = get_equipment_sprite(sprite_id)
            assert sprite is not None, f"Missing mapping for {sprite_id}"
            assert sprite.tint is None, f"{sprite_id} has native variant, should not have tint"
    
    def test_tools_mapped(self):
        """Tools should be mapped."""
        tools = [
            "equip_bronze_pickaxe",
            "equip_iron_pickaxe",
            "equip_bronze_axe",
            "equip_iron_axe",
        ]
        for sprite_id in tools:
            sprite = get_equipment_sprite(sprite_id)
            assert sprite is not None, f"Missing mapping for {sprite_id}"
            assert "tools" in sprite.base_path or "smash" in sprite.base_path


class TestLookupFunctions:
    """Tests for lookup helper functions."""
    
    def test_get_equipment_sprite_found(self):
        """get_equipment_sprite returns sprite for valid ID."""
        sprite = get_equipment_sprite("equip_copper_shortsword")
        assert sprite is not None
        assert isinstance(sprite, EquipmentSprite)
    
    def test_get_equipment_sprite_not_found(self):
        """get_equipment_sprite returns None for invalid ID."""
        sprite = get_equipment_sprite("equip_nonexistent_item")
        assert sprite is None
    
    def test_resolve_equipment_found(self):
        """resolve_equipment returns path and tint tuple."""
        path, tint = resolve_equipment("equip_copper_dagger")
        assert path is not None
        assert path.endswith(".png")
        assert tint is not None  # Dagger needs tint
    
    def test_resolve_equipment_no_tint(self):
        """resolve_equipment returns None tint for native variants."""
        path, tint = resolve_equipment("equip_copper_shortsword")
        assert path is not None
        assert tint is None  # Native variant, no tint
    
    def test_resolve_equipment_not_found(self):
        """resolve_equipment returns (None, None) for invalid ID."""
        path, tint = resolve_equipment("equip_nonexistent")
        assert path is None
        assert tint is None
    
    def test_get_all_sprite_ids(self):
        """get_all_sprite_ids returns all mapped IDs."""
        sprite_ids = get_all_sprite_ids()
        assert isinstance(sprite_ids, list)
        assert len(sprite_ids) > 0
        assert "equip_copper_shortsword" in sprite_ids
    
    def test_validate_sprite_id_valid(self):
        """validate_sprite_id returns True for valid ID."""
        assert validate_sprite_id("equip_copper_shortsword") is True
    
    def test_validate_sprite_id_invalid(self):
        """validate_sprite_id returns False for invalid ID."""
        assert validate_sprite_id("equip_nonexistent") is False


class TestResolveEquipmentSprite:
    """Tests for the resolve_equipment_sprite path function."""
    
    def test_resolve_returns_full_path(self):
        """resolve_equipment_sprite returns full path with lpc prefix."""
        path, tint = resolve_equipment_sprite("equip_copper_shortsword")
        assert path.startswith("lpc/")
        assert path.endswith(".png")
    
    def test_resolve_with_animation(self):
        """resolve_equipment_sprite uses specified animation."""
        walk_path, _ = resolve_equipment_sprite("equip_copper_shortsword", animation="walk")
        slash_path, _ = resolve_equipment_sprite("equip_copper_shortsword", animation="slash")
        
        assert "walk" in walk_path
        assert "slash" in slash_path
    
    def test_resolve_fallback_for_unknown(self):
        """Unknown sprite IDs get fallback path."""
        path, tint = resolve_equipment_sprite("equip_unknown_item")
        assert "unknown" in path
        assert tint is None


class TestEquippedVisualsWithTints:
    """Tests for EquippedVisuals with tint fields."""
    
    def test_to_dict_includes_tints(self):
        """to_dict should include tint fields when present."""
        visuals = EquippedVisuals(
            main_hand="equip_copper_dagger",
            main_hand_tint="#B87333",
        )
        data = visuals.to_dict()
        
        assert "main_hand" in data
        assert "main_hand_tint" in data
        assert data["main_hand_tint"] == "#B87333"
    
    def test_to_dict_excludes_none_tints(self):
        """to_dict should exclude None tint values."""
        visuals = EquippedVisuals(
            main_hand="equip_copper_shortsword",
            main_hand_tint=None,
        )
        data = visuals.to_dict()
        
        assert "main_hand" in data
        assert "main_hand_tint" not in data
    
    def test_from_dict_with_tints(self):
        """from_dict should restore tint fields."""
        data = {
            "head": "equip_copper_helmet",
            "body": "equip_copper_platebody",
            "body_tint": "#B87333",
        }
        visuals = EquippedVisuals.from_dict(data)
        
        assert visuals.head == "equip_copper_helmet"
        assert visuals.body == "equip_copper_platebody"
        assert visuals.body_tint == "#B87333"
        assert visuals.head_tint is None
    
    def test_from_equipment_map_extracts_tints(self):
        """from_equipment_map should look up tints from mapping."""
        # Simulate equipment map with items that have sprite IDs
        equipment = {
            "main_hand": {"sprite_id": "equip_copper_dagger"},
            "head": {"sprite_id": "equip_copper_helmet"},
        }
        visuals = EquippedVisuals.from_equipment_map(equipment)
        
        assert visuals.main_hand == "equip_copper_dagger"
        assert visuals.head == "equip_copper_helmet"
        
        # Dagger should have tint (no native variant)
        assert visuals.main_hand_tint is not None
        
        # Helmet should NOT have tint (native variant exists)
        assert visuals.head_tint is None
    
    def test_get_slot_tint(self):
        """get_slot_tint should return correct tint for slot."""
        from common.src.sprites.enums import EquipmentSlot
        
        visuals = EquippedVisuals(
            main_hand="equip_copper_dagger",
            main_hand_tint="#B87333",
        )
        
        assert visuals.get_slot_tint(EquipmentSlot.MAIN_HAND) == "#B87333"
        assert visuals.get_slot_tint(EquipmentSlot.HEAD) is None


class TestAllEquipmentMapped:
    """Verify all game equipment items have sprite mappings."""
    
    def test_all_weapon_tiers_mapped(self):
        """All weapon tiers should have sprite mappings."""
        weapon_types = ["dagger", "shortsword", "longsword", "mace", "battleaxe", "2h_sword"]
        tiers = ["copper", "bronze", "iron", "steel"]
        
        for tier in tiers:
            for weapon in weapon_types:
                sprite_id = f"equip_{tier}_{weapon}"
                assert validate_sprite_id(sprite_id), f"Missing mapping for {sprite_id}"
    
    def test_all_armor_tiers_mapped(self):
        """All armor tiers should have sprite mappings."""
        armor_types = ["helmet", "platebody", "platelegs"]
        tiers = ["copper", "bronze", "iron", "steel"]
        
        for tier in tiers:
            for armor in armor_types:
                sprite_id = f"equip_{tier}_{armor}"
                assert validate_sprite_id(sprite_id), f"Missing mapping for {sprite_id}"
    
    def test_shields_mapped(self):
        """All shields should have sprite mappings."""
        shields = [
            "equip_wooden_shield",
            "equip_copper_shield",
            "equip_bronze_shield",
            "equip_iron_shield",
            "equip_steel_shield",
        ]
        for sprite_id in shields:
            assert validate_sprite_id(sprite_id), f"Missing mapping for {sprite_id}"
    
    def test_leather_armor_mapped(self):
        """Leather armor should have sprite mappings."""
        leather = [
            "equip_leather_body",
            "equip_leather_chaps",
            "equip_leather_boots",
            "equip_leather_gloves",
        ]
        for sprite_id in leather:
            assert validate_sprite_id(sprite_id), f"Missing mapping for {sprite_id}"
