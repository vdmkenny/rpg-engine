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

from server.src.tests.websocket_test_utils import WebSocketTestClient, ErrorResponseError
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
        assert "total_stats" in equipment_data  # Equipment stats aggregated for player
        
        # Equipment slots should be a list
        slots = equipment_data["slots"]
        assert isinstance(slots, list)
        
        # All slot entries should have slot information
        for slot_data in slots:
            assert isinstance(slot_data, dict)
            assert "slot" in slot_data
            if slot_data.get("item") is not None:
                assert "item" in slot_data
    
    @pytest.mark.asyncio
    async def test_equipment_operations_with_correlation_ids(self, test_client):
        """Test equip/unequip operations error handling with proper correlation ID tracking"""
        client: WebSocketTestClient = test_client
        
        # Test equipment operation with correlation ID - should fail with empty inventory
        try:
            equip_response = await client.send_command(
                MessageType.CMD_ITEM_EQUIP,
                ItemEquipPayload(inventory_slot=0).model_dump()
            )
            pytest.fail("Expected ErrorResponseError when equipping from empty inventory slot")
        except ErrorResponseError as e:
            # Should get error response because inventory slot 0 is empty
            assert e.error_code
            assert e.error_message
            assert "empty" in e.error_message.lower() or "not" in e.error_message.lower()
            
            print("✅ Equipment operations with correlation IDs and proper error handling working correctly")
    
    @pytest.mark.asyncio
    async def test_equipment_error_handling(self, test_client):
        """Test equipment error handling with structured error codes"""
        client: WebSocketTestClient = test_client
        
        # Try to equip from invalid inventory slot
        try:
            error_response = await client.send_command(
                MessageType.CMD_ITEM_EQUIP,
                ItemEquipPayload(inventory_slot=999).model_dump()
            )
            pytest.fail("Expected ErrorResponseError when equipping from invalid inventory slot")
        except ErrorResponseError as e:
            # Should get error response
            assert e.error_code
            assert e.error_message
            
            # Should be equipment-related error
            assert e.error_code.startswith("EQ_") or e.error_code.startswith("INVENTORY_")
            
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
async def test_protocol_equipment_integration(test_client):
    """
    Integration test for complete equipment workflow.
    
    This test verifies the entire equipment system works with the protocol
    without any hanging issues, focusing on error handling and proper responses.
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
    
    # Step 2: Test equipping from empty inventory (should fail with proper error)
    try:
        equip_response = await client.send_command(
            MessageType.CMD_ITEM_EQUIP,
            ItemEquipPayload(inventory_slot=0).model_dump()
        )
        pytest.fail("Expected ErrorResponseError when equipping from empty inventory slot")
    except ErrorResponseError as e:
        # Should get error response because inventory is empty
        assert e.error_code
        assert e.error_message
        assert "empty" in e.error_message.lower() or "not" in e.error_message.lower()
        print("✅ Equipment error handling working correctly")
    
    # Add delay between equipment commands to avoid rate limiting
    await asyncio.sleep(0.6)
    
    # Step 3: Test equipping from invalid inventory slot (should fail with proper error)
    try:
        invalid_equip_response = await client.send_command(
            MessageType.CMD_ITEM_EQUIP,
            ItemEquipPayload(inventory_slot=999).model_dump()
        )
        pytest.fail("Expected ErrorResponseError when equipping from invalid inventory slot")
    except ErrorResponseError as e:
        # Should get error response for invalid slot
        assert e.error_code
        assert e.error_message
        print("✅ Invalid slot error handling working correctly")
    
    # Add delay between equipment commands to avoid rate limiting
    await asyncio.sleep(0.6)
    
    # Step 4: Test unequipping from empty equipment slot (should fail with proper error)
    try:
        unequip_response = await client.send_command(
            MessageType.CMD_ITEM_UNEQUIP,
            ItemUnequipPayload(equipment_slot="main_hand").model_dump()
        )
        pytest.fail("Expected ErrorResponseError when unequipping from empty equipment slot")
    except ErrorResponseError as e:
        # Should get error response because equipment slot is empty
        assert e.error_code
        assert e.error_message
        print("✅ Unequip error handling working correctly")
    
    # Step 5: Final equipment query to verify state consistency
    final_response = await client.send_query(
        MessageType.QUERY_EQUIPMENT,
        EquipmentQueryPayload().model_dump()
    )
    
    assert final_response.type == MessageType.RESP_DATA
    final_equipment = final_response.payload["equipment"]
    
    # Equipment should still be empty (no items were successfully equipped)
    # Check for slots where item is not None
    equipped_items = [
        slot_data for slot_data in final_equipment["slots"]
        if slot_data is not None and slot_data.get("item") is not None
    ]
    assert len(equipped_items) == 0, "Equipment should be empty after failed operations"
    
    print("✅ Complete equipment workflow successful - proper error handling verified, no hanging issues detected!")


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
    
    # Performance requirements (relaxed for Docker integration tests)
    assert avg_time < 0.2, f"Equipment queries too slow: {avg_time:.3f}s average"
    assert total_time < 3.0, f"Batch queries too slow: {total_time:.3f}s total"
    
    print("✅ Equipment query performance meets requirements")