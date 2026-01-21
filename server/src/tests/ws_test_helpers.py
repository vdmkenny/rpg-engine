"""
Shared test utilities for WebSocket integration tests.

Provides common functions for:
- User registration and authentication
- WebSocket message handling
- Player/item setup helpers
"""

import os
import uuid
import pytest
import msgpack
from typing import Dict, Any, List, Optional
from starlette.testclient import TestClient

from server.src.main import app
from server.src.core.database import get_valkey, get_db, reset_engine, reset_valkey
from server.src.api.websockets import manager
from server.src.game.game_loop import player_visible_state, player_chunk_positions
from common.src.protocol import MessageType
from server.src.tests.conftest import FakeValkey


# Skip WebSocket integration tests unless RUN_INTEGRATION_TESTS is set
SKIP_WS_INTEGRATION = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "").lower() not in ("1", "true", "yes"),
    reason="WebSocket integration tests require RUN_INTEGRATION_TESTS=1"
)


# Global FakeValkey instance for tests
_test_valkey: FakeValkey | None = None


def get_test_valkey() -> FakeValkey:
    """Get or create the test valkey instance."""
    global _test_valkey
    if _test_valkey is None:
        _test_valkey = FakeValkey()
    return _test_valkey


def unique_username(prefix: str = "user") -> str:
    """Generate a unique username for testing."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def register_and_login(client, username: str, password: str = "password123") -> str:
    """Register a user via API and return their JWT token.
    
    Uses the real PostgreSQL database configured via DATABASE_URL.
    """
    # Register the user
    response = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 201, f"Registration failed: {response.text}"
    
    # Login to get the token
    login_response = client.post(
        "/auth/login",
        data={"username": username, "password": password},
    )
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    return login_response.json()["access_token"]


def authenticate_websocket(websocket, token: str) -> Dict[str, Any]:
    """Send authentication message and return WELCOME response.
    
    Also consumes the welcome chat message sent after authentication.
    Returns the WELCOME response payload containing player info.
    """
    auth_message = {
        "type": MessageType.CMD_AUTHENTICATE.value,
        "payload": {"token": token},
    }
    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
    response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
    
    # After EVENT_WELCOME, server sends a EVENT_CHAT_MESSAGE welcome - consume it
    if response["type"] == MessageType.EVENT_WELCOME.value:
        # Consume the welcome chat message
        chat_response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
        # Should be the welcome chat message
        assert chat_response["type"] == MessageType.EVENT_CHAT_MESSAGE.value
    
    return response


def send_ws_message(websocket, message_type: MessageType, payload: dict, correlation_id: Optional[str] = None):
    """Send a WebSocket message with the given type and payload."""
    import uuid
    import time
    
    # Generate correlation ID for command/query messages if not provided
    if correlation_id is None and (message_type.value.startswith("cmd_") or message_type.value.startswith("query_")):
        correlation_id = str(uuid.uuid4())
    
    message = {
        "id": correlation_id,
        "type": message_type.value,
        "payload": payload,
        "timestamp": int(time.time() * 1000),
        "version": "2.0"
    }
    websocket.send_bytes(msgpack.packb(message, use_bin_type=True))


def receive_message(websocket) -> Dict[str, Any]:
    """Receive and decode a single WebSocket message."""
    return msgpack.unpackb(websocket.receive_bytes(), raw=False)


def receive_message_of_type(
    websocket, expected_types: list[str], max_attempts: int = 10
) -> Dict[str, Any]:
    """Receive messages until we get one of the expected types.
    
    The game loop may send EVENT_STATE_UPDATE messages at any time, so we need
    to consume them while waiting for specific responses.
    """
    for _ in range(max_attempts):
        response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
        if response["type"] in expected_types:
            return response
        # Skip EVENT_STATE_UPDATE messages from game loop
        if response["type"] == MessageType.EVENT_STATE_UPDATE.value:
            continue
        # Unexpected message type - return it for test to handle
        return response
    raise TimeoutError(
        f"Did not receive expected message types {expected_types} after {max_attempts} attempts"
    )


def receive_until_type(
    websocket, 
    target_type: str, 
    max_attempts: int = 20,
    collect_types: Optional[List[str]] = None
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Receive messages until we get the target type.
    
    Returns:
        (target_message, collected_messages) - The target message and any collected messages
    
    Args:
        websocket: The WebSocket connection
        target_type: The MessageType value to wait for
        max_attempts: Maximum number of messages to receive
        collect_types: Optional list of types to collect while waiting
    """
    collected = []
    for _ in range(max_attempts):
        response = receive_message(websocket)
        if response["type"] == target_type:
            return response, collected
        if collect_types and response["type"] in collect_types:
            collected.append(response)
    raise TimeoutError(f"Did not receive {target_type} after {max_attempts} attempts")


@pytest.fixture(scope="function")
def integration_client():
    """
    Create a TestClient for each test function.
    
    Using function scope ensures each test gets its own event loop context,
    avoiding asyncpg connection pool issues when connections from one
    test try to be reused in another test's context.
    """
    # Reset engine to ensure fresh connections for this test
    reset_engine()
    reset_valkey()
    
    # Clear any state from previous test runs
    manager.clear()
    player_visible_state.clear()
    player_chunk_positions.clear()
    
    # Set up FakeValkey override
    test_valkey = get_test_valkey()
    test_valkey.clear()
    
    async def override_get_valkey():
        return test_valkey
    
    app.dependency_overrides[get_valkey] = override_get_valkey
    
    with TestClient(app) as client:
        yield client
    
    # Cleanup after test completes
    manager.clear()
    player_visible_state.clear()
    player_chunk_positions.clear()
    app.dependency_overrides.clear()


def get_player_id_from_welcome(welcome_response: Dict[str, Any]) -> int:
    """Extract player ID from WELCOME response."""
    return welcome_response["payload"]["player"]["id"]
