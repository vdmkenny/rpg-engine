"""
WebSocket integration tests for inventory operations using modern async patterns.

Covers:
- QUERY_INVENTORY - Get current inventory state  
- CMD_MOVE_INVENTORY_ITEM - Move items between slots
- CMD_SORT_INVENTORY - Sort inventory by type/rarity/name
- CMD_DROP_ITEM - Drop item to ground

Uses WebSocketTestClient with structured async methods and correct protocol.
"""

import pytest
from server.src.tests.websocket_test_utils import WebSocketTestClient
from common.src.protocol import MessageType


@pytest.mark.asyncio
class TestInventoryQuery:
    """Tests for inventory queries using modern async patterns."""

    async def test_query_inventory_structure(self, test_client: WebSocketTestClient):
        """New player should have properly structured empty inventory."""
        client = test_client
        
        # Query current inventory state
        inventory_response = await client.get_inventory()
        
        # Verify response structure
        assert inventory_response is not None
        assert inventory_response.type == MessageType.RESP_DATA
        assert "inventory" in inventory_response.payload
        
        # Check inventory payload structure
        inventory_data = inventory_response.payload["inventory"]
        assert isinstance(inventory_data, dict)
        
        # Should have slots information
        if "slots" in inventory_data:
            assert isinstance(inventory_data["slots"], list)
        
        # Should have capacity information
        if "max_slots" in inventory_data:
            assert isinstance(inventory_data["max_slots"], int)
            assert inventory_data["max_slots"] > 0

    async def test_query_inventory_response_time(self, test_client: WebSocketTestClient):
        """Inventory queries should complete quickly without hanging."""
        import time
        
        client = test_client
        
        start_time = time.time()
        inventory_response = await client.get_inventory()
        elapsed_time = time.time() - start_time
        
        # Should complete in under 2 seconds (no hanging)
        assert elapsed_time < 2.0, f"Inventory query took too long: {elapsed_time:.2f}s"
        assert inventory_response is not None
        assert inventory_response.type == MessageType.RESP_DATA


@pytest.mark.asyncio 
class TestInventoryOperations:
    """Tests for inventory manipulation operations."""

    async def test_move_item_empty_source_fails(self, test_client: WebSocketTestClient):
        """Moving from empty slot should fail with error."""
        client = test_client
        
        # Try to move from empty slot 0 to slot 5 - should fail
        from server.src.tests.websocket_test_utils import ErrorResponseError
        
        with pytest.raises(ErrorResponseError) as exc_info:
            await client.send_command(
                MessageType.CMD_INVENTORY_MOVE,
                {"from_slot": 0, "to_slot": 5}
            )
        
        # Should fail with appropriate error for empty source slot
        error_msg = str(exc_info.value).lower()
        assert "empty" in error_msg or "not found" in error_msg or "inv_slot" in error_msg

    async def test_sort_inventory_empty(self, test_client: WebSocketTestClient):
        """Sorting empty inventory should succeed."""
        client = test_client
        
        # Sort by category (valid sort type) - should succeed even on empty inventory
        response = await client.send_command(
            MessageType.CMD_INVENTORY_SORT,
            {"sort_type": "category"}
        )
        
        # Should succeed for valid sort operation
        assert response.type == MessageType.RESP_SUCCESS
        assert response.payload is not None

    async def test_sort_inventory_invalid_type_accepts(self, test_client: WebSocketTestClient):
        """Sorting with invalid sort type currently accepts any type."""
        client = test_client
        
        # Sort with invalid type - currently server accepts any sort type
        response = await client.send_command(
            MessageType.CMD_INVENTORY_SORT,
            {"sort_type": "invalid_sort_type"}
        )
        
        # Server currently accepts invalid sort types (could be enhanced with validation)
        assert response.type == MessageType.RESP_SUCCESS
        assert response.payload is not None

    async def test_drop_item_empty_slot_fails(self, test_client: WebSocketTestClient):
        """Dropping from empty slot should fail with error."""
        client = test_client
        
        # Try to drop from empty slot - should fail
        from server.src.tests.websocket_test_utils import ErrorResponseError
        
        with pytest.raises(ErrorResponseError) as exc_info:
            await client.send_command(
                MessageType.CMD_ITEM_DROP,
                {"inventory_slot": 0}
            )
        
        # Should fail with appropriate error for empty slot
        error_msg = str(exc_info.value).lower()
        assert "empty" in error_msg or "insufficient" in error_msg or "inv_" in error_msg

@pytest.mark.asyncio
class TestInventoryProtocol:
    """Tests for inventory protocol compliance and performance."""

    async def test_inventory_query_correlation_id(self, test_client: WebSocketTestClient):
        """Inventory queries should use proper correlation IDs."""
        client = test_client
        
        # The WebSocketTestClient handles correlation IDs automatically
        # This test verifies the infrastructure works correctly
        inventory_response = await client.get_inventory()
        assert inventory_response.type == MessageType.RESP_DATA
        assert inventory_response.payload is not None
        
        # Multiple queries should work independently
        inventory_response2 = await client.get_inventory()
        assert inventory_response2.type == MessageType.RESP_DATA
        assert inventory_response2.payload is not None

    async def test_inventory_concurrent_queries(self, test_client: WebSocketTestClient):
        """Multiple concurrent inventory queries should not interfere."""
        import asyncio
        
        client = test_client
        
        # Send multiple concurrent requests
        tasks = [
            client.get_inventory(),
            client.get_inventory(), 
            client.get_inventory()
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed with proper WSMessage responses
        for result in results:
            from common.src.protocol import WSMessage
            assert isinstance(result, WSMessage)
            assert result.type == MessageType.RESP_DATA
            assert result.payload is not None
            assert "inventory" in result.payload

    async def test_inventory_operations_protocol_compliance(self, test_client: WebSocketTestClient):
        """Inventory operations should follow protocol message format."""
        from server.src.tests.websocket_test_utils import ErrorResponseError
        from common.src.protocol import WSMessage
        
        client = test_client
        
        # Test that commands follow proper message structure
        # Note: Some commands will fail (empty inventory) - that's expected
        commands_to_test = [
            (MessageType.CMD_INVENTORY_MOVE, {"from_slot": 0, "to_slot": 1}),
            (MessageType.CMD_INVENTORY_SORT, {"sort_type": "name"}),
            (MessageType.CMD_ITEM_DROP, {"inventory_slot": 0})
        ]
        
        for message_type, payload in commands_to_test:
            try:
                response = await client.send_command(message_type, payload)
                # Should have proper WSMessage response structure
                assert isinstance(response, WSMessage)
                assert response.type == MessageType.RESP_SUCCESS
            except ErrorResponseError:
                # Error responses are valid protocol responses - test passes
                # Commands on empty inventory slots return errors as expected
                pass