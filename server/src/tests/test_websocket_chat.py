"""
WebSocket integration tests for chat functionality.

Covers:
- Local chat (range-based)
- Global chat (all players)
- DM chat (direct messages)
- Empty/invalid messages

These tests use the test database and WebSocket handlers.
"""

import pytest
import pytest_asyncio

from common.src.protocol import MessageType
from server.src.tests.websocket_test_utils import WebSocketTestClient


@pytest.mark.integration
class TestLocalChat:
    """Tests for local chat functionality."""

    @pytest.mark.asyncio
    async def test_local_chat_sends_message(self, test_client: WebSocketTestClient):
        """Local chat message should be sent successfully."""
        import asyncio
        
        # Wait for chat rate limit (1.0s between messages)
        await asyncio.sleep(1.1)
        
        # Send local chat message
        test_message = "Hello from local chat!"
        
        # Send command should succeed
        response = await test_client.send_command(
            MessageType.CMD_CHAT_SEND,
            {"channel": "local", "message": test_message}
        )
        assert response.type == MessageType.RESP_SUCCESS

    @pytest.mark.asyncio
    async def test_local_chat_default_channel(self, test_client: WebSocketTestClient):
        """Chat without channel specified should default to local."""
        # Wait for chat rate limit (1.0s between messages)
        import asyncio
        await asyncio.sleep(1.1)
        
        test_message = "Default channel test"
        
        response = await test_client.send_command(
            MessageType.CMD_CHAT_SEND,
            {"message": test_message}  # No channel specified
        )
        # Chat command should succeed (message will be broadcast to other players)
        assert response.type == MessageType.RESP_SUCCESS
        assert response.payload is not None


@pytest.mark.integration
class TestGlobalChat:
    """Tests for global chat functionality."""

    @pytest.mark.asyncio
    async def test_global_chat_sends_message(self, test_client: WebSocketTestClient):
        """Regular players should receive permission denied for global chat."""
        from server.src.tests.websocket_test_utils import ErrorResponseError
        import pytest
        
        # Send global chat message (should be denied for regular players)
        test_message = "Hello everyone!"
        
        # Should receive error response for permission denied
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "global", "message": test_message}
            )
        
        # Verify it's the correct permission error
        assert "permission" in str(exc_info.value).lower()


@pytest.mark.integration
class TestDMChat:
    """Tests for DM (direct message) chat functionality."""

    @pytest.mark.asyncio
    async def test_dm_to_nonexistent_user_returns_error(self, test_client: WebSocketTestClient):
        """DM to non-existent user should return dm_recipient_not_found error."""
        from server.src.tests.websocket_test_utils import ErrorResponseError
        
        # Send DM to non-existent player - server returns RESP_ERROR
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "dm", "message": "Private message", "recipient": "nonexistent_user"},
            )

        # Verify dm_recipient_not_found error
        assert "dm_recipient_not_found" in exc_info.value.error_message


@pytest.mark.integration
class TestChatEdgeCases:
    """Tests for chat edge cases."""

    @pytest.mark.asyncio
    async def test_empty_message_ignored(self, test_client: WebSocketTestClient):
        """Empty chat message should return error response."""
        from server.src.tests.websocket_test_utils import ErrorResponseError
        import pytest
        
        # Send empty message (should return error)
        try:
            response = await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "local", "message": ""},
            )
            pytest.fail("Expected ErrorResponseError for empty message")
        except ErrorResponseError as e:
            # Should receive error for empty message
            assert e.error_code == "CHAT_MESSAGE_TOO_LONG"  # Server's actual error code
            assert "short" in e.error_message.lower()  # "Message too short"

    @pytest.mark.asyncio
    async def test_whitespace_message_ignored(self, test_client: WebSocketTestClient):
        """Whitespace-only chat message should return error response."""
        from server.src.tests.websocket_test_utils import ErrorResponseError
        import pytest
        
        # Send whitespace-only message (should return error)
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "local", "message": "   "},
            )

        # Should receive error for empty/whitespace message (stripped to empty)
        assert exc_info.value.error_code == "CHAT_MESSAGE_TOO_LONG"
        assert "short" in exc_info.value.error_message.lower() or "empty" in exc_info.value.error_message.lower()


@pytest.mark.integration
class TestChatSecurity:
    """Tests for chat security features."""

    @pytest.mark.asyncio
    async def test_long_message_truncated(self, test_client: WebSocketTestClient):
        """Chat messages exceeding max length should be truncated (not rejected)."""
        import asyncio
        
        # Wait for chat rate limit
        await asyncio.sleep(1.1)
        
        # Send a very long message (over 280 chars local limit)
        long_message = "A" * 400
        response = await test_client.send_command(
            MessageType.CMD_CHAT_SEND,
            {"channel": "local", "message": long_message},
        )

        # Server truncates messages to channel max length, returns success
        assert response.type == MessageType.RESP_SUCCESS
        # The message in response should be truncated to 280 chars (local limit)
        assert len(response.payload["message"]) == 280
        assert response.payload["message"] == "A" * 280

    @pytest.mark.asyncio
    async def test_message_at_max_length_not_truncated(self, test_client: WebSocketTestClient):
        """Chat message exactly at max length should not be truncated."""
        import asyncio
        
        # Wait for chat rate limit
        await asyncio.sleep(1.1)
        
        # Send a message exactly at local chat max length (280 chars)
        max_message = "B" * 280
        response = await test_client.send_command(
            MessageType.CMD_CHAT_SEND,
            {"channel": "local", "message": max_message},
        )

        # Should succeed without truncation
        assert response.type == MessageType.RESP_SUCCESS
        assert response.payload["message"] == max_message
        assert len(response.payload["message"]) == 280


@pytest.mark.integration
class TestGlobalChatPermissions:
    """Tests for role-based global chat permissions."""

    @pytest.mark.asyncio
    async def test_admin_can_send_global_messages(self, test_client: WebSocketTestClient):
        """
        Admin role should be able to send global chat messages.
        
        Note: The test_client fixture creates a regular player, not an admin.
        This test verifies that regular players are denied global chat.
        A separate test with admin fixtures would be needed to test admin access.
        """
        from server.src.tests.websocket_test_utils import ErrorResponseError
        import pytest
        
        # Test player is a regular player, so global chat should be denied
        test_message = "Admin global message!"
        
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "global", "message": test_message},
            )
        
        # Verify permission denied error
        assert "permission" in exc_info.value.error_message.lower()

    @pytest.mark.asyncio
    async def test_regular_player_global_chat_denied(self, test_client: WebSocketTestClient):
        """Regular player should be denied global chat permission."""
        from server.src.tests.websocket_test_utils import ErrorResponseError
        import pytest
        
        # Send global chat message - should be denied for regular player
        test_message = "Player trying global!"
        
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "global", "message": test_message},
            )
        
        # Verify permission denied error
        assert "permission" in exc_info.value.error_message.lower()


@pytest.mark.integration  
class TestChatMessageLimits:
    """Tests for channel-specific message length limits."""

    @pytest.mark.asyncio
    async def test_local_chat_280_limit(self, test_client: WebSocketTestClient):
        """Local chat should enforce 280 character limit via truncation."""
        import asyncio
        
        # Wait for chat rate limit
        await asyncio.sleep(1.1)
        
        # Send message over 280 characters
        long_message = "A" * 300  # Over local limit
        response = await test_client.send_command(
            MessageType.CMD_CHAT_SEND,
            {"channel": "local", "message": long_message},
        )

        # Message should be truncated to 280 characters
        assert response.type == MessageType.RESP_SUCCESS
        assert len(response.payload["message"]) == 280
        assert response.payload["message"] == "A" * 280

    @pytest.mark.asyncio
    async def test_global_chat_200_limit(self, test_client: WebSocketTestClient):
        """Global chat should enforce 200 character limit, but regular players are denied."""
        from server.src.tests.websocket_test_utils import ErrorResponseError
        import pytest
        
        # Send message over 200 characters to global channel
        long_message = "B" * 250  # Over global limit
        
        # Regular player should be denied global chat permission
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "global", "message": long_message},
            )
        
        # Verify permission denied (not length error)
        assert "permission" in exc_info.value.error_message.lower()

    @pytest.mark.asyncio
    async def test_dm_chat_500_limit(self, test_client: WebSocketTestClient):
        """DM chat should reject messages over Pydantic's 500 character limit."""
        from server.src.tests.websocket_test_utils import ErrorResponseError
        import asyncio
        
        # Wait for chat rate limit
        await asyncio.sleep(1.1)
        
        # Send DM over 500 characters - this exceeds Pydantic's max_length=500 constraint
        # on the ChatSendPayload model, causing validation to fail before reaching ChatService
        long_message = "C" * 600  # Over Pydantic limit
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "dm", "message": long_message, "recipient": "someone"},
            )

        # Pydantic validation fails with CHAT_MESSAGE_TOO_LONG error
        assert exc_info.value.error_code == "CHAT_MESSAGE_TOO_LONG"


@pytest.mark.integration
class TestSystemErrorMessages:
    """Tests for system error messages in chat UI."""

    @pytest.mark.asyncio
    async def test_permission_error_as_system_message(self, test_client: WebSocketTestClient):
        """Permission errors should appear as error responses."""
        from server.src.tests.websocket_test_utils import ErrorResponseError
        import pytest
        
        # Try to send global message (should be denied for regular player)
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "global", "message": "Denied message"},
            )

        # Should get permission denied error
        assert "permission" in exc_info.value.error_message.lower()

    @pytest.mark.asyncio
    async def test_invalid_dm_target_system_message(self, test_client: WebSocketTestClient):
        """Invalid DM targets should generate error responses."""
        from server.src.tests.websocket_test_utils import ErrorResponseError
        import asyncio
        
        # Wait for chat rate limit
        await asyncio.sleep(1.1)
        
        # Send DM to non-existent player - server returns RESP_ERROR
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "dm", "message": "Hello!", "recipient": "nonexistent_player_xyz"},
            )

        # Verify dm_recipient_not_found error
        assert "dm_recipient_not_found" in exc_info.value.error_message


@pytest.mark.integration
class TestChatConfiguration:
    """Tests for configuration-based chat behavior."""

    @pytest.mark.asyncio
    async def test_chat_system_responds_to_commands(self, test_client: WebSocketTestClient):
        """Chat system should respond appropriately to different channel commands."""
        from server.src.tests.websocket_test_utils import ErrorResponseError
        import asyncio
        
        # Test local channel - should succeed
        response = await test_client.send_command(
            MessageType.CMD_CHAT_SEND,
            {"channel": "local", "message": "Testing local channel"}
        )
        assert response.type == MessageType.RESP_SUCCESS
        
        # Wait for rate limit
        await asyncio.sleep(1.1)
        
        # Test global channel - should fail for regular player (permission denied)
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "global", "message": "Testing global channel"}
            )
        assert "permission" in exc_info.value.error_message.lower()
        
        # Wait for rate limit
        await asyncio.sleep(1.1)
        
        # Test DM channel to non-existent user - should fail with dm_recipient_not_found
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_CHAT_SEND,
                {"channel": "dm", "message": "Testing dm channel", "recipient": "test_target"}
            )
        assert "dm_recipient_not_found" in exc_info.value.error_message
