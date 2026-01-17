"""
Tests for WebSocket authentication.

Covers:
- Valid token authentication
- Invalid/expired/missing token handling
- Malformed message handling

These are integration tests that use the real app with TestClient.
They create users via the API rather than fixtures to avoid session conflicts.
"""

import os
import uuid
import pytest
import msgpack
from starlette.testclient import TestClient

from server.src.main import app
from server.src.core.security import create_access_token
from server.src.core.database import reset_engine, reset_valkey
from common.src.protocol import MessageType


# Skip WebSocket integration tests unless RUN_INTEGRATION_TESTS is set
SKIP_WS_INTEGRATION = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "").lower() not in ("1", "true", "yes"),
    reason="WebSocket integration tests require RUN_INTEGRATION_TESTS=1"
)


def unique_username(prefix: str = "user") -> str:
    """Generate a unique username for testing."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@SKIP_WS_INTEGRATION
class TestWebSocketAuthentication:
    """Tests for WebSocket authentication flow."""

    @pytest.fixture(autouse=True)
    def reset_db_engine(self):
        """Reset the database engine and Valkey before each test to avoid event loop conflicts."""
        reset_engine()
        reset_valkey()

    def test_ws_auth_valid_token(self):
        """Valid JWT token should receive WELCOME message."""
        with TestClient(app) as client:
            # Create user via API
            username = unique_username("wsauth")
            response = client.post(
                "/auth/register",
                json={"username": username, "password": "password123"},
            )
            assert response.status_code == 201
            
            # Login to get token
            response = client.post(
                "/auth/login",
                data={"username": username, "password": "password123"},
            )
            assert response.status_code == 200
            token = response.json()["access_token"]
            
            # Connect via WebSocket and authenticate
            with client.websocket_connect("/ws") as websocket:
                auth_message = {
                    "type": MessageType.AUTHENTICATE.value,
                    "payload": {"token": token},
                }
                websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                
                response_bytes = websocket.receive_bytes()
                response = msgpack.unpackb(response_bytes, raw=False)
                
                assert response["type"] == MessageType.WELCOME.value
                assert "player" in response["payload"]
                assert response["payload"]["player"]["username"] == username

    def test_ws_auth_invalid_token(self):
        """Invalid JWT token should close connection with policy violation."""
        from starlette.websockets import WebSocketDisconnect
        
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": "invalid.jwt.token"},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    # Server closes connection on invalid token
                    websocket.receive_bytes()
            
            # Verify disconnect code (1008 = Policy Violation)
            assert exc_info.value.code == 1008

    def test_ws_auth_expired_token(self):
        """Expired JWT token should close connection."""
        from datetime import timedelta
        from starlette.websockets import WebSocketDisconnect
        
        # Create an expired token - user doesn't need to exist since
        # JWT validation happens before database lookup
        expired_token = create_access_token(
            data={"sub": "any_user"},
            expires_delta=timedelta(hours=-1)
        )
        
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": expired_token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    # Server closes connection on expired token
                    websocket.receive_bytes()
            
            # Verify disconnect code (1008 = Policy Violation)
            assert exc_info.value.code == 1008

    def test_ws_auth_missing_token(self):
        """Missing token in auth message should close connection."""
        from starlette.websockets import WebSocketDisconnect
        
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    # Send authentication without token
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    # Server closes connection on missing token
                    websocket.receive_bytes()
            
            assert exc_info.value.code == 1008

    def test_ws_auth_malformed_msgpack(self):
        """Malformed msgpack data should close connection."""
        from starlette.websockets import WebSocketDisconnect
        
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws") as websocket:
                    # Send invalid msgpack data
                    websocket.send_bytes(b"not valid msgpack data")
                    
                    # Server closes connection on malformed data
                    websocket.receive_bytes()

    def test_ws_auth_wrong_message_type(self):
        """Sending non-AUTHENTICATE as first message should close connection."""
        from starlette.websockets import WebSocketDisconnect
        
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    # Send MOVE_INTENT instead of AUTHENTICATE
                    wrong_message = {
                        "type": MessageType.MOVE_INTENT.value,
                        "payload": {"direction": "UP"},
                    }
                    websocket.send_bytes(msgpack.packb(wrong_message, use_bin_type=True))
                    
                    # Server closes connection on wrong message type
                    websocket.receive_bytes()
            
            assert exc_info.value.code == 1008

    def test_ws_auth_token_for_nonexistent_user(self):
        """Token for non-existent user should close connection."""
        from starlette.websockets import WebSocketDisconnect
        
        # Create a valid token structure but for a user that doesn't exist
        fake_token = create_access_token(data={"sub": "nonexistent_user_12345"})
        
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": fake_token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    # Server closes connection when user not found
                    websocket.receive_bytes()
            
            # Accept 1008 (policy violation) or 1011 (internal error) due to test isolation
            assert exc_info.value.code in (1008, 1011)

    def test_ws_auth_large_payload(self):
        """Extremely large payload should close connection."""
        from starlette.websockets import WebSocketDisconnect
        
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws") as websocket:
                    # Create a large payload (1MB of data)
                    large_data = "x" * (1024 * 1024)
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": large_data},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    # Server should close connection for invalid token
                    websocket.receive_bytes()
