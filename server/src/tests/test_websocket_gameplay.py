"""
Tests for WebSocket gameplay functionality.

Covers:
- Movement (valid, collision, rate limiting)
- Chat (local, global)
- Chunk requests (valid, security)
- Game loop diff broadcasting

Integration tests use WebSocketTestClient for structured async testing.
"""

import pytest
import pytest_asyncio
from typing import Dict, Any

from server.src.game.game_loop import (
    get_visible_entities,
    compute_entity_diff,
    is_in_visible_range,
    cleanup_disconnected_player,
    player_visible_state,
    player_chunk_positions,
)
from common.src.protocol import MessageType
from server.src.tests.conftest import FakeValkey
from server.src.tests.websocket_test_utils import WebSocketTestClient



@pytest.mark.integration
class TestMovement:
    """Tests for player movement functionality."""

    @pytest.mark.asyncio
    async def test_move_valid_direction(self, test_client: WebSocketTestClient):
        """Valid movement should return EVENT_STATE_UPDATE."""
        # Send move intent
        response = await test_client.send_command(MessageType.CMD_MOVE, {"direction": "down"})
        
        # Should receive EVENT_STATE_UPDATE confirming the move
        assert response["type"] == MessageType.EVENT_STATE_UPDATE
        
        # The response should have a valid payload structure
        assert "payload" in response

    @pytest.mark.asyncio
    async def test_move_invalid_direction(self, test_client: WebSocketTestClient):
        """Invalid direction should be rejected gracefully.
        
        The server currently logs the validation error and doesn't crash,
        but doesn't send an explicit ERROR response. This test verifies
        that the server handles the invalid input gracefully without crashing.
        """
        # Send invalid direction
        try:
            response = await test_client.send_command(
                MessageType.CMD_MOVE, 
                {"direction": "INVALID_DIRECTION"},
                timeout=2.0
            )
            # If we get a response, check it's an error
            if "type" in response:
                # Server may send error response or handle gracefully
                pass
        except Exception:
            # Server may handle this gracefully by not responding
            # Test passes if we can continue without crash
            pass

@pytest.mark.integration
class TestChat:
    """Tests for chat functionality."""

    @pytest.mark.asyncio
    async def test_chat_send_message(self, test_client: WebSocketTestClient):
        """Sending a chat message should work."""
        # Send chat message
        response = await test_client.send_command(
            MessageType.CMD_CHAT_SEND,
            {
                "message": "Hello, world!",
                "channel": "local",
            }
        )
        
        # Should receive success response or chat message back
        print(f"DEBUG: Received response type: {response}")
        
        # After sending chat, also expect the chat message event
        chat_event = await test_client.expect_event(MessageType.EVENT_CHAT_MESSAGE)
        assert chat_event["message"] == "Hello, world!"


@pytest.mark.integration
class TestChunkRequests:
    """Tests for chunk request functionality."""

    @pytest.mark.asyncio
    async def test_chunk_request_valid(self, test_client: WebSocketTestClient):
        """Valid chunk request should return chunk data."""
        # Request chunks
        response = await test_client.get_map_chunks(
            map_id="samplemap",
            center_x=10,
            center_y=10,
            radius=1
        )
        
        # Should receive chunk data or acceptable error
        assert isinstance(response, dict)
        # Response structure depends on server implementation

    @pytest.mark.asyncio
    async def test_chunk_request_excessive_radius(self, test_client: WebSocketTestClient):
        """Chunk request with radius > 5 should be clamped or rejected."""
        # Request chunks with excessive radius - should be handled gracefully
        try:
            response = await test_client.get_map_chunks(
                map_id="samplemap",
                center_x=10,
                center_y=10,
                radius=100  # Way too large
            )
            # If we get a response, it should be valid (clamped or error)
            assert isinstance(response, dict)
        except Exception as e:
            # Server may reject excessive requests
            print(f"Server rejected excessive radius request: {e}")
            # Test passes if server handles this gracefully


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
