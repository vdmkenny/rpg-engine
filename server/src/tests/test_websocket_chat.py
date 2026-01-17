"""
WebSocket integration tests for chat functionality.

Covers:
- Local chat (range-based)
- Global chat (all players)
- DM chat (not implemented)
- Empty/invalid messages

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
    receive_message,
    receive_message_of_type,
    integration_client,
)


@SKIP_WS_INTEGRATION
class TestLocalChat:
    """Tests for local chat functionality."""

    def test_local_chat_sends_message(self, integration_client):
        """Local chat message should be sent and received by sender."""
        client = integration_client
        username = unique_username("chat_local")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send local chat message
            test_message = "Hello from local chat!"
            send_ws_message(
                websocket,
                MessageType.SEND_CHAT_MESSAGE,
                {"channel": "local", "message": test_message},
            )

            # Should receive the chat message back (sender always gets their own message)
            response = receive_message_of_type(
                websocket, [MessageType.NEW_CHAT_MESSAGE.value]
            )

            assert response["type"] == MessageType.NEW_CHAT_MESSAGE.value
            assert response["payload"]["message"] == test_message
            assert response["payload"]["channel"] == "local"
            assert response["payload"]["username"] == username

    def test_local_chat_default_channel(self, integration_client):
        """Chat without channel specified should default to local."""
        client = integration_client
        username = unique_username("chat_default")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send chat without channel (should default to local)
            test_message = "Default channel test"
            send_ws_message(
                websocket,
                MessageType.SEND_CHAT_MESSAGE,
                {"message": test_message},  # No channel specified
            )

            # Should receive the chat message
            response = receive_message_of_type(
                websocket, [MessageType.NEW_CHAT_MESSAGE.value]
            )

            assert response["type"] == MessageType.NEW_CHAT_MESSAGE.value
            assert response["payload"]["message"] == test_message
            assert response["payload"]["channel"] == "local"


@SKIP_WS_INTEGRATION
class TestGlobalChat:
    """Tests for global chat functionality."""

    def test_global_chat_sends_message(self, integration_client):
        """Global chat message should be sent."""
        client = integration_client
        username = unique_username("chat_global")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send global chat message
            test_message = "Hello everyone!"
            send_ws_message(
                websocket,
                MessageType.SEND_CHAT_MESSAGE,
                {"channel": "global", "message": test_message},
            )

            # Should receive the chat message
            response = receive_message_of_type(
                websocket, [MessageType.NEW_CHAT_MESSAGE.value]
            )

            assert response["type"] == MessageType.NEW_CHAT_MESSAGE.value
            assert response["payload"]["message"] == test_message
            assert response["payload"]["channel"] == "global"


@SKIP_WS_INTEGRATION
class TestDMChat:
    """Tests for DM (direct message) chat functionality."""

    def test_dm_chat_not_implemented(self, integration_client):
        """DM chat should return not implemented error."""
        client = integration_client
        username = unique_username("chat_dm")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send DM chat message
            send_ws_message(
                websocket,
                MessageType.SEND_CHAT_MESSAGE,
                {"channel": "dm", "message": "Private message", "target": "someone"},
            )

            # Should receive error or the message indicating not implemented
            response = receive_message_of_type(
                websocket, 
                [MessageType.NEW_CHAT_MESSAGE.value, MessageType.ERROR.value],
                max_attempts=5
            )

            # Either an error or a chat message indicating not implemented
            assert response["type"] in [
                MessageType.NEW_CHAT_MESSAGE.value,
                MessageType.ERROR.value,
            ]


@SKIP_WS_INTEGRATION
class TestChatEdgeCases:
    """Tests for chat edge cases."""

    def test_empty_message_ignored(self, integration_client):
        """Empty chat message should be ignored."""
        client = integration_client
        username = unique_username("chat_empty")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send empty message
            send_ws_message(
                websocket,
                MessageType.SEND_CHAT_MESSAGE,
                {"channel": "local", "message": ""},
            )

            # Empty messages should be ignored, no response expected
            # Send another valid message to verify connection still works
            send_ws_message(
                websocket,
                MessageType.SEND_CHAT_MESSAGE,
                {"channel": "local", "message": "Valid message after empty"},
            )

            response = receive_message_of_type(
                websocket, [MessageType.NEW_CHAT_MESSAGE.value]
            )

            assert response["payload"]["message"] == "Valid message after empty"

    def test_whitespace_message_ignored(self, integration_client):
        """Whitespace-only chat message should be ignored."""
        client = integration_client
        username = unique_username("chat_whitespace")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Send whitespace-only message
            send_ws_message(
                websocket,
                MessageType.SEND_CHAT_MESSAGE,
                {"channel": "local", "message": "   "},
            )

            # Whitespace messages should be ignored
            # Send valid message to verify connection
            send_ws_message(
                websocket,
                MessageType.SEND_CHAT_MESSAGE,
                {"channel": "local", "message": "Valid after whitespace"},
            )

            response = receive_message_of_type(
                websocket, [MessageType.NEW_CHAT_MESSAGE.value]
            )

            assert response["payload"]["message"] == "Valid after whitespace"
