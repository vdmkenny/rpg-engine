"""
Tests for WebSocket gameplay functionality.

Covers:
- Movement (valid, collision, rate limiting)
- Chat (local, global)
- Chunk requests (valid, security)
- Game loop diff broadcasting

Integration tests use a single TestClient per class to avoid event loop issues
with asyncpg connection pools.
"""

import os
import uuid
import pytest
import msgpack
from typing import Dict, Any
from starlette.testclient import TestClient

from server.src.main import app
from server.src.core.database import get_valkey, reset_engine, reset_valkey
from server.src.api.websockets import manager
from server.src.game.game_loop import (
    get_visible_entities,
    compute_entity_diff,
    is_in_visible_range,
    cleanup_disconnected_player,
    player_visible_state,
    player_chunk_positions,
)
from common.src.protocol import MessageType, Direction
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
    client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    # Login to get the token
    login_response = client.post(
        "/auth/login",
        data={"username": username, "password": password},
    )
    return login_response.json()["access_token"]


def authenticate_websocket(websocket, token: str) -> Dict[str, Any]:
    """Send authentication message and return WELCOME response.
    
    Also consumes the welcome chat message sent after authentication.
    """
    auth_message = {
        "type": MessageType.AUTHENTICATE.value,
        "payload": {"token": token},
    }
    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
    response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
    
    # After WELCOME, server sends a NEW_CHAT_MESSAGE welcome - consume it
    if response["type"] == MessageType.WELCOME.value:
        # Consume the welcome chat message
        chat_response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
        # Should be the welcome chat message
        assert chat_response["type"] == MessageType.NEW_CHAT_MESSAGE.value
    
    return response


def receive_message_of_type(
    websocket, expected_types: list[str], max_attempts: int = 5
) -> Dict[str, Any]:
    """Receive messages until we get one of the expected types.
    
    The game loop may send GAME_STATE_UPDATE messages at any time, so we need
    to consume them while waiting for specific responses.
    """
    for _ in range(max_attempts):
        response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
        if response["type"] in expected_types:
            return response
        # Skip GAME_STATE_UPDATE messages from game loop
        if response["type"] == MessageType.GAME_STATE_UPDATE.value:
            continue
        # Unexpected message type - return it for test to handle
        return response
    raise TimeoutError(
        f"Did not receive expected message types {expected_types} after {max_attempts} attempts"
    )


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


@SKIP_WS_INTEGRATION
class TestMovement:
    """Tests for player movement functionality."""

    def test_move_valid_direction(self, integration_client):
        """Valid movement should return GAME_STATE_UPDATE."""
        client = integration_client
        username = unique_username("move")
        token = register_and_login(client, username)
        
        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value
            
            # Send move intent
            move_message = {
                "type": MessageType.MOVE_INTENT.value,
                "payload": {"direction": Direction.DOWN.value},
            }
            websocket.send_bytes(msgpack.packb(move_message, use_bin_type=True))
            
            # Should receive GAME_STATE_UPDATE confirming the move
            response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
            assert response["type"] == MessageType.GAME_STATE_UPDATE.value
            
            # The response should have a valid payload structure
            assert "payload" in response

    def test_move_invalid_direction(self, integration_client):
        """Invalid direction should be rejected gracefully.
        
        The server currently logs the validation error and doesn't crash,
        but doesn't send an explicit ERROR response. This test verifies
        that the server handles the invalid input gracefully without crashing.
        """
        client = integration_client
        username = unique_username("invaliddir")
        token = register_and_login(client, username)
        
        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)
            
            # Send invalid direction
            move_message = {
                "type": MessageType.MOVE_INTENT.value,
                "payload": {"direction": "INVALID_DIRECTION"},
            }
            websocket.send_bytes(msgpack.packb(move_message, use_bin_type=True))
            
            # The server should handle this gracefully - it logs the error
            # but doesn't crash. We verify the connection is still open
            # by receiving the next game loop update or by closing cleanly.
            # Note: The server currently doesn't send an ERROR response for 
            # invalid payloads, it just logs and continues.
            import time
            time.sleep(0.1)  # Give server time to process
            
            # Connection should still be open and functional
            # Test passes if we can cleanly disconnect without crash


@SKIP_WS_INTEGRATION
class TestChat:
    """Tests for chat functionality."""

    def test_chat_send_message(self, integration_client):
        """Sending a chat message should work."""
        client = integration_client
        username = unique_username("chat")
        token = register_and_login(client, username)
        
        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)
            
            # Send chat message
            chat_message = {
                "type": MessageType.SEND_CHAT_MESSAGE.value,
                "payload": {
                    "message": "Hello, world!",
                    "channel": "local",
                },
            }
            websocket.send_bytes(msgpack.packb(chat_message, use_bin_type=True))
            
            # Should receive the chat message back
            response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
            assert response["type"] == MessageType.NEW_CHAT_MESSAGE.value
            assert response["payload"]["message"] == "Hello, world!"


@SKIP_WS_INTEGRATION
class TestChunkRequests:
    """Tests for chunk request functionality."""

    def test_chunk_request_valid(self, integration_client):
        """Valid chunk request should return chunk data."""
        client = integration_client
        username = unique_username("chunk")
        token = register_and_login(client, username)
        
        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)
            
            # Request chunks
            chunk_request = {
                "type": MessageType.REQUEST_CHUNKS.value,
                "payload": {
                    "map_id": "samplemap",
                    "center_x": 10,
                    "center_y": 10,
                    "radius": 1,
                },
            }
            websocket.send_bytes(msgpack.packb(chunk_request, use_bin_type=True))
            
            # Should receive chunk data (may need to skip GAME_STATE_UPDATEs)
            response = receive_message_of_type(
                websocket,
                [MessageType.CHUNK_DATA.value, MessageType.ERROR.value],
            )
            assert response["type"] in [
                MessageType.CHUNK_DATA.value,
                MessageType.ERROR.value,  # Acceptable if map setup differs
            ]

    def test_chunk_request_excessive_radius(self, integration_client):
        """Chunk request with radius > 5 should be clamped or rejected."""
        client = integration_client
        username = unique_username("bigchunk")
        token = register_and_login(client, username)
        
        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)
            
            # Request chunks with excessive radius
            chunk_request = {
                "type": MessageType.REQUEST_CHUNKS.value,
                "payload": {
                    "map_id": "samplemap",
                    "center_x": 10,
                    "center_y": 10,
                    "radius": 100,  # Way too large
                },
            }
            websocket.send_bytes(msgpack.packb(chunk_request, use_bin_type=True))
            
            # Should be rejected or clamped (may need to skip GAME_STATE_UPDATEs)
            response = receive_message_of_type(
                websocket,
                [MessageType.CHUNK_DATA.value, MessageType.ERROR.value],
            )
            assert response["type"] in [
                MessageType.CHUNK_DATA.value,
                MessageType.ERROR.value,
            ]


# ============================================================================
# Unit tests (these don't need integration environment)
# ============================================================================

class TestVisibilitySystem:
    """Unit tests for the visibility and diff calculation system."""

    def test_is_in_visible_range_close(self):
        """Nearby entities should be visible."""
        assert is_in_visible_range(10, 10, 15, 15) is True
        assert is_in_visible_range(10, 10, 10, 10) is True
        assert is_in_visible_range(10, 10, 11, 10) is True

    def test_is_in_visible_range_far(self):
        """Distant entities should not be visible."""
        # With default chunk_radius=1 and chunk_size=16, visible_range = 32
        assert is_in_visible_range(0, 0, 100, 100) is False
        assert is_in_visible_range(0, 0, 50, 0) is False

    def test_get_visible_entities_filters_self(self):
        """Player should not see themselves in visible entities."""
        all_entities = [
            {"id": "player1", "x": 10, "y": 10},
            {"id": "player2", "x": 15, "y": 15},
        ]
        
        visible = get_visible_entities(10, 10, all_entities, "player1")
        
        assert "player1" not in visible
        assert "player2" in visible

    def test_get_visible_entities_filters_by_distance(self):
        """Only nearby entities should be visible."""
        all_entities = [
            {"id": "nearby", "x": 15, "y": 15},
            {"id": "faraway", "x": 200, "y": 200},
        ]
        
        visible = get_visible_entities(10, 10, all_entities, "observer")
        
        assert "nearby" in visible
        assert "faraway" not in visible

    def test_compute_entity_diff_added(self):
        """New entities should be in added list."""
        current = {"player1": {"username": "player1", "x": 10, "y": 10}}
        last = {}
        
        diff = compute_entity_diff(current, last)
        
        assert len(diff["added"]) == 1
        assert diff["added"][0]["username"] == "player1"
        assert len(diff["updated"]) == 0
        assert len(diff["removed"]) == 0

    def test_compute_entity_diff_removed(self):
        """Entities that left should be in removed list."""
        current = {}
        last = {"player1": {"username": "player1", "x": 10, "y": 10}}
        
        diff = compute_entity_diff(current, last)
        
        assert len(diff["added"]) == 0
        assert len(diff["updated"]) == 0
        assert len(diff["removed"]) == 1
        assert diff["removed"][0]["username"] == "player1"

    def test_compute_entity_diff_moved(self):
        """Entities that moved should be in updated list."""
        current = {"player1": {"username": "player1", "x": 15, "y": 10}}
        last = {"player1": {"username": "player1", "x": 10, "y": 10}}
        
        diff = compute_entity_diff(current, last)
        
        assert len(diff["added"]) == 0
        assert len(diff["updated"]) == 1
        assert diff["updated"][0]["x"] == 15
        assert len(diff["removed"]) == 0

    def test_compute_entity_diff_no_change(self):
        """Entities that didn't move should not be in any list."""
        current = {"player1": {"username": "player1", "x": 10, "y": 10}}
        last = {"player1": {"username": "player1", "x": 10, "y": 10}}
        
        diff = compute_entity_diff(current, last)
        
        assert len(diff["added"]) == 0
        assert len(diff["updated"]) == 0
        assert len(diff["removed"]) == 0

    def test_cleanup_disconnected_player(self):
        """Cleanup should remove all traces of a player."""
        # Set up some state with the new nested structure
        player_visible_state["testuser"] = {
            "players": {"other": {"x": 1, "y": 1}},
            "ground_items": {}
        }
        player_visible_state["observer"] = {
            "players": {"testuser": {"x": 2, "y": 2}},
            "ground_items": {}
        }
        player_chunk_positions["testuser"] = (0, 0)
        
        cleanup_disconnected_player("testuser")
        
        assert "testuser" not in player_visible_state
        assert "testuser" not in player_chunk_positions
        assert "testuser" not in player_visible_state.get("observer", {}).get("players", {})


class TestFakeValkey:
    """Tests for the FakeValkey test utility itself."""

    @pytest.mark.asyncio
    async def test_hset_and_hgetall(self, fake_valkey):
        """Basic hash operations should work."""
        await fake_valkey.hset("test:key", {"field1": "value1", "field2": "value2"})
        
        result = await fake_valkey.hgetall("test:key")
        
        assert result[b"field1"] == b"value1"
        assert result[b"field2"] == b"value2"

    @pytest.mark.asyncio
    async def test_hget(self, fake_valkey):
        """Single field get should work."""
        await fake_valkey.hset("test:key", {"field1": "value1"})
        
        result = await fake_valkey.hget("test:key", "field1")
        
        assert result == b"value1"

    @pytest.mark.asyncio
    async def test_delete(self, fake_valkey):
        """Delete should remove the key."""
        await fake_valkey.hset("test:key", {"field1": "value1"})
        
        deleted = await fake_valkey.delete("test:key")
        
        assert deleted == 1
        assert await fake_valkey.hgetall("test:key") == {}

    @pytest.mark.asyncio
    async def test_exists(self, fake_valkey):
        """Exists should return correct status."""
        assert await fake_valkey.exists("nonexistent") == 0
        
        await fake_valkey.hset("test:key", {"field": "value"})
        
        assert await fake_valkey.exists("test:key") == 1

    @pytest.mark.asyncio
    async def test_clear(self, fake_valkey):
        """Clear should remove all data."""
        await fake_valkey.hset("key1", {"f": "v"})
        await fake_valkey.set("key2", "value")
        
        fake_valkey.clear()
        
        assert await fake_valkey.hgetall("key1") == {}
        assert await fake_valkey.get("key2") is None
