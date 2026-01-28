"""
Test Skills Auto-Loading Pattern in GameStateManager.

Tests the skills-specific auto-loading functionality where GSM transparently
loads skills data from database when not found in Valkey, making online/offline
players indistinguishable to services.

These tests follow the NEW ARCHITECTURE where:
- SkillService handles ALL business logic (XP calculations)
- GSM provides transparent data access with auto-loading
- No online/offline branching in service methods
"""

import pytest
import pytest_asyncio
from unittest.mock import patch

from server.src.services.game_state_manager import (
    GameStateManager, 
    get_game_state_manager
)
from server.src.models.skill import PlayerSkill, Skill
from server.src.core.skills import SkillType
from server.src.services.skill_service import SkillService
from server.src.tests.conftest import FakeValkey


class TestSkillsAutoLoadingCore:
    """Test core skills auto-loading functionality."""

    @pytest_asyncio.fixture
    async def gsm_with_offline_skills(self, session, fake_valkey: FakeValkey, gsm: GameStateManager, create_player_with_skills):
        """Create GSM with offline player skills in database only."""
        # Ensure skills exist in database
        await SkillService.sync_skills_to_db()
        
        # Create player with skills using proper fixture (satisfies foreign key constraints)
        player_id = 100
        skills_data = {
            'attack': {'level': 5, 'xp': 388},
            'hitpoints': {'level': 15, 'xp': 2411}
        }
        
        # Create player with skills in database (offline player)
        await create_player_with_skills(player_id, skills_data, username=f"offline_player_{player_id}")
        await session.commit()
        
        # Ensure player is NOT registered as online
        assert not gsm.is_online(player_id)
        
        # Ensure Valkey is empty for this player
        skills_key = f"skills:{player_id}"
        raw_data = await fake_valkey.hgetall(skills_key)
        assert not raw_data, "Valkey should be empty initially"
        
        return gsm

    async def test_skills_auto_loading_from_database(self, gsm_with_offline_skills: GameStateManager):
        """Test that GSM auto-loads skills from database when not in Valkey."""
        gsm = gsm_with_offline_skills
        player_id = 100
        
        # Call get_all_skills - should auto-load from database
        skills = await gsm.get_all_skills(player_id)
        
        # Verify data was loaded correctly
        assert len(skills) == 2
        assert skills["attack"]["level"] == 5
        assert skills["attack"]["experience"] == 388
        assert skills["hitpoints"]["level"] == 15
        assert skills["hitpoints"]["experience"] == 2411
        
        # Verify data was cached in Valkey after loading
        skills_key = f"skills:{player_id}"
        raw_data_after = await gsm._valkey.hgetall(skills_key)
        assert raw_data_after, "Skills should be cached in Valkey after auto-load"

    async def test_get_skill_auto_loading(self, gsm_with_offline_skills: GameStateManager):
        """Test that get_skill also triggers auto-loading of skills data."""
        gsm = gsm_with_offline_skills
        player_id = 100
        
        # Get specific skill - should trigger auto-loading of all skills
        attack_skill = await gsm.get_skill(player_id, "attack")
        
        # Verify skill data loaded correctly
        assert attack_skill is not None
        assert attack_skill["level"] == 5
        assert attack_skill["experience"] == 388
        assert "skill_id" in attack_skill, "Skill data should include skill_id"
        
        # Verify all skills were cached after single skill access
        skills_key = f"skills:{player_id}"
        raw_data = await gsm._valkey.hgetall(skills_key)
        assert raw_data, "All skills should be cached after single skill access"
        assert len(raw_data) == 2, "Both skills should be cached"

    async def test_skills_auto_loading_sets_ttl(self, gsm_with_offline_skills: GameStateManager):
        """Test that auto-loaded skills have TTL set in Valkey."""
        gsm = gsm_with_offline_skills
        player_id = 100
        
        # Mock the expire method to track calls
        expire_called = False
        original_expire = gsm._valkey.expire
        
        async def mock_expire(key, seconds):
            nonlocal expire_called
            expire_called = True
            assert seconds == 3600, "Should set 1 hour TTL"
            return await original_expire(key, seconds)
        
        gsm._valkey.expire = mock_expire
        
        # Auto-load skills data
        await gsm.get_all_skills(player_id)
        
        # Verify TTL was set
        assert expire_called, "TTL should be set when auto-loading skills"

    async def test_no_database_access_when_skills_cached(self, gsm_with_offline_skills: GameStateManager):
        """Test that no database access occurs when skills exist in Valkey."""
        gsm = gsm_with_offline_skills
        player_id = 100
        
        # First call - should auto-load and cache
        skills1 = await gsm.get_all_skills(player_id)
        
        # Mock the offline method to detect if it's called
        offline_called = False
        original_method = gsm.get_skills_offline
        
        async def mock_offline_method(*args, **kwargs):
            nonlocal offline_called
            offline_called = True
            return await original_method(*args, **kwargs)
        
        gsm.get_skills_offline = mock_offline_method
        
        # Second call - should use cached data, not database
        skills2 = await gsm.get_all_skills(player_id)
        
        # Verify no database access on second call
        assert not offline_called, "Should not access database when skills cached"
        assert skills1 == skills2, "Results should be identical"


class TestSkillsServiceTransparency:
    """Test that SkillService sees no difference between online/offline players."""

    @pytest_asyncio.fixture
    async def gsm_with_mixed_skill_players(self, session, gsm: GameStateManager, create_offline_player):
        """Create GSM with both online and offline players with skills."""
        await SkillService.sync_skills_to_db()
        
        # Player 400: Create player first, then make online with skills in Valkey
        online_player_id = 400
        await create_offline_player(online_player_id, username="online_player")
        await session.commit()  # Ensure player exists in DB before GSM operations
        
        gsm.register_online_player(online_player_id, "online_player")
        await SkillService.grant_all_skills_to_player(online_player_id)
        
        # Use SkillService to add XP to online player (proper architecture)
        await SkillService.add_experience(online_player_id, SkillType.ATTACK, 388)  # Should reach level 5
        
        # Player 500: Create player first, then handle as offline player with skills only in database
        offline_player_id = 500
        await create_offline_player(offline_player_id, username="offline_player")
        await session.commit()  # Ensure player exists in DB before SkillService operations
        
        await SkillService.grant_all_skills_to_player(offline_player_id)
        
        # Use SkillService to add same XP to offline player (proper architecture)
        await SkillService.add_experience(offline_player_id, SkillType.ATTACK, 388)  # Same XP as online player
        
        return gsm

    async def test_skill_service_identical_results_online_offline(self, gsm_with_mixed_skill_players: GameStateManager):
        """Test that SkillService returns identical data for online/offline players."""
        gsm = gsm_with_mixed_skill_players
        online_player = 400
        offline_player = 500
        
        # Get skills using SkillService transparent methods
        online_total = await SkillService.get_total_level(online_player)
        offline_total = await SkillService.get_total_level(offline_player)
        
        # Should have identical total levels
        assert online_total == offline_total, "Total levels should be identical for players with same skills"
        
        # Get hitpoints levels
        online_hp = await SkillService.get_hitpoints_level(online_player)
        offline_hp = await SkillService.get_hitpoints_level(offline_player)
        
        # Should have identical hitpoints levels
        assert online_hp == offline_hp, "Hitpoints levels should be identical"

    async def test_skill_service_add_experience_transparency(self, gsm_with_mixed_skill_players: GameStateManager):
        """Test that SkillService.add_experience works identically for online/offline players."""
        gsm = gsm_with_mixed_skill_players
        online_player = 400
        offline_player = 500
        
        # Add same XP to both players
        online_result = await SkillService.add_experience(online_player, SkillType.ATTACK, 100)
        offline_result = await SkillService.add_experience(offline_player, SkillType.ATTACK, 100)
        
        # Results should be identical
        assert online_result is not None, "Online player should get valid result"
        assert offline_result is not None, "Offline player should get valid result"
        assert online_result.new_level == offline_result.new_level, "New levels should be identical"
        assert online_result.current_xp == offline_result.current_xp, "XP totals should be identical"
        assert online_result.leveled_up == offline_result.leveled_up, "Level up status should be identical"

    async def test_gsm_skill_access_transparency(self, gsm_with_mixed_skill_players: GameStateManager):
        """Test that GSM skill methods work identically for online/offline players."""
        gsm_singleton = get_game_state_manager()
        assert gsm_singleton is gsm_with_mixed_skill_players, "Should use same GSM instance"
        
        online_player = 400
        offline_player = 500
        
        # Access skills using GSM auto-loading methods
        online_attack = await gsm_singleton.get_skill(online_player, "attack")
        offline_attack = await gsm_singleton.get_skill(offline_player, "attack")
        
        # Should return identical data structure and values
        assert online_attack is not None, "Online player skill should be found"
        assert offline_attack is not None, "Offline player skill should be found"
        assert online_attack["level"] == offline_attack["level"], "Skill levels should be identical"
        assert online_attack["experience"] == offline_attack["experience"], "Skill XP should be identical"
        assert "skill_id" in online_attack, "Online skill should have skill_id"
        assert "skill_id" in offline_attack, "Offline skill should have skill_id"


class TestSkillsValkeyFallback:
    """Test skills behavior when Valkey is unavailable or disabled."""

    async def test_skills_valkey_unavailable_fallback(self, session, gsm: GameStateManager, create_offline_player):
        """Test database fallback when Valkey is unavailable for skills."""
        await SkillService.sync_skills_to_db()
        
        # Create player first to satisfy foreign key constraints
        player_id = 200
        await create_offline_player(player_id, username=f"fallback_player_{player_id}")
        await session.commit()  # Ensure player exists before SkillService operations
        
        # Add test skills to database
        await SkillService.grant_all_skills_to_player(player_id)
        
        # Simulate Valkey being unavailable
        original_valkey = gsm._valkey
        gsm._valkey = None
        
        try:
            # Should fallback to database without error
            skills = await gsm.get_all_skills(player_id)
            
            # Verify skills loaded from database
            assert len(skills) >= 9, "Should load all skills from database"
            assert "attack" in skills, "Attack skill should be loaded"
            assert "hitpoints" in skills, "Hitpoints skill should be loaded"
            assert skills["hitpoints"]["level"] == 10, "Hitpoints should start at level 10"
        finally:
            # Restore Valkey
            gsm._valkey = original_valkey

    @patch('server.src.core.config.settings.USE_VALKEY', False)
    async def test_skills_valkey_disabled_uses_database(self, session, gsm: GameStateManager, create_offline_player):
        """Test that USE_VALKEY=False uses database even when Valkey available for skills."""
        await SkillService.sync_skills_to_db()
        
        # Create player first to satisfy foreign key constraints
        player_id = 300
        await create_offline_player(player_id, username=f"valkey_disabled_player_{player_id}")
        await session.commit()  # Ensure player exists before SkillService operations
        
        await SkillService.grant_all_skills_to_player(player_id)
        
        # Verify Valkey is available but should be bypassed
        assert gsm._valkey is not None, "Valkey should be available"
        
        # Should use database despite Valkey being available
        skills = await gsm.get_all_skills(player_id)
        
        # Verify skills loaded from database
        assert len(skills) >= 9, "Should load all skills from database"
        assert "attack" in skills, "Attack skill should be loaded"
        
        # Verify Valkey was NOT used (should be empty)
        skills_key = f"skills:{player_id}"
        raw_data = await gsm._valkey.hgetall(skills_key)
        assert not raw_data, "Valkey should not be used when USE_VALKEY=False"