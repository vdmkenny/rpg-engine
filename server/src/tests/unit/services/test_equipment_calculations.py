"""
Unit tests for equipment stat calculations.
"""

import pytest

from server.src.core.items import EquipmentSlot
from server.src.services.equipment_service import EquipmentService


class TestEquipmentStatCalculations:
    """Test equipment stat calculation logic."""

    def test_empty_equipment_zero_stats(self):
        """Empty equipment should return zero stats."""
        empty_equipment = {}
        
        stats = EquipmentService._calculate_stats_from_equipment(empty_equipment)
        
        assert stats.attack_bonus == 0
        assert stats.strength_bonus == 0
        assert stats.physical_defence_bonus == 0
        assert stats.health_bonus == 0

    def test_single_item_stats_calculation(self):
        """Single equipped item should contribute its stats."""
        mock_item = {
            "attack_bonus": 4,
            "strength_bonus": 3,
            "physical_defence_bonus": 0,
            "magic_defence_bonus": 0,
            "health_bonus": 0,
            "magic_attack_bonus": 0,
            "speed_bonus": 0,
        }
        
        equipment = {EquipmentSlot.WEAPON.value: mock_item}
        stats = EquipmentService._calculate_stats_from_equipment(equipment)
        
        assert stats.attack_bonus == 4
        assert stats.strength_bonus == 3

    def test_multiple_items_aggregate_stats(self):
        """Multiple items should aggregate stats."""
        weapon = {
            "attack_bonus": 4,
            "strength_bonus": 3,
            "physical_defence_bonus": 0,
            "magic_defence_bonus": 0,
            "health_bonus": 0,
            "magic_attack_bonus": 0,
            "speed_bonus": 0,
        }
        helmet = {
            "attack_bonus": 0,
            "strength_bonus": 0,
            "physical_defence_bonus": 2,
            "magic_defence_bonus": 0,
            "health_bonus": 0,
            "magic_attack_bonus": -1,
            "speed_bonus": 0,
        }
        platebody = {
            "attack_bonus": 0,
            "strength_bonus": 0,
            "physical_defence_bonus": 5,
            "magic_defence_bonus": 1,
            "health_bonus": 3,
            "magic_attack_bonus": -2,
            "speed_bonus": -1,
        }
        
        equipment = {
            EquipmentSlot.WEAPON.value: weapon,
            EquipmentSlot.HEAD.value: helmet,
            EquipmentSlot.BODY.value: platebody,
        }
        
        stats = EquipmentService._calculate_stats_from_equipment(equipment)
        
        assert stats.attack_bonus == 4
        assert stats.strength_bonus == 3
        assert stats.physical_defence_bonus == 7
        assert stats.magic_defence_bonus == 1
        assert stats.health_bonus == 3
        assert stats.magic_attack_bonus == -3
        assert stats.speed_bonus == -1

    def test_negative_stats_reduce_total(self):
        """Negative stats should reduce totals."""
        platebody = {
            "attack_bonus": 0,
            "strength_bonus": 0,
            "physical_defence_bonus": 5,
            "magic_defence_bonus": 1,
            "health_bonus": 3,
            "magic_attack_bonus": -2,
            "speed_bonus": -1,
        }
        
        equipment = {EquipmentSlot.BODY.value: platebody}
        stats = EquipmentService._calculate_stats_from_equipment(equipment)
        
        assert stats.magic_attack_bonus == -2
        assert stats.speed_bonus == -1

    def test_all_slots_can_contribute(self):
        """Test that all equipment slots can contribute to stats."""
        equipment = {}
        
        for slot in EquipmentSlot:
            equipment[slot.value] = {
                "attack_bonus": 1,
                "strength_bonus": 1,
                "physical_defence_bonus": 1,
                "magic_defence_bonus": 1,
                "health_bonus": 1,
                "magic_attack_bonus": 1,
                "speed_bonus": 1,
            }
        
        stats = EquipmentService._calculate_stats_from_equipment(equipment)
        
        slot_count = len(EquipmentSlot)
        assert stats.attack_bonus == slot_count
        assert stats.strength_bonus == slot_count
        assert stats.physical_defence_bonus == slot_count
        assert stats.magic_defence_bonus == slot_count
        assert stats.health_bonus == slot_count
        assert stats.magic_attack_bonus == slot_count
        assert stats.speed_bonus == slot_count

    def test_none_item_data_handled(self):
        """Test that None item data is handled gracefully."""
        equipment = {
            EquipmentSlot.WEAPON.value: None,
            EquipmentSlot.HEAD.value: {
                "attack_bonus": 5,
                "strength_bonus": 0,
                "physical_defence_bonus": 10,
                "magic_defence_bonus": 0,
                "health_bonus": 0,
                "magic_attack_bonus": 0,
                "speed_bonus": 0,
            }
        }
        
        stats = EquipmentService._calculate_stats_from_equipment(equipment)
        
        assert stats.attack_bonus == 5
        assert stats.physical_defence_bonus == 10


class TestEquipmentSlotEnum:
    """Test EquipmentSlot enum values."""

    def test_equipment_slot_values(self):
        """Test that EquipmentSlot enum has expected values."""
        assert EquipmentSlot.HEAD.value == "head"
        assert EquipmentSlot.BODY.value == "body"
        assert EquipmentSlot.LEGS.value == "legs"
        assert EquipmentSlot.BOOTS.value == "boots"
        assert EquipmentSlot.GLOVES.value == "gloves"
        assert EquipmentSlot.WEAPON.value == "weapon"
        assert EquipmentSlot.SHIELD.value == "shield"
        assert EquipmentSlot.AMMO.value == "ammo"
        assert EquipmentSlot.RING.value == "ring"
        assert EquipmentSlot.AMULET.value == "amulet"
        assert EquipmentSlot.CAPE.value == "cape"

    def test_equipment_slot_from_string(self):
        """Test that EquipmentSlot can be created from string."""
        assert EquipmentSlot("head") == EquipmentSlot.HEAD
        assert EquipmentSlot("weapon") == EquipmentSlot.WEAPON
        assert EquipmentSlot("ammo") == EquipmentSlot.AMMO
