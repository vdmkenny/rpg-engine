"""
Stress tests for concurrent operations to validate thread-safety improvements.

Tests the atomic operations we implemented in GSM.
"""

import asyncio
import pytest
import pytest_asyncio
import random


from server.src.core.items import EquipmentSlot
from server.src.services.game_state import (
    get_player_state_manager,
    get_inventory_manager,
    get_equipment_manager,
)


class TestConcurrencyStress:
    """Stress tests for concurrent operations."""


    
    @pytest.mark.asyncio
    async def test_concurrent_inventory_operations(self, create_test_player):
        """Test concurrent inventory operations don't cause data corruption."""
        # Create a test player
        player = await create_test_player("concurrency_inv_player", "testpass123")
        player_id = player.id
        
        # Get manager instances
        player_mgr = get_player_state_manager()
        inv_mgr = get_inventory_manager()
        
        # Register player as online so GSM operations work
        await player_mgr.register_online_player(player_id, "concurrency_inv_player")
        
        operations_completed = []
        
        async def concurrent_inventory_ops(operation_id: int):
            """Perform concurrent inventory operations."""
            for i in range(10):
                slot = (operation_id * 10 + i) % 28  # Keep within inventory bounds
                item_id = random.randint(1, 100)
                quantity = random.randint(1, 10)
                durability = 100.0
                
                # Perform actual GSM operations
                await inv_mgr.set_inventory_slot(player_id, slot, item_id, quantity, durability)
                
                # Occasionally delete the slot
                if i % 3 == 0:
                    await inv_mgr.delete_inventory_slot(player_id, slot)
            
            operations_completed.append(operation_id)
        
        # Run 5 concurrent tasks performing inventory operations
        tasks = [concurrent_inventory_ops(i) for i in range(5)]
        await asyncio.gather(*tasks)
        
        # Verify all operations completed without errors
        assert len(operations_completed) == 5
        
        # Cleanup
        await player_mgr.unregister_online_player(player_id)
    
    @pytest.mark.asyncio
    async def test_concurrent_equipment_operations(self, create_test_player):
        """Test concurrent equipment operations don't cause data corruption."""
        # Create a test player
        player = await create_test_player("concurrency_eq_player", "testpass123")
        player_id = player.id
        
        # Get manager instances
        player_mgr = get_player_state_manager()
        equip_mgr = get_equipment_manager()
        
        # Register player as online
        await player_mgr.register_online_player(player_id, "concurrency_eq_player")
        
        equipment_slots = [EquipmentSlot.HEAD, EquipmentSlot.BODY, EquipmentSlot.LEGS, EquipmentSlot.WEAPON, EquipmentSlot.SHIELD]
        operations_completed = []
        
        async def concurrent_equipment_ops(operation_id: int):
            """Perform concurrent equipment operations."""
            for i in range(20):
                slot = equipment_slots[i % len(equipment_slots)]
                slot_name = slot.value
                item_id = random.randint(1, 50)
                quantity = 1  # Equipment typically has quantity 1
                durability = 100.0
                
                # Perform actual GSM operations
                await equip_mgr.set_equipment_slot(player_id, slot_name, item_id, quantity, durability)
                
                # Occasionally unequip (delete)
                if i % 4 == 0:
                    await equip_mgr.delete_equipment_slot(player_id, slot_name)
            
            operations_completed.append(operation_id)
        
        # Run 3 concurrent tasks performing equipment operations
        tasks = [concurrent_equipment_ops(i) for i in range(3)]
        await asyncio.gather(*tasks)
        
        # Verify all operations completed without errors
        assert len(operations_completed) == 3
        
        # Cleanup
        await player_mgr.unregister_online_player(player_id)
    
    @pytest.mark.asyncio 
    async def test_concurrent_hp_operations(self, create_test_player):
        """Test concurrent HP update operations don't cause data corruption."""
        # Create a test player
        player = await create_test_player("concurrency_hp_player", "testpass123")
        player_id = player.id
        
        # Get manager instances
        player_mgr = get_player_state_manager()
        
        # Register player as online
        await player_mgr.register_online_player(player_id, "concurrency_hp_player")
        
        operations_completed = []
        
        async def concurrent_hp_ops(operation_id: int):
            """Perform concurrent HP update operations."""
            for i in range(50):
                current_hp = random.randint(1, 100)
                max_hp = random.randint(current_hp, 150)
                
                # Perform actual GSM HP update
                await player_mgr.set_player_hp(player_id, current_hp, max_hp)
            
            operations_completed.append(operation_id)
        
        # Run 4 concurrent tasks performing HP operations
        tasks = [concurrent_hp_ops(i) for i in range(4)]
        await asyncio.gather(*tasks)
        
        # Verify all operations completed without errors
        assert len(operations_completed) == 4
        
        # Cleanup
        await player_mgr.unregister_online_player(player_id)
