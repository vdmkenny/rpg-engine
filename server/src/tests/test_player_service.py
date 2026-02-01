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
from server.src.services.game_state_manager import GameStateManager
from server.src.schemas.player import PlayerCreate, PlayerRole
from server.src.models.player import Player
from fastapi import HTTPException


class TestPlayerCreation:
    """Tests for PlayerService.create_player()"""

    @pytest.mark.asyncio
    async def test_create_player_success(self, gsm: GameStateManager, session):
        """Test successful player creation."""
        player_data = PlayerCreate(username="new_test_player", password="password123")
        
        player = await PlayerService.create_player(player_data, x=15, y=25, map_id="samplemap")
        
        assert player.username == "new_test_player"
        assert player.x_coord == 15
        assert player.y_coord == 25
        assert player.map_id == "samplemap"
        assert player.id is not None

    @pytest.mark.asyncio
    async def test_create_player_default_position(self, gsm: GameStateManager, session):
        """Test player creation with default position."""
        player_data = PlayerCreate(username="default_pos_player", password="password123")
        
        player = await PlayerService.create_player(player_data)
        
        # Default position from PlayerCreate or service defaults
        assert player.x_coord is not None
        assert player.y_coord is not None
        assert player.map_id is not None

    @pytest.mark.asyncio
    async def test_create_player_duplicate_username(self, gsm: GameStateManager, session):
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
    async def test_login_player_success(self, gsm: GameStateManager, create_test_player):
        """Test successful player login."""
        player = await create_test_player("login_test_user", "password123")
        
        # Unregister first so we can test login (async method)
        await gsm.unregister_online_player(player.id)
        assert not gsm.is_online(player.id)
        
        await PlayerService.login_player(player)
        
        assert gsm.is_online(player.id)

    @pytest.mark.asyncio
    async def test_login_loads_player_state(self, gsm: GameStateManager, create_test_player):
        """Test that login loads player state into GSM."""
        player = await create_test_player("state_load_test", "password123")
        
        # Unregister to clear state (async method)
        await gsm.unregister_online_player(player.id)
        
        await PlayerService.login_player(player)
        
        # State should be loaded
        state = await gsm.get_player_full_state(player.id)
        assert state is not None


class TestPlayerLogout:
    """Tests for PlayerService.logout_player()"""

    @pytest.mark.asyncio
    async def test_logout_player_success(self, gsm: GameStateManager, create_test_player):
        """Test successful player logout."""
        player = await create_test_player("logout_test_user", "password123")
        
        assert gsm.is_online(player.id)
        
        await PlayerService.logout_player(player.id, player.username)
        
        assert not gsm.is_online(player.id)


class TestGetPlayerByUsername:
    """Tests for PlayerService.get_player_by_username()"""

    @pytest.mark.asyncio
    async def test_get_existing_player(self, gsm: GameStateManager, create_test_player):
        """Test getting an existing player by username."""
        original = await create_test_player("get_by_username_test", "password123")
        
        player = await PlayerService.get_player_by_username("get_by_username_test")
        
        assert player is not None
        assert player.id == original.id
        assert player.username == "get_by_username_test"

    @pytest.mark.asyncio
    async def test_get_nonexistent_player(self, gsm: GameStateManager):
        """Test getting a non-existent player returns None."""
        player = await PlayerService.get_player_by_username("nonexistent_username_12345")
        
        assert player is None


class TestGetPlayerById:
    """Tests for PlayerService.get_player_by_id()"""

    @pytest.mark.asyncio
    async def test_get_existing_player_by_id(self, gsm: GameStateManager, create_test_player):
        """Test getting an existing player by ID."""
        original = await create_test_player("get_by_id_test", "password123")
        
        player = await PlayerService.get_player_by_id(original.id)
        
        assert player is not None
        assert player.id == original.id
        assert player.username == "get_by_id_test"

    @pytest.mark.asyncio
    async def test_get_nonexistent_player_by_id(self, gsm: GameStateManager):
        """Test getting a non-existent player by ID returns None."""
        player = await PlayerService.get_player_by_id(99999)
        
        assert player is None


class TestIsPlayerOnline:
    """Tests for PlayerService.is_player_online()"""

    def test_online_player(self, gsm: GameStateManager):
        """Test that online player returns True."""
        gsm.register_online_player(123, "online_test")
        
        result = PlayerService.is_player_online(123)
        
        assert result is True

    def test_offline_player(self, gsm: GameStateManager):
        """Test that offline player returns False."""
        result = PlayerService.is_player_online(99999)
        
        assert result is False


class TestGetPlayerPosition:
    """Tests for PlayerService.get_player_position()"""

    @pytest.mark.asyncio
    async def test_get_position_online_player(self, gsm: GameStateManager, create_test_player):
        """Test getting position for online player."""
        player = await create_test_player("position_test", "password123")
        
        # Set up position
        await gsm.set_player_full_state(player.id, 50, 60, "samplemap", 100, 100)
        
        position = await PlayerService.get_player_position(player.id)
        
        assert position is not None
        assert position["x"] == 50
        assert position["y"] == 60
        assert position["map_id"] == "samplemap"

    @pytest.mark.asyncio
    async def test_get_position_offline_player(self, gsm: GameStateManager):
        """Test getting position for offline player returns None."""
        position = await PlayerService.get_player_position(99999)
        
        assert position is None


class TestGetNearbyPlayers:
    """Tests for PlayerService.get_nearby_players()"""

    @pytest.mark.asyncio
    async def test_get_nearby_players_same_map(self, gsm: GameStateManager, create_test_player):
        """Test finding nearby players on the same map."""
        player1 = await create_test_player("nearby_test1", "password123")
        player2 = await create_test_player("nearby_test2", "password123")
        
        # Place both players near each other on same map
        await gsm.set_player_full_state(player1.id, 50, 50, "samplemap", 100, 100)
        await gsm.set_player_full_state(player2.id, 55, 55, "samplemap", 100, 100)
        
        nearby = await PlayerService.get_nearby_players(player1.id, range_tiles=80)
        
        # player2 should be nearby
        nearby_ids = [p["player_id"] for p in nearby]
        assert player2.id in nearby_ids

    @pytest.mark.asyncio
    async def test_get_nearby_players_different_map(self, gsm: GameStateManager, create_test_player):
        """Test that players on different maps are not nearby."""
        player1 = await create_test_player("map_test1", "password123")
        player2 = await create_test_player("map_test2", "password123")
        
        # Place players on different maps
        await gsm.set_player_full_state(player1.id, 50, 50, "samplemap", 100, 100)
        await gsm.set_player_full_state(player2.id, 50, 50, "othermap", 100, 100)
        
        nearby = await PlayerService.get_nearby_players(player1.id, range_tiles=80)
        
        # player2 should NOT be nearby (different map)
        nearby_ids = [p["player_id"] for p in nearby]
        assert player2.id not in nearby_ids

    @pytest.mark.asyncio
    async def test_get_nearby_players_out_of_range(self, gsm: GameStateManager, create_test_player):
        """Test that players far away are not nearby."""
        player1 = await create_test_player("range_test1", "password123")
        player2 = await create_test_player("range_test2", "password123")
        
        # Place players far apart
        await gsm.set_player_full_state(player1.id, 0, 0, "samplemap", 100, 100)
        await gsm.set_player_full_state(player2.id, 500, 500, "samplemap", 100, 100)
        
        nearby = await PlayerService.get_nearby_players(player1.id, range_tiles=80)
        
        # player2 should NOT be nearby (too far)
        nearby_ids = [p["player_id"] for p in nearby]
        assert player2.id not in nearby_ids

    @pytest.mark.asyncio
    async def test_get_nearby_players_excludes_self(self, gsm: GameStateManager, create_test_player):
        """Test that player is not in their own nearby list."""
        player = await create_test_player("self_test", "password123")
        
        await gsm.set_player_full_state(player.id, 50, 50, "samplemap", 100, 100)
        
        nearby = await PlayerService.get_nearby_players(player.id, range_tiles=80)
        
        # Self should NOT be in nearby list
        nearby_ids = [p["player_id"] for p in nearby]
        assert player.id not in nearby_ids


class TestValidatePlayerPositionAccess:
    """Tests for PlayerService.validate_player_position_access()"""

    @pytest.mark.asyncio
    async def test_valid_access_same_area(self, gsm: GameStateManager, create_test_player):
        """Test that access is valid for nearby position."""
        player = await create_test_player("access_test", "password123")
        
        await gsm.set_player_full_state(player.id, 50, 50, "samplemap", 100, 100)
        
        result = await PlayerService.validate_player_position_access(
            player.id, "samplemap", 55, 55  # Close to player
        )
        
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_access_wrong_map(self, gsm: GameStateManager, create_test_player):
        """Test that access is denied for different map."""
        player = await create_test_player("wrong_map_test", "password123")
        
        await gsm.set_player_full_state(player.id, 50, 50, "samplemap", 100, 100)
        
        result = await PlayerService.validate_player_position_access(
            player.id, "other_map", 50, 50
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_access_too_far(self, gsm: GameStateManager, create_test_player):
        """Test that access is denied for distant position."""
        player = await create_test_player("far_pos_test", "password123")
        
        await gsm.set_player_full_state(player.id, 50, 50, "samplemap", 100, 100)
        
        result = await PlayerService.validate_player_position_access(
            player.id, "samplemap", 500, 500  # Too far
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_access_offline_player(self, gsm: GameStateManager):
        """Test that access is denied for offline player."""
        result = await PlayerService.validate_player_position_access(
            99999, "samplemap", 50, 50
        )
        
        assert result is False


class TestGetPlayerRole:
    """Tests for PlayerService.get_player_role()"""

    @pytest.mark.asyncio
    async def test_get_player_role(self, gsm: GameStateManager, create_test_player):
        """Test getting player role."""
        player = await create_test_player("role_test", "password123")
        
        # Mock permissions to return a role
        with patch.object(gsm, "get_player_permissions", new_callable=AsyncMock) as mock_perm:
            mock_perm.return_value = {"role": "admin"}
            
            role = await PlayerService.get_player_role(player.id)
            
            assert role == PlayerRole.ADMIN

    @pytest.mark.asyncio
    async def test_get_player_role_default(self, gsm: GameStateManager, create_test_player):
        """Test getting default player role."""
        player = await create_test_player("default_role_test", "password123")
        
        with patch.object(gsm, "get_player_permissions", new_callable=AsyncMock) as mock_perm:
            mock_perm.return_value = {"role": "player"}
            
            role = await PlayerService.get_player_role(player.id)
            
            assert role == PlayerRole.PLAYER

    @pytest.mark.asyncio
    async def test_get_player_role_none(self, gsm: GameStateManager):
        """Test getting role for non-existent player."""
        with patch.object(gsm, "get_player_permissions", new_callable=AsyncMock) as mock_perm:
            mock_perm.return_value = None
            
            role = await PlayerService.get_player_role(99999)
            
            assert role is None


class TestCheckGlobalChatPermission:
    """Tests for PlayerService.check_global_chat_permission()"""

    @pytest.mark.asyncio
    async def test_admin_has_global_chat_permission(self, gsm: GameStateManager, create_test_player):
        """Test that admin has global chat permission."""
        player = await create_test_player("admin_chat_test", "password123")
        
        with patch("server.src.services.player_service.settings") as mock_settings:
            mock_settings.CHAT_GLOBAL_ENABLED = True
            mock_settings.CHAT_GLOBAL_ALLOWED_ROLES = ["ADMIN", "MODERATOR"]
            
            with patch.object(PlayerService, "get_player_role", new_callable=AsyncMock) as mock_role:
                mock_role.return_value = PlayerRole.ADMIN
                
                result = await PlayerService.check_global_chat_permission(player.id)
                
                assert result is True

    @pytest.mark.asyncio
    async def test_player_no_global_chat_permission(self, gsm: GameStateManager, create_test_player):
        """Test that regular player lacks global chat permission."""
        player = await create_test_player("player_chat_test", "password123")
        
        with patch("server.src.services.player_service.settings") as mock_settings:
            mock_settings.CHAT_GLOBAL_ENABLED = True
            mock_settings.CHAT_GLOBAL_ALLOWED_ROLES = ["ADMIN", "MODERATOR"]  # Player not in list
            
            with patch.object(PlayerService, "get_player_role", new_callable=AsyncMock) as mock_role:
                mock_role.return_value = PlayerRole.PLAYER
                
                result = await PlayerService.check_global_chat_permission(player.id)
                
                assert result is False

    @pytest.mark.asyncio
    async def test_global_chat_disabled(self, gsm: GameStateManager, create_test_player):
        """Test that global chat is denied when disabled."""
        player = await create_test_player("disabled_chat_test", "password123")
        
        with patch("server.src.services.player_service.settings") as mock_settings:
            mock_settings.CHAT_GLOBAL_ENABLED = False
            
            result = await PlayerService.check_global_chat_permission(player.id)
            
            assert result is False


class TestGetUsernameByPlayerId:
    """Tests for PlayerService.get_username_by_player_id()"""

    @pytest.mark.asyncio
    async def test_get_username_online_player(self, gsm: GameStateManager, create_test_player):
        """Test getting username for online player (fast path)."""
        player = await create_test_player("username_lookup_test", "password123")
        
        username = await PlayerService.get_username_by_player_id(player.id)
        
        assert username == "username_lookup_test"

    @pytest.mark.asyncio
    async def test_get_username_nonexistent_player(self, gsm: GameStateManager):
        """Test getting username for non-existent player."""
        username = await PlayerService.get_username_by_player_id(99999)
        
        assert username is None


class TestDeletePlayer:
    """Tests for PlayerService.delete_player()"""

    @pytest.mark.asyncio
    async def test_delete_existing_player(self, gsm: GameStateManager, session):
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
    async def test_delete_nonexistent_player(self, gsm: GameStateManager):
        """Test deleting a non-existent player."""
        result = await PlayerService.delete_player(99999)
        
        assert result is False


class TestGetPlayerDataById:
    """Tests for PlayerService.get_player_data_by_id() - alias test"""

    @pytest.mark.asyncio
    async def test_get_player_data_by_id(self, gsm: GameStateManager, create_test_player):
        """Test that get_player_data_by_id works as alias."""
        player = await create_test_player("data_by_id_test", "password123")
        
        result = await PlayerService.get_player_data_by_id(player.id)
        
        assert result is not None
        assert result.id == player.id
        assert result.username == "data_by_id_test"
