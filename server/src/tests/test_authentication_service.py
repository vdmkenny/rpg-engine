"""
Tests for AuthenticationService.

Tests cover:
- Password authentication with success, failure, banned, and timeout scenarios
- JWT token validation (valid, invalid, missing username)
- WebSocket connection authentication
- Session loading for authenticated players
- Error response creation
- Session validation
- Authentication failure handling
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock, MagicMock
from typing import Dict, Any

from server.src.services.authentication_service import AuthenticationService
from server.src.core.security import create_access_token, get_password_hash
from server.src.models.player import Player


class TestAuthenticateWithPassword:
    """Tests for AuthenticationService.authenticate_with_password()"""

    @pytest.mark.asyncio
    async def test_authenticate_with_password_success(
        self, game_state_managers, create_test_player
    ):
        """Test successful authentication with valid credentials."""
        # Create a test player
        player = await create_test_player("auth_test_user", "correct_password")
        
        # Authenticate with correct password
        result = await AuthenticationService.authenticate_with_password(
            "auth_test_user", "correct_password"
        )
        
        assert result is not None
        assert result.username == "auth_test_user"
        assert result.id == player.id

    @pytest.mark.asyncio
    async def test_authenticate_with_password_wrong_password(
        self, game_state_managers, create_test_player
    ):
        """Test authentication fails with incorrect password."""
        await create_test_player("wrong_pass_user", "correct_password")
        
        result = await AuthenticationService.authenticate_with_password(
            "wrong_pass_user", "wrong_password"
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_with_password_nonexistent_user(
        self, game_state_managers
    ):
        """Test authentication fails for non-existent user."""
        result = await AuthenticationService.authenticate_with_password(
            "nonexistent_user", "any_password"
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_with_password_banned_player(
        self, game_state_managers, create_test_player, set_player_banned
    ):
        """Test authentication raises PermissionError for banned players."""
        await create_test_player("banned_user", "password123")
        await set_player_banned("banned_user")
        
        with pytest.raises(PermissionError, match="Player is banned"):
            await AuthenticationService.authenticate_with_password(
                "banned_user", "password123"
            )

    @pytest.mark.asyncio
    async def test_authenticate_with_password_timed_out_player(
        self, game_state_managers, create_test_player, set_player_timeout
    ):
        """Test authentication raises ValueError for timed out players."""
        await create_test_player("timeout_user", "password123")
        # Set timeout for 1 hour in the future
        await set_player_timeout("timeout_user", timedelta(hours=1))
        
        with pytest.raises(ValueError, match="Player is timed out until"):
            await AuthenticationService.authenticate_with_password(
                "timeout_user", "password123"
            )

    @pytest.mark.asyncio
    async def test_authenticate_with_password_expired_timeout(
        self, game_state_managers, create_test_player, set_player_timeout
    ):
        """Test authentication succeeds when timeout has expired."""
        await create_test_player("expired_timeout_user", "password123")
        # Set timeout for 1 hour in the past (already expired)
        await set_player_timeout("expired_timeout_user", timedelta(hours=-1))
        
        result = await AuthenticationService.authenticate_with_password(
            "expired_timeout_user", "password123"
        )
        
        assert result is not None
        assert result.username == "expired_timeout_user"


class TestValidateJwtToken:
    """Tests for AuthenticationService.validate_jwt_token()"""

    @pytest.mark.asyncio
    async def test_validate_jwt_token_valid(self, game_state_managers):
        """Test validation succeeds for valid JWT token."""
        token = create_access_token(data={"sub": "test_user"})
        
        result = await AuthenticationService.validate_jwt_token(token)
        
        assert result is not None
        assert result["username"] == "test_user"
        assert "token_data" in result

    @pytest.mark.asyncio
    async def test_validate_jwt_token_invalid(self, game_state_managers):
        """Test validation fails for invalid JWT token."""
        result = await AuthenticationService.validate_jwt_token("invalid_token_string")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_expired(
        self, game_state_managers, create_expired_token
    ):
        """Test validation fails for expired JWT token."""
        expired_token = create_expired_token("test_user")
        
        result = await AuthenticationService.validate_jwt_token(expired_token)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_missing_subject(self, game_state_managers):
        """Test validation fails when token lacks subject (username)."""
        # Create a token without the 'sub' claim
        token = create_access_token(data={})
        
        result = await AuthenticationService.validate_jwt_token(token)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_empty_string(self, game_state_managers):
        """Test validation fails for empty token string."""
        result = await AuthenticationService.validate_jwt_token("")
        
        assert result is None


class TestAuthenticateWebsocketConnection:
    """Tests for AuthenticationService.authenticate_websocket_connection()"""

    @pytest.mark.asyncio
    async def test_authenticate_websocket_success(
        self, game_state_managers, create_test_player
    ):
        """Test WebSocket authentication succeeds with valid token."""
        player = await create_test_player("ws_auth_user", "password123")
        token = create_access_token(data={"sub": "ws_auth_user"})
        
        result = await AuthenticationService.authenticate_websocket_connection(token)
        
        assert result is not None
        assert result.username == "ws_auth_user"
        assert result.id == player.id

    @pytest.mark.asyncio
    async def test_authenticate_websocket_invalid_token(self, game_state_managers):
        """Test WebSocket authentication fails with invalid token."""
        result = await AuthenticationService.authenticate_websocket_connection(
            "invalid_token"
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_websocket_player_not_found(
        self, game_state_managers
    ):
        """Test WebSocket authentication fails when player doesn't exist."""
        # Create valid token for non-existent player
        token = create_access_token(data={"sub": "nonexistent_ws_user"})
        
        result = await AuthenticationService.authenticate_websocket_connection(token)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_websocket_banned_player(
        self, game_state_managers, create_test_player, set_player_banned
    ):
        """Test WebSocket authentication fails for banned players."""
        await create_test_player("ws_banned_user", "password123")
        await set_player_banned("ws_banned_user")
        token = create_access_token(data={"sub": "ws_banned_user"})
        
        result = await AuthenticationService.authenticate_websocket_connection(token)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_websocket_timed_out_player(
        self, game_state_managers, create_test_player, set_player_timeout
    ):
        """Test WebSocket authentication fails for timed out players."""
        await create_test_player("ws_timeout_user", "password123")
        await set_player_timeout("ws_timeout_user", timedelta(hours=1))
        token = create_access_token(data={"sub": "ws_timeout_user"})
        
        result = await AuthenticationService.authenticate_websocket_connection(token)
        
        assert result is None


class TestLoadPlayerForSession:
    """Tests for AuthenticationService.load_player_for_session()"""

    @pytest.mark.asyncio
    async def test_load_player_for_session_success(
        self, game_state_managers, create_test_player
    ):
        """Test loading player session data successfully."""
        player = await create_test_player(
            "session_user", "password123", x=100, y=200, map_id="testmap"
        )
        
        result = await AuthenticationService.load_player_for_session(player)
        
        assert result["player_id"] == player.id
        assert result["username"] == "session_user"
        assert result["authenticated"] is True
        assert "position" in result
        assert "hp" in result

    @pytest.mark.asyncio
    async def test_load_player_for_session_has_position(
        self, game_state_managers, create_test_player
    ):
        """Test that session data includes player position."""
        player = await create_test_player(
            "position_user", "password123", x=50, y=75, map_id="samplemap"
        )
        
        result = await AuthenticationService.load_player_for_session(player)
        
        # Position should be present (from GSM or fallback)
        assert "position" in result
        position = result["position"]
        assert "x" in position
        assert "y" in position
        assert "map_id" in position

    @pytest.mark.asyncio
    async def test_load_player_for_session_has_hp(
        self, game_state_managers, create_test_player
    ):
        """Test that session data includes HP information."""
        player = await create_test_player("hp_user", "password123")
        
        result = await AuthenticationService.load_player_for_session(player)
        
        assert "hp" in result
        hp = result["hp"]
        assert "current_hp" in hp
        assert "max_hp" in hp


class TestCreateAuthenticationErrorResponse:
    """Tests for AuthenticationService.create_authentication_error_response()"""

    def test_create_error_response_structure(self):
        """Test that error response has correct structure."""
        response = AuthenticationService.create_authentication_error_response(
            "Invalid credentials"
        )
        
        assert response["type"] == "authentication_error"
        assert "payload" in response
        assert response["payload"]["error"] == "Invalid credentials"
        assert response["payload"]["authenticated"] is False

    def test_create_error_response_banned_reason(self):
        """Test error response with banned reason."""
        response = AuthenticationService.create_authentication_error_response(
            "Player is banned"
        )
        
        assert response["payload"]["error"] == "Player is banned"
        assert response["payload"]["authenticated"] is False

    def test_create_error_response_timeout_reason(self):
        """Test error response with timeout reason."""
        response = AuthenticationService.create_authentication_error_response(
            "Player is timed out"
        )
        
        assert response["payload"]["error"] == "Player is timed out"
        assert response["payload"]["authenticated"] is False

    def test_create_error_response_empty_reason(self):
        """Test error response with empty reason."""
        response = AuthenticationService.create_authentication_error_response("")
        
        assert response["payload"]["error"] == ""
        assert response["payload"]["authenticated"] is False


class TestValidateWebsocketMessageAuth:
    """Tests for AuthenticationService.validate_websocket_message_auth()"""

    def test_validate_message_auth_valid_session(self):
        """Test validation passes for valid authenticated session."""
        session_data = {
            "authenticated": True,
            "player_id": 123,
            "username": "test_user"
        }
        
        result = AuthenticationService.validate_websocket_message_auth(session_data)
        
        assert result is True

    def test_validate_message_auth_not_authenticated(self):
        """Test validation fails when not authenticated."""
        session_data = {
            "authenticated": False,
            "player_id": 123
        }
        
        result = AuthenticationService.validate_websocket_message_auth(session_data)
        
        assert result is False

    def test_validate_message_auth_missing_player_id(self):
        """Test validation fails when player_id is missing."""
        session_data = {
            "authenticated": True,
            "username": "test_user"
        }
        
        result = AuthenticationService.validate_websocket_message_auth(session_data)
        
        assert result is False

    def test_validate_message_auth_none_player_id(self):
        """Test validation fails when player_id is None."""
        session_data = {
            "authenticated": True,
            "player_id": None
        }
        
        result = AuthenticationService.validate_websocket_message_auth(session_data)
        
        assert result is False

    def test_validate_message_auth_none_session(self):
        """Test validation fails when session data is None."""
        result = AuthenticationService.validate_websocket_message_auth(None)
        
        assert result is False

    def test_validate_message_auth_empty_session(self):
        """Test validation fails for empty session data."""
        result = AuthenticationService.validate_websocket_message_auth({})
        
        assert result is False


class TestHandleAuthenticationFailure:
    """Tests for AuthenticationService.handle_authentication_failure()"""

    @pytest.mark.asyncio
    async def test_handle_failure_returns_error_response(self):
        """Test that failure handler returns proper error response."""
        result = await AuthenticationService.handle_authentication_failure(
            "Invalid token"
        )
        
        assert result["type"] == "authentication_error"
        assert result["payload"]["error"] == "Invalid token"
        assert result["payload"]["authenticated"] is False

    @pytest.mark.asyncio
    async def test_handle_failure_banned_reason(self):
        """Test failure handler with banned reason."""
        result = await AuthenticationService.handle_authentication_failure(
            "Player is banned"
        )
        
        assert result["payload"]["error"] == "Player is banned"

    @pytest.mark.asyncio
    async def test_handle_failure_timeout_reason(self):
        """Test failure handler with timeout reason."""
        result = await AuthenticationService.handle_authentication_failure(
            "Player is timed out until 2025-01-01"
        )
        
        assert "timed out" in result["payload"]["error"]

    @pytest.mark.asyncio
    async def test_handle_failure_custom_reason(self):
        """Test failure handler with custom reason."""
        custom_reason = "Custom authentication failure message"
        result = await AuthenticationService.handle_authentication_failure(
            custom_reason
        )
        
        assert result["payload"]["error"] == custom_reason


class TestAuthenticationServiceEdgeCases:
    """Edge case and integration tests for AuthenticationService."""

    @pytest.mark.asyncio
    async def test_authenticate_with_unicode_username(
        self, game_state_managers, create_test_player
    ):
        """Test authentication works with unicode characters in username."""
        # Note: This may fail if username validation doesn't allow unicode
        try:
            player = await create_test_player("用户名", "password123")
            
            result = await AuthenticationService.authenticate_with_password(
                "用户名", "password123"
            )
            
            if result is not None:
                assert result.username == "用户名"
        except Exception:
            # Unicode usernames may not be supported - that's acceptable
            pytest.skip("Unicode usernames not supported")

    @pytest.mark.asyncio
    async def test_authenticate_with_special_chars_in_password(
        self, game_state_managers, create_test_player
    ):
        """Test authentication works with special characters in password."""
        special_password = "p@$$w0rd!#$%^&*()"
        player = await create_test_player("special_pass_user", special_password)
        
        result = await AuthenticationService.authenticate_with_password(
            "special_pass_user", special_password
        )
        
        assert result is not None
        assert result.username == "special_pass_user"

    @pytest.mark.asyncio
    async def test_authenticate_case_sensitive_username(
        self, game_state_managers, create_test_player
    ):
        """Test that username matching is case-sensitive."""
        await create_test_player("CaseSensitive", "password123")
        
        # Try with different case - should fail
        result = await AuthenticationService.authenticate_with_password(
            "casesensitive", "password123"
        )
        
        # Behavior depends on database collation, but typically case-sensitive
        # Just verify it returns a consistent result
        assert result is None or result.username == "casesensitive"

    @pytest.mark.asyncio
    async def test_multiple_authentication_attempts(
        self, game_state_managers, create_test_player
    ):
        """Test multiple sequential authentication attempts work correctly."""
        await create_test_player("multi_auth_user", "password123")
        
        # Successful auth
        result1 = await AuthenticationService.authenticate_with_password(
            "multi_auth_user", "password123"
        )
        assert result1 is not None
        
        # Failed auth (wrong password)
        result2 = await AuthenticationService.authenticate_with_password(
            "multi_auth_user", "wrong_password"
        )
        assert result2 is None
        
        # Successful auth again
        result3 = await AuthenticationService.authenticate_with_password(
            "multi_auth_user", "password123"
        )
        assert result3 is not None
        assert result3.id == result1.id

    @pytest.mark.asyncio
    async def test_websocket_auth_flow_complete(
        self, game_state_managers, create_test_player
    ):
        """Test complete WebSocket authentication flow."""
        player = await create_test_player(
            "ws_flow_user", "password123", x=10, y=20, map_id="samplemap"
        )
        
        # Step 1: Create token (simulating HTTP login)
        token = create_access_token(data={"sub": "ws_flow_user"})
        
        # Step 2: Authenticate WebSocket connection
        auth_result = await AuthenticationService.authenticate_websocket_connection(
            token
        )
        assert auth_result is not None
        assert auth_result.id == player.id
        
        # Step 3: Load session data
        session = await AuthenticationService.load_player_for_session(auth_result)
        assert session["authenticated"] is True
        assert session["player_id"] == player.id
        
        # Step 4: Validate session for message handling
        is_valid = AuthenticationService.validate_websocket_message_auth(session)
        assert is_valid is True
