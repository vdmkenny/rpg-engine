"""
Tests for the skills system.

Tests cover:
- XP formula calculations (with multipliers)
- Level calculations from XP
- Skill definitions and metadata
- Skill service operations (sync, grant, add XP)
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

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
)
from server.src.models.skill import Skill, PlayerSkill
from server.src.services.skill_service import SkillService, LevelUpResult


# =============================================================================
# XP Formula Tests
# =============================================================================


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
        """Negative XP should be treated as level 1."""
        assert level_for_xp(-100) == 1

    def test_level_caps_at_max_level(self):
        """Level should not exceed MAX_LEVEL even with excessive XP."""
        # 100 million XP should still be level 99
        assert level_for_xp(100_000_000) == MAX_LEVEL
        assert level_for_xp(100_000_000, xp_multiplier=0.1) == MAX_LEVEL


class TestXPToNextLevel:
    """Test XP remaining calculations."""

    def test_xp_to_next_at_level_start(self):
        """At the start of a level, XP to next should be the full level gap."""
        xp_at_50 = xp_for_level(50)
        xp_at_51 = xp_for_level(51)
        
        xp_to_next = xp_to_next_level(xp_at_50)
        assert xp_to_next == xp_at_51 - xp_at_50

    def test_xp_to_next_at_max_level(self):
        """At max level, XP to next should be 0."""
        xp_at_99 = xp_for_level(99)
        assert xp_to_next_level(xp_at_99) == 0
        assert xp_to_next_level(xp_at_99 + 1000) == 0

    def test_xp_to_next_with_multiplier(self):
        """XP to next should respect the multiplier."""
        multiplier = 0.5
        xp_at_50 = xp_for_level(50, multiplier)
        xp_at_51 = xp_for_level(51, multiplier)
        
        xp_to_next = xp_to_next_level(xp_at_50, multiplier)
        assert xp_to_next == xp_at_51 - xp_at_50


class TestProgressCalculation:
    """Test progress percentage calculations."""

    def test_progress_at_level_start(self):
        """Progress should be 0% at the start of a level."""
        xp_at_50 = xp_for_level(50)
        progress = progress_to_next_level(xp_at_50)
        assert progress == 0.0

    def test_progress_at_max_level(self):
        """Progress should be 100% at max level."""
        xp_at_99 = xp_for_level(99)
        assert progress_to_next_level(xp_at_99) == 100.0
        assert progress_to_next_level(xp_at_99 + 1000) == 100.0

    def test_progress_midway_through_level(self):
        """Progress should be approximately 50% halfway through a level."""
        xp_at_50 = xp_for_level(50)
        xp_at_51 = xp_for_level(51)
        midpoint_xp = xp_at_50 + (xp_at_51 - xp_at_50) // 2
        
        progress = progress_to_next_level(midpoint_xp)
        assert 45.0 <= progress <= 55.0  # Allow some rounding variance


class TestXPForCurrentLevel:
    """Test XP threshold for current level."""

    def test_xp_for_current_level_exact(self):
        """Should return exact threshold when at level boundary."""
        xp_at_50 = xp_for_level(50)
        assert xp_for_current_level(xp_at_50) == xp_at_50

    def test_xp_for_current_level_mid_level(self):
        """Should return start of current level when mid-level."""
        xp_at_50 = xp_for_level(50)
        xp_at_51 = xp_for_level(51)
        mid_xp = xp_at_50 + 1000
        
        assert xp_for_current_level(mid_xp) == xp_at_50


# =============================================================================
# Skill Definition Tests
# =============================================================================


class TestSkillDefinitions:
    """Test skill enum and metadata."""

    def test_all_skills_have_categories(self):
        """Every skill should have a valid category."""
        for skill in SkillType:
            assert isinstance(skill.value.category, SkillCategory)

    def test_all_skills_have_names(self):
        """Every skill should have a non-empty name."""
        for skill in SkillType:
            assert skill.value.name
            assert len(skill.value.name) > 0

    def test_all_skills_have_descriptions(self):
        """Every skill should have a non-empty description."""
        for skill in SkillType:
            assert skill.value.description
            assert len(skill.value.description) > 0

    def test_from_name_case_insensitive(self):
        """from_name should be case-insensitive."""
        assert SkillType.from_name("attack") == SkillType.ATTACK
        assert SkillType.from_name("ATTACK") == SkillType.ATTACK
        assert SkillType.from_name("Attack") == SkillType.ATTACK

    def test_from_name_returns_none_for_invalid(self):
        """from_name should return None for invalid skill names."""
        assert SkillType.from_name("invalid_skill") is None
        assert SkillType.from_name("") is None

    def test_all_skill_names_returns_lowercase(self):
        """all_skill_names should return lowercase names."""
        names = SkillType.all_skill_names()
        assert len(names) == len(SkillType)
        for name in names:
            assert name == name.lower()

    def test_expected_skills_exist(self):
        """All expected skills should be defined."""
        expected = ["attack", "strength", "defence", "mining", "fishing", "woodcutting", "cooking", "crafting", "hitpoints"]
        actual = SkillType.all_skill_names()
        for skill in expected:
            assert skill in actual, f"Missing skill: {skill}"

    def test_combat_skills_have_combat_category(self):
        """Combat skills should have COMBAT category."""
        combat_skills = [SkillType.ATTACK, SkillType.STRENGTH, SkillType.DEFENCE]
        for skill in combat_skills:
            assert skill.value.category == SkillCategory.COMBAT

    def test_gathering_skills_have_gathering_category(self):
        """Gathering skills should have GATHERING category."""
        gathering_skills = [SkillType.MINING, SkillType.FISHING, SkillType.WOODCUTTING]
        for skill in gathering_skills:
            assert skill.value.category == SkillCategory.GATHERING

    def test_crafting_skills_have_crafting_category(self):
        """Crafting skills should have CRAFTING category."""
        crafting_skills = [SkillType.COOKING, SkillType.CRAFTING]
        for skill in crafting_skills:
            assert skill.value.category == SkillCategory.CRAFTING


# =============================================================================
# Skill Service Tests (Database)
# =============================================================================


class TestSkillServiceSync:
    """Test skill synchronization to database."""

    @pytest.mark.asyncio
    async def test_sync_skills_creates_all_skills(self, session: AsyncSession, gsm):
        """sync_skills_to_db should create all skills in the database."""
        # Sync skills
        skills = await SkillService.sync_skills_to_db(session)
        
        # Verify all skills were created
        assert len(skills) == len(SkillType)
        
        skill_names = {s.name for s in skills}
        for skill_type in SkillType:
            assert skill_type.name.lower() in skill_names

    @pytest.mark.asyncio
    async def test_sync_skills_is_idempotent(self, session: AsyncSession, gsm):
        """Calling sync_skills_to_db multiple times should not create duplicates."""
        # Sync twice
        await SkillService.sync_skills_to_db(session)
        skills = await SkillService.sync_skills_to_db(session)
        
        # Should still have exactly the right number
        assert len(skills) == len(SkillType)


class TestSkillServiceGrant:
    """Test granting skills to players."""

    @pytest.mark.asyncio
    async def test_grant_all_skills_to_player(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """grant_all_skills_to_player should create PlayerSkill records for all skills."""
        # Create player and sync skills first
        player = await create_test_player("test_skills", "password123")
        await SkillService.sync_skills_to_db(session)
        
        # Grant skills
        player_skills = await SkillService.grant_all_skills_to_player(session, player.id)
        
        # Verify all skills were granted
        assert len(player_skills) == len(SkillType)
        
        for ps in player_skills:
            # Get skill name to check if it's hitpoints
            result = await session.execute(
                select(Skill).where(Skill.id == ps.skill_id)
            )
            skill = result.scalar_one()
            if skill.name == "hitpoints":
                # Hitpoints starts at level 10 with XP to match
                assert ps.current_level == HITPOINTS_START_LEVEL
                # Hitpoints should have the XP required for level 10
                assert ps.experience > 0
            else:
                # All other skills start at level 1
                assert ps.current_level == 1
                assert ps.experience == 0

    @pytest.mark.asyncio
    async def test_grant_skills_is_idempotent(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """Granting skills multiple times should not create duplicates."""
        player = await create_test_player("test_idempotent", "password123")
        await SkillService.sync_skills_to_db(session)
        
        # Grant twice
        await SkillService.grant_all_skills_to_player(session, player.id)
        await SkillService.grant_all_skills_to_player(session, player.id)
        
        # Check we don't have duplicates
        result = await session.execute(
            select(PlayerSkill).where(PlayerSkill.player_id == player.id)
        )
        player_skills = result.scalars().all()
        assert len(player_skills) == len(SkillType)


class TestSkillServiceAddExperience:
    """Test adding experience to skills."""

    @pytest.mark.asyncio
    async def test_add_experience_basic(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """Adding XP should update the PlayerSkill record."""
        player = await create_test_player("test_xp", "password123")
        await SkillService.sync_skills_to_db(session)
        await SkillService.grant_all_skills_to_player(session, player.id)
        
        # Add some XP to attack
        result = await SkillService.add_experience(
            session, player.id, SkillType.ATTACK, 100, state_manager=gsm
        )
        
        assert result is not None
        assert result.skill_name == "Attack"
        assert result.current_xp == 100
        assert result.previous_level == 1

    @pytest.mark.asyncio
    async def test_add_experience_causes_level_up(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """Adding enough XP should trigger a level up."""
        player = await create_test_player("test_levelup", "password123")
        await SkillService.sync_skills_to_db(session)
        await SkillService.grant_all_skills_to_player(session, player.id)
        
        # Add enough XP to reach level 2 (around 83 XP)
        result = await SkillService.add_experience(
            session, player.id, SkillType.ATTACK, 100, state_manager=gsm
        )
        
        assert result is not None
        assert result.leveled_up is True
        assert result.new_level == 2
        assert result.levels_gained == 1

    @pytest.mark.asyncio
    async def test_add_experience_multiple_level_ups(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """Adding a large amount of XP should trigger multiple level ups."""
        player = await create_test_player("test_multi_levelup", "password123")
        await SkillService.sync_skills_to_db(session)
        await SkillService.grant_all_skills_to_player(session, player.id)
        
        # Add enough XP for level 10+ (around 1,154 XP for level 10)
        result = await SkillService.add_experience(
            session, player.id, SkillType.ATTACK, 5000, state_manager=gsm
        )
        
        assert result is not None
        assert result.leveled_up is True
        assert result.new_level > 10
        assert result.levels_gained > 5

    @pytest.mark.asyncio
    async def test_add_zero_experience_returns_none(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """Adding 0 or negative XP should return None."""
        player = await create_test_player("test_zero_xp", "password123")
        await SkillService.sync_skills_to_db(session)
        await SkillService.grant_all_skills_to_player(session, player.id)
        
        result = await SkillService.add_experience(
            session, player.id, SkillType.ATTACK, 0, state_manager=gsm
        )
        assert result is None
        
        result = await SkillService.add_experience(
            session, player.id, SkillType.ATTACK, -100, state_manager=gsm
        )
        assert result is None


class TestSkillServiceGetPlayerSkills:
    """Test fetching player skills."""

    @pytest.mark.asyncio
    async def test_get_player_skills(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """get_player_skills should return all skills with metadata."""
        player = await create_test_player("test_get_skills", "password123")
        await SkillService.sync_skills_to_db(session)
        await SkillService.grant_all_skills_to_player(session, player.id)
        
        skills = await SkillService.get_player_skills(session, player.id)
        
        assert len(skills) == len(SkillType)
        
        for skill_data in skills:
            assert "name" in skill_data
            assert "category" in skill_data
            assert "description" in skill_data
            assert "current_level" in skill_data
            assert "experience" in skill_data
            assert "xp_for_current_level" in skill_data
            assert "xp_for_next_level" in skill_data
            assert "xp_to_next_level" in skill_data
            assert "xp_multiplier" in skill_data
            assert "progress_percent" in skill_data
            assert "max_level" in skill_data

    @pytest.mark.asyncio
    async def test_get_total_level(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """get_total_level should return sum of all skill levels."""
        player = await create_test_player("test_total_level", "password123")
        await SkillService.sync_skills_to_db(session)
        await SkillService.grant_all_skills_to_player(session, player.id)
        
        # All skills start at level 1 except Hitpoints which starts at level 10
        # So total = (num_skills - 1) * 1 + 10 = num_skills + 9
        expected_total = (len(SkillType) - 1) + HITPOINTS_START_LEVEL
        total = await SkillService.get_total_level(session, player.id)
        assert total == expected_total
        
        # Add some XP to level up one skill
        await SkillService.add_experience(
            session, player.id, SkillType.ATTACK, 5000, state_manager=gsm
        )
        
        # Total should increase
        new_total = await SkillService.get_total_level(session, player.id)
        assert new_total > total
