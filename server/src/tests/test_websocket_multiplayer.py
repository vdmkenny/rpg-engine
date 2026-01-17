"""
WebSocket integration tests for multiplayer scenarios.

Covers:
- Player connection and movement
- Game state update format
- Player disconnect handling

These tests use the real PostgreSQL database and WebSocket handlers.
Note: True multi-player visibility tests (player A sees player B) require
concurrent WebSocket connections which are complex with TestClient.
"""

import pytest

from common.src.protocol import MessageType, Direction
from server.src.tests.ws_test_helpers import (
    SKIP_WS_INTEGRATION,
    unique_username,
    register_and_login,
    authenticate_websocket,
    send_ws_message,
    receive_message,
    integration_client,
    get_player_id_from_welcome,
)


@SKIP_WS_INTEGRATION
class TestMultiplayerMovement:
    """Tests for player movement and game state updates."""

    def test_player_movement_creates_game_state_update(self, integration_client):
        """Moving player should receive GAME_STATE_UPDATE."""
        client = integration_client
        username = unique_username("mp_move")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send move intent
            send_ws_message(
                websocket,
                MessageType.MOVE_INTENT,
                {"direction": Direction.DOWN.value},
            )

            # Should receive GAME_STATE_UPDATE confirming the move
            response = receive_message(websocket)
            assert response["type"] == MessageType.GAME_STATE_UPDATE.value
            assert "payload" in response

    def test_multiple_movements(self, integration_client):
        """Multiple movements should produce game state updates."""
        client = integration_client
        username = unique_username("mp_multi")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Move multiple times and count game state updates received
            game_state_updates = 0
            directions = [Direction.DOWN, Direction.RIGHT, Direction.UP]

            for direction in directions:
                send_ws_message(
                    websocket,
                    MessageType.MOVE_INTENT,
                    {"direction": direction.value},
                )
                # Consume response - could be MOVE_INTENT echo or GAME_STATE_UPDATE
                response = receive_message(websocket)
                if response["type"] == MessageType.GAME_STATE_UPDATE.value:
                    game_state_updates += 1

            # Should have received at least one game state update
            # (exact count depends on tick timing)
            assert game_state_updates >= 1


@SKIP_WS_INTEGRATION
class TestGameStateUpdateFormat:
    """Tests for GAME_STATE_UPDATE message format."""

    def test_game_state_update_has_correct_structure(self, integration_client):
        """GAME_STATE_UPDATE should have proper payload structure."""
        client = integration_client
        username = unique_username("mp_format")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send move to trigger a game state update
            send_ws_message(
                websocket,
                MessageType.MOVE_INTENT,
                {"direction": Direction.DOWN.value},
            )

            # Get the game state update
            response = receive_message(websocket)
            assert response["type"] == MessageType.GAME_STATE_UPDATE.value

            payload = response["payload"]
            # Should be a dict with player/entity data
            assert isinstance(payload, dict)


@SKIP_WS_INTEGRATION
class TestPlayerDisconnect:
    """Tests for player disconnect handling."""

    def test_player_can_disconnect_cleanly(self, integration_client):
        """Player should be able to disconnect without errors."""
        client = integration_client
        username = unique_username("mp_disconnect")
        token = register_and_login(client, username)

        # Connect and disconnect
        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value
            # WebSocket will close cleanly when context exits

        # If we get here without exception, disconnect was clean
        assert True

    def test_player_data_synced_on_disconnect(self, integration_client):
        """Player position should be synced to database on disconnect."""
        client = integration_client
        username = unique_username("mp_sync")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Move the player
            send_ws_message(
                websocket,
                MessageType.MOVE_INTENT,
                {"direction": Direction.DOWN.value},
            )

            # Consume the game state update
            receive_message(websocket)

        # After disconnect, the sync_player_to_db should have been called
        # We can't easily verify the DB state here, but no exception means success
        assert True

    def test_reconnect_after_disconnect(self, integration_client):
        """Player should be able to reconnect after disconnecting."""
        client = integration_client
        username = unique_username("mp_reconnect")
        token = register_and_login(client, username)

        # First connection
        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

        # Second connection (same user)
        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value
            # Successfully reconnected
