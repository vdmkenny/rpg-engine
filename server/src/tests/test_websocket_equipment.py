"""
WebSocket Equipment Tests

Tests equipment operations using the WebSocket protocol with:
- Correlation ID support for request/response pairing
- Message patterns (QUERY_EQUIPMENT → RESP_DATA)
- Structured error handling
- Reliable equipment request handling

This ensures equipment queries complete reliably without hanging.
"""

import asyncio
import pytest
import time
from typing import Dict, Any, Optional

from server.src.tests.websocket_test_utils import WebSocketTestClient
from common.src.protocol import (
    WSMessage,
    MessageType,
    EquipmentQueryPayload,
    ItemEquipPayload,
    ItemUnequipPayload,
)


class TestEquipmentWebSocket:
    """Test equipment operations via WebSocket"""
    
    @pytest.mark.asyncio
    async def test_equipment_query_no_hanging(self, test_client):
        """
        Test that equipment queries return immediately with correlation ID.
        
        This is the critical test that verifies the hanging issue is fixed.
        """
        client: WebSocketTestClient = test_client
        
        # Query equipment - should return immediately
        start_time = time.time()
        
        response = await client.send_query(
            MessageType.QUERY_EQUIPMENT,
            EquipmentQueryPayload().model_dump(),
            timeout=5.0  # Should complete in under 1 second
        )
        
        elapsed_time = time.time() - start_time
        
        # Verify response received quickly (not hanging)
        assert elapsed_time < 2.0, f"Equipment query took too long: {elapsed_time:.2f}s"
        
        # Verify correct response type
        assert response.type == MessageType.RESP_DATA
        assert "equipment" in response.payload
        assert "query_type" in response.payload
        assert response.payload["query_type"] == "equipment"
        
        print(f"✅ Equipment query completed in {elapsed_time:.3f}s (no hanging)")
    
    @pytest.mark.asyncio
    async def test_equipment_query_structure(self, test_client):
        """Test equipment query response structure"""
        client: WebSocketTestClient = test_client
        
        response = await client.send_query(
            MessageType.QUERY_EQUIPMENT,
            EquipmentQueryPayload().model_dump()
        )
        
        # Verify response structure
        assert response.type == MessageType.RESP_DATA
        equipment_data = response.payload["equipment"]
        
        # Should have equipment structure
        assert "slots" in equipment_data
        assert "stats" in equipment_data
        
        # Equipment slots should be a dictionary
        slots = equipment_data["slots"]
        assert isinstance(slots, dict)
        
        # All slot values should be None (empty) or item data
        for slot_name, slot_data in slots.items():
            if slot_data is not None:
                assert isinstance(slot_data, dict)
                assert "item_id" in slot_data
    
    @pytest.mark.asyncio
    async def test_equipment_operations_with_correlation_ids(self, test_client, test_item_id):
        """Test equip/unequip operations with proper correlation ID tracking"""
        client: WebSocketTestClient = test_client
        
        # First add an item to inventory (using old method for setup)
        await client.add_test_item_to_inventory(test_item_id, slot=0)
        
        # Test equipment operation with correlation ID
        equip_response = await client.send_command(
            MessageType.CMD_ITEM_EQUIP,
            ItemEquipPayload(inventory_slot=0).model_dump()
        )
        
        # Should get success response
        assert equip_response.type == MessageType.RESP_SUCCESS
        assert equip_response.id is not None  # Has correlation ID
        
        # Wait for state update event
        state_update = await client.wait_for_event(MessageType.EVENT_STATE_UPDATE, timeout=3.0)
        assert state_update is not None
        assert "equipment" in state_update.payload.get("systems", {})
        assert "inventory" in state_update.payload.get("systems", {})
        assert "stats" in state_update.payload.get("systems", {})
        
        # Query equipment again to verify item is equipped
        equipment_response = await client.send_query(
            MessageType.QUERY_EQUIPMENT,
            EquipmentQueryPayload().model_dump()
        )
        
        equipment_data = equipment_response.payload["equipment"]
        slots = equipment_data["slots"]
        
        # Should find the item in one of the equipment slots
        equipped_item_found = False
        for slot_data in slots.values():
            if slot_data and slot_data.get("item_id") == test_item_id:
                equipped_item_found = True
                break
        
        assert equipped_item_found, f"Item {test_item_id} not found in equipment slots"
        
        print("✅ Equipment operations with correlation IDs working correctly")
    
    @pytest.mark.asyncio
    async def test_equipment_error_handling(self, test_client):
        """Test equipment error handling with structured error codes"""
        client: WebSocketTestClient = test_client
        
        # Try to equip from invalid inventory slot
        error_response = await client.send_command(
            MessageType.CMD_ITEM_EQUIP,
            ItemEquipPayload(inventory_slot=999).model_dump()
        )
        
        # Should get error response
        assert error_response.type == MessageType.RESP_ERROR
        assert error_response.id is not None  # Has correlation ID
        
        # Check error structure
        error_payload = error_response.payload
        assert "error_code" in error_payload
        assert "error_category" in error_payload
        assert "message" in error_payload
        
        # Should be equipment-related error
        assert error_payload["error_code"].startswith("EQUIPMENT_") or error_payload["error_code"].startswith("INVENTORY_")
        
        print("✅ Equipment error handling with structured responses working correctly")
    
    @pytest.mark.asyncio
    async def test_multiple_equipment_queries_no_interference(self, test_client):
        """Test multiple rapid equipment queries don't interfere with each other"""
        client: WebSocketTestClient = test_client
        
        # Send multiple queries rapidly
        query_count = 5
        query_tasks = []
        
        for i in range(query_count):
            task = client.send_query(
                MessageType.QUERY_EQUIPMENT,
                EquipmentQueryPayload().model_dump(),
                timeout=5.0
            )
            query_tasks.append(task)
        
        # Wait for all responses
        start_time = time.time()
        responses = await asyncio.gather(*query_tasks)
        elapsed_time = time.time() - start_time
        
        # All queries should complete quickly
        assert elapsed_time < 3.0, f"Multiple queries took too long: {elapsed_time:.2f}s"
        
        # All responses should be valid
        assert len(responses) == query_count
        for response in responses:
            assert response.type == MessageType.RESP_DATA
            assert "equipment" in response.payload
            assert "query_type" in response.payload
            assert response.payload["query_type"] == "equipment"
        
        print(f"✅ {query_count} equipment queries completed in {elapsed_time:.3f}s (no interference)")
    
    @pytest.mark.asyncio 
    async def test_equipment_query_timeout_protection(self, test_client):
        """Test that equipment queries have timeout protection"""
        client: WebSocketTestClient = test_client
        
        # Send query with short timeout to verify it doesn't hang indefinitely
        start_time = time.time()
        
        try:
            response = await client.send_query(
                MessageType.QUERY_EQUIPMENT,
                EquipmentQueryPayload().model_dump(),
                timeout=1.0  # Very short timeout
            )
            
            elapsed_time = time.time() - start_time
            
            # Should complete within timeout
            assert elapsed_time < 1.0, f"Query should complete quickly: {elapsed_time:.3f}s"
            assert response.type == MessageType.RESP_DATA
            
        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            pytest.fail(f"Equipment query timed out after {elapsed_time:.3f}s - hanging issue not fixed!")
        
        print("✅ Equipment query timeout protection working correctly")


@pytest.mark.asyncio
async def test_protocol_equipment_integration(test_client, test_item_id):
    """
    Integration test for complete equipment workflow.
    
    This test verifies the entire equipment system works with the protocol
    without any hanging issues.
    """
    client: WebSocketTestClient = test_client
    
    print("🔧 Testing complete equipment workflow...")
    
    # Step 1: Query initial equipment (should be empty)
    initial_response = await client.send_query(
        MessageType.QUERY_EQUIPMENT,
        EquipmentQueryPayload().model_dump()
    )
    
    assert initial_response.type == MessageType.RESP_DATA
    initial_equipment = initial_response.payload["equipment"]
    print(f"✅ Initial equipment query: {len(initial_equipment['slots'])} slots")
    
    # Step 2: Add item to inventory for testing
    await client.add_test_item_to_inventory(test_item_id, slot=0)
    print(f"✅ Added test item {test_item_id} to inventory")
    
    # Step 3: Equip the item
    equip_response = await client.send_command(
        MessageType.CMD_ITEM_EQUIP,
        ItemEquipPayload(inventory_slot=0).model_dump()
    )
    
    assert equip_response.type == MessageType.RESP_SUCCESS
    print("✅ Item equipped successfully")
    
    # Step 4: Wait for equipment state update
    state_update = await client.wait_for_event(MessageType.EVENT_STATE_UPDATE, timeout=3.0)
    assert state_update is not None
    assert "equipment" in state_update.payload.get("systems", {})
    print("✅ Equipment state update received")
    
    # Step 5: Query equipment again to verify
    final_response = await client.send_query(
        MessageType.QUERY_EQUIPMENT,
        EquipmentQueryPayload().model_dump()
    )
    
    assert final_response.type == MessageType.RESP_DATA
    final_equipment = final_response.payload["equipment"]
    
    # Verify item is equipped
    equipped_items = [
        slot_data for slot_data in final_equipment["slots"].values()
        if slot_data is not None
    ]
    assert len(equipped_items) > 0, "No items found in equipment after equipping"
    
    equipped_item = equipped_items[0]
    assert equipped_item["item_id"] == test_item_id
    print(f"✅ Item {test_item_id} verified in equipment")
    
    # Step 6: Test unequip
    equipment_slot = None
    for slot_name, slot_data in final_equipment["slots"].items():
        if slot_data and slot_data["item_id"] == test_item_id:
            equipment_slot = slot_name
            break
    
    assert equipment_slot is not None
    
    unequip_response = await client.send_command(
        MessageType.CMD_ITEM_UNEQUIP,
        ItemUnequipPayload(equipment_slot=equipment_slot).model_dump()
    )
    
    assert unequip_response.type == MessageType.RESP_SUCCESS
    print("✅ Item unequipped successfully")
    
    # Step 7: Final equipment query to verify unequip
    final_check_response = await client.send_query(
        MessageType.QUERY_EQUIPMENT,
        EquipmentQueryPayload().model_dump()
    )
    
    assert final_check_response.type == MessageType.RESP_DATA
    final_check_equipment = final_check_response.payload["equipment"]
    
    # Verify item is no longer equipped
    remaining_items = [
        slot_data for slot_data in final_check_equipment["slots"].values()
        if slot_data is not None and slot_data.get("item_id") == test_item_id
    ]
    assert len(remaining_items) == 0, f"Item {test_item_id} still found in equipment after unequipping"
    
    print("✅ Complete equipment workflow successful - no hanging issues detected!")


# Test timing benchmarks
@pytest.mark.asyncio
async def test_equipment_query_performance_benchmark(test_client):
    """Benchmark equipment query performance to ensure no regression"""
    client: WebSocketTestClient = test_client
    
    # Warm up
    await client.send_query(MessageType.QUERY_EQUIPMENT, {})
    
    # Benchmark multiple queries
    query_count = 10
    start_time = time.time()
    
    for _ in range(query_count):
        response = await client.send_query(MessageType.QUERY_EQUIPMENT, {})
        assert response.type == MessageType.RESP_DATA
    
    total_time = time.time() - start_time
    avg_time = total_time / query_count
    
    print(f"🚀 Equipment query performance: {avg_time:.3f}s avg ({query_count} queries in {total_time:.3f}s)")
    
    # Performance requirements
    assert avg_time < 0.1, f"Equipment queries too slow: {avg_time:.3f}s average"
    assert total_time < 2.0, f"Batch queries too slow: {total_time:.3f}s total"
    
    print("✅ Equipment query performance meets requirements")