"""
Integration tests for SkillService.

Tests real skill operations with database and SkillsManager.
No mocking - tests actual business logic.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from server.src.core.skills import (
    SkillType,
    HITPOINTS_START_LEVEL,
    xp_for_level,
    get_skill_xp_multiplier,
)
from server.src.services.skill_service import SkillService
from server.src.services.game_state import get_skills_manager


class TestSkillServiceGrant:
    """Test granting skills to players."""

    @pytest.mark.asyncio
    async def test_grant_all_skills_to_player(
        self, session: AsyncSession, create_test_player
    ):
        """grant_all_skills_to_player should create all skills at level 1 (10 for hitpoints)."""
        player = await create_test_player("skill_grant_test", "password123")
        
        # Grant all skills
        await SkillService.grant_all_skills_to_player(player.id)
        
        # Verify via manager
        skills_mgr = get_skills_manager()
        all_skills = await skills_mgr.get_all_skills(player.id)
        
        # Should have all skill types
        assert len(all_skills) == len(SkillType)
        
        # Check hitpoints starts at level 10
        hitpoints = all_skills.get("hitpoints")
        assert hitpoints is not None
        assert hitpoints["level"] == HITPOINTS_START_LEVEL
        assert hitpoints["experience"] > 0  # Has XP for level 10
        
        # Check other skills start at level 1
        for skill_name, skill_data in all_skills.items():
            if skill_name != "hitpoints":
                assert skill_data["level"] == 1, f"{skill_name} should start at level 1"
                assert skill_data["experience"] == 0, f"{skill_name} should start with 0 XP"

    @pytest.mark.asyncio
    async def test_grant_skills_is_idempotent(
        self, session: AsyncSession, create_test_player
    ):
        """Granting skills multiple times should not create duplicates or reset progress."""
        player = await create_test_player("skill_idempotent_test", "password123")
        
        # Grant skills first time
        await SkillService.grant_all_skills_to_player(player.id)
        
        # Add some XP to attack
        await SkillService.add_experience(player.id, SkillType.ATTACK, 500)
        
        # Get attack level before second grant
        attack_level_before = await SkillService.get_skill_level(player.id, SkillType.ATTACK)
        assert attack_level_before > 1  # Should have leveled up
        
        # Grant skills again (should be idempotent)
        await SkillService.grant_all_skills_to_player(player.id)
        
        # Verify attack level unchanged
        attack_level_after = await SkillService.get_skill_level(player.id, SkillType.ATTACK)
        assert attack_level_after == attack_level_before


class TestSkillServiceAddXP:
    """Test adding experience to skills."""

    @pytest.mark.asyncio
    async def test_add_xp_increases_skill_level(
        self, session: AsyncSession, create_test_player
    ):
        """Adding enough XP should increase skill level."""
        player = await create_test_player("skill_xp_test", "password123")
        
        # Grant skills
        await SkillService.grant_all_skills_to_player(player.id)
        
        # Add XP to attack (enough for several levels)
        result = await SkillService.add_experience(
            player.id, SkillType.ATTACK, 2000
        )
        
        assert result is not None
        assert result.previous_level == 1
        assert result.current_level > 1
        assert result.leveled_up is True
        assert result.xp_gained == 2000
        assert result.current_xp > 0

    @pytest.mark.asyncio
    async def test_add_zero_xp_does_nothing(
        self, session: AsyncSession, create_test_player
    ):
        """Adding zero or negative XP should return None."""
        player = await create_test_player("skill_zero_xp", "password123")
        await SkillService.grant_all_skills_to_player(player.id)
        
        result_zero = await SkillService.add_experience(
            player.id, SkillType.ATTACK, 0
        )
        assert result_zero is None
        
        result_negative = await SkillService.add_experience(
            player.id, SkillType.ATTACK, -100
        )
        assert result_negative is None

    @pytest.mark.asyncio
    async def test_add_xp_no_level_up(
        self, session: AsyncSession, create_test_player
    ):
        """Adding small XP should not level up."""
        player = await create_test_player("skill_small_xp", "password123")
        await SkillService.grant_all_skills_to_player(player.id)
        
        # Add small amount of XP
        result = await SkillService.add_experience(
            player.id, SkillType.ATTACK, 50
        )
        
        assert result is not None
        assert result.previous_level == 1
        assert result.current_level == 1  # No level up
        assert result.leveled_up is False
        assert result.current_xp == 50

    @pytest.mark.asyncio
    async def test_xp_calculations_are_accurate(
        self, session: AsyncSession, create_test_player
    ):
        """XP calculations should match expected formula."""
        player = await create_test_player("skill_calc_test", "password123")
        await SkillService.grant_all_skills_to_player(player.id)
        
        # Add XP for exactly level 5
        xp_for_5 = xp_for_level(5, get_skill_xp_multiplier(SkillType.ATTACK))
        
        result = await SkillService.add_experience(
            player.id, SkillType.ATTACK, xp_for_5
        )
        
        assert result.current_level == 5
        assert result.current_xp == xp_for_5


class TestSkillServiceQueries:
    """Test skill query operations."""

    @pytest.mark.asyncio
    async def test_get_player_skills_returns_all(
        self, session: AsyncSession, create_test_player
    ):
        """get_player_skills should return all player skills."""
        player = await create_test_player("skill_query_test", "password123")
        await SkillService.grant_all_skills_to_player(player.id)
        
        skills = await SkillService.get_player_skills(player.id)
        
        assert len(skills) == len(SkillType)
        
        # Check structure - skills are Pydantic SkillData models
        for skill in skills:
            assert skill.name is not None
            assert skill.current_level >= 1
            assert skill.experience >= 0

    @pytest.mark.asyncio
    async def test_get_skill_level_returns_correct_value(
        self, session: AsyncSession, create_test_player
    ):
        """get_skill_level should return current level."""
        player = await create_test_player("skill_level_test", "password123")
        await SkillService.grant_all_skills_to_player(player.id)
        
        # Check default levels
        attack_level = await SkillService.get_skill_level(player.id, SkillType.ATTACK)
        assert attack_level == 1
        
        hitpoints_level = await SkillService.get_skill_level(player.id, SkillType.HITPOINTS)
        assert hitpoints_level == HITPOINTS_START_LEVEL
        
        # Level up and check again
        await SkillService.add_experience(player.id, SkillType.ATTACK, 2000)
        new_level = await SkillService.get_skill_level(player.id, SkillType.ATTACK)
        assert new_level > 1

    @pytest.mark.asyncio
    async def test_get_total_level_sums_correctly(
        self, session: AsyncSession, create_test_player
    ):
        """get_total_level should sum all skill levels."""
        player = await create_test_player("skill_total_test", "password123")
        await SkillService.grant_all_skills_to_player(player.id)
        
        initial_total = await SkillService.get_total_level(player.id)
        
        # Should be: (num_skills - 1) * 1 + hitpoints_10
        expected_initial = (len(SkillType) - 1) * 1 + HITPOINTS_START_LEVEL
        assert initial_total == expected_initial
        
        # Level up attack
        await SkillService.add_experience(player.id, SkillType.ATTACK, 2000)
        
        new_total = await SkillService.get_total_level(player.id)
        assert new_total > initial_total

    @pytest.mark.asyncio
    async def test_get_hitpoints_level(
        self, session: AsyncSession, create_test_player
    ):
        """get_hitpoints_level should return hitpoints specifically."""
        player = await create_test_player("skill_hp_test", "password123")
        await SkillService.grant_all_skills_to_player(player.id)
        
        hp_level = await SkillService.get_hitpoints_level(player.id)
        assert hp_level == HITPOINTS_START_LEVEL
        
        # Add XP to hitpoints
        await SkillService.add_experience(
            player.id, SkillType.HITPOINTS, 5000
        )
        
        new_hp = await SkillService.get_hitpoints_level(player.id)
        assert new_hp > HITPOINTS_START_LEVEL
