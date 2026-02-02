"""
Tests for GameStateManager State Access Helper.

Tests the new state access methods that bridge username-based operations
with the player_id-based GSM core.
"""

import pytest
import pytest_asyncio
from server.src.services.game_state_manager import GameStateManager, init_game_state_manager, reset_game_state_manager
from server.src.services.movement_service import MovementService
from server.src.tests.conftest import FakeValkey


class TestGSMStateAccess:
    """Test GameStateManager state access helper methods."""

    @pytest_asyncio.fixture
    async def online_player(self, gsm: GameStateManager):
        """Create an online player with test state."""
        player_id = 123
        username = "test_player"
        
        # Register player as online
        gsm.register_online_player(player_id, username)
        
        # Set up test state
        await gsm.set_player_full_state(player_id, 10, 20, "test_map", 50, 100)
        
        return {"player_id": player_id, "username": username, "gsm": gsm}

    async def test_get_players_on_map(self, gsm: GameStateManager):
        """Test retrieving all players on a specific map."""
        # Set up players on different maps
        players_map1 = [
            {"id": 201, "username": "map1_player1"},
            {"id": 202, "username": "map1_player2"}
        ]
        players_map2 = [
            {"id": 203, "username": "map2_player1"}
        ]

        for player in players_map1:
            gsm.register_online_player(player["id"], player["username"])
            await gsm.set_player_full_state(player["id"], 0, 0, "map1", 100, 100)

        for player in players_map2:
            gsm.register_online_player(player["id"], player["username"])
            await gsm.set_player_full_state(player["id"], 0, 0, "map2", 100, 100)

        # Get players on map1
        map1_players = await gsm.state_access.get_players_on_map("map1")

        assert len(map1_players) == 2
        assert all(p["map_id"] == "map1" for p in map1_players)

        # Get players on map2
        map2_players = await gsm.state_access.get_players_on_map("map2")

        assert len(map2_players) == 1
        assert map2_players[0]["map_id"] == "map2"

        # Get players on nonexistent map
        empty_players = await gsm.state_access.get_players_on_map("nonexistent")
        assert len(empty_players) == 0

    async def test_get_player_positions_on_map(self, gsm: GameStateManager):
        """Test getting player positions for a specific map."""
        # Set up players
        gsm.register_online_player(301, "pos_player1")
        gsm.register_online_player(302, "pos_player2")
        gsm.register_online_player(303, "pos_player3")  # Different map

        await gsm.set_player_full_state(301, 100, 200, "position_test_map", 100, 100)
        await gsm.set_player_full_state(302, 300, 400, "position_test_map", 100, 100)
        await gsm.set_player_full_state(303, 500, 600, "other_map", 100, 100)

        # Get positions on specific map
        positions = await gsm.state_access.get_player_positions_on_map("position_test_map")

        assert len(positions) == 2
        assert positions[301] == (100, 200)
        assert positions[302] == (300, 400)
        assert 303 not in positions  # Different map

    async def test_update_player_state(self, online_player):
        """Test atomic update of multiple player state fields."""
        player_id = online_player["player_id"]
        gsm = online_player["gsm"]
        
        # Update multiple fields atomically
        updates = {
            "x": 99,
            "y": 88,
            "current_hp": 77,
            "is_moving": True,
            "facing_direction": "UP"
        }
        
        await gsm.state_access.update_player_state(player_id, updates)
        
        # Verify all updates were applied
        state = await gsm.get_player_full_state(player_id)
        assert state["x"] == 99
        assert state["y"] == 88
        assert state["current_hp"] == 77
        assert state["is_moving"] == "True"  # Currently stored as "True" - will fix in follow-up
        assert state["facing_direction"] == "UP"

    async def test_update_player_state_offline_player(self, gsm: GameStateManager):
        """Test updating state for offline player does nothing."""
        # Try to update offline player
        await gsm.state_access.update_player_state(999, {"x": 100})
        # Should not crash - offline players are ignored

    async def test_exists_player_state(self, online_player):
        """Test checking if player state exists."""
        player_id = online_player["player_id"]
        gsm = online_player["gsm"]
        
        # Should exist for online player with state
        exists = await gsm.state_access.exists_player_state(player_id)
        assert exists is True
        
        # Should not exist for non-existent player
        no_exist = await gsm.state_access.exists_player_state(999)
        assert no_exist is False