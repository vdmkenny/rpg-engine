"""
Unit tests for ChatService functionality.

Covers:
- Message validation with channel-specific limits
- Permission system for global chat (role-based)
- System message generation
- Recipient resolution (local, global, DM)
- Configuration-based behavior

These are unit tests that test ChatService methods directly without WebSocket integration.
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from server.src.services.chat_service import ChatService
from server.src.schemas.player import PlayerRole
from server.src.core.config import settings


class TestMessageValidation:
    """Tests for message validation functionality."""

    @pytest.mark.asyncio
    async def test_validate_message_local_success(self, db_session):
        """Valid local message should pass validation."""
        message = "Hello world!"
        result = await ChatService.validate_message(message, "local", 1)
        
        assert result["valid"] is True
        assert result["message"] == "Hello world!"
        assert result["reason"] is None
        assert result["system_message"] is None

    @pytest.mark.asyncio
    async def test_validate_message_empty_message(self, db_session):
        """Empty message should be rejected."""
        result = await ChatService.validate_message("", "local", 1)
        
        assert result["valid"] is False
        assert result["reason"] == "Message too short"
        assert result["system_message"] is not None
        assert "cannot be empty" in result["system_message"]["message"]

    @pytest.mark.asyncio
    async def test_validate_message_whitespace_only(self, db_session):
        """Whitespace-only message should be rejected after stripping."""
        result = await ChatService.validate_message("   ", "local", 1)
        
        assert result["valid"] is False
        assert result["reason"] == "Message empty after processing"
        assert result["system_message"] is not None

    @pytest.mark.asyncio
    async def test_validate_message_local_length_limit(self, db_session):
        """Local message should be truncated at 280 characters."""
        # Create a message longer than local limit (280 chars)
        long_message = "A" * 300
        result = await ChatService.validate_message(long_message, "local", 1)
        
        assert result["valid"] is True
        assert len(result["message"]) == settings.CHAT_MAX_MESSAGE_LENGTH_LOCAL
        assert result["message"] == "A" * 280

    @pytest.mark.asyncio
    async def test_validate_message_global_length_limit(self, db_session):
        """Global message should be truncated at 200 characters."""
        # Create a message longer than global limit (200 chars)
        long_message = "B" * 250
        
        with patch('server.src.services.chat_service.ChatService.validate_global_chat_permission') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            result = await ChatService.validate_message(long_message, "global", 1)
            
            assert result["valid"] is True
            assert len(result["message"]) == settings.CHAT_MAX_MESSAGE_LENGTH_GLOBAL
            assert result["message"] == "B" * 200

    @pytest.mark.asyncio
    async def test_validate_message_dm_length_limit(self, db_session):
        """DM message should be truncated at 500 characters."""
        # Create a message longer than DM limit (500 chars)
        long_message = "C" * 600
        result = await ChatService.validate_message(long_message, "dm", 1)
        
        assert result["valid"] is True
        assert len(result["message"]) == settings.CHAT_MAX_MESSAGE_LENGTH_DM
        assert result["message"] == "C" * 500

    @pytest.mark.asyncio
    async def test_validate_message_at_exact_limit(self, db_session):
        """Message exactly at limit should not be truncated."""
        # Test local chat limit
        message = "D" * settings.CHAT_MAX_MESSAGE_LENGTH_LOCAL
        result = await ChatService.validate_message(message, "local", 1)
        
        assert result["valid"] is True
        assert len(result["message"]) == settings.CHAT_MAX_MESSAGE_LENGTH_LOCAL
        assert result["message"] == message


class TestPermissionSystem:
    """Tests for role-based permission system."""

    @pytest.mark.asyncio
    async def test_validate_global_chat_permission_admin_allowed(self, db_session):
        """Admin player should have global chat permission."""
        with patch('server.src.services.chat_service.PlayerService.check_global_chat_permission') as mock_check:
            mock_check.return_value = True
            
            result = await ChatService.validate_global_chat_permission(1)
            
            assert result["valid"] is True
            assert "error_message" not in result
            assert "system_message" not in result
            mock_check.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_validate_global_chat_permission_player_denied(self, db_session):
        """Regular player should be denied global chat permission."""
        with patch('server.src.services.chat_service.PlayerService.check_global_chat_permission') as mock_check:
            mock_check.return_value = False
            
            result = await ChatService.validate_global_chat_permission(1)
            
            assert result["valid"] is False
            assert "don't have permission" in result["error_message"]
            assert result["system_message"]["username"] == "System"
            assert "don't have permission" in result["system_message"]["message"]

    @pytest.mark.asyncio
    async def test_validate_global_chat_permission_global_disabled(self, db_session):
        """Global chat disabled should deny all players."""
        with patch('server.src.core.config.settings.CHAT_GLOBAL_ENABLED', False):
            result = await ChatService.validate_global_chat_permission(1)
            
            assert result["valid"] is False
            assert "currently disabled" in result["error_message"]
            assert result["system_message"]["message"] == "Global chat is currently disabled."

    @pytest.mark.asyncio
    async def test_validate_message_global_permission_check(self, db_session):
        """Global message should check permissions when validating."""
        with patch('server.src.services.chat_service.ChatService.validate_global_chat_permission') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            result = await ChatService.validate_message(
                "Global message", "global", 1
            )
            
            assert result["valid"] is True
            mock_validate.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_validate_message_global_permission_denied(self, db_session):
        """Global message should be denied when permissions fail."""
        with patch('server.src.services.chat_service.ChatService.validate_global_chat_permission') as mock_validate:
            mock_validate.return_value = {
                "valid": False,
                "error_message": "Permission denied",
                "system_message": {"username": "System", "message": "Access denied"}
            }
            
            result = await ChatService.validate_message(
                "Global message", "global", 1
            )
            
            assert result["valid"] is False
            assert result["reason"] == "Permission denied"
            assert result["system_message"]["username"] == "System"


class TestSystemMessages:
    """Tests for system message generation."""

    def test_create_system_error_message_default_channel(self):
        """System error message should have correct default format."""
        message = ChatService.create_system_error_message("Test error")
        
        assert message["username"] == "System"
        assert message["message"] == "Test error"
        assert message["channel"] == "system"
        assert "timestamp" in message
        assert isinstance(message["timestamp"], float)

    def test_create_system_error_message_custom_channel(self):
        """System error message should accept custom channel."""
        message = ChatService.create_system_error_message("Test error", "error")
        
        assert message["username"] == "System"
        assert message["message"] == "Test error"
        assert message["channel"] == "error"
        assert "timestamp" in message


class TestConfigurationBehavior:
    """Tests for configuration-based behavior."""

    def test_get_message_length_limit_local(self):
        """Should return correct limit for local channel."""
        limit = ChatService.get_message_length_limit("local")
        assert limit == settings.CHAT_MAX_MESSAGE_LENGTH_LOCAL

    def test_get_message_length_limit_global(self):
        """Should return correct limit for global channel."""
        limit = ChatService.get_message_length_limit("global")
        assert limit == settings.CHAT_MAX_MESSAGE_LENGTH_GLOBAL

    def test_get_message_length_limit_dm(self):
        """Should return correct limit for DM channel."""
        limit = ChatService.get_message_length_limit("dm")
        assert limit == settings.CHAT_MAX_MESSAGE_LENGTH_DM

    def test_get_message_length_limit_unknown_channel(self):
        """Unknown channel should default to local limit."""
        limit = ChatService.get_message_length_limit("unknown")
        assert limit == settings.CHAT_MAX_MESSAGE_LENGTH_LOCAL

    def test_get_message_length_limit_case_insensitive(self):
        """Channel names should be case insensitive."""
        limit_upper = ChatService.get_message_length_limit("GLOBAL")
        limit_lower = ChatService.get_message_length_limit("global")
        assert limit_upper == limit_lower == settings.CHAT_MAX_MESSAGE_LENGTH_GLOBAL


class TestRecipientResolution:
    """Tests for recipient resolution functionality."""

    @pytest.mark.asyncio
    async def test_get_local_chat_recipients_calculation(self):
        """Local chat recipients should be calculated based on configured range."""
        with patch('server.src.services.chat_service.PlayerService.get_nearby_players') as mock_nearby:
            mock_nearby.return_value = [
                {"player_id": 2, "username": "player2", "x": 10, "y": 10},
                {"player_id": 3, "username": "player3", "x": 15, "y": 15}
            ]
            
            recipients = await ChatService.get_local_chat_recipients(1, "testmap")
            
            # Should call PlayerService with calculated range (chunk_radius * 16)
            expected_range = settings.CHAT_LOCAL_CHUNK_RADIUS * 16
            mock_nearby.assert_called_once_with(1, expected_range)
            
            assert len(recipients) == 2
            assert recipients[0]["player_id"] == 2
            assert recipients[1]["player_id"] == 3

    @pytest.mark.asyncio
    async def test_get_dm_recipient_found_and_online(self, db_session):
        """DM recipient resolution should work for online players."""
        mock_player = type('Player', (), {'id': 2, 'username': 'target_player'})()
        
        with patch('server.src.services.chat_service.PlayerService.get_player_by_username') as mock_get_player, \
             patch('server.src.services.chat_service.PlayerService.is_player_online') as mock_is_online:
            
            mock_get_player.return_value = mock_player
            mock_is_online.return_value = True
            
            result = await ChatService.get_dm_recipient("target_player")
            
            assert result is not None
            assert result["player_id"] == 2
            assert result["username"] == "target_player"

    @pytest.mark.asyncio
    async def test_get_dm_recipient_not_found(self, db_session):
        """DM recipient resolution should return None for non-existent players."""
        with patch('server.src.services.chat_service.PlayerService.get_player_by_username') as mock_get_player:
            mock_get_player.return_value = None
            
            result = await ChatService.get_dm_recipient("nonexistent")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_get_dm_recipient_offline(self, db_session):
        """DM recipient resolution should return None for offline players."""
        mock_player = type('Player', (), {'id': 2, 'username': 'offline_player'})()
        
        with patch('server.src.services.chat_service.PlayerService.get_player_by_username') as mock_get_player, \
             patch('server.src.services.chat_service.PlayerService.is_player_online') as mock_is_online:
            
            mock_get_player.return_value = mock_player
            mock_is_online.return_value = False
            
            result = await ChatService.get_dm_recipient("offline_player")
            
            assert result is None


class TestChannelValidation:
    """Tests for channel type validation."""

    def test_is_valid_channel_type_valid_channels(self):
        """Should accept valid channel types."""
        assert ChatService.is_valid_channel_type("local") is True
        assert ChatService.is_valid_channel_type("global") is True
        assert ChatService.is_valid_channel_type("dm") is True

    def test_is_valid_channel_type_invalid_channels(self):
        """Should reject invalid channel types."""
        assert ChatService.is_valid_channel_type("invalid") is False
        assert ChatService.is_valid_channel_type("") is False
        assert ChatService.is_valid_channel_type("LOCAL") is False  # Case sensitive

    def test_format_chat_message_basic(self):
        """Should format chat message correctly."""
        result = ChatService.format_chat_message("user1", "Hello", "local")
        
        assert result["sender"] == "user1"
        assert result["message"] == "Hello"
        assert result["channel"] == "local"
        assert result["timestamp"] is None

    def test_format_chat_message_with_recipient(self):
        """Should format DM message with recipient."""
        result = ChatService.format_chat_message("user1", "Hello", "dm", "user2")
        
        assert result["sender"] == "user1"
        assert result["message"] == "Hello"
        assert result["channel"] == "dm"
        assert result["recipient"] == "user2"


# Test fixtures and helpers
@pytest_asyncio.fixture
async def db_session():
    """Mock database session for testing."""
    return AsyncMock(spec=AsyncSession)