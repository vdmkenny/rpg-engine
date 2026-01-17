"""
WebSocket integration tests for equipment operations.

Covers:
- REQUEST_EQUIPMENT - Get equipment state
- EQUIP_ITEM - Equip from inventory
- UNEQUIP_ITEM - Unequip to inventory
- REQUEST_STATS - Get aggregated stats

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
class TestEquipmentRequest:
    """Tests for REQUEST_EQUIPMENT message handler."""

    def test_request_equipment_empty(self, integration_client):
        """New player should have no equipment."""
        client = integration_client
        username = unique_username("equip_empty")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Request equipment
            send_ws_message(websocket, MessageType.REQUEST_EQUIPMENT, {})

            # Should receive EQUIPMENT_UPDATE
            response = receive_message_of_type(
                websocket, [MessageType.EQUIPMENT_UPDATE.value]
            )

            assert response["type"] == MessageType.EQUIPMENT_UPDATE.value
            payload = response["payload"]
            assert "slots" in payload
            assert "total_stats" in payload
            # All slots should be present (some empty)
            slots = payload["slots"]
            assert isinstance(slots, list)
            # Should have all equipment slot types represented
            assert len(slots) > 0


@SKIP_WS_INTEGRATION
class TestEquipItem:
    """Tests for EQUIP_ITEM message handler."""

    def test_equip_item_empty_slot_fails(self, integration_client):
        """Equipping from empty inventory slot should fail."""
        client = integration_client
        username = unique_username("equip_empty_slot")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to equip from empty inventory slot
            send_ws_message(
                websocket,
                MessageType.EQUIP_ITEM,
                {"inventory_slot": 0},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "equip_item"
            assert response["payload"]["success"] is False

    def test_equip_item_invalid_slot_fails(self, integration_client):
        """Equipping from invalid inventory slot should fail."""
        client = integration_client
        username = unique_username("equip_invalid_slot")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to equip from invalid slot
            send_ws_message(
                websocket,
                MessageType.EQUIP_ITEM,
                {"inventory_slot": 999},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "equip_item"
            assert response["payload"]["success"] is False


@SKIP_WS_INTEGRATION
class TestUnequipItem:
    """Tests for UNEQUIP_ITEM message handler."""

    def test_unequip_empty_slot_fails(self, integration_client):
        """Unequipping from empty equipment slot should fail."""
        client = integration_client
        username = unique_username("unequip_empty")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to unequip from empty weapon slot
            send_ws_message(
                websocket,
                MessageType.UNEQUIP_ITEM,
                {"equipment_slot": "weapon"},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "unequip_item"
            assert response["payload"]["success"] is False

    def test_unequip_invalid_slot_fails(self, integration_client):
        """Unequipping from invalid equipment slot should fail."""
        client = integration_client
        username = unique_username("unequip_invalid")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to unequip from invalid slot
            send_ws_message(
                websocket,
                MessageType.UNEQUIP_ITEM,
                {"equipment_slot": "invalid_slot_name"},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "unequip_item"
            assert response["payload"]["success"] is False


@SKIP_WS_INTEGRATION
class TestRequestStats:
    """Tests for REQUEST_STATS message handler."""

    def test_request_stats_base(self, integration_client):
        """New player should have base stats."""
        client = integration_client
        username = unique_username("stats_base")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Request stats
            send_ws_message(websocket, MessageType.REQUEST_STATS, {})

            # Should receive STATS_UPDATE
            response = receive_message_of_type(
                websocket, [MessageType.STATS_UPDATE.value]
            )

            assert response["type"] == MessageType.STATS_UPDATE.value
            payload = response["payload"]
            
            # Should have basic stat structure (ItemStats fields)
            # All stats default to 0 for new player with no equipment
            assert "attack_bonus" in payload
            assert "strength_bonus" in payload
            assert "physical_defence_bonus" in payload
            assert isinstance(payload["attack_bonus"], int)
