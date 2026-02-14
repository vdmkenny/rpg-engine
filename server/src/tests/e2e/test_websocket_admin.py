"""
WebSocket integration tests for admin commands.

Covers:
- Admin give command (granting items to players)
- Permission checks (non-admins get denied)
- Error handling (item not found, player not found, inventory full)
- Success responses and player inventory updates

These tests use the test database and WebSocket handlers.
"""

import pytest
import pytest_asyncio
import asyncio

from common.src.protocol import MessageType, AdminGivePayload
from server.src.tests.websocket_test_utils import WebSocketTestClient, ErrorResponseError


@pytest.mark.integration
class TestAdminGive:
    """Tests for admin give command functionality."""

    @pytest.mark.asyncio
    async def test_admin_give_item_to_self(self, test_client: WebSocketTestClient):
        """Admin should be able to give items to themselves."""
        # Wait a bit before sending
        await asyncio.sleep(0.1)
        
        # Send admin give command to self
        response = await test_client.send_command(
            MessageType.CMD_ADMIN_GIVE,
            AdminGivePayload(
                target_username=test_client.username,
                item_name="bronze_shortsword",
                quantity=1
            ).model_dump()
        )
        
        # Should succeed
        assert response.type == MessageType.RESP_SUCCESS
        assert response.payload is not None
        assert response.payload.get("target_username") == test_client.username
        assert response.payload.get("item_name") == "bronze_shortsword"
        assert response.payload.get("quantity") == 1

    @pytest.mark.asyncio
    async def test_admin_give_multiple_items(self, test_client: WebSocketTestClient):
        """Admin should be able to give multiple items of same type."""
        # Wait a bit before sending
        await asyncio.sleep(0.1)
        
        # Send admin give command with quantity > 1
        response = await test_client.send_command(
            MessageType.CMD_ADMIN_GIVE,
            AdminGivePayload(
                target_username=test_client.username,
                item_name="gold_coin",
                quantity=5
            ).model_dump()
        )
        
        # Should succeed
        assert response.type == MessageType.RESP_SUCCESS
        assert response.payload is not None
        assert response.payload.get("quantity") == 5

    @pytest.mark.asyncio
    async def test_admin_give_item_not_found(self, test_client: WebSocketTestClient):
        """Admin give should fail with item not found error."""
        # Wait a bit before sending
        await asyncio.sleep(0.1)
        
        # Send admin give command with non-existent item
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_ADMIN_GIVE,
                AdminGivePayload(
                    target_username=test_client.username,
                    item_name="nonexistent_item",
                    quantity=1
                ).model_dump()
            )
        
        # Verify it's the correct error
        assert exc_info.value.error_code == "admin_item_not_found"
        assert "not found" in exc_info.value.error_message.lower()

    @pytest.mark.asyncio
    async def test_admin_give_player_not_found(self, test_client: WebSocketTestClient):
        """Admin give should fail with player not found error."""
        # Wait a bit before sending
        await asyncio.sleep(0.1)
        
        # Send admin give command with non-existent target player
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_ADMIN_GIVE,
                AdminGivePayload(
                    target_username="nonexistent_player_xyz",  # Non-existent username
                    item_name="bronze_shortsword",
                    quantity=1
                ).model_dump()
            )
        
        # Verify it's the correct error
        assert exc_info.value.error_code == "admin_player_not_found"
        assert "not found" in exc_info.value.error_message.lower()

    @pytest.mark.asyncio
    async def test_admin_give_invalid_quantity(self, test_client: WebSocketTestClient):
        """Admin give should fail with invalid quantity error."""
        # Wait a bit before sending
        await asyncio.sleep(0.1)
        
        # Send admin give command with invalid quantity
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_ADMIN_GIVE,
                AdminGivePayload(
                    target_username=test_client.username,
                    item_name="bronze_shortsword",
                    quantity=0  # Invalid quantity
                ).model_dump()
            )
        
        # Verify it's the correct error
        assert exc_info.value.error_code == "admin_invalid_quantity"
        assert "invalid" in exc_info.value.error_message.lower() or "quantity" in exc_info.value.error_message.lower()


@pytest.mark.integration
class TestAdminGivePermissions:
    """Tests for admin give permission checks."""

    @pytest.mark.asyncio
    async def test_non_admin_cannot_give_items(self, test_client_regular: WebSocketTestClient):
        """Non-admin players should get permission denied when trying to use admin give."""
        # Wait a bit before sending
        await asyncio.sleep(0.1)
        
        # Send admin give command as non-admin (should be denied)
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client_regular.send_command(
                MessageType.CMD_ADMIN_GIVE,
                AdminGivePayload(
                    target_username=test_client_regular.username,
                    item_name="bronze_shortsword",
                    quantity=1
                ).model_dump()
            )
        
        # Verify it's a permission denied error
        assert exc_info.value.error_code == "admin_not_authorized"
        assert "admin" in exc_info.value.error_message.lower() or "permission" in exc_info.value.error_message.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_give_updates_inventory(test_client: WebSocketTestClient):
    """Admin give should update the target player's inventory."""
    # Wait a bit before sending
    await asyncio.sleep(0.1)
    
    # Query initial inventory
    initial_inventory = await test_client.send_query(
        MessageType.QUERY_INVENTORY,
        {}
    )
    
    initial_count = len(initial_inventory.payload.get("inventory", []))
    
    # Wait a bit
    await asyncio.sleep(0.1)
    
    # Give item via admin give command
    give_response = await test_client.send_command(
        MessageType.CMD_ADMIN_GIVE,
        AdminGivePayload(
            target_username=test_client.username,
            item_name="bronze_shortsword",
            quantity=1
        ).model_dump()
    )
    
    assert give_response.type == MessageType.RESP_SUCCESS
    
    # Wait a bit
    await asyncio.sleep(0.1)
    
    # Query updated inventory
    updated_inventory = await test_client.send_query(
        MessageType.QUERY_INVENTORY,
        {}
    )
    
    updated_count = len(updated_inventory.payload.get("inventory", []))
    
    # Should have one more item
    assert updated_count == initial_count + 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_give_fills_inventory(test_client: WebSocketTestClient):
    """Admin give should fail when player inventory is full."""
    # Fill the inventory first by giving many items
    max_inventory_slots = 20  # Standard inventory size
    
    # Give items until inventory is full
    for i in range(max_inventory_slots):
        await asyncio.sleep(0.05)  # Small delay between gives
        
        response = await test_client.send_command(
            MessageType.CMD_ADMIN_GIVE,
            AdminGivePayload(
                target_username=test_client.username,
                item_name="gold_coin",
                quantity=1
            ).model_dump()
        )
        
        # Most should succeed, but we might hit the limit
        if response.type == MessageType.RESP_ERROR:
            # Inventory is full
            break
    
    # Wait a bit
    await asyncio.sleep(0.1)
    
    # Try to give one more item (should fail with inventory full)
    with pytest.raises(ErrorResponseError) as exc_info:
        await test_client.send_command(
            MessageType.CMD_ADMIN_GIVE,
            AdminGivePayload(
                target_username=test_client.username,
                item_name="gold_coin",
                quantity=1
            ).model_dump()
        )
    
    # Verify it's the correct error
    assert exc_info.value.error_code == "admin_inventory_full"
    assert "inventory" in exc_info.value.error_message.lower() or "full" in exc_info.value.error_message.lower()
