"""
Unit tests for combat calculations.

Tests pure calculation logic without dependencies:
- Hit chance calculations
- Max hit calculations
- Damage rolls
- XP calculations
"""

import pytest

from server.src.services.combat_service import CombatService, CombatStats
from server.src.core.skills import SkillType


class TestCombatCalculations:
    """Test combat calculation formulas"""

    def test_calculate_hit_chance_equal_stats(self):
        """Test hit chance with equal stats (should be ~50%)"""
        attacker = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )
        defender = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Defender"
        )

        hit_chance = CombatService.calculate_hit_chance(attacker, defender)
        assert 0.45 <= hit_chance <= 0.55, f"Expected ~50% hit chance, got {hit_chance}"

    def test_calculate_hit_chance_high_attack(self):
        """Test hit chance with high attack vs low defence (should be high)"""
        attacker = CombatStats(
            attack_level=50,
            strength_level=50,
            attack_bonus=50,
            strength_bonus=50,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )
        defender = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=1,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Defender"
        )

        hit_chance = CombatService.calculate_hit_chance(attacker, defender)
        assert hit_chance == 0.95, f"Expected max hit chance (0.95), got {hit_chance}"

    def test_calculate_hit_chance_high_defence(self):
        """Test hit chance with low attack vs high defence (should be low)"""
        attacker = CombatStats(
            attack_level=1,
            strength_level=1,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=1,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )
        defender = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=50,
            defence_bonus=50,
            current_hp=10,
            max_hp=10,
            name="Defender"
        )

        hit_chance = CombatService.calculate_hit_chance(attacker, defender)
        assert hit_chance == 0.05, f"Expected min hit chance (0.05), got {hit_chance}"

    def test_calculate_max_hit_no_bonuses(self):
        """Test max hit calculation with no bonuses"""
        attacker = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )

        max_hit = CombatService.calculate_max_hit(attacker)
        assert max_hit == 1, f"Expected max hit of 1, got {max_hit}"

    def test_calculate_max_hit_with_bonuses(self):
        """Test max hit calculation with strength bonuses"""
        attacker = CombatStats(
            attack_level=50,
            strength_level=50,
            attack_bonus=50,
            strength_bonus=50,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )

        max_hit = CombatService.calculate_max_hit(attacker)
        assert max_hit == 9, f"Expected max hit of 9, got {max_hit}"

    def test_calculate_max_hit_minimum(self):
        """Test max hit has minimum of 1"""
        attacker = CombatStats(
            attack_level=1,
            strength_level=1,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=1,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )

        max_hit = CombatService.calculate_max_hit(attacker)
        assert max_hit >= 1, f"Expected minimum max hit of 1, got {max_hit}"

    def test_roll_damage_on_miss(self):
        """Test damage is 0 on miss"""
        attacker = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )

        damage = CombatService.roll_damage(attacker, did_hit=False)
        assert damage == 0, f"Expected 0 damage on miss, got {damage}"

    def test_roll_damage_on_hit(self):
        """Test damage is between 0 and max_hit on hit"""
        attacker = CombatStats(
            attack_level=50,
            strength_level=50,
            attack_bonus=50,
            strength_bonus=50,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )

        max_hit = CombatService.calculate_max_hit(attacker)

        for _ in range(100):
            damage = CombatService.roll_damage(attacker, did_hit=True)
            assert 0 <= damage <= max_hit, f"Damage {damage} outside range [0, {max_hit}]"

    def test_calculate_combat_xp_no_damage(self):
        """Test XP calculation with no damage"""
        xp_rewards = CombatService.calculate_combat_xp(damage_dealt=0, defender_died=False)
        assert len(xp_rewards) == 0, "Expected no XP for 0 damage"

    def test_calculate_combat_xp_with_damage(self):
        """Test XP calculation with damage dealt"""
        damage = 5
        xp_rewards = CombatService.calculate_combat_xp(damage_dealt=damage, defender_died=False)

        assert SkillType.ATTACK in xp_rewards
        assert SkillType.STRENGTH in xp_rewards
        assert SkillType.HITPOINTS in xp_rewards

        assert xp_rewards[SkillType.ATTACK] == damage * 4
        assert xp_rewards[SkillType.STRENGTH] == damage * 4

        assert xp_rewards[SkillType.HITPOINTS] == int(damage * 4 / 3)

    def test_calculate_defensive_xp_on_miss(self):
        """Test defensive XP when attack misses (player dodges)"""
        xp_rewards = CombatService.calculate_defensive_xp(did_hit=False, damage_taken=0)

        assert SkillType.DEFENCE in xp_rewards
        assert xp_rewards[SkillType.DEFENCE] == 2
        assert SkillType.HITPOINTS not in xp_rewards

    def test_calculate_defensive_xp_on_hit(self):
        """Test defensive XP when attack hits (player takes damage)"""
        damage = 6
        xp_rewards = CombatService.calculate_defensive_xp(did_hit=True, damage_taken=damage)

        assert SkillType.HITPOINTS in xp_rewards
        assert xp_rewards[SkillType.HITPOINTS] == damage // 3
        assert SkillType.DEFENCE not in xp_rewards

    def test_calculate_defensive_xp_minimum_hp_xp(self):
        """Test defensive XP has minimum of 1 HP XP on hit"""
        damage = 1
        xp_rewards = CombatService.calculate_defensive_xp(did_hit=True, damage_taken=damage)

        assert SkillType.HITPOINTS in xp_rewards
        assert xp_rewards[SkillType.HITPOINTS] == 1

    def test_calculate_defensive_xp_zero_damage_hit(self):
        """Test defensive XP when hit but zero damage (e.g., 0 hit)"""
        xp_rewards = CombatService.calculate_defensive_xp(did_hit=True, damage_taken=0)

        assert len(xp_rewards) == 0
