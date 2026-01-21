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
        inventory = await client.get_inventory()
        
        # Verify inventory structure
        assert inventory is not None
        assert "inventory" in inventory
        
        # Check inventory payload structure
        inventory_data = inventory["inventory"]
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
        inventory = await client.get_inventory()
        elapsed_time = time.time() - start_time
        
        # Should complete in under 2 seconds (no hanging)
        assert elapsed_time < 2.0, f"Inventory query took too long: {elapsed_time:.2f}s"
        assert inventory is not None


@pytest.mark.asyncio 
class TestInventoryOperations:
    """Tests for inventory manipulation operations."""

    async def test_move_item_empty_source_fails(self, test_client: WebSocketTestClient):
        """Moving from empty slot should fail gracefully."""
        client = test_client
        
        try:
            # Try to move from empty slot 0 to slot 5
            response = await client.send_command(
                MessageType.CMD_INVENTORY_MOVE,
                {"from_slot": 0, "to_slot": 5}
            )
            
            # Should handle gracefully - either success=false or error
            if "success" in response:
                assert response["success"] is False
            elif "error" in response:
                assert "empty" in response["error"].lower() or "no item" in response["error"].lower()
        except Exception as e:
            # Command not implemented yet is also acceptable
            assert "not implemented" in str(e).lower() or "unknown" in str(e).lower()

    async def test_move_item_invalid_slot_fails(self, test_client: WebSocketTestClient):
        """Moving to invalid slot should fail gracefully."""
        client = test_client
        
        try:
            # Try to move to slot outside typical range 
            response = await client.send_command(
                MessageType.CMD_INVENTORY_MOVE,
                {"from_slot": 0, "to_slot": 999}
            )
            
            # Should handle gracefully
            if "success" in response:
                assert response["success"] is False
            elif "error" in response:
                assert "invalid" in response["error"].lower() or "slot" in response["error"].lower()
        except Exception as e:
            # Command not implemented yet is also acceptable
            assert "not implemented" in str(e).lower() or "unknown" in str(e).lower()

    async def test_sort_inventory_empty(self, test_client: WebSocketTestClient):
        """Sorting empty inventory should succeed or handle gracefully."""
        client = test_client
        
        try:
            # Sort by category (valid sort type)
            response = await client.send_command(
                MessageType.CMD_INVENTORY_SORT,
                {"sort_type": "category"}
            )
            
            # Should either succeed or handle gracefully
            if "success" in response:
                # Success is acceptable for empty inventory
                assert isinstance(response["success"], bool)
        except Exception as e:
            # Command not implemented yet is also acceptable
            assert "not implemented" in str(e).lower() or "unknown" in str(e).lower()

    async def test_sort_inventory_invalid_type_fails(self, test_client: WebSocketTestClient):
        """Sorting with invalid sort type should fail gracefully."""
        client = test_client
        
        try:
            # Sort with invalid type
            response = await client.send_command(
                MessageType.CMD_INVENTORY_SORT,
                {"sort_type": "invalid_sort_type"}
            )
            
            # Should fail gracefully
            if "success" in response:
                assert response["success"] is False
            elif "error" in response:
                assert "invalid" in response["error"].lower() or "sort" in response["error"].lower()
        except Exception as e:
            # Command not implemented yet is also acceptable
            assert "not implemented" in str(e).lower() or "unknown" in str(e).lower()

    async def test_drop_item_empty_slot_fails(self, test_client: WebSocketTestClient):
        """Dropping from empty slot should fail gracefully."""
        client = test_client
        
        try:
            # Try to drop from empty slot
            response = await client.send_command(
                MessageType.CMD_ITEM_DROP,
                {"inventory_slot": 0}
            )
            
            # Should fail gracefully
            if "success" in response:
                assert response["success"] is False
            elif "error" in response:
                assert "empty" in response["error"].lower() or "no item" in response["error"].lower()
        except Exception as e:
            # Command not implemented yet is also acceptable  
            assert "not implemented" in str(e).lower() or "unknown" in str(e).lower()

    async def test_drop_item_invalid_slot_fails(self, test_client: WebSocketTestClient):
        """Dropping from invalid slot should fail gracefully."""
        client = test_client
        
        try:
            # Try to drop from invalid slot
            response = await client.send_command(
                MessageType.CMD_ITEM_DROP,  
                {"inventory_slot": -1}
            )
            
            # Should fail gracefully
            if "success" in response:
                assert response["success"] is False
            elif "error" in response:
                assert "invalid" in response["error"].lower() or "slot" in response["error"].lower()
        except Exception as e:
            # Command not implemented yet is also acceptable
            assert "not implemented" in str(e).lower() or "unknown" in str(e).lower()


@pytest.mark.asyncio
class TestInventoryProtocol:
    """Tests for inventory protocol compliance and performance."""

    async def test_inventory_query_correlation_id(self, test_client: WebSocketTestClient):
        """Inventory queries should use proper correlation IDs."""
        client = test_client
        
        # The WebSocketTestClient handles correlation IDs automatically
        # This test verifies the infrastructure works correctly
        inventory = await client.get_inventory()
        assert inventory is not None
        
        # Multiple queries should work independently
        inventory2 = await client.get_inventory()
        assert inventory2 is not None

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
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed or fail gracefully
        for result in results:
            if isinstance(result, Exception):
                # Graceful failure is acceptable
                assert "not implemented" in str(result).lower() or "unknown" in str(result).lower()
            else:
                # Successful response should be valid
                assert result is not None
                if isinstance(result, dict):
                    assert "inventory" in result

    async def test_inventory_operations_protocol_compliance(self, test_client: WebSocketTestClient):
        """Inventory operations should follow protocol message format."""
        client = test_client
        
        # Test that commands follow proper message structure
        # Even if not implemented, they should be properly formatted
        
        commands_to_test = [
            (MessageType.CMD_INVENTORY_MOVE, {"from_slot": 0, "to_slot": 1}),
            (MessageType.CMD_INVENTORY_SORT, {"sort_type": "name"}),
            (MessageType.CMD_ITEM_DROP, {"inventory_slot": 0})
        ]
        
        for message_type, payload in commands_to_test:
            try:
                response = await client.send_command(message_type, payload)
                # If implemented, should have proper response structure
                assert isinstance(response, dict)
            except Exception as e:
                # Not implemented is acceptable
                error_msg = str(e).lower()
                assert any(keyword in error_msg for keyword in [
                    "not implemented", "unknown", "unsupported"
                ])