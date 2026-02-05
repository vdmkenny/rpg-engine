"""
Unit tests for skill XP formulas and calculations.

Pure unit tests - no database, no managers, just math.
"""

import pytest

from server.src.core.skills import (
    SkillType,
    SkillCategory,
    MAX_LEVEL,
    HITPOINTS_START_LEVEL,
    base_xp_for_level,
    xp_for_level,
    level_for_xp,
    xp_to_next_level,
    xp_for_current_level,
    progress_to_next_level,
    _base_xp_table,
    get_skill_xp_multiplier,
)


class TestXPFormula:
    """Test the XP formula calculations."""

    def test_level_1_requires_zero_xp(self):
        """Level 1 should require 0 XP."""
        assert base_xp_for_level(1) == 0
        assert xp_for_level(1) == 0
        assert xp_for_level(1, xp_multiplier=0.5) == 0
        assert xp_for_level(1, xp_multiplier=2.0) == 0

    def test_level_2_xp_threshold(self):
        """Level 2 should require a small amount of XP."""
        xp = base_xp_for_level(2)
        # Based on RS formula: floor((1 + 300 * 2^(1/7)) / 4) ≈ 83
        assert xp > 0
        assert xp < 100

    def test_level_99_xp_approximately_13m(self):
        """Level 99 should require approximately 13 million XP with 1.0 multiplier."""
        xp = base_xp_for_level(99)
        # Level 99 is approximately 13,034,431 XP
        assert 13_000_000 <= xp <= 13_100_000

    def test_xp_multiplier_scales_requirements(self):
        """XP multiplier should scale requirements proportionally."""
        base = base_xp_for_level(50)
        
        assert xp_for_level(50, xp_multiplier=1.0) == base
        assert xp_for_level(50, xp_multiplier=0.5) == int(base * 0.5)
        assert xp_for_level(50, xp_multiplier=2.0) == int(base * 2.0)

    def test_xp_table_is_monotonically_increasing(self):
        """XP requirements should always increase with level."""
        xp_table = _base_xp_table(MAX_LEVEL)
        for i in range(1, len(xp_table)):
            assert xp_table[i] > xp_table[i - 1], f"XP should increase at level {i + 1}"

    def test_level_boundaries_with_default_multiplier(self):
        """Test that level boundaries are correctly detected."""
        # At exactly the XP for level 50, should be level 50
        xp_50 = xp_for_level(50)
        assert level_for_xp(xp_50) == 50
        
        # One XP less should be level 49
        assert level_for_xp(xp_50 - 1) == 49
        
        # One XP more should still be level 50
        assert level_for_xp(xp_50 + 1) == 50

    def test_level_boundaries_with_multiplier(self):
        """Test level boundaries with non-default multipliers."""
        multiplier = 0.5
        xp_50 = xp_for_level(50, multiplier)
        
        assert level_for_xp(xp_50, multiplier) == 50
        assert level_for_xp(xp_50 - 1, multiplier) == 49

    def test_level_for_zero_xp(self):
        """Zero XP should be level 1."""
        assert level_for_xp(0) == 1
        assert level_for_xp(0, xp_multiplier=0.5) == 1

    def test_level_for_negative_xp(self):
        """Negative XP should be level 1 (minimum)."""
        assert level_for_xp(-100) == 1
        assert level_for_xp(-1) == 1

    def test_xp_to_next_level_at_threshold(self):
        """XP to next level should return full XP requirement at threshold."""
        xp_50 = xp_for_level(50)
        xp_51 = xp_for_level(51)
        # At level 50 threshold, need XP to reach level 51
        expected_xp_needed = xp_51 - xp_50
        assert xp_to_next_level(xp_50) == expected_xp_needed

    def test_xp_to_next_level_between_levels(self):
        """XP to next level should decrease as we approach threshold."""
        xp_50 = xp_for_level(50)
        xp_51 = xp_for_level(51)
        
        # Halfway between level 50 and 51
        halfway = (xp_50 + xp_51) // 2
        needed = xp_to_next_level(halfway)
        expected = xp_51 - halfway
        assert needed == expected
        assert needed > 0
        assert needed < (xp_51 - xp_50)

    def test_xp_to_next_level_at_max(self):
        """XP to next level should be 0 at max level."""
        xp_99 = xp_for_level(99)
        assert xp_to_next_level(xp_99) == 0

    def test_progress_to_next_level(self):
        """Progress should be 0% at start and approach 100% near next threshold."""
        xp_50 = xp_for_level(50)
        xp_51 = xp_for_level(51)
        
        # At exact level 50 threshold (start of level), progress should be 0%
        assert progress_to_next_level(xp_50) == 0.0
        
        # Just before level 51, progress should be close to 100%
        almost_51 = xp_51 - 1
        progress_almost = progress_to_next_level(almost_51)
        assert progress_almost > 99.0
        
        # Halfway should be ~50%
        halfway = (xp_50 + xp_51) // 2
        progress = progress_to_next_level(halfway)
        assert 40.0 < progress < 60.0  # Allow some rounding variance

    def test_xp_for_current_level(self):
        """XP for current level should return the threshold."""
        assert xp_for_current_level(0) == 0  # Level 1
        assert xp_for_current_level(xp_for_level(2)) == xp_for_level(2)  # Level 2
        
        halfway_to_50 = (xp_for_level(49) + xp_for_level(50)) // 2
        assert xp_for_current_level(halfway_to_50) == xp_for_level(49)


class TestSkillMetadata:
    """Test skill metadata and categorization."""

    def test_all_skills_have_categories(self):
        """Every skill type should have a defined category."""
        for skill_type in SkillType:
            category = skill_type.value.category
            assert category is not None
            assert isinstance(category, SkillCategory)

    def test_all_skills_have_multipliers(self):
        """Every skill type should have an XP multiplier."""
        for skill_type in SkillType:
            multiplier = get_skill_xp_multiplier(skill_type)
            assert multiplier > 0
            assert isinstance(multiplier, (int, float))

    def test_hitpoints_has_correct_starting_level(self):
        """Hitpoints should start at level 10."""
        assert HITPOINTS_START_LEVEL == 10

    def test_max_level_is_reasonable(self):
        """Max level should be 99 (classic RPG convention)."""
        assert MAX_LEVEL == 99


class TestSkillCategories:
    """Test skill categorization."""

    def test_combat_skills_category(self):
        """Combat skills should have combat category."""
        combat_skills = [
            SkillType.ATTACK,
            SkillType.STRENGTH,
            SkillType.DEFENCE,
            SkillType.HITPOINTS,
        ]
        for skill in combat_skills:
            assert skill.value.category == SkillCategory.COMBAT

    def test_gathering_skills_category(self):
        """Gathering skills should have gathering category."""
        gathering_skills = [
            SkillType.MINING,
            SkillType.WOODCUTTING,
            SkillType.FISHING,
        ]
        for skill in gathering_skills:
            assert skill.value.category == SkillCategory.GATHERING
