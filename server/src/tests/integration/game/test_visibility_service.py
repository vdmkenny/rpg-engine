"""
Unit tests for VisibilityService.

Tests visibility tracking, diff calculations, cache management,
and player lifecycle operations.
"""

import pytest
import pytest_asyncio
from typing import Dict, Any

from server.src.services.visibility_service import (
    VisibilityService,
    get_visibility_service,
    init_visibility_service,
)


@pytest_asyncio.fixture
async def visibility_service():
    """Create a fresh VisibilityService for each test."""
    service = VisibilityService(max_cache_size=100)
    yield service
    await service.clear_cache()


class TestVisibilityServiceInitialization:
    """Tests for VisibilityService initialization."""

    def test_default_initialization(self):
        """Test that service initializes with default cache size."""
        service = VisibilityService()
        assert service.max_cache_size > 0
        assert service._player_visible_cache == {}

    def test_custom_cache_size(self):
        """Test initialization with custom cache size."""
        service = VisibilityService(max_cache_size=50)
        assert service.max_cache_size == 50


class TestGetPlayerVisibleEntities:
    """Tests for VisibilityService.get_player_visible_entities()"""

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_player(self, visibility_service):
        """Test that empty dict returned for untracked player."""
        result = await visibility_service.get_player_visible_entities("unknown_player")
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_entities_for_tracked_player(self, visibility_service):
        """Test that entities are returned for tracked player."""
        # First add some entities
        entities = {
            "entity1": {"id": "entity1", "x": 10, "y": 20},
            "entity2": {"id": "entity2", "x": 30, "y": 40}
        }
        await visibility_service.update_player_visible_entities("test_player", entities)
        
        result = await visibility_service.get_player_visible_entities("test_player")
        
        assert result == entities

    @pytest.mark.asyncio
    async def test_returns_copy_not_reference(self, visibility_service):
        """Test that a copy of the cache is returned, not the original dict."""
        entities = {"entity1": {"id": "entity1", "x": 10}}
        await visibility_service.update_player_visible_entities("test_player", entities)
        
        result = await visibility_service.get_player_visible_entities("test_player")
        
        # Modifying the returned dict at the top level shouldn't affect cache
        result["entity2"] = {"id": "entity2", "x": 50}
        
        # Original cache should not have entity2
        original = await visibility_service.get_player_visible_entities("test_player")
        assert "entity2" not in original
        assert "entity1" in original


class TestUpdatePlayerVisibleEntities:
    """Tests for VisibilityService.update_player_visible_entities()"""

    @pytest.mark.asyncio
    async def test_first_update_all_added(self, visibility_service):
        """Test that first update marks all entities as added."""
        entities = {
            "entity1": {"id": "entity1", "x": 10},
            "entity2": {"id": "entity2", "x": 20}
        }
        
        diff = await visibility_service.update_player_visible_entities("test_player", entities)
        
        assert len(diff["added"]) == 2
        assert diff["updated"] == []
        assert diff["removed"] == []

    @pytest.mark.asyncio
    async def test_no_changes_empty_diff(self, visibility_service):
        """Test that identical updates produce empty diff."""
        entities = {"entity1": {"id": "entity1", "x": 10}}
        
        # First update
        await visibility_service.update_player_visible_entities("test_player", entities)
        
        # Same update again
        diff = await visibility_service.update_player_visible_entities("test_player", entities)
        
        assert diff["added"] == []
        assert diff["updated"] == []
        assert diff["removed"] == []

    @pytest.mark.asyncio
    async def test_entity_added(self, visibility_service):
        """Test that new entities are detected as added."""
        # Initial state
        await visibility_service.update_player_visible_entities(
            "test_player", 
            {"entity1": {"id": "entity1", "x": 10}}
        )
        
        # Add entity2
        diff = await visibility_service.update_player_visible_entities(
            "test_player",
            {
                "entity1": {"id": "entity1", "x": 10},
                "entity2": {"id": "entity2", "x": 20}
            }
        )
        
        assert len(diff["added"]) == 1
        assert diff["added"][0]["id"] == "entity2"
        assert diff["updated"] == []
        assert diff["removed"] == []

    @pytest.mark.asyncio
    async def test_entity_removed(self, visibility_service):
        """Test that missing entities are detected as removed."""
        # Initial state with two entities
        await visibility_service.update_player_visible_entities(
            "test_player",
            {
                "entity1": {"id": "entity1", "x": 10},
                "entity2": {"id": "entity2", "x": 20}
            }
        )
        
        # Remove entity2
        diff = await visibility_service.update_player_visible_entities(
            "test_player",
            {"entity1": {"id": "entity1", "x": 10}}
        )
        
        assert diff["added"] == []
        assert diff["updated"] == []
        assert len(diff["removed"]) == 1
        assert diff["removed"][0]["id"] == "entity2"

    @pytest.mark.asyncio
    async def test_entity_updated(self, visibility_service):
        """Test that changed entities are detected as updated."""
        # Initial state
        await visibility_service.update_player_visible_entities(
            "test_player",
            {"entity1": {"id": "entity1", "x": 10, "y": 20}}
        )
        
        # Update entity position
        diff = await visibility_service.update_player_visible_entities(
            "test_player",
            {"entity1": {"id": "entity1", "x": 15, "y": 20}}  # x changed
        )
        
        assert diff["added"] == []
        assert len(diff["updated"]) == 1
        assert diff["updated"][0]["id"] == "entity1"
        assert diff["updated"][0]["x"] == 15
        assert diff["removed"] == []

    @pytest.mark.asyncio
    async def test_mixed_changes(self, visibility_service):
        """Test that mixed add/update/remove changes are detected correctly."""
        # Initial state
        await visibility_service.update_player_visible_entities(
            "test_player",
            {
                "entity1": {"id": "entity1", "x": 10},  # Will be updated
                "entity2": {"id": "entity2", "x": 20},  # Will be removed
            }
        )
        
        # Mixed changes
        diff = await visibility_service.update_player_visible_entities(
            "test_player",
            {
                "entity1": {"id": "entity1", "x": 99},  # Updated
                "entity3": {"id": "entity3", "x": 30},  # Added
                # entity2 removed
            }
        )
        
        assert len(diff["added"]) == 1
        assert diff["added"][0]["id"] == "entity3"
        
        assert len(diff["updated"]) == 1
        assert diff["updated"][0]["id"] == "entity1"
        
        assert len(diff["removed"]) == 1
        assert diff["removed"][0]["id"] == "entity2"

    @pytest.mark.asyncio
    async def test_cache_eviction_when_full(self, visibility_service):
        """Test that LRU eviction occurs when cache is full."""
        # Create a small cache
        small_service = VisibilityService(max_cache_size=3)
        
        # Fill the cache
        await small_service.update_player_visible_entities("player1", {"e1": {"id": "e1"}})
        await small_service.update_player_visible_entities("player2", {"e2": {"id": "e2"}})
        await small_service.update_player_visible_entities("player3", {"e3": {"id": "e3"}})
        
        # Add another player - should evict player1 (oldest)
        await small_service.update_player_visible_entities("player4", {"e4": {"id": "e4"}})
        
        # player1 should be evicted
        result = await small_service.get_player_visible_entities("player1")
        assert result == {}
        
        # Other players should still be there
        assert await small_service.get_player_visible_entities("player2") != {}
        assert await small_service.get_player_visible_entities("player4") != {}


class TestRemovePlayer:
    """Tests for VisibilityService.remove_player()"""

    @pytest.mark.asyncio
    async def test_remove_existing_player(self, visibility_service):
        """Test removing an existing player from cache."""
        await visibility_service.update_player_visible_entities(
            "test_player",
            {"entity1": {"id": "entity1"}}
        )
        
        await visibility_service.remove_player("test_player")
        
        result = await visibility_service.get_player_visible_entities("test_player")
        assert result == {}

    @pytest.mark.asyncio
    async def test_remove_nonexistent_player(self, visibility_service):
        """Test removing a player that doesn't exist (no error)."""
        # Should not raise any error
        await visibility_service.remove_player("nonexistent_player")


class TestGetCacheStats:
    """Tests for VisibilityService.get_cache_stats()"""

    @pytest.mark.asyncio
    async def test_empty_cache_stats(self, visibility_service):
        """Test stats for empty cache."""
        stats = await visibility_service.get_cache_stats()
        
        assert stats["current_size"] == 0
        assert stats["max_size"] == 100
        assert stats["utilization_percent"] == 0.0
        assert stats["available_slots"] == 100

    @pytest.mark.asyncio
    async def test_partial_cache_stats(self, visibility_service):
        """Test stats for partially filled cache."""
        # Add 10 players
        for i in range(10):
            await visibility_service.update_player_visible_entities(
                f"player{i}",
                {"entity": {"id": "entity"}}
            )
        
        stats = await visibility_service.get_cache_stats()
        
        assert stats["current_size"] == 10
        assert stats["max_size"] == 100
        assert stats["utilization_percent"] == 10.0
        assert stats["available_slots"] == 90

    @pytest.mark.asyncio
    async def test_full_cache_stats(self):
        """Test stats for full cache."""
        service = VisibilityService(max_cache_size=5)
        
        for i in range(5):
            await service.update_player_visible_entities(
                f"player{i}",
                {"entity": {"id": "entity"}}
            )
        
        stats = await service.get_cache_stats()
        
        assert stats["current_size"] == 5
        assert stats["max_size"] == 5
        assert stats["utilization_percent"] == 100.0
        assert stats["available_slots"] == 0


class TestClearCache:
    """Tests for VisibilityService.clear_cache()"""

    @pytest.mark.asyncio
    async def test_clear_cache(self, visibility_service):
        """Test clearing the cache."""
        # Add some data
        for i in range(5):
            await visibility_service.update_player_visible_entities(
                f"player{i}",
                {"entity": {"id": "entity"}}
            )
        
        await visibility_service.clear_cache()
        
        stats = await visibility_service.get_cache_stats()
        assert stats["current_size"] == 0

    @pytest.mark.asyncio
    async def test_clear_empty_cache(self, visibility_service):
        """Test clearing an already empty cache."""
        await visibility_service.clear_cache()  # Should not raise
        
        stats = await visibility_service.get_cache_stats()
        assert stats["current_size"] == 0


class TestSingletonManagement:
    """Tests for singleton pattern management."""

    def test_get_visibility_service_returns_singleton(self):
        """Test that get_visibility_service returns same instance."""
        import server.src.services.visibility_service as vs_module
        
        # Store original
        original = vs_module._visibility_service
        vs_module._visibility_service = None
        
        try:
            service1 = get_visibility_service()
            service2 = get_visibility_service()
            
            assert service1 is service2
        finally:
            vs_module._visibility_service = original

    def test_init_visibility_service_creates_new_instance(self):
        """Test that init_visibility_service creates new instance."""
        import server.src.services.visibility_service as vs_module
        
        original = vs_module._visibility_service
        
        try:
            service1 = init_visibility_service(max_cache_size=50)
            service2 = get_visibility_service()
            
            assert service1 is service2
            assert service1.max_cache_size == 50
            
            # Re-init with different size
            service3 = init_visibility_service(max_cache_size=100)
            assert service3.max_cache_size == 100
            assert service3 is not service1
        finally:
            vs_module._visibility_service = original


class TestConcurrency:
    """Tests for concurrent access patterns."""

    @pytest.mark.asyncio
    async def test_concurrent_updates(self, visibility_service):
        """Test that concurrent updates don't corrupt data."""
        import asyncio
        
        async def update_player(player_num: int):
            entities = {f"entity{player_num}": {"id": f"entity{player_num}", "x": player_num}}
            for _ in range(10):
                await visibility_service.update_player_visible_entities(
                    f"player{player_num}",
                    entities
                )
        
        # Run many concurrent updates
        await asyncio.gather(*[update_player(i) for i in range(10)])
        
        # Verify data integrity
        stats = await visibility_service.get_cache_stats()
        assert stats["current_size"] == 10

    @pytest.mark.asyncio
    async def test_concurrent_read_write(self, visibility_service):
        """Test that concurrent reads and writes work correctly."""
        import asyncio
        
        # Set initial state
        await visibility_service.update_player_visible_entities(
            "test_player",
            {"entity1": {"id": "entity1", "x": 0}}
        )
        
        read_results = []
        
        async def reader():
            for _ in range(10):
                result = await visibility_service.get_player_visible_entities("test_player")
                read_results.append(result)
                await asyncio.sleep(0.001)
        
        async def writer():
            for i in range(10):
                await visibility_service.update_player_visible_entities(
                    "test_player",
                    {"entity1": {"id": "entity1", "x": i}}
                )
                await asyncio.sleep(0.001)
        
        await asyncio.gather(reader(), writer())
        
        # All reads should have valid data (not empty or corrupted)
        for result in read_results:
            assert "entity1" in result
            assert "id" in result["entity1"]


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_entities_update(self, visibility_service):
        """Test updating with empty entities dict."""
        diff = await visibility_service.update_player_visible_entities("test_player", {})
        
        assert diff["added"] == []
        assert diff["updated"] == []
        assert diff["removed"] == []

    @pytest.mark.asyncio
    async def test_all_entities_removed(self, visibility_service):
        """Test removing all entities."""
        # Add some entities
        await visibility_service.update_player_visible_entities(
            "test_player",
            {
                "entity1": {"id": "entity1"},
                "entity2": {"id": "entity2"}
            }
        )
        
        # Remove all
        diff = await visibility_service.update_player_visible_entities("test_player", {})
        
        assert diff["added"] == []
        assert diff["updated"] == []
        assert len(diff["removed"]) == 2

    @pytest.mark.asyncio
    async def test_zero_cache_size_uses_default(self):
        """Test behavior with zero max cache size falls back to default."""
        # When max_cache_size is 0, it falls back to settings.MAX_PLAYERS
        service = VisibilityService(max_cache_size=0)
        
        # Should use settings.MAX_PLAYERS as fallback (0 is falsy)
        # The implementation uses `max_cache_size or settings.MAX_PLAYERS`
        # so 0 will be replaced with the default
        stats = await service.get_cache_stats()
        # max_size should be the default (settings.MAX_PLAYERS), not 0
        assert stats["max_size"] > 0

    @pytest.mark.asyncio
    async def test_special_characters_in_username(self, visibility_service):
        """Test that special characters in username work correctly."""
        special_usernames = [
            "player@domain.com",
            "player_123",
            "player-name",
            "Player Name",
            "プレイヤー"
        ]
        
        for username in special_usernames:
            await visibility_service.update_player_visible_entities(
                username,
                {"entity": {"id": "entity"}}
            )
            result = await visibility_service.get_player_visible_entities(username)
            assert result == {"entity": {"id": "entity"}}

    @pytest.mark.asyncio
    async def test_nested_entity_data(self, visibility_service):
        """Test that complex nested entity data works correctly."""
        complex_entity = {
            "id": "entity1",
            "position": {"x": 10, "y": 20, "z": 0},
            "attributes": {
                "health": 100,
                "buffs": ["speed", "strength"],
                "stats": {"strength": 10, "agility": 15}
            }
        }
        
        await visibility_service.update_player_visible_entities(
            "test_player",
            {"entity1": complex_entity}
        )
        
        result = await visibility_service.get_player_visible_entities("test_player")
        assert result["entity1"] == complex_entity
