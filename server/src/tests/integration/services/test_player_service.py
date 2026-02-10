"""
Unit tests for PlayerService.

Tests player creation, login/logout, position management, 
role checking, and permission validation.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from server.src.services.player_service import PlayerService
from server.src.services.game_state import get_player_state_manager
from server.src.core.constants import PlayerRole
from server.src.schemas.player import PlayerCreate
from server.src.models.player import Player
from fastapi import HTTPException


class TestPlayerCreation:
    """Tests for PlayerService.create_player()"""

    @pytest.mark.asyncio
    async def test_create_player_success(self, game_state_managers, session):
        """Test successful player creation."""
        player_data = PlayerCreate(username="new_test_player", password="password123")
        
        player = await PlayerService.create_player(player_data, x=15, y=25, map_id="samplemap")
        
        assert player.username == "new_test_player"
        assert player.x == 15
        assert player.y == 25
        assert player.map_id == "samplemap"
        assert player.id is not None

    @pytest.mark.asyncio
    async def test_create_player_default_position(self, game_state_managers, session):
        """Test player creation with default position."""
        player_data = PlayerCreate(username="default_pos_player", password="password123")
        
        player = await PlayerService.create_player(player_data)
        
        # Default position from PlayerCreate or service defaults
        assert player.x is not None
        assert player.y is not None
        assert player.map_id is not None

    @pytest.mark.asyncio
    async def test_create_player_duplicate_username(self, game_state_managers, session):
        """Test that duplicate username raises HTTPException."""
        player_data = PlayerCreate(username="duplicate_test", password="password123")
        
        # Create first player
        await PlayerService.create_player(player_data)
        
        # Attempt to create duplicate
        with pytest.raises(HTTPException) as exc_info:
            await PlayerService.create_player(player_data)
        
        assert exc_info.value.status_code == 400
        assert "already exists" in str(exc_info.value.detail)


class TestPlayerLogin:
    """Tests for PlayerService.login_player()"""

    @pytest.mark.asyncio
    async def test_login_player_success(self, game_state_managers, create_test_player):
        """Test successful player login."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("login_test_user", "password123")
        
        # Unregister first so we can test login (async method)
        await player_mgr.unregister_online_player(player.id)
        assert not await player_mgr.is_online(player.id)
        
        await PlayerService.login_player(player.id)
        
        assert await player_mgr.is_online(player.id)

    @pytest.mark.asyncio
    async def test_login_loads_player_state(self, game_state_managers, create_test_player):
        """Test that login loads player state into GSM."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("state_load_test", "password123")
        
        # Unregister to clear state (async method)
        await player_mgr.unregister_online_player(player.id)
        
        await PlayerService.login_player(player.id)
        
        # State should be loaded
        state = await player_mgr.get_player_full_state(player.id)
        assert state is not None


class TestPlayerLogout:
    """Tests for PlayerService.logout_player()"""

    @pytest.mark.asyncio
    async def test_logout_player_success(self, game_state_managers, create_test_player):
        """Test successful player logout."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("logout_test_user", "password123")
        
        assert await player_mgr.is_online(player.id)
        
        await PlayerService.logout_player(player.id)
        
        assert not await player_mgr.is_online(player.id)


class TestGetPlayerByUsername:
    """Tests for PlayerService.get_player_by_username()"""

    @pytest.mark.asyncio
    async def test_get_existing_player(self, game_state_managers, create_test_player):
        """Test getting an existing player by username."""
        original = await create_test_player("get_by_username_test", "password123")
        
        player = await PlayerService.get_player_by_username("get_by_username_test")
        
        assert player is not None
        assert player.id == original.id
        assert player.username == "get_by_username_test"

    @pytest.mark.asyncio
    async def test_get_nonexistent_player(self, game_state_managers):
        """Test getting a non-existent player returns None."""
        player = await PlayerService.get_player_by_username("nonexistent_username_12345")
        
        assert player is None


class TestGetPlayerById:
    """Tests for PlayerService.get_player_by_id()"""

    @pytest.mark.asyncio
    async def test_get_existing_player_by_id(self, game_state_managers, create_test_player):
        """Test getting an existing player by ID."""
        original = await create_test_player("get_by_id_test", "password123")
        
        player = await PlayerService.get_player_by_id(original.id)
        
        assert player is not None
        assert player.id == original.id
        assert player.username == "get_by_id_test"

    @pytest.mark.asyncio
    async def test_get_nonexistent_player_by_id(self, game_state_managers):
        """Test getting a non-existent player by ID returns None."""
        player = await PlayerService.get_player_by_id(99999)
        
        assert player is None


class TestIsPlayerOnline:
    """Tests for PlayerService.is_player_online()"""

    @pytest.mark.asyncio
    async def test_online_player(self, game_state_managers):
        """Test that online player returns True."""
        player_mgr = get_player_state_manager()
        await player_mgr.register_online_player(123, "test_user_123")
        
        result = await PlayerService.is_player_online(123)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_offline_player(self, game_state_managers):
        """Test that offline player returns False."""
        result = await PlayerService.is_player_online(99999)
        
        assert result is False


class TestGetPlayerPosition:
    """Tests for PlayerService.get_player_position()"""

    @pytest.mark.asyncio
    async def test_get_position_online_player(self, game_state_managers, create_test_player):
        """Test getting position for online player."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("position_test", "password123")
        
        # Set up position
        await player_mgr.set_player_full_state(
            player.id,
            state={"x": 50, "y": 60, "map_id": "samplemap", "current_hp": 100, "max_hp": 100}
        )
        
        position = await PlayerService.get_player_position(player.id)
        
        assert position is not None
        assert position.x == 50
        assert position.y == 60
        assert position.map_id == "samplemap"

    @pytest.mark.asyncio
    async def test_get_position_offline_player(self, game_state_managers):
        """Test getting position for offline player returns None."""
        position = await PlayerService.get_player_position(99999)
        
        assert position is None


class TestGetNearbyPlayers:
    """Tests for PlayerService.get_nearby_players()"""

    @pytest.mark.asyncio
    async def test_get_nearby_players_same_map(self, game_state_managers, create_test_player):
        """Test finding nearby players on the same map."""
        player_mgr = get_player_state_manager()
        player1 = await create_test_player("nearby_test1", "password123")
        player2 = await create_test_player("nearby_test2", "password123")
        
        # Place both players near each other on same map
        await player_mgr.set_player_full_state(
            player1.id,
            state={"x": 50, "y": 50, "map_id": "samplemap", "current_hp": 100, "max_hp": 100}
        )
        await player_mgr.set_player_full_state(
            player2.id,
            state={"x": 55, "y": 55, "map_id": "samplemap", "current_hp": 100, "max_hp": 100}
        )
        
        nearby = await PlayerService.get_nearby_players(player1.id, radius=80)
        
        # player2 should be nearby
        nearby_ids = [p.player_id for p in nearby]
        assert player2.id in nearby_ids

    @pytest.mark.asyncio
    async def test_get_nearby_players_different_map(self, game_state_managers, create_test_player):
        """Test that players on different maps are not nearby."""
        player_mgr = get_player_state_manager()
        player1 = await create_test_player("map_test1", "password123")
        player2 = await create_test_player("map_test2", "password123")
        
        # Place players on different maps
        await player_mgr.set_player_full_state(
            player1.id,
            state={"x": 50, "y": 50, "map_id": "samplemap", "current_hp": 100, "max_hp": 100}
        )
        await player_mgr.set_player_full_state(
            player2.id,
            state={"x": 50, "y": 50, "map_id": "othermap", "current_hp": 100, "max_hp": 100}
        )
        
        nearby = await PlayerService.get_nearby_players(player1.id, radius=80)
        
        # player2 should NOT be nearby (different map)
        nearby_ids = [p.player_id for p in nearby]
        assert player2.id not in nearby_ids

    @pytest.mark.asyncio
    async def test_get_nearby_players_out_of_range(self, game_state_managers, create_test_player):
        """Test that players far away are not nearby."""
        player_mgr = get_player_state_manager()
        player1 = await create_test_player("range_test1", "password123")
        player2 = await create_test_player("range_test2", "password123")
        
        # Place players far apart
        await player_mgr.set_player_full_state(player1.id, state={"x": 0, "y": 0, "map_id": "samplemap", "current_hp": 100, "max_hp": 100})
        await player_mgr.set_player_full_state(player2.id, state={"x": 500, "y": 500, "map_id": "samplemap", "current_hp": 100, "max_hp": 100})
        
        nearby = await PlayerService.get_nearby_players(player1.id, radius=80)
        
        # player2 should NOT be nearby (too far)
        nearby_ids = [p.player_id for p in nearby]
        assert player2.id not in nearby_ids

    @pytest.mark.asyncio
    async def test_get_nearby_players_excludes_self(self, game_state_managers, create_test_player):
        """Test that player is not in their own nearby list."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("self_test", "password123")
        
        await player_mgr.set_player_full_state(player.id, state={"x": 50, "y": 50, "map_id": "samplemap", "current_hp": 100, "max_hp": 100})
        
        nearby = await PlayerService.get_nearby_players(player.id, radius=80)
        
        # Self should NOT be in nearby list
        nearby_ids = [p.player_id for p in nearby]
        assert player.id not in nearby_ids


class TestDeletePlayer:
    """Tests for PlayerService.delete_player()"""

    @pytest.mark.asyncio
    async def test_delete_existing_player(self, game_state_managers, session):
        """Test deleting an existing player."""
        # Create player directly
        player_data = PlayerCreate(username="delete_test_player", password="password123")
        player = await PlayerService.create_player(player_data)
        player_id = player.id
        
        result = await PlayerService.delete_player(player_id)
        
        assert result is True
        
        # Verify player is gone
        deleted_player = await PlayerService.get_player_by_id(player_id)
        assert deleted_player is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_player(self, game_state_managers):
        """Test deleting a non-existent player."""
        result = await PlayerService.delete_player(99999)
        
        assert result is False


class TestGetPlayersOnMap:
    """Tests for PlayerService.get_players_on_map()"""

    @pytest.mark.asyncio
    async def test_get_players_on_map_returns_players(self, game_state_managers, create_test_player):
        """Test getting players on a specific map."""
        player_mgr = get_player_state_manager()
        player1 = await create_test_player("map_player1", "password123")
        player2 = await create_test_player("map_player2", "password123")
        
        # Place both players on same map
        await player_mgr.set_player_full_state(player1.id, state={"x": 50, "y": 50, "map_id": "test_map", "current_hp": 100, "max_hp": 100})
        await player_mgr.set_player_full_state(player2.id, state={"x": 60, "y": 60, "map_id": "test_map", "current_hp": 100, "max_hp": 100})
        
        players = await PlayerService.get_players_on_map("test_map")
        
        assert len(players) >= 2
        player_ids = [p.player_id for p in players]
        assert player1.id in player_ids
        assert player2.id in player_ids
        
        # Check structure of returned data
        for player in players:
            if player.player_id == player1.id:
                assert player.username == "map_player1"
                assert player.x == 50
                assert player.y == 50

    @pytest.mark.asyncio
    async def test_get_players_on_map_filters_by_map(self, game_state_managers, create_test_player):
        """Test that only players on specified map are returned."""
        player_mgr = get_player_state_manager()
        player1 = await create_test_player("filter_test1", "password123")
        player2 = await create_test_player("filter_test2", "password123")
        
        # Place players on different maps
        await player_mgr.set_player_full_state(player1.id, state={"x": 50, "y": 50, "map_id": "map_a", "current_hp": 100, "max_hp": 100})
        await player_mgr.set_player_full_state(player2.id, state={"x": 60, "y": 60, "map_id": "map_b", "current_hp": 100, "max_hp": 100})
        
        players_on_a = await PlayerService.get_players_on_map("map_a")
        players_on_b = await PlayerService.get_players_on_map("map_b")
        
        # player1 should be on map_a only
        ids_on_a = [p.player_id for p in players_on_a]
        ids_on_b = [p.player_id for p in players_on_b]
        
        assert player1.id in ids_on_a
        assert player1.id not in ids_on_b
        assert player2.id in ids_on_b
        assert player2.id not in ids_on_a

    @pytest.mark.asyncio
    async def test_get_players_on_map_empty(self, game_state_managers):
        """Test getting players on a map with no players."""
        players = await PlayerService.get_players_on_map("nonexistent_map_12345")
        
        assert players == []

    @pytest.mark.asyncio
    async def test_get_players_on_map_includes_position(self, game_state_managers, create_test_player):
        """Test that returned player data includes position."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("pos_check_test", "password123")
        
        await player_mgr.set_player_full_state(player.id, state={"x": 123, "y": 456, "map_id": "pos_map", "current_hp": 100, "max_hp": 100})
        
        players = await PlayerService.get_players_on_map("pos_map")
        
        found = False
        for p in players:
            if p.player_id == player.id:
                found = True
                assert p.x == 123
                assert p.y == 456
                assert p.username == "pos_check_test"
                break
        
        assert found, "Player not found in results"
