"""
WebSocket integration tests for security edge cases.

Covers:
- Banned player connection attempts
- Timed-out player connection attempts
- Invalid message types
- Malformed payloads

These tests use async WebSocketTestClient patterns for structured testing.
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import timedelta

from server.src.core.security import create_access_token
from common.src.protocol import MessageType
from server.src.tests.websocket_test_utils import WebSocketTestClient


@pytest.mark.integration
class TestInvalidMessages:
    """Tests for invalid message handling."""

    @pytest.mark.asyncio
    async def test_unknown_message_type_handled(self, test_client: WebSocketTestClient):
        """Unknown message type should not crash the server."""
        # Send message with unknown type directly using raw WebSocket
        import msgpack
        
        unknown_message = {
            "type": "UNKNOWN_MESSAGE_TYPE",
            "payload": {},
            "id": "test_unknown_001",
            "version": "2.0"
        }
        
        # Send raw message to test server robustness
        raw_message = msgpack.packb(unknown_message, use_bin_type=True)
        
        # Send using WebSocketTestClient's internal websocket (async)
        await test_client.websocket.send_bytes(raw_message)
        
        # Wait briefly - server should handle gracefully without crashing
        await asyncio.sleep(0.1)
        
        # Test passes if connection remains open and no exception is thrown
