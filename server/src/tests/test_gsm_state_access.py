"""
Tests for GameStateManager State Access Helper.

Tests the new state access methods that bridge username-based operations
with the player_id-based GSM core.
"""

import pytest
import pytest_asyncio
from server.src.services.game_state_manager import GameStateManager, init_game_state_manager, reset_game_state_manager
from server.src.tests.conftest import FakeValkey


class TestGSMStateAccess:
    """Test GameStateManager state access helper methods."""

    @pytest_asyncio.fixture
    async def gsm_with_state_access(self, fake_valkey: FakeValkey, db_session_factory):
        """Create GSM instance with state access helper."""
        gsm = init_game_state_manager(fake_valkey, db_session_factory)
        await gsm.load_item_cache_from_db()
        yield gsm
        reset_game_state_manager()

    @pytest_asyncio.fixture
    async def online_player(self, gsm_with_state_access: GameStateManager):
        """Create an online player with test state."""
        gsm = gsm_with_state_access
        player_id = 123
        username = "test_player"
        
        # Register player as online
        gsm.register_online_player(player_id, username)
        
        # Set up test state
        await gsm.set_player_full_state(player_id, 10, 20, "test_map", 50, 100)
        
        return {"player_id": player_id, "username": username, "gsm": gsm}

    async def test_get_player_state_by_username(self, online_player):
        """Test retrieving player state by username."""
        player_id = online_player["player_id"] 
        username = online_player["username"]
        gsm = online_player["gsm"]
        
        # Get state by username
        state = await gsm.state_access.get_player_state_by_username(username)
        
        assert state is not None
        assert state["x"] == 10
        assert state["y"] == 20 
        assert state["map_id"] == "test_map"
        assert state["current_hp"] == 50
        assert state["max_hp"] == 100
        assert state["username"] == username
        assert state["player_id"] == str(player_id)

    async def test_get_player_state_by_username_not_online(self, gsm_with_state_access: GameStateManager):
        """Test retrieving state for offline player returns None."""
        gsm = gsm_with_state_access
        
        state = await gsm.state_access.get_player_state_by_username("offline_player")
        
        assert state is None

    async def test_set_player_hp_by_username(self, online_player):
        """Test setting HP by username."""
        username = online_player["username"]
        gsm = online_player["gsm"]
        
        # Update HP by username
        await gsm.state_access.set_player_hp_by_username(username, 75, 120)
        
        # Verify HP was updated
        hp_data = await gsm.get_player_hp(online_player["player_id"])
        assert hp_data["current_hp"] == 75
        assert hp_data["max_hp"] == 120

    async def test_set_player_hp_by_username_offline(self, gsm_with_state_access: GameStateManager):
        """Test setting HP for offline player does nothing."""
        gsm = gsm_with_state_access
        
        # Should not raise error, just log warning
        await gsm.state_access.set_player_hp_by_username("offline_player", 50)
        
        # No assertion needed - just verify it doesn't crash

    async def test_get_multiple_players_by_usernames(self, gsm_with_state_access: GameStateManager, fake_valkey: FakeValkey):
        """Test batch retrieval of multiple players by username."""
        gsm = gsm_with_state_access
        
        # Set up multiple players
        players = [
            {"id": 101, "username": "player1", "x": 10, "y": 20},
            {"id": 102, "username": "player2", "x": 30, "y": 40}, 
            {"id": 103, "username": "player3", "x": 50, "y": 60}
        ]
        
        for player in players:
            gsm.register_online_player(player["id"], player["username"])
            await gsm.set_player_position(player["id"], player["x"], player["y"], "test_map")
        
        # Get multiple players by username
        usernames = ["player1", "player2", "player3", "nonexistent"]
        states = await gsm.state_access.get_multiple_players_by_usernames(usernames)
        
        assert len(states) == 3  # Only existing players returned
        assert "player1" in states
        assert "player2" in states  
        assert "player3" in states
        assert "nonexistent" not in states
        
        assert states["player1"]["x"] == 10
        assert states["player2"]["x"] == 30
        assert states["player3"]["x"] == 50

    async def test_get_players_on_map(self, gsm_with_state_access: GameStateManager):
        """Test retrieving all players on a specific map."""
        gsm = gsm_with_state_access
        
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
            await gsm.set_player_position(player["id"], 0, 0, "map1")
            
        for player in players_map2:
            gsm.register_online_player(player["id"], player["username"]) 
            await gsm.set_player_position(player["id"], 0, 0, "map2")
        
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

    async def test_get_player_positions_on_map(self, gsm_with_state_access: GameStateManager):
        """Test getting player positions for a specific map."""
        gsm = gsm_with_state_access
        
        # Set up players
        gsm.register_online_player(301, "pos_player1")
        gsm.register_online_player(302, "pos_player2")
        gsm.register_online_player(303, "pos_player3")  # Different map
        
        await gsm.set_player_position(301, 100, 200, "position_test_map")
        await gsm.set_player_position(302, 300, 400, "position_test_map") 
        await gsm.set_player_position(303, 500, 600, "other_map")
        
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
        assert state["is_moving"] == "true"  # Stored as string
        assert state["facing_direction"] == "UP"

    async def test_update_player_state_offline_player(self, gsm_with_state_access: GameStateManager):
        """Test updating state for offline player does nothing."""
        gsm = gsm_with_state_access
        
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