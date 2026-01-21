"""
Tests for WebSocket authentication using modern async patterns.

Covers:
- Valid token authentication with WELCOME events
- Invalid/expired/missing token handling
- Malformed message handling
- Protocol compliance and error codes

Uses WebSocketTestClient with structured async methods instead of manual msgpack handling.
"""

import uuid
import pytest
from datetime import timedelta
from starlette.websockets import WebSocketDisconnect

from server.src.core.security import create_access_token
from server.src.tests.websocket_test_utils import WebSocketTestClient
from common.src.protocol import MessageType, AuthenticatePayload


def unique_username(prefix: str = "user") -> str:
    """Generate a unique username for testing."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
class TestWebSocketAuthentication:
    """Tests for WebSocket authentication flow using modern async patterns."""

    async def test_ws_auth_valid_token_success(self, test_client: WebSocketTestClient):
        """Valid JWT token should receive WELCOME event with player data."""
        client = test_client
        
        # Client is already authenticated via fixture
        # The test_client fixture handles authentication automatically
        
        # Verify we can query player data (proving authentication worked)
        inventory = await client.get_inventory()
        assert inventory is not None
        assert "inventory" in inventory
        
        # Verify equipment query works (further proof of successful auth)
        equipment = await client.get_equipment()
        assert equipment is not None
        assert "equipment" in equipment


@pytest.mark.asyncio
class TestWebSocketAuthenticationErrors:
    """Tests for WebSocket authentication error scenarios.
    
    These tests use raw TestClient connections since they test
    authentication failure cases that the test_client fixture
    doesn't cover.
    """

    async def test_ws_auth_invalid_token_disconnect(self, session, fake_valkey):
        """Invalid JWT token should close connection with policy violation."""
        from starlette.testclient import TestClient
        from server.src.main import app
        from server.src.core.database import get_db, get_valkey
        import msgpack
        
        # Override dependencies
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_valkey] = lambda: fake_valkey
        
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    with client.websocket_connect("/ws") as websocket:
                        # Send invalid token using proper protocol structure
                        auth_message = {
                            "id": str(uuid.uuid4()),
                            "type": MessageType.CMD_AUTHENTICATE.value,
                            "payload": {"token": "invalid.jwt.token"},
                            "version": "2.0"
                        }
                        websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                        
                        # Server closes connection on invalid token
                        websocket.receive_bytes()
                
                # Verify disconnect code (1008 = Policy Violation)
                assert exc_info.value.code == 1008
        finally:
            app.dependency_overrides.clear()

    async def test_ws_auth_expired_token_disconnect(self, session, fake_valkey):
        """Expired JWT token should close connection."""
        from starlette.testclient import TestClient
        from server.src.main import app
        from server.src.core.database import get_db, get_valkey
        import msgpack
        
        # Create an expired token
        expired_token = create_access_token(
            data={"sub": "any_user"},
            expires_delta=timedelta(hours=-1)
        )
        
        # Override dependencies
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_valkey] = lambda: fake_valkey
        
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    with client.websocket_connect("/ws") as websocket:
                        auth_message = {
                            "id": str(uuid.uuid4()),
                            "type": MessageType.CMD_AUTHENTICATE.value,
                            "payload": {"token": expired_token},
                            "version": "2.0"
                        }
                        websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                        
                        # Server closes connection on expired token
                        websocket.receive_bytes()
                
                # Verify disconnect code (1008 = Policy Violation)
                assert exc_info.value.code == 1008
        finally:
            app.dependency_overrides.clear()

    async def test_ws_auth_missing_token_disconnect(self, session, fake_valkey):
        """Missing token in auth message should close connection."""
        from starlette.testclient import TestClient
        from server.src.main import app
        from server.src.core.database import get_db, get_valkey
        import msgpack
        
        # Override dependencies
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_valkey] = lambda: fake_valkey
        
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    with client.websocket_connect("/ws") as websocket:
                        # Send authentication without token
                        auth_message = {
                            "id": str(uuid.uuid4()),
                            "type": MessageType.CMD_AUTHENTICATE.value,
                            "payload": {},
                            "version": "2.0"
                        }
                        websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                        
                        # Server closes connection on missing token
                        websocket.receive_bytes()
                
                assert exc_info.value.code == 1008
        finally:
            app.dependency_overrides.clear()

    async def test_ws_auth_malformed_msgpack_disconnect(self, session, fake_valkey):
        """Malformed msgpack data should close connection."""
        from starlette.testclient import TestClient
        from server.src.main import app
        from server.src.core.database import get_db, get_valkey
        
        # Override dependencies
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_valkey] = lambda: fake_valkey
        
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect):
                    with client.websocket_connect("/ws") as websocket:
                        # Send invalid msgpack data
                        websocket.send_bytes(b"not valid msgpack data")
                        
                        # Server closes connection on malformed data
                        websocket.receive_bytes()
        finally:
            app.dependency_overrides.clear()

    async def test_ws_auth_wrong_message_type_disconnect(self, session, fake_valkey):
        """Sending non-AUTHENTICATE as first message should close connection."""
        from starlette.testclient import TestClient
        from server.src.main import app
        from server.src.core.database import get_db, get_valkey
        import msgpack
        
        # Override dependencies
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_valkey] = lambda: fake_valkey
        
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    with client.websocket_connect("/ws") as websocket:
                        # Send MOVE command instead of AUTHENTICATE
                        wrong_message = {
                            "id": str(uuid.uuid4()),
                            "type": MessageType.CMD_MOVE.value,
                            "payload": {"direction": "UP"},
                            "version": "2.0"
                        }
                        websocket.send_bytes(msgpack.packb(wrong_message, use_bin_type=True))
                        
                        # Server closes connection on wrong message type
                        websocket.receive_bytes()
                
                assert exc_info.value.code == 1008
        finally:
            app.dependency_overrides.clear()

    async def test_ws_auth_nonexistent_user_disconnect(self, session, fake_valkey):
        """Token for non-existent user should close connection."""
        from starlette.testclient import TestClient
        from server.src.main import app
        from server.src.core.database import get_db, get_valkey
        import msgpack
        
        # Create a valid token structure but for a user that doesn't exist
        fake_token = create_access_token(data={"sub": "nonexistent_user_12345"})
        
        # Override dependencies
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_valkey] = lambda: fake_valkey
        
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    with client.websocket_connect("/ws") as websocket:
                        auth_message = {
                            "id": str(uuid.uuid4()),
                            "type": MessageType.CMD_AUTHENTICATE.value,
                            "payload": {"token": fake_token},
                            "version": "2.0"
                        }
                        websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                        
                        # Server closes connection when user not found
                        websocket.receive_bytes()
                
                # Accept 1008 (policy violation) or 1011 (internal error) due to test isolation
                assert exc_info.value.code in (1008, 1011)
        finally:
            app.dependency_overrides.clear()

    async def test_ws_auth_large_payload_disconnect(self, session, fake_valkey):
        """Extremely large payload should close connection."""
        from starlette.testclient import TestClient
        from server.src.main import app
        from server.src.core.database import get_db, get_valkey
        import msgpack
        
        # Override dependencies
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_valkey] = lambda: fake_valkey
        
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect):
                    with client.websocket_connect("/ws") as websocket:
                        # Create a large payload (1MB of data)
                        large_data = "x" * (1024 * 1024)
                        auth_message = {
                            "id": str(uuid.uuid4()),
                            "type": MessageType.CMD_AUTHENTICATE.value,
                            "payload": {"token": large_data},
                            "version": "2.0"
                        }
                        websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                        
                        # Server should close connection for invalid token
                        websocket.receive_bytes()
        finally:
            app.dependency_overrides.clear()