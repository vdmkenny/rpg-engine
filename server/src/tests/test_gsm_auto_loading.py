"""
Test GameStateManager Auto-Loading and Fallback Patterns.

Tests the critical auto-loading functionality where GSM transparently
loads data from database when not found in Valkey, making online/offline
players indistinguishable to services.

These tests follow the NEW ARCHITECTURE where:
- Services do NOT take database sessions
- GSM handles all data access transparently 
- Auto-loading makes online/offline players identical
"""

import pytest
import pytest_asyncio
from unittest.mock import patch

from server.src.services.game_state_manager import (
    GameStateManager, 
    get_game_state_manager
)
from server.src.models.item import PlayerInventory
from server.src.models.player import Player
from server.src.tests.conftest import FakeValkey


class TestGSMAutoLoadingCore:
    """Test core GSM auto-loading functionality."""

    @pytest_asyncio.fixture
    async def gsm_with_offline_data(self, session, fake_valkey: FakeValkey, gsm: GameStateManager):
        """Create GSM with offline player data in database only."""
        # Create the player first (required for foreign key constraint)
        player = Player(
            id=100,
            username="test_offline_player", 
            hashed_password="dummy_hash",
            x_coord=50,
            y_coord=50,
            map_id="test_map"
        )
        session.add(player)
        await session.commit()
        
        # Add inventory data directly to database (simulating offline player)
        inv1 = PlayerInventory(
            player_id=100, item_id=1, slot=0, quantity=5, current_durability=1.0
        )
        inv2 = PlayerInventory(
            player_id=100, item_id=2, slot=1, quantity=10, current_durability=0.8
        )
        session.add(inv1)
        session.add(inv2)
        await session.commit()
        
        # Ensure player is NOT registered as online
        player_id = 100
        assert not gsm.is_online(player_id)
        
        # Ensure Valkey is empty for this player
        inventory_key = f"inventory:{player_id}"
        raw_data = await fake_valkey.hgetall(inventory_key)
        assert not raw_data, "Valkey should be empty initially"
        
        return gsm

    async def test_auto_loading_from_database(self, gsm_with_offline_data: GameStateManager):
        """Test that GSM auto-loads inventory from database when not in Valkey."""
        gsm = gsm_with_offline_data
        player_id = 100
        
        # Call get_inventory - should auto-load from database
        inventory = await gsm.get_inventory(player_id)
        
        # Verify data was loaded correctly
        assert len(inventory) == 2
        assert inventory[0]["item_id"] == 1
        assert inventory[0]["quantity"] == 5
        assert inventory[1]["item_id"] == 2
        assert inventory[1]["quantity"] == 10
        
        # Verify data was cached in Valkey after loading
        inventory_key = f"inventory:{player_id}"
        raw_data_after = await gsm._valkey.hgetall(inventory_key)
        assert raw_data_after, "Data should be cached in Valkey after auto-load"

    async def test_auto_loading_sets_ttl(self, gsm_with_offline_data: GameStateManager):
        """Test that auto-loaded data has TTL set in Valkey."""
        gsm = gsm_with_offline_data
        player_id = 100
        
        # Mock the expire method to track calls
        expire_called = False
        original_expire = gsm._valkey.expire
        
        async def mock_expire(key, seconds):
            nonlocal expire_called
            expire_called = True
            from server.src.core.config import settings
            assert seconds == settings.OFFLINE_PLAYER_CACHE_TTL, f"Should set TTL to {settings.OFFLINE_PLAYER_CACHE_TTL} seconds"
            return await original_expire(key, seconds)
        
        gsm._valkey.expire = mock_expire
        
        # Auto-load data
        await gsm.get_inventory(player_id)
        
        # Verify TTL was set
        assert expire_called, "TTL should be set when auto-loading data"

    async def test_get_inventory_slot_auto_loading(self, gsm_with_offline_data: GameStateManager):
        """Test that get_inventory_slot also auto-loads data."""
        gsm = gsm_with_offline_data
        player_id = 100
        
        # Get specific slot - should trigger auto-loading of full inventory
        slot_data = await gsm.get_inventory_slot(player_id, 0)
        
        # Verify slot data loaded correctly
        assert slot_data is not None
        assert slot_data["item_id"] == 1
        assert slot_data["quantity"] == 5
        
        # Verify full inventory was cached after slot access
        inventory_key = f"inventory:{player_id}"
        raw_data = await gsm._valkey.hgetall(inventory_key)
        assert raw_data, "Full inventory should be cached after slot access"

    async def test_no_database_access_when_cached(self, gsm_with_offline_data: GameStateManager):
        """Test that no database access occurs when data exists in Valkey."""
        gsm = gsm_with_offline_data
        player_id = 100
        
        # First call - should auto-load and cache
        inventory1 = await gsm.get_inventory(player_id)
        
        # Mock the offline method to detect if it's called
        offline_called = False
        original_method = gsm.get_inventory_offline
        
        async def mock_offline_method(*args, **kwargs):
            nonlocal offline_called
            offline_called = True
            return await original_method(*args, **kwargs)
        
        gsm.get_inventory_offline = mock_offline_method
        
        # Second call - should use cached data, not database
        inventory2 = await gsm.get_inventory(player_id)
        
        # Verify no database access on second call
        assert not offline_called, "Should not access database when data cached"
        assert inventory1 == inventory2, "Results should be identical"


class TestGSMValkeyFallback:
    """Test GSM behavior when Valkey is unavailable or disabled."""

    async def test_valkey_unavailable_fallback(self, session, gsm: GameStateManager, create_offline_player):
        """Test that GSM fails fast when Valkey is unavailable (no fallback)."""
        # Create player first to satisfy foreign key constraints
        player_id = 200
        await create_offline_player(player_id, username=f"fallback_player_{player_id}")
        await session.commit()  # Ensure player exists before creating inventory
        
        # Add test data to database
        inv = PlayerInventory(
            player_id=player_id, item_id=1, slot=0, quantity=3, current_durability=1.0
        )
        session.add(inv)
        await session.commit()
        
        # Simulate Valkey being unavailable
        original_valkey = gsm._valkey
        gsm._valkey = None
        
        try:
            # Should fail fast with RuntimeError (no fallback in current architecture)
            with pytest.raises(RuntimeError, match="Cache infrastructure unavailable"):
                await gsm.get_inventory(player_id)
        finally:
            # Restore Valkey
            gsm._valkey = original_valkey

    @patch('server.src.core.config.settings.USE_VALKEY', False)
    async def test_valkey_disabled_uses_database(self, session, gsm: GameStateManager, create_offline_player):
        """Test that USE_VALKEY=False uses database even when Valkey available."""
        player_id = 300
        
        # Create player first to satisfy foreign key constraints
        await create_offline_player(player_id, username=f"valkey_disabled_player_{player_id}")
        await session.commit()  # Ensure player exists before creating inventory
        
        # Add test data to database
        inv = PlayerInventory(
            player_id=player_id, item_id=1, slot=0, quantity=8, current_durability=1.0
        )
        session.add(inv)
        await session.commit()
        
        # Verify Valkey is available but should be bypassed
        assert gsm._valkey is not None, "Valkey should be available"
        
        # Should use database despite Valkey being available
        inventory = await gsm.get_inventory(player_id)
        
        # Verify data loaded from database
        assert len(inventory) == 1
        assert inventory[0]["item_id"] == 1
        assert inventory[0]["quantity"] == 8
        
        # Verify Valkey was NOT used (should be empty)
        inventory_key = f"inventory:{player_id}"
        raw_data = await gsm._valkey.hgetall(inventory_key)
        assert not raw_data, "Valkey should not be used when USE_VALKEY=False"


class TestGSMServiceTransparency:
    """Test that services see no difference between online/offline players."""

    @pytest_asyncio.fixture
    async def gsm_with_mixed_players(self, session, gsm: GameStateManager):
        """Create GSM with both online and offline player data."""
        # Create player records first (required for foreign key constraints)
        player_400 = Player(
            id=400,
            username="online_player",
            hashed_password="dummy_hash",
            x_coord=50,
            y_coord=50,
            map_id="test_map"
        )
        player_500 = Player(
            id=500,
            username="offline_player", 
            hashed_password="dummy_hash",
            x_coord=50,
            y_coord=50,
            map_id="test_map"
        )
        session.add(player_400)
        session.add(player_500)
        await session.commit()
        
        # Player 400: Online with data in Valkey
        player_online = 400
        gsm.register_online_player(player_online, "online_player")
        await gsm.set_inventory_slot(player_online, 0, 1, 15, 1.0)
        
        # Player 500: Offline with data only in database
        inv_offline = PlayerInventory(
            player_id=500, item_id=1, slot=0, quantity=15, current_durability=1.0
        )
        session.add(inv_offline)
        await session.commit()
        
        return gsm

    async def test_identical_results_online_offline(self, gsm_with_mixed_players: GameStateManager):
        """Test that online and offline players return identical data structure."""
        gsm = gsm_with_mixed_players
        online_player = 400
        offline_player = 500
        
        # Get inventory for both players using same GSM method
        online_inventory = await gsm.get_inventory(online_player)
        offline_inventory = await gsm.get_inventory(offline_player)
        
        # Should have identical structure and values  
        assert len(online_inventory) == len(offline_inventory)
        assert online_inventory[0]["item_id"] == offline_inventory[0]["item_id"]
        assert online_inventory[0]["quantity"] == offline_inventory[0]["quantity"]

    async def test_identical_slot_access_online_offline(self, gsm_with_mixed_players: GameStateManager):
        """Test that slot access works identically for online/offline players."""
        gsm = gsm_with_mixed_players
        online_player = 400
        offline_player = 500
        
        # Get slot data for both players using same GSM method
        online_slot = await gsm.get_inventory_slot(online_player, 0)
        offline_slot = await gsm.get_inventory_slot(offline_player, 0)
        
        # Should return identical data
        assert online_slot["item_id"] == offline_slot["item_id"]
        assert online_slot["quantity"] == offline_slot["quantity"]
        assert online_slot["current_durability"] == offline_slot["current_durability"]

    async def test_service_integration_transparency(self, gsm_with_mixed_players: GameStateManager):
        """Test that services can work with both online/offline players transparently."""
        # This test shows how services should interact with GSM
        # Services should use get_game_state_manager() singleton, not pass sessions
        
        gsm_singleton = get_game_state_manager()
        assert gsm_singleton is gsm_with_mixed_players, "Should use same GSM instance"
        
        online_player = 400
        offline_player = 500
        
        # Services should call GSM methods directly (no sessions passed)
        online_data = await gsm_singleton.get_inventory(online_player)
        offline_data = await gsm_singleton.get_inventory(offline_player)
        
        # Both should work identically
        assert len(online_data) == 1
        assert len(offline_data) == 1
        assert online_data[0]["item_id"] == offline_data[0]["item_id"]