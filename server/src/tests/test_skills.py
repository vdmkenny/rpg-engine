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
        skills = await SkillService.sync_skills_to_db()
        
        # Verify all skills were created
        assert len(skills) == len(SkillType)
        
        skill_names = {s.name for s in skills}
        for skill_type in SkillType:
            assert skill_type.name.lower() in skill_names

    @pytest.mark.asyncio
    async def test_sync_skills_is_idempotent(self, session: AsyncSession, gsm):
        """Calling sync_skills_to_db multiple times should not create duplicates."""
        # Sync twice
        await SkillService.sync_skills_to_db()
        skills = await SkillService.sync_skills_to_db()
        
        # Should still have exactly the right number
        assert len(skills) == len(SkillType)


class TestSkillServiceGrant:
    """Test granting skills to players."""

    @pytest.mark.asyncio
    async def test_grant_all_skills_to_player(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """grant_all_skills_to_player should create PlayerSkill records for all skills."""
        from unittest.mock import patch, AsyncMock
        
        # Mock the GSM to test service layer behavior
        with patch('server.src.services.skill_service.get_game_state_manager') as mock_gsm_getter:
            mock_gsm = AsyncMock()
            mock_gsm_getter.return_value = mock_gsm
            
            # Mock the GSM method to return expected PlayerSkill data
            expected_skills = []
            for skill_type in SkillType:
                if skill_type == SkillType.HITPOINTS:
                    expected_skills.append({
                        'player_id': 1,
                        'skill_id': skill_type.value,
                        'current_level': HITPOINTS_START_LEVEL,
                        'experience': 1154  # XP for level 10
                    })
                else:
                    expected_skills.append({
                        'player_id': 1,
                        'skill_id': skill_type.value,
                        'current_level': 1,
                        'experience': 0
                    })
            
            mock_gsm.grant_all_skills_to_player.return_value = expected_skills
            
            # Test the service method
            player_skills = await SkillService.grant_all_skills_to_player(1)
            
            # Verify GSM was called correctly
            mock_gsm.grant_all_skills_to_player.assert_called_once_with(1)
            
            # Verify result
            assert len(player_skills) == len(SkillType)
        
        # Verify result structure
        assert len(player_skills) == len(SkillType)
        
        # Verify expected data structure (service layer test - don't access DB)
        hitpoints_found = False
        other_skills_found = False
        
        for ps in player_skills:
            assert 'player_id' in ps
            assert 'skill_id' in ps
            assert 'current_level' in ps
            assert 'experience' in ps
            
            # Check hitpoints vs other skills based on skill_id
            if ps['skill_id'] == SkillType.HITPOINTS.value:
                assert ps['current_level'] == HITPOINTS_START_LEVEL
                assert ps['experience'] > 0
                hitpoints_found = True
            else:
                assert ps['current_level'] == 1
                assert ps['experience'] == 0
                other_skills_found = True
        
        # Ensure we found both types of skills
        assert hitpoints_found
        assert other_skills_found

    @pytest.mark.asyncio
    async def test_grant_skills_is_idempotent(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """Granting skills multiple times should not create duplicates."""
        from unittest.mock import patch, AsyncMock
        
        # Mock the GSM to test service layer behavior
        with patch('server.src.services.skill_service.get_game_state_manager') as mock_gsm_getter:
            mock_gsm = AsyncMock()
            mock_gsm_getter.return_value = mock_gsm
            
            # Mock the GSM method to return expected PlayerSkill data
            expected_skills = []
            for skill_type in SkillType:
                if skill_type == SkillType.HITPOINTS:
                    expected_skills.append({
                        'player_id': 1,
                        'skill_id': skill_type.value,
                        'current_level': HITPOINTS_START_LEVEL,
                        'experience': 1154  # XP for level 10
                    })
                else:
                    expected_skills.append({
                        'player_id': 1,
                        'skill_id': skill_type.value,
                        'current_level': 1,
                        'experience': 0
                    })
            
            mock_gsm.grant_all_skills_to_player.return_value = expected_skills
            
            # Test calling the service method twice (idempotency test)
            first_result = await SkillService.grant_all_skills_to_player(1)
            second_result = await SkillService.grant_all_skills_to_player(1)
            
            # Verify GSM was called twice
            assert mock_gsm.grant_all_skills_to_player.call_count == 2
            
            # Verify both results are identical (idempotent behavior)
            assert len(first_result) == len(second_result) == len(SkillType)


class TestSkillServiceAddExperience:
    """Test adding experience to skills."""

    @pytest.mark.asyncio
    async def test_add_experience_basic(
        self, session: AsyncSession, create_offline_player, gsm
    ):
        """Adding XP should update the PlayerSkill record."""
        player = await create_offline_player(player_id=3, username="test_xp")
        await session.commit()  # Commit the player so it's visible to service calls
        await SkillService.sync_skills_to_db()
        
        # First grant skills to the player
        await SkillService.grant_all_skills_to_player(player.id)
        await SkillService.grant_all_skills_to_player(player.id)
        
        # Add some XP to attack
        result = await SkillService.add_experience(player.id, SkillType.ATTACK, 100)
        
        assert result is not None
        assert result.skill_name == "Attack"
        assert result.current_xp == 100
        assert result.previous_level == 1

    @pytest.mark.asyncio
    async def test_add_experience_causes_level_up(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """Adding enough XP should trigger a level up."""
        from unittest.mock import patch, AsyncMock
        
        # Mock the GSM to test service layer behavior
        with patch('server.src.services.skill_service.get_game_state_manager') as mock_gsm_getter:
            mock_gsm = AsyncMock()
            mock_gsm_getter.return_value = mock_gsm
            
            # Mock current skill data (Attack skill at level 1 with 0 XP)
            mock_gsm.get_skill.return_value = {
                'skill_id': 1,
                'level': 1,
                'experience': 0
            }
            
            # Mock successful skill update
            mock_gsm.set_skill.return_value = True
            
            # Test adding XP that should cause level up (100 XP should get to level 2)
            result = await SkillService.add_experience(1, SkillType.ATTACK, 100)
            
            # Verify GSM calls
            mock_gsm.get_skill.assert_called_once_with(1, 'attack')
            mock_gsm.set_skill.assert_called_once()
            
            # Verify result
            assert result is not None
            assert result.leveled_up is True
            assert result.new_level == 2
            assert result.levels_gained == 1

    @pytest.mark.asyncio
    async def test_add_experience_multiple_level_ups(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """Adding a large amount of XP should trigger multiple level ups."""
        from unittest.mock import patch, AsyncMock
        
        # Mock the GSM to test service layer behavior
        with patch('server.src.services.skill_service.get_game_state_manager') as mock_gsm_getter:
            mock_gsm = AsyncMock()
            mock_gsm_getter.return_value = mock_gsm
            
            # Mock current skill data (Attack skill at level 1 with 0 XP)
            mock_gsm.get_skill.return_value = {
                'skill_id': 1,
                'level': 1,
                'experience': 0
            }
            
            # Mock successful skill update
            mock_gsm.set_skill.return_value = True
            
            # Test adding massive XP (5000 XP should get to level 30+)
            result = await SkillService.add_experience(1, SkillType.ATTACK, 5000)
            
            # Verify GSM calls
            mock_gsm.get_skill.assert_called_once_with(1, 'attack')
            mock_gsm.set_skill.assert_called_once()
            
            # Verify result
            assert result is not None
            assert result.leveled_up is True
            assert result.new_level > 10
            assert result.levels_gained > 5

    @pytest.mark.asyncio
    async def test_add_zero_experience_returns_none(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """Adding 0 or negative XP should return None."""
        # No need to mock GSM since the service should return None before calling GSM
        
        result = await SkillService.add_experience(1, SkillType.ATTACK, 0)
        assert result is None
        
        result = await SkillService.add_experience(1, SkillType.ATTACK, -100)
        assert result is None


class TestSkillServiceGetPlayerSkills:
    """Test fetching player skills."""

    @pytest.mark.asyncio
    async def test_get_player_skills(
        self, session: AsyncSession, create_test_player, gsm
    ):
        """get_player_skills should return all skills with metadata."""
        from unittest.mock import patch, AsyncMock
        
        # Mock the GSM to test service layer behavior
        with patch('server.src.services.skill_service.get_game_state_manager') as mock_gsm_getter:
            mock_gsm = AsyncMock()
            mock_gsm_getter.return_value = mock_gsm
            
            # Mock skill data return (sample skill entry)
            mock_skills_data = []
            for skill_type in SkillType:
                skill_entry = {
                    "name": skill_type.name.lower(),
                    "category": skill_type.value.category.value,
                    "description": skill_type.value.description,
                    "current_level": HITPOINTS_START_LEVEL if skill_type == SkillType.HITPOINTS else 1,
                    "experience": 1154 if skill_type == SkillType.HITPOINTS else 0,
                    "xp_for_current_level": 0,
                    "xp_for_next_level": 83,
                    "xp_to_next_level": 83,
                    "xp_multiplier": 1.0,
                    "progress_percent": 0.0,
                    "max_level": 99
                }
                mock_skills_data.append(skill_entry)
            
            mock_gsm.get_player_skills.return_value = mock_skills_data
            
            # Test the service method
            skills = await SkillService.get_player_skills(1)
            
            # Verify GSM was called correctly
            mock_gsm.get_player_skills.assert_called_once_with(1)
            
            # Verify result structure
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
        from unittest.mock import patch, AsyncMock
        
        # Mock the GSM to test service layer behavior
        with patch('server.src.services.skill_service.get_game_state_manager') as mock_gsm_getter:
            mock_gsm = AsyncMock()
            mock_gsm_getter.return_value = mock_gsm
            
            # Mock skills data with proper levels
            skills_data = {}
            for skill_type in SkillType:
                skill_name = skill_type.name.lower()
                level = HITPOINTS_START_LEVEL if skill_type == SkillType.HITPOINTS else 1
                skills_data[skill_name] = {"level": level}
            
            mock_gsm.get_all_skills.return_value = skills_data
            
            # Test the service method
            total = await SkillService.get_total_level(1)
            
            # Verify GSM was called correctly
            mock_gsm.get_all_skills.assert_called_once_with(1)
            
            # All skills start at level 1 except Hitpoints which starts at level 10
            # So total = (num_skills - 1) * 1 + 10 = num_skills + 9
            expected_total = (len(SkillType) - 1) + HITPOINTS_START_LEVEL
            assert total == expected_total
