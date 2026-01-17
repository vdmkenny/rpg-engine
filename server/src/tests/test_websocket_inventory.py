"""
WebSocket integration tests for inventory operations.

Covers:
- REQUEST_INVENTORY - Get inventory state
- MOVE_INVENTORY_ITEM - Move items between slots
- SORT_INVENTORY - Sort inventory by type/rarity/name
- DROP_ITEM - Drop item to ground

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
    get_player_id_from_welcome,
)


@SKIP_WS_INTEGRATION
class TestInventoryRequest:
    """Tests for REQUEST_INVENTORY message handler."""

    def test_request_inventory_empty(self, integration_client):
        """New player should have empty inventory."""
        client = integration_client
        username = unique_username("inv_empty")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Request inventory
            send_ws_message(websocket, MessageType.REQUEST_INVENTORY, {})

            # Should receive INVENTORY_UPDATE
            response = receive_message_of_type(
                websocket, [MessageType.INVENTORY_UPDATE.value]
            )

            assert response["type"] == MessageType.INVENTORY_UPDATE.value
            payload = response["payload"]
            # Check payload structure
            assert "slots" in payload
            assert "max_slots" in payload
            assert "used_slots" in payload
            assert "free_slots" in payload
            # New player should have empty inventory
            assert payload["slots"] == []
            assert payload["used_slots"] == 0


@SKIP_WS_INTEGRATION
class TestInventoryMove:
    """Tests for MOVE_INVENTORY_ITEM message handler."""

    def test_move_item_empty_source_fails(self, integration_client):
        """Moving from empty slot should fail."""
        client = integration_client
        username = unique_username("inv_move_empty")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to move from empty slot 0 to slot 5
            send_ws_message(
                websocket,
                MessageType.MOVE_INVENTORY_ITEM,
                {"from_slot": 0, "to_slot": 5},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "move_item"
            assert response["payload"]["success"] is False

    def test_move_item_invalid_slot_fails(self, integration_client):
        """Moving to invalid slot should fail."""
        client = integration_client
        username = unique_username("inv_move_invalid")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to move to slot outside range (inventory is typically 28 slots)
            send_ws_message(
                websocket,
                MessageType.MOVE_INVENTORY_ITEM,
                {"from_slot": 0, "to_slot": 999},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "move_item"
            assert response["payload"]["success"] is False


@SKIP_WS_INTEGRATION
class TestInventorySort:
    """Tests for SORT_INVENTORY message handler."""

    def test_sort_inventory_empty(self, integration_client):
        """Sorting empty inventory should succeed with no changes."""
        client = integration_client
        username = unique_username("inv_sort_empty")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Sort by category (valid sort type)
            send_ws_message(
                websocket,
                MessageType.SORT_INVENTORY,
                {"sort_type": "category"},
            )

            # Should receive OPERATION_RESULT with success
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "sort_inventory"
            assert response["payload"]["success"] is True

    def test_sort_inventory_invalid_type_fails(self, integration_client):
        """Sorting with invalid sort type should fail."""
        client = integration_client
        username = unique_username("inv_sort_invalid")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Sort with invalid type
            send_ws_message(
                websocket,
                MessageType.SORT_INVENTORY,
                {"sort_type": "invalid_sort_type"},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "sort_inventory"
            assert response["payload"]["success"] is False


@SKIP_WS_INTEGRATION
class TestInventoryDrop:
    """Tests for DROP_ITEM message handler."""

    def test_drop_item_empty_slot_fails(self, integration_client):
        """Dropping from empty slot should fail."""
        client = integration_client
        username = unique_username("inv_drop_empty")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to drop from empty slot
            send_ws_message(
                websocket,
                MessageType.DROP_ITEM,
                {"inventory_slot": 0},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "drop_item"
            assert response["payload"]["success"] is False

    def test_drop_item_invalid_slot_fails(self, integration_client):
        """Dropping from invalid slot should fail."""
        client = integration_client
        username = unique_username("inv_drop_invalid")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to drop from invalid slot
            send_ws_message(
                websocket,
                MessageType.DROP_ITEM,
                {"inventory_slot": -1},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "drop_item"
            assert response["payload"]["success"] is False
