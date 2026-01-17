"""
WebSocket integration tests for ground item operations.

Covers:
- PICKUP_ITEM - Pick up item from ground

These tests use the real PostgreSQL database and WebSocket handlers.
"""

import pytest

from common.src.protocol import MessageType
from server.src.tests.ws_test_helpers import (
    SKIP_WS_INTEGRATION,
    unique_username,
    register_and_login,
    authenticate_websocket,
    send_ws_message,
    receive_message_of_type,
    integration_client,
)


@SKIP_WS_INTEGRATION
class TestPickupItem:
    """Tests for PICKUP_ITEM message handler."""

    def test_pickup_item_not_found(self, integration_client):
        """Picking up non-existent item should fail."""
        client = integration_client
        username = unique_username("pickup_notfound")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to pick up non-existent ground item
            send_ws_message(
                websocket,
                MessageType.PICKUP_ITEM,
                {"ground_item_id": 99999},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "pickup_item"
            assert response["payload"]["success"] is False
            # Message should indicate item not found
            assert "not found" in response["payload"]["message"].lower() or \
                   "does not exist" in response["payload"]["message"].lower()

    def test_pickup_item_invalid_id(self, integration_client):
        """Picking up with invalid ID format should fail gracefully."""
        client = integration_client
        username = unique_username("pickup_invalid")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to pick up with negative ID
            send_ws_message(
                websocket,
                MessageType.PICKUP_ITEM,
                {"ground_item_id": -1},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "pickup_item"
            assert response["payload"]["success"] is False
