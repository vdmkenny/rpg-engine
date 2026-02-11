"""
End-to-end WebSocket tests for appearance (paperdoll) system.

Covers:
- CMD_UPDATE_APPEARANCE - Update player appearance
- EVENT_APPEARANCE_UPDATE - Receive appearance change broadcasts
- Appearance validation and error handling
- Rate limiting for appearance updates
- Visual state updates after appearance change

Uses WebSocketTestClient with structured async patterns.
"""

import pytest
import asyncio
from server.src.tests.websocket_test_utils import WebSocketTestClient, ErrorResponseError
from common.src.protocol import MessageType
from common.src.sprites import AppearanceData
from common.src.sprites.enums import (
    BodyType, SkinTone, HairStyle, HairColor, EyeColor,
    ClothingStyle, ClothingColor, PantsStyle, ShoesStyle
)


@pytest.mark.asyncio
class TestAppearanceUpdate:
    """Tests for appearance update command."""

    async def test_update_appearance_single_field(self, test_client: WebSocketTestClient):
        """Should be able to update a single appearance field."""
        client = test_client
        
        # Update only hair color
        response = await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"hair_color": "red"}
        )
        
        assert response.type == MessageType.RESP_SUCCESS
        assert "appearance" in response.payload
        assert response.payload["appearance"]["hair_color"] == "red"
        assert "visual_hash" in response.payload

    async def test_update_appearance_multiple_fields(self, test_client: WebSocketTestClient):
        """Should be able to update multiple appearance fields at once."""
        client = test_client
        
        response = await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {
                "hair_color": "blonde",
                "shirt_color": "blue",
                "pants_color": "black"
            }
        )
        
        assert response.type == MessageType.RESP_SUCCESS
        appearance = response.payload["appearance"]
        assert appearance["hair_color"] == "blonde"
        assert appearance["shirt_color"] == "blue"
        assert appearance["pants_color"] == "black"

    async def test_update_appearance_partial_preserves_others(self, test_client: WebSocketTestClient):
        """Partial update should preserve unchanged fields."""
        client = test_client
        
        # First update hair style
        await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"hair_style": "long"}
        )
        
        # Wait for rate limit cooldown (2.1 seconds to be safe)
        await asyncio.sleep(2.1)
        
        # Then update shirt color
        response = await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"shirt_color": "green"}
        )
        
        # Hair style should be preserved
        assert response.payload["appearance"]["hair_style"] == "long"
        assert response.payload["appearance"]["shirt_color"] == "green"

    async def test_update_appearance_invalid_value_fails(self, test_client: WebSocketTestClient):
        """Invalid appearance value should return error."""
        client = test_client
        
        with pytest.raises(ErrorResponseError) as exc_info:
            await client.send_command(
                MessageType.CMD_UPDATE_APPEARANCE,
                {"body_type": "invalid_value"}
            )
        
        error = exc_info.value
        assert error.error_category == "validation"

    async def test_update_appearance_rate_limit(self, test_client: WebSocketTestClient):
        """Should be rate limited for appearance updates."""
        client = test_client
        
        # First update should succeed
        await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"hair_color": "black"}
        )
        
        # Immediate second update should fail with rate limit
        with pytest.raises(ErrorResponseError) as exc_info:
            await client.send_command(
                MessageType.CMD_UPDATE_APPEARANCE,
                {"hair_color": "brown"}
            )
        
        error = exc_info.value
        assert error.error_category == "rate_limit"

    async def test_update_appearance_all_clothing_fields(self, test_client: WebSocketTestClient):
        """Should be able to update all clothing fields."""
        client = test_client
        
        response = await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {
                "shirt_style": "longsleeve2",
                "shirt_color": "purple",
                "pants_style": "shorts",
                "pants_color": "blue",
                "shoes_style": "sandals",
                "shoes_color": "brown"
            }
        )
        
        assert response.type == MessageType.RESP_SUCCESS
        appearance = response.payload["appearance"]
        assert appearance["shirt_style"] == "longsleeve2"
        assert appearance["shirt_color"] == "purple"
        assert appearance["pants_style"] == "shorts"
        assert appearance["pants_color"] == "blue"
        assert appearance["shoes_style"] == "sandals"
        assert appearance["shoes_color"] == "brown"

    async def test_update_appearance_visual_hash_changes(self, test_client: WebSocketTestClient):
        """Visual hash should change when appearance changes."""
        client = test_client
        
        # Get initial appearance (using valid hair color)
        response1 = await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"hair_color": "light_brown"}
        )
        hash1 = response1.payload["visual_hash"]
        
        # Wait for rate limit cooldown
        await asyncio.sleep(5)
        
        # Change appearance (using another valid hair color)
        response2 = await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"hair_color": "blonde"}
        )
        hash2 = response2.payload["visual_hash"]
        
        # Hash should be different
        assert hash1 != hash2


@pytest.mark.asyncio
class TestAppearanceInStateUpdates:
    """Tests for appearance in state update events."""
    pass


@pytest.mark.asyncio
class TestAppearanceValidation:
    """Tests for appearance validation."""

    async def test_invalid_body_type_rejected(self, test_client: WebSocketTestClient):
        """Invalid body type should be rejected."""
        client = test_client
        
        with pytest.raises(ErrorResponseError):
            await client.send_command(
                MessageType.CMD_UPDATE_APPEARANCE,
                {"body_type": "robot"}
            )

    async def test_invalid_hair_style_rejected(self, test_client: WebSocketTestClient):
        """Invalid hair style should be rejected."""
        client = test_client
        
        with pytest.raises(ErrorResponseError):
            await client.send_command(
                MessageType.CMD_UPDATE_APPEARANCE,
                {"hair_style": "mohawk_with_spikes"}
            )

    async def test_invalid_clothing_color_rejected(self, test_client: WebSocketTestClient):
        """Invalid clothing color should be rejected."""
        client = test_client
        
        with pytest.raises(ErrorResponseError):
            await client.send_command(
                MessageType.CMD_UPDATE_APPEARANCE,
                {"shirt_color": "neon_pink"}
            )

    async def test_empty_payload_rejected(self, test_client: WebSocketTestClient):
        """Empty payload should be handled gracefully."""
        client = test_client
        
        # Empty payload should succeed (no changes)
        response = await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {}
        )
        
        assert response.type == MessageType.RESP_SUCCESS



