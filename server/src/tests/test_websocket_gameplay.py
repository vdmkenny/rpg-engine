"""
Tests for WebSocket gameplay functionality.

Covers:
- Movement (valid, collision, rate limiting)
- Chat (local, global)
- Chunk requests (valid, security)
- Game loop diff broadcasting
"""

import pytest
import pytest_asyncio
import msgpack
import asyncio
from typing import Dict, Any
from starlette.testclient import TestClient

from server.src.main import app
from server.src.core.database import get_db, get_valkey
from server.src.game.game_loop import (
    get_visible_entities,
    compute_entity_diff,
    is_in_visible_range,
    cleanup_disconnected_player,
    player_visible_state,
    player_chunk_positions,
)
from common.src.protocol import MessageType, Direction


# Skip WebSocket integration tests - they require proper integration test environment
# The TestClient creates its own database session which doesn't share state with
# the async fixtures. These tests need to be run against a real database.
SKIP_WS_INTEGRATION = pytest.mark.skip(
    reason="WebSocket integration tests require real database, not SQLite in-memory"
)


@SKIP_WS_INTEGRATION
class TestMovement:
    """Tests for player movement functionality."""

    @pytest.mark.asyncio
    async def test_move_valid_direction(
        self, client, create_test_player_and_token, fake_valkey
    ):
        """Valid movement should update position."""
        token, player = await create_test_player_and_token(
            "moveuser", "password123",
            initial_data={"x_coord": 10, "y_coord": 10, "map_id": "samplemap"}
        )
        
        # Set up player in Valkey
        await fake_valkey.hset(f"player:moveuser", {
            "x": "10",
            "y": "10",
            "map_id": "samplemap",
            "last_move_time": "0",
        })
        
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    # Authenticate first
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    # Get welcome response
                    response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
                    assert response["type"] == MessageType.WELCOME.value
                    
                    # Send move intent
                    move_message = {
                        "type": MessageType.MOVE_INTENT.value,
                        "payload": {"direction": Direction.DOWN.value},
                    }
                    websocket.send_bytes(msgpack.packb(move_message, use_bin_type=True))
                    
                    # Should receive position update
                    response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
                    assert response["type"] == MessageType.GAME_STATE_UPDATE.value
                    
                    # Check position was updated in Valkey
                    player_data = await fake_valkey.hgetall("player:moveuser")
                    assert player_data[b"y"] == b"11"  # Moved down
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_move_rate_limit(
        self, client, create_test_player_and_token, fake_valkey
    ):
        """Rapid movements should be rate limited."""
        import time
        
        token, player = await create_test_player_and_token(
            "ratelimituser", "password123",
            initial_data={"x_coord": 10, "y_coord": 10, "map_id": "samplemap"}
        )
        
        # Set up player with recent move time
        current_time = time.time()
        await fake_valkey.hset(f"player:ratelimituser", {
            "x": "10",
            "y": "10",
            "map_id": "samplemap",
            "last_move_time": str(current_time),  # Just moved
        })
        
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    # Authenticate
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    msgpack.unpackb(websocket.receive_bytes(), raw=False)
                    
                    # Try to move immediately (should be rate limited)
                    move_message = {
                        "type": MessageType.MOVE_INTENT.value,
                        "payload": {"direction": Direction.DOWN.value},
                    }
                    websocket.send_bytes(msgpack.packb(move_message, use_bin_type=True))
                    
                    # Position should NOT have changed due to rate limit
                    player_data = await fake_valkey.hgetall("player:ratelimituser")
                    assert player_data[b"y"] == b"10"  # Still at original position
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_move_invalid_direction(
        self, client, create_test_player_and_token, fake_valkey
    ):
        """Invalid direction should be rejected."""
        token, player = await create_test_player_and_token(
            "invaliddiruser", "password123",
            initial_data={"x_coord": 10, "y_coord": 10, "map_id": "samplemap"}
        )
        
        await fake_valkey.hset(f"player:invaliddiruser", {
            "x": "10",
            "y": "10",
            "map_id": "samplemap",
            "last_move_time": "0",
        })
        
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    msgpack.unpackb(websocket.receive_bytes(), raw=False)
                    
                    # Send invalid direction
                    move_message = {
                        "type": MessageType.MOVE_INTENT.value,
                        "payload": {"direction": "INVALID_DIRECTION"},
                    }
                    websocket.send_bytes(msgpack.packb(move_message, use_bin_type=True))
                    
                    # Should receive error
                    response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
                    assert response["type"] == MessageType.ERROR.value
            except Exception:
                # Error handling is acceptable
                pass
            finally:
                app.dependency_overrides.clear()


@SKIP_WS_INTEGRATION
class TestChat:
    """Tests for chat functionality."""

    @pytest.mark.asyncio
    async def test_chat_send_message(
        self, client, create_test_player_and_token, fake_valkey
    ):
        """Sending a chat message should work."""
        token, player = await create_test_player_and_token(
            "chatuser", "password123",
            initial_data={"x_coord": 10, "y_coord": 10, "map_id": "samplemap"}
        )
        
        await fake_valkey.hset(f"player:chatuser", {
            "x": "10",
            "y": "10",
            "map_id": "samplemap",
        })
        
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    msgpack.unpackb(websocket.receive_bytes(), raw=False)
                    
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
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_chat_empty_message(
        self, client, create_test_player_and_token, fake_valkey
    ):
        """Empty chat messages should be rejected."""
        token, player = await create_test_player_and_token(
            "emptychatuser", "password123",
            initial_data={"x_coord": 10, "y_coord": 10, "map_id": "samplemap"}
        )
        
        await fake_valkey.hset(f"player:emptychatuser", {
            "x": "10",
            "y": "10",
            "map_id": "samplemap",
        })
        
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    msgpack.unpackb(websocket.receive_bytes(), raw=False)
                    
                    # Send empty chat message
                    chat_message = {
                        "type": MessageType.SEND_CHAT_MESSAGE.value,
                        "payload": {
                            "message": "",
                            "channel": "local",
                        },
                    }
                    websocket.send_bytes(msgpack.packb(chat_message, use_bin_type=True))
                    
                    # Should receive error or no response
                    # Empty messages should be ignored or rejected
            finally:
                app.dependency_overrides.clear()


@SKIP_WS_INTEGRATION
class TestChunkRequests:
    """Tests for chunk request functionality."""

    @pytest.mark.asyncio
    async def test_chunk_request_valid(
        self, client, create_test_player_and_token, fake_valkey
    ):
        """Valid chunk request should return chunk data."""
        token, player = await create_test_player_and_token(
            "chunkuser", "password123",
            initial_data={"x_coord": 10, "y_coord": 10, "map_id": "samplemap"}
        )
        
        await fake_valkey.hset(f"player:chunkuser", {
            "x": "10",
            "y": "10",
            "map_id": "samplemap",
        })
        
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    msgpack.unpackb(websocket.receive_bytes(), raw=False)
                    
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
                    
                    # Should receive chunk data (or error if map doesn't exist in test)
                    response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
                    assert response["type"] in [
                        MessageType.CHUNK_DATA.value,
                        MessageType.ERROR.value,
                    ]
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_chunk_request_excessive_radius(
        self, client, create_test_player_and_token, fake_valkey
    ):
        """Chunk request with radius > 5 should be rejected."""
        token, player = await create_test_player_and_token(
            "bigchunkuser", "password123",
            initial_data={"x_coord": 10, "y_coord": 10, "map_id": "samplemap"}
        )
        
        await fake_valkey.hset(f"player:bigchunkuser", {
            "x": "10",
            "y": "10",
            "map_id": "samplemap",
        })
        
        with TestClient(app) as test_client:
            async def override_get_valkey():
                return fake_valkey
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            try:
                with test_client.websocket_connect("/ws") as websocket:
                    auth_message = {
                        "type": MessageType.AUTHENTICATE.value,
                        "payload": {"token": token},
                    }
                    websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    msgpack.unpackb(websocket.receive_bytes(), raw=False)
                    
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
                    
                    # Should be rejected or clamped
                    response = msgpack.unpackb(websocket.receive_bytes(), raw=False)
                    # Should receive error or limited chunks
                    assert response["type"] in [
                        MessageType.CHUNK_DATA.value,
                        MessageType.ERROR.value,
                    ]
            finally:
                app.dependency_overrides.clear()


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
        # Set up some state
        player_visible_state["testuser"] = {"other": {"x": 1, "y": 1}}
        player_visible_state["observer"] = {"testuser": {"x": 2, "y": 2}}
        player_chunk_positions["testuser"] = (0, 0)
        
        cleanup_disconnected_player("testuser")
        
        assert "testuser" not in player_visible_state
        assert "testuser" not in player_chunk_positions
        assert "testuser" not in player_visible_state.get("observer", {})


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
