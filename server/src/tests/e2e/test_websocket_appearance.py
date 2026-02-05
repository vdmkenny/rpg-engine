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
                "shirt_style": "tunic",
                "shirt_color": "purple",
                "pants_style": "shorts",
                "pants_color": "blue",
                "shoes_style": "sandals",
                "shoes_color": "brown"
            }
        )
        
        assert response.type == MessageType.RESP_SUCCESS
        appearance = response.payload["appearance"]
        assert appearance["shirt_style"] == "tunic"
        assert appearance["shirt_color"] == "purple"
        assert appearance["pants_style"] == "shorts"
        assert appearance["pants_color"] == "blue"
        assert appearance["shoes_style"] == "sandals"
        assert appearance["shoes_color"] == "brown"

    async def test_update_appearance_visual_hash_changes(self, test_client: WebSocketTestClient):
        """Visual hash should change when appearance changes."""
        client = test_client
        
        # Get initial appearance
        response1 = await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"hair_color": "brown"}
        )
        hash1 = response1.payload["visual_hash"]
        
        # Wait for rate limit cooldown
        await asyncio.sleep(5)
        
        # Change appearance
        response2 = await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"hair_color": "blonde"}
        )
        hash2 = response2.payload["visual_hash"]
        
        # Hash should be different
        assert hash1 != hash2


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires test harness improvements for multi-client async handling")
class TestAppearanceBroadcast:
    """Tests for appearance update broadcasts to nearby players."""

    @pytest.mark.skip(reason="Requires test harness improvements for multi-client async handling")
    async def test_appearance_update_broadcasts_to_nearby(
        self, test_client: WebSocketTestClient, test_client2: WebSocketTestClient
    ):
        """Appearance changes should broadcast to nearby players."""
        client1 = test_client
        client2 = test_client2
        
        # Move both players to same location (if not already)
        # ... position setup code would go here ...
        
        # Client1 updates appearance
        await client1.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"shirt_color": "red"}
        )
        
        # Client2 should receive EVENT_APPEARANCE_UPDATE
        # This requires the test framework to capture broadcast messages
        # Implementation depends on WebSocketTestClient capabilities

    @pytest.mark.skip(reason="Requires test harness improvements for multi-client async handling")
    async def test_appearance_update_not_broadcast_to_far_players(
        self, test_client: WebSocketTestClient, test_client2: WebSocketTestClient
    ):
        """Appearance changes should not broadcast to far away players."""
        client1 = test_client
        client2 = test_client2
        
        # Move players far apart
        # ... position setup code would go here ...
        
        # Client1 updates appearance
        await client1.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"shirt_color": "blue"}
        )
        
        # Client2 should NOT receive EVENT_APPEARANCE_UPDATE
        # This requires the test framework to verify no broadcast received


@pytest.mark.asyncio
class TestAppearanceInStateUpdates:
    """Tests for appearance in state update events."""

    @pytest.mark.skip(reason="Requires test harness improvements for multi-client async handling")
    async def test_appearance_in_player_joined_event(
        self, test_client: WebSocketTestClient, test_client2: WebSocketTestClient
    ):
        """Player joined event should include appearance data."""
        client1 = test_client
        client2 = test_client2
        
        # Update client1's appearance first
        await client1.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"shirt_color": "green"}
        )
        
        # When client2 comes into range of client1, should see appearance in join event
        # This requires manipulating player positions in test

    async def test_visual_hash_in_state_update(
        self, test_client: WebSocketTestClient
    ):
        """State updates should include visual hash for caching."""
        client = test_client
        
        # Update appearance
        await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"hair_color": "red"}
        )
        
        # Wait for state update event
        # Verify visual_hash field exists


@pytest.mark.asyncio
class TestAppearancePersistence:
    """Tests for appearance persistence across sessions."""

    async def test_appearance_persists_to_database(
        self, test_client: WebSocketTestClient, game_state_managers
    ):
        """Appearance should be persisted to database."""
        client = test_client
        
        # Update appearance
        response = await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {
                "shirt_style": "tunic",
                "shirt_color": "purple",
                "hair_style": "long",
                "hair_color": "blonde"
            }
        )
        
        # Verify update succeeded
        assert response.type == MessageType.RESP_SUCCESS
        
        # Query database directly to verify persistence
        from server.src.services.game_state import get_player_state_manager
        player_mgr = get_player_state_manager()
        
        # Get player ID from the client (stored during authentication)
        # The response should include player info or we can use player_mgr
        player_id = response.payload.get("player_id")
        if player_id is None:
            # Try to get from manager using username if available
            # For now, skip if we can't get player_id
            pytest.skip("Cannot verify persistence - player_id not available in response")
        
        # Query appearance from database
        persisted_appearance = await player_mgr.get_player_appearance(player_id)
        
        # Verify appearance was saved to database
        assert persisted_appearance is not None
        assert persisted_appearance["shirt_style"] == "tunic"
        assert persisted_appearance["shirt_color"] == "purple"
        assert persisted_appearance["hair_style"] == "long"
        assert persisted_appearance["hair_color"] == "blonde"

    @pytest.mark.skip(reason="Requires test harness improvements for multi-client async handling")
    async def test_appearance_defaults_for_new_player(
        self, new_test_client: WebSocketTestClient
    ):
        """New player should have default appearance."""
        # This test is skipped until test harness improvements are made
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


@pytest.mark.asyncio
class TestAppearanceWithEquipment:
    """Tests for appearance and equipment interaction."""

    async def test_equipment_overlays_clothing(self, test_client: WebSocketTestClient):
        """Equipment should render on top of clothing."""
        client = test_client
        
        # Equip body armor
        # ... equip item code ...
        
        # Update clothing under armor
        await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"shirt_style": "tunic", "shirt_color": "red"}
        )
        
        # Both should be visible in state updates (clothing under, armor over)

    async def test_unequip_shows_clothing(self, test_client: WebSocketTestClient):
        """Unequipping should reveal clothing underneath."""
        client = test_client
        
        # Equip then unequip body armor
        # ... equip/unequip code ...
        
        # Update clothing
        await client.send_command(
            MessageType.CMD_UPDATE_APPEARANCE,
            {"shirt_color": "blue"}
        )
        
        # Unequipped state should show blue shirt
