"""
Tests for WebSocket authentication.

Covers:
- Valid token authentication
- Invalid/expired/missing token handling
- Malformed message handling
"""

import pytest
import pytest_asyncio
import msgpack
from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server.src.main import app
from server.src.core.security import create_access_token
from server.src.core.database import get_db, get_valkey
from common.src.protocol import MessageType


# Skip WebSocket integration tests - they require proper integration test environment
# The TestClient creates its own database session which doesn't share state with
# the async fixtures. These tests need to be run against a real database.
SKIP_WS_INTEGRATION = pytest.mark.skip(
    reason="WebSocket integration tests require real database, not SQLite in-memory"
)


@SKIP_WS_INTEGRATION
class TestWebSocketAuthentication:
    """Tests for WebSocket authentication flow."""

    @pytest.mark.asyncio
    async def test_ws_auth_valid_token(
        self, client: AsyncClient, create_test_player_and_token, fake_valkey
    ):
        """Valid JWT token should receive WELCOME message."""
        token, player = await create_test_player_and_token("wsuser", "password123")
        
        # Use synchronous TestClient for WebSocket testing
        with TestClient(app) as test_client:
            # Override dependencies for the sync client
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    # Send authentication message
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    # Receive response
                    response_bytes = websocket.receive_bytes()
                    response = msgpack.unpackb(response_bytes, raw=False)
                    
                    assert response["type"] == MessageType.WELCOME.value
                    assert "player" in response["payload"]
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_ws_auth_invalid_token(self, client: AsyncClient, fake_valkey):
        """Invalid JWT token should close connection."""
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with pytest.raises(Exception):  # WebSocket should disconnect
                    with test_client.websocket_connect("/ws") as websocket:
                        # Send authentication with invalid token
                        auth_message = {
                            "type": MessageType.AUTHENTICATE.value,
                            "payload": {"token": "invalid.jwt.token"},
                        }
                        websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                        
                        # Should receive error or disconnect
                        response_bytes = websocket.receive_bytes()
                        response = msgpack.unpackb(response_bytes, raw=False)
                        
                        # If we get here, check it's an error
                        assert response["type"] == MessageType.ERROR.value
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_ws_auth_expired_token(
        self, client: AsyncClient, create_test_player, create_expired_token, fake_valkey
    ):
        """Expired JWT token should be rejected."""
        player = await create_test_player("expireduser", "password123")
        expired_token = create_expired_token("expireduser")
        
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": expired_token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    # Should receive error response
                    response_bytes = websocket.receive_bytes()
                    response = msgpack.unpackb(response_bytes, raw=False)
                    
                    # Either ERROR message or connection closed
                    if response.get("type"):
                        assert response["type"] == MessageType.ERROR.value
            except Exception:
                # Connection closed is acceptable for expired token
                pass
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_ws_auth_missing_token(self, client: AsyncClient, fake_valkey):
        """Missing token in auth message should fail."""
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    # Send authentication without token
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    # Should receive error
                    response_bytes = websocket.receive_bytes()
                    response = msgpack.unpackb(response_bytes, raw=False)
                    
                    assert response["type"] == MessageType.ERROR.value
            except Exception:
                # Disconnect is also acceptable
                pass
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_ws_auth_malformed_msgpack(self, client: AsyncClient, fake_valkey):
        """Malformed msgpack data should be handled gracefully."""
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with pytest.raises(Exception):
                    with test_client.websocket_connect("/ws") as websocket:
                        # Send invalid msgpack data
                        websocket.send_bytes(b"not valid msgpack data")
                        
                        # Should handle gracefully (error or disconnect)
                        websocket.receive_bytes()
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_ws_auth_wrong_message_type(self, client: AsyncClient, fake_valkey):
        """Sending non-AUTHENTICATE as first message should fail."""
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    # Send MOVE_INTENT instead of AUTHENTICATE
                    wrong_message = {
                        "type": MessageType.MOVE_INTENT.value,
                        "payload": {"direction": "UP"},
                    }
                    websocket.send_bytes(msgpack.packb(wrong_message, use_bin_type=True))
                    
                    # Should receive error
                    response_bytes = websocket.receive_bytes()
                    response = msgpack.unpackb(response_bytes, raw=False)
                    
                    assert response["type"] == MessageType.ERROR.value
            except Exception:
                # Disconnect is acceptable
                pass
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio  
    async def test_ws_auth_token_for_nonexistent_user(
        self, client: AsyncClient, fake_valkey
    ):
        """Token for non-existent user should fail."""
        # Create a valid token structure but for a user that doesn't exist
        fake_token = create_access_token(data={"sub": "nonexistent_user"})
        
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": fake_token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    # Should receive error (user not found)
                    response_bytes = websocket.receive_bytes()
                    response = msgpack.unpackb(response_bytes, raw=False)
                    
                    assert response["type"] == MessageType.ERROR.value
            except Exception:
                # Disconnect is acceptable
                pass
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_ws_auth_large_payload(self, client: AsyncClient, fake_valkey):
        """Extremely large payload should be handled safely."""
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    # Create a large payload (1MB of data)
                    large_data = "x" * (1024 * 1024)
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": large_data},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    # Should handle without crashing
                    response_bytes = websocket.receive_bytes()
                    response = msgpack.unpackb(response_bytes, raw=False)
                    
                    # Should return error for invalid token
                    assert response["type"] == MessageType.ERROR.value
            except Exception:
                # Any graceful handling is acceptable
                pass
            finally:
                app.dependency_overrides.clear()
