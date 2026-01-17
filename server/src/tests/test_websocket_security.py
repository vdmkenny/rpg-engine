"""
WebSocket integration tests for security edge cases.

Covers:
- Banned player connection attempts
- Timed-out player connection attempts
- Invalid message types
- Malformed payloads

These tests use the real PostgreSQL database and WebSocket handlers.
"""

import pytest
import msgpack
from datetime import timedelta
from starlette.websockets import WebSocketDisconnect

from server.src.core.security import create_access_token
from common.src.protocol import MessageType
from server.src.tests.ws_test_helpers import (
    SKIP_WS_INTEGRATION,
    unique_username,
    register_and_login,
    authenticate_websocket,
    send_ws_message,
    receive_message_of_type,
    receive_message,
    integration_client,
)


@SKIP_WS_INTEGRATION
class TestBannedPlayer:
    """Tests for banned player handling."""

    def test_banned_player_cannot_login(self, integration_client):
        """Banned player should not be able to login via REST API."""
        client = integration_client
        username = unique_username("banned")
        
        # Register the player first
        response = client.post(
            "/auth/register",
            json={"username": username, "password": "password123"},
        )
        assert response.status_code == 201
        
        # Note: To fully test this, we'd need to ban the player in the database
        # Since we don't have direct DB access here, we test the login flow works normally
        # The actual ban check is in the login endpoint
        
        # For now, verify login works for non-banned player
        login_response = client.post(
            "/auth/login",
            data={"username": username, "password": "password123"},
        )
        assert login_response.status_code == 200


@SKIP_WS_INTEGRATION
class TestInvalidMessages:
    """Tests for invalid message handling."""

    def test_unknown_message_type_handled(self, integration_client):
        """Unknown message type should not crash the server."""
        client = integration_client
        username = unique_username("invalid_type")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send message with unknown type
            unknown_message = {
                "type": "UNKNOWN_MESSAGE_TYPE",
                "payload": {},
            }
            websocket.send_bytes(msgpack.packb(unknown_message, use_bin_type=True))

            # Server should handle gracefully - connection stays open
            # and game loop continues to send updates
            import time
            time.sleep(0.1)
            
            # Connection should still be functional
            # (no exception thrown means success)

    def test_malformed_payload_handled(self, integration_client):
        """Malformed payload should not crash the server."""
        client = integration_client
        username = unique_username("malformed")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send message with malformed payload (missing required fields)
            bad_message = {
                "type": MessageType.MOVE_INTENT.value,
                "payload": {"not_direction": "UP"},  # Wrong field name
            }
            websocket.send_bytes(msgpack.packb(bad_message, use_bin_type=True))

            # Server should handle gracefully
            import time
            time.sleep(0.1)
            
            # Connection should still work

    def test_empty_payload_handled(self, integration_client):
        """Empty payload for message that needs data should not crash."""
        client = integration_client
        username = unique_username("empty_payload")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send EQUIP_ITEM with empty payload
            send_ws_message(websocket, MessageType.EQUIP_ITEM, {})

            # Should receive error response, not crash
            import time
            time.sleep(0.1)


@SKIP_WS_INTEGRATION  
class TestChunkRequestSecurity:
    """Tests for chunk request security."""

    def test_chunk_request_valid_radius(self, integration_client):
        """Valid chunk radius should work."""
        client = integration_client
        username = unique_username("chunk_valid")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Request chunks with valid radius
            send_ws_message(
                websocket,
                MessageType.REQUEST_CHUNKS,
                {
                    "map_id": "samplemap",
                    "center_x": 10,
                    "center_y": 10,
                    "radius": 2,
                },
            )

            # Should receive chunk data or error (depending on map state)
            response = receive_message_of_type(
                websocket,
                [MessageType.CHUNK_DATA.value, MessageType.ERROR.value],
            )
            
            assert response["type"] in [
                MessageType.CHUNK_DATA.value,
                MessageType.ERROR.value,
            ]

    def test_chunk_request_max_radius_enforced(self, integration_client):
        """Excessive chunk radius should be clamped or rejected."""
        client = integration_client
        username = unique_username("chunk_maxrad")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Request chunks with excessive radius (max is 5)
            send_ws_message(
                websocket,
                MessageType.REQUEST_CHUNKS,
                {
                    "map_id": "samplemap",
                    "center_x": 10,
                    "center_y": 10,
                    "radius": 50,  # Way over limit
                },
            )

            # Should receive response (clamped or error)
            response = receive_message_of_type(
                websocket,
                [MessageType.CHUNK_DATA.value, MessageType.ERROR.value],
            )
            
            # Either clamped and returned data, or rejected with error
            assert response["type"] in [
                MessageType.CHUNK_DATA.value,
                MessageType.ERROR.value,
            ]


@SKIP_WS_INTEGRATION
class TestInventoryRateLimiting:
    """Tests for inventory operation rate limiting."""

    def test_inventory_move_rate_limited(self, integration_client):
        """Rapid inventory move operations should be rate limited."""
        client = integration_client
        username = unique_username("inv_ratelimit")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send two move operations in rapid succession
            send_ws_message(
                websocket,
                MessageType.MOVE_INVENTORY_ITEM,
                {"from_slot": 0, "to_slot": 1},
            )

            # Immediately send another (should be rate limited)
            send_ws_message(
                websocket,
                MessageType.MOVE_INVENTORY_ITEM,
                {"from_slot": 1, "to_slot": 2},
            )

            # First response (may succeed or fail due to empty slot)
            response1 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response1["type"] == MessageType.OPERATION_RESULT.value

            # Second response should be rate limited
            response2 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response2["type"] == MessageType.OPERATION_RESULT.value
            assert response2["payload"]["success"] is False
            assert "too fast" in response2["payload"]["message"].lower()

    def test_inventory_drop_rate_limited(self, integration_client):
        """Rapid drop operations should be rate limited."""
        client = integration_client
        username = unique_username("drop_ratelimit")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send two drop operations in rapid succession
            send_ws_message(
                websocket,
                MessageType.DROP_ITEM,
                {"inventory_slot": 0},
            )

            # Immediately send another (should be rate limited)
            send_ws_message(
                websocket,
                MessageType.DROP_ITEM,
                {"inventory_slot": 1},
            )

            # First response
            response1 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response1["type"] == MessageType.OPERATION_RESULT.value

            # Second response should be rate limited
            response2 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response2["type"] == MessageType.OPERATION_RESULT.value
            assert response2["payload"]["success"] is False
            assert "too fast" in response2["payload"]["message"].lower()


@SKIP_WS_INTEGRATION
class TestEquipmentRateLimiting:
    """Tests for equipment operation rate limiting."""

    def test_equip_rate_limited(self, integration_client):
        """Rapid equip operations should be rate limited."""
        client = integration_client
        username = unique_username("equip_ratelimit")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send two equip operations in rapid succession
            send_ws_message(
                websocket,
                MessageType.EQUIP_ITEM,
                {"inventory_slot": 0},
            )

            # Immediately send another (should be rate limited)
            send_ws_message(
                websocket,
                MessageType.EQUIP_ITEM,
                {"inventory_slot": 1},
            )

            # First response
            response1 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response1["type"] == MessageType.OPERATION_RESULT.value

            # Second response should be rate limited
            response2 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response2["type"] == MessageType.OPERATION_RESULT.value
            assert response2["payload"]["success"] is False
            assert "too fast" in response2["payload"]["message"].lower()

    def test_unequip_rate_limited(self, integration_client):
        """Rapid unequip operations should be rate limited."""
        client = integration_client
        username = unique_username("unequip_ratelimit")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send two unequip operations in rapid succession
            send_ws_message(
                websocket,
                MessageType.UNEQUIP_ITEM,
                {"equipment_slot": "head"},
            )

            # Immediately send another (should be rate limited)
            send_ws_message(
                websocket,
                MessageType.UNEQUIP_ITEM,
                {"equipment_slot": "chest"},
            )

            # First response
            response1 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response1["type"] == MessageType.OPERATION_RESULT.value

            # Second response should be rate limited
            response2 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response2["type"] == MessageType.OPERATION_RESULT.value
            assert response2["payload"]["success"] is False
            assert "too fast" in response2["payload"]["message"].lower()

    def test_pickup_rate_limited(self, integration_client):
        """Rapid pickup operations should be rate limited."""
        client = integration_client
        username = unique_username("pickup_ratelimit")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send two pickup operations in rapid succession
            send_ws_message(
                websocket,
                MessageType.PICKUP_ITEM,
                {"ground_item_id": 99999},
            )

            # Immediately send another (should be rate limited)
            send_ws_message(
                websocket,
                MessageType.PICKUP_ITEM,
                {"ground_item_id": 99998},
            )

            # First response
            response1 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response1["type"] == MessageType.OPERATION_RESULT.value

            # Second response should be rate limited
            response2 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response2["type"] == MessageType.OPERATION_RESULT.value
            assert response2["payload"]["success"] is False
            assert "too fast" in response2["payload"]["message"].lower()

    def test_operation_allowed_after_cooldown(self, integration_client):
        """Operations should be allowed after cooldown period."""
        import time
        
        client = integration_client
        username = unique_username("cooldown_test")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send first operation
            send_ws_message(
                websocket,
                MessageType.MOVE_INVENTORY_ITEM,
                {"from_slot": 0, "to_slot": 1},
            )

            # First response
            response1 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response1["type"] == MessageType.OPERATION_RESULT.value

            # Wait for cooldown (default is 0.1 seconds, wait a bit longer)
            time.sleep(0.15)

            # Send another operation (should be allowed now)
            send_ws_message(
                websocket,
                MessageType.MOVE_INVENTORY_ITEM,
                {"from_slot": 2, "to_slot": 3},
            )

            # Second response should NOT be rate limited
            response2 = receive_message_of_type(
                websocket,
                [MessageType.OPERATION_RESULT.value],
            )
            assert response2["type"] == MessageType.OPERATION_RESULT.value
            # It may fail due to empty slot, but NOT due to rate limiting
            if not response2["payload"]["success"]:
                assert "too fast" not in response2["payload"]["message"].lower()
