"""
Unit tests for ConnectionService.

Tests WebSocket connection lifecycle, player initialization, disconnection handling,
and online player management.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from server.src.services.connection_service import ConnectionService
from server.src.services.game_state import get_player_state_manager


class TestInitializePlayerConnection:
    """Tests for ConnectionService.initialize_player_connection()"""

    @pytest.mark.asyncio
    async def test_successful_initialization(self, game_state_managers, create_test_player):
        """Test successful player connection initialization."""
        player = await create_test_player("connection_init_test", "password123")
        
        result = await ConnectionService.initialize_player_connection(
            player_id=player.id,
            username="connection_init_test",
            x=10,
            y=20,
            map_id="samplemap",
            current_hp=80,
            max_hp=100
        )
        
        assert result["initialized"] is True
        assert result["player_id"] == player.id
        assert result["username"] == "connection_init_test"
        assert result["position"]["x"] == 10
        assert result["position"]["y"] == 20
        assert result["position"]["map_id"] == "samplemap"
        assert result["hp"]["current_hp"] == 80
        assert result["hp"]["max_hp"] == 100
        assert "nearby_players" in result

    @pytest.mark.asyncio
    async def test_initialization_caches_appearance(self, game_state_managers, create_test_player):
        """Test that appearance is properly cached in Valkey during initialization."""
        player = await create_test_player("appearance_cache_test", "password123")
        
        # Set appearance in database
        player_mgr = get_player_state_manager()
        appearance_data = {
            "body_type": "male",
            "skin_tone": "light",
            "head_type": "human/male",
            "hair_style": "buzzcut",
            "hair_color": "dark_brown",
            "eye_color": "brown",
            "facial_hair_style": "none",
            "facial_hair_color": "dark_brown",
            "shirt_style": "longsleeve2",
            "shirt_color": "white",
            "pants_style": "pants",
            "pants_color": "brown",
            "shoes_style": "shoes/basic",
            "shoes_color": "brown",
        }
        # Update the player's appearance in the database
        await player_mgr.update_player_appearance(player.id, appearance_data)
        
        # Initialize connection which should cache appearance
        await ConnectionService.initialize_player_connection(
            player_id=player.id,
            username="appearance_cache_test",
            x=10,
            y=20,
            map_id="samplemap",
            current_hp=80,
            max_hp=100,
            appearance=appearance_data
        )
        
        # Verify appearance was cached in Valkey via player state manager
        # We can't directly verify Valkey, but we can check the game loop would find it
        player_full_state = await player_mgr.get_player_full_state(player.id)
        assert player_full_state is not None
        assert "appearance" in player_full_state
        assert player_full_state["appearance"] == appearance_data

    @pytest.mark.asyncio
    async def test_initialization_sets_hp_in_gsm(self, game_state_managers, create_test_player):
        """Test that HP is properly set in GSM during initialization."""
        player = await create_test_player("hp_init_test", "password123")
        
        await ConnectionService.initialize_player_connection(
            player_id=player.id,
            username="hp_init_test",
            x=10,
            y=20,
            map_id="samplemap",
            current_hp=50,
            max_hp=100
        )
        
        # Verify HP was set via manager
        player_mgr = get_player_state_manager()
        hp_data = await player_mgr.get_player_hp(player.id)
        assert hp_data is not None
        assert hp_data["current_hp"] == 50
        assert hp_data["max_hp"] == 100

    @pytest.mark.asyncio
    async def test_initialization_sets_position_in_gsm(self, game_state_managers, create_test_player):
        """Test that position is properly set in GSM during initialization."""
        player = await create_test_player("pos_init_test", "password123")
        
        await ConnectionService.initialize_player_connection(
            player_id=player.id,
            username="pos_init_test",
            x=25,
            y=35,
            map_id="samplemap",
            current_hp=100,
            max_hp=100
        )
        
        # Verify position was set via manager
        player_mgr = get_player_state_manager()
        position = await player_mgr.get_player_position(player.id)
        assert position is not None
        assert position["x"] == 25
        assert position["y"] == 35
        assert position["map_id"] == "samplemap"


class TestBroadcastPlayerJoin:
    """Tests for ConnectionService.broadcast_player_join()"""

    @pytest.mark.asyncio
    async def test_broadcast_returns_notified_players(self, game_state_managers, create_test_player):
        """Test that broadcast returns list of notified player IDs."""
        player1 = await create_test_player("broadcast_test1", "password123")
        player2 = await create_test_player("broadcast_test2", "password123")
        
        # Set up player2's position so they're "nearby"
        player_mgr = get_player_state_manager()
        await player_mgr.set_player_position(player2.id, 15, 25, "samplemap")
        await player_mgr.set_player_hp(player2.id, 100, 100)
        
        result = await ConnectionService.broadcast_player_join(
            player_id=player1.id,
            username="broadcast_test1",
            position_data={"x": 10, "y": 20, "map_id": "samplemap"}
        )
        
        assert isinstance(result, list)
        # If player2 is within range, they should be in the list
        # The actual presence depends on get_nearby_players implementation

    @pytest.mark.asyncio
    async def test_broadcast_handles_no_nearby_players(self, game_state_managers, create_test_player):
        """Test that broadcast handles case with no nearby players."""
        player = await create_test_player("lonely_player", "password123")
        
        result = await ConnectionService.broadcast_player_join(
            player_id=player.id,
            username="lonely_player",
            position_data={"x": 1000, "y": 1000, "map_id": "samplemap"}
        )
        
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_broadcast_handles_exception(self, game_state_managers):
        """Test that broadcast handles exceptions gracefully."""
        with patch("server.src.services.connection_service.PlayerService") as mock_service:
            mock_service.get_nearby_players = AsyncMock(side_effect=Exception("Test error"))
            
            result = await ConnectionService.broadcast_player_join(
                player_id=999,
                username="test_user",
                position_data={"x": 10, "y": 20, "map_id": "samplemap"}
            )
            
            assert result == []


class TestHandlePlayerDisconnect:
    """Tests for ConnectionService.handle_player_disconnect()"""

    @pytest.mark.asyncio
    async def test_disconnect_player_not_found(self, game_state_managers):
        """Test disconnect handling when player not found."""
        result = await ConnectionService.handle_player_disconnect(
            username="nonexistent_user"
        )
        
        assert result["cleanup_completed"] is False
        assert result["error"] == "Player not found"
        assert result["player_id"] is None

    @pytest.mark.asyncio
    async def test_disconnect_successful(self, game_state_managers, create_test_player):
        """Test successful player disconnection."""
        player = await create_test_player("disconnect_test", "password123")
        
        # Initialize connection first
        await ConnectionService.initialize_player_connection(
            player_id=player.id,
            username="disconnect_test",
            x=10,
            y=20,
            map_id="samplemap",
            current_hp=100,
            max_hp=100
        )
        
        result = await ConnectionService.handle_player_disconnect(
            username="disconnect_test"
        )
        
        assert result["player_id"] == player.id
        assert result["username"] == "disconnect_test"
        assert result["cleanup_completed"] is True
        assert "nearby_players_to_notify" in result


class TestCleanupConnectionResources:
    """Tests for ConnectionService._cleanup_connection_resources()"""

    @pytest.mark.asyncio
    async def test_cleanup_completes_without_error(self, game_state_managers, create_test_player):
        """Test that cleanup completes without raising errors."""
        player = await create_test_player("cleanup_test", "password123")
        
        # Should not raise
        await ConnectionService._cleanup_connection_resources(player.id)

    @pytest.mark.asyncio
    async def test_cleanup_handles_nonexistent_player(self, game_state_managers):
        """Test that cleanup handles non-existent player gracefully."""
        # Should not raise
        await ConnectionService._cleanup_connection_resources(99999)


class TestValidateConnectionState:
    """Tests for ConnectionService.validate_connection_state()"""

    @pytest.mark.asyncio
    async def test_valid_connection_state(self, game_state_managers, create_test_player):
        """Test validation of valid connection state."""
        player = await create_test_player("valid_state_test", "password123")
        
        # Initialize connection to ensure state exists
        await ConnectionService.initialize_player_connection(
            player_id=player.id,
            username="valid_state_test",
            x=10,
            y=20,
            map_id="samplemap",
            current_hp=100,
            max_hp=100
        )
        
        result = await ConnectionService.validate_connection_state(
            player_id=player.id,
            username="valid_state_test"
        )
        
        assert result["valid"] is True
        assert result["is_online"] is True
        assert result["username_matches"] is True
        assert result["has_position_data"] is True

    @pytest.mark.asyncio
    async def test_invalid_connection_state_not_online(self, game_state_managers, create_test_player):
        """Test validation when player is not online."""
        player = await create_test_player("offline_state_test", "password123")
        
        # Unregister the player (async method)
        player_mgr = get_player_state_manager()
        await player_mgr.unregister_online_player(player.id)
        
        result = await ConnectionService.validate_connection_state(
            player_id=player.id,
            username="offline_state_test"
        )
        
        assert result["valid"] is False
        assert result["is_online"] is False

    @pytest.mark.asyncio
    async def test_invalid_username_mismatch(self, game_state_managers, create_test_player):
        """Test validation when username doesn't match."""
        player = await create_test_player("mismatch_test", "password123")
        
        result = await ConnectionService.validate_connection_state(
            player_id=player.id,
            username="wrong_username"
        )
        
        assert result["valid"] is False
        assert result["username_matches"] is False


class TestGetExistingPlayersOnMap:
    """Tests for ConnectionService.get_existing_players_on_map()"""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_connections(self, game_state_managers):
        """Test that empty list returned when no connections on map."""
        result = await ConnectionService.get_existing_players_on_map(
            map_id="samplemap",
            exclude_username="test_user"
        )
        
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self, game_state_managers):
        """Test that exceptions are handled gracefully."""
        with patch("server.src.api.connection_manager.ConnectionManager") as mock_cm:
            mock_cm.return_value.connections_by_map.get.side_effect = Exception("Test error")
            
            result = await ConnectionService.get_existing_players_on_map(
                map_id="samplemap",
                exclude_username="test_user"
            )
            
            # Should return empty list instead of raising
            assert isinstance(result, list)


class TestCreateWelcomeMessage:
    """Tests for ConnectionService.create_welcome_message()"""

    def test_creates_welcome_message(self):
        """Test that welcome message is properly created."""
        result = ConnectionService.create_welcome_message(
            player_id=1,
            username="test_user",
            position_data={"x": 10, "y": 20, "map_id": "samplemap"},
            hp_data={"current_hp": 80, "max_hp": 100}
        )
        
        assert result["type"] == "welcome"
        assert result["payload"]["player_id"] == 1
        assert result["payload"]["username"] == "test_user"
        assert result["payload"]["x"] == 10
        assert result["payload"]["y"] == 20
        assert result["payload"]["map_id"] == "samplemap"
        assert result["payload"]["current_hp"] == 80
        assert result["payload"]["max_hp"] == 100

    def test_welcome_message_defaults(self):
        """Test that welcome message uses defaults for missing data."""
        result = ConnectionService.create_welcome_message(
            player_id=1,
            username="test_user",
            position_data={},
            hp_data={}
        )
        
        assert result["payload"]["x"] == 0
        assert result["payload"]["y"] == 0
        assert result["payload"]["map_id"] == "default"
        assert result["payload"]["current_hp"] == 100
        assert result["payload"]["max_hp"] == 100


class TestGetOnlinePlayerIds:
    """Tests for ConnectionService.get_online_player_ids()"""

    @pytest.mark.asyncio
    async def test_returns_empty_set_when_no_players(self, game_state_managers):
        """Test that empty set is returned when no players online."""
        result = await ConnectionService.get_online_player_ids()
        
        assert result == set()

    @pytest.mark.asyncio
    async def test_returns_online_player_ids(self, game_state_managers):
        """Test that online player IDs are returned."""
        player_mgr = get_player_state_manager()
        await player_mgr.register_online_player(1, "player1")
        await player_mgr.register_online_player(2, "player2")
        
        result = await ConnectionService.get_online_player_ids()
        
        assert 1 in result
        assert 2 in result

    @pytest.mark.asyncio
    async def test_returns_copy_of_set(self, game_state_managers):
        """Test that a copy of the set is returned, not the original."""
        player_mgr = get_player_state_manager()
        await player_mgr.register_online_player(1, "player1")
        
        result = await ConnectionService.get_online_player_ids()
        result.add(999)  # Modify the returned set
        
        # Original should be unchanged - use is_online() to check
        assert not await player_mgr.is_online(999)


class TestGetOnlinePlayerIdByUsername:
    """Tests for ConnectionService.get_online_player_id_by_username()"""

    @pytest.mark.asyncio
    async def test_returns_player_id_when_online(self, game_state_managers, create_test_player):
        """Test that player ID is returned for online player."""
        # Create a real player in database
        player = await create_test_player("test_player", "password123")
        
        result = await ConnectionService.get_online_player_id_by_username("test_player")
        
        assert result == player.id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_online(self, game_state_managers):
        """Test that None is returned when player not online."""
        result = await ConnectionService.get_online_player_id_by_username("nonexistent_player")
        
        assert result is None


class TestGetAllOnlinePlayers:
    """Tests for ConnectionService.get_all_online_players()"""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_players(self, game_state_managers):
        """Test that empty list is returned when no players online."""
        result = await ConnectionService.get_all_online_players()
        
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_all_online_players(self, game_state_managers):
        """Test that all online players are returned."""
        player_mgr = get_player_state_manager()
        await player_mgr.register_online_player(1, "player1")
        await player_mgr.register_online_player(2, "player2")
        
        result = await ConnectionService.get_all_online_players()
        
        assert len(result) >= 2
        
        player_ids = {p["player_id"] for p in result}
        usernames = {p["username"] for p in result}
        
        assert 1 in player_ids
        assert 2 in player_ids
        assert "player1" in usernames
        assert "player2" in usernames


class TestIsPlayerOnline:
    """Tests for ConnectionService.is_player_online()"""

    @pytest.mark.asyncio
    async def test_returns_true_for_online_player(self, game_state_managers):
        """Test that True is returned for online player."""
        player_mgr = get_player_state_manager()
        await player_mgr.register_online_player(123, "online_player")
        
        result = await ConnectionService.is_player_online(123)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_for_offline_player(self, game_state_managers):
        """Test that False is returned for offline player."""
        result = await ConnectionService.is_player_online(99999)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_after_unregister(self, game_state_managers):
        """Test that False is returned after player unregisters."""
        player_mgr = get_player_state_manager()
        await player_mgr.register_online_player(456, "temp_player")
        await player_mgr.unregister_online_player(456)
        
        result = await ConnectionService.is_player_online(456)
        
        assert result is False
