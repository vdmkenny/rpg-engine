"""
Race condition detection tests for multiplayer scenarios.

These tests specifically target race conditions that could occur in real multiplayer 
gameplay and validate that our atomic operations prevent data corruption.
"""
import asyncio
import random
import pytest

from server.src.models.player import Player
from server.src.core.security import get_password_hash
from server.src.core.items import EquipmentSlot
from server.src.services.game_state import (
    get_player_state_manager,
    get_inventory_manager,
    get_equipment_manager,
)


@pytest.mark.asyncio
class TestRaceConditionDetection:
    """Test specific race conditions that could occur in multiplayer gameplay."""

    async def test_concurrent_equipment_swap_race(self, session, game_state_managers):
        """Test race condition when multiple operations try to equip/unequip same slot."""
        # Create test player
        player_data = {
            "username": "race_player2",
            "hashed_password": get_password_hash("testpass"),
            "map_id": "samplemap",
            "x": 25,
            "y": 25
        }
        player = Player(**player_data)
        session.add(player)
        await session.commit()
        await session.refresh(player)
        player_id = player.id
        
        # Get manager instances
        player_mgr = get_player_state_manager()
        inv_mgr = get_inventory_manager()
        equip_mgr = get_equipment_manager()
        
        await player_mgr.register_online_player(player_id, "race_player2")
        
        # Pre-populate inventory with items to equip
        for slot in range(5):
            await inv_mgr.set_inventory_slot(player_id, slot, 200 + slot, 1, 1.0)
        
        equipment_slot = EquipmentSlot.WEAPON
        slot_name = equipment_slot.value
        operations_results = []

        async def equipment_swap_operation(operation_id: int):
            """Simulate rapid equipment swapping operations."""
            try:
                item_id = 200 + (operation_id % 5)  # Cycle through available items
                
                if operation_id % 2 == 0:
                    # Even operations: equip an item
                    await equip_mgr.set_equipment_slot(player_id, slot_name, item_id, 1, 0.9)
                    operation_type = "equip"
                else:
                    # Odd operations: unequip
                    await equip_mgr.delete_equipment_slot(player_id, slot_name)
                    operation_type = "unequip"
                
                # Check final state
                equipment = await equip_mgr.get_equipment(player_id)
                equipped_item = equipment.get(slot_name, {}).get('item_id')
                
                operations_results.append({
                    'operation_id': operation_id,
                    'operation_type': operation_type,
                    'attempted_item_id': item_id if operation_type == "equip" else None,
                    'final_equipped_item': equipped_item
                })
                
            except Exception as e:
                operations_results.append({
                    'operation_id': operation_id,
                    'error': str(e)
                })

        # Launch 20 concurrent equip/unequip operations
        tasks = [equipment_swap_operation(i) for i in range(20)]
        await asyncio.gather(*tasks)
        
        # Verify no data corruption
        assert len(operations_results) == 20
        
        # Check final equipment state is valid
        final_equipment = await equip_mgr.get_equipment(player_id)
        
        # Equipment slot should either be empty or contain a valid item
        if slot_name in final_equipment:
            equipped_item_id = final_equipment[slot_name]['item_id']
            assert equipped_item_id in range(200, 205)  # Valid item range
        
        # No operations should have failed due to race conditions
        failed_operations = [r for r in operations_results if 'error' in r]
        assert len(failed_operations) == 0

    async def test_concurrent_hp_updates_during_combat(self, session, game_state_managers):
        """Test race condition during rapid HP updates (simulating combat)."""
        # Create test player
        player_data = {
            "username": "race_player3",
            "hashed_password": get_password_hash("testpass"),
            "map_id": "samplemap",
            "x": 25,
            "y": 25
        }
        player = Player(**player_data)
        session.add(player)
        await session.commit()
        await session.refresh(player)
        player_id = player.id
        
        # Get manager instances
        player_mgr = get_player_state_manager()
        
        await player_mgr.register_online_player(player_id, "race_player3")
        
        # Set initial HP
        initial_hp = 100
        max_hp = 100
        await player_mgr.set_player_hp(player_id, initial_hp, max_hp)
        
        hp_changes = []
        
        async def damage_healing_operation(operation_id: int):
            """Simulate rapid damage and healing during combat."""
            try:
                # Get current HP
                hp_data = await player_mgr.get_player_hp(player_id)
                current_hp = hp_data['current_hp'] if hp_data else initial_hp
                
                if operation_id % 2 == 0:
                    # Even operations: take damage
                    damage = random.randint(5, 15)
                    new_hp = max(0, current_hp - damage)
                    operation_type = "damage"
                    amount = -damage
                else:
                    # Odd operations: heal
                    healing = random.randint(3, 10)
                    new_hp = min(max_hp, current_hp + healing)
                    operation_type = "heal"
                    amount = healing
                
                # Apply the HP change
                await player_mgr.set_player_hp(player_id, new_hp, max_hp)
                
                # Verify the change was applied
                final_hp_data = await player_mgr.get_player_hp(player_id)
                final_hp = final_hp_data['current_hp'] if final_hp_data else 0
                
                hp_changes.append({
                    'operation_id': operation_id,
                    'operation_type': operation_type,
                    'initial_hp': current_hp,
                    'attempted_hp': new_hp,
                    'final_hp': final_hp,
                    'amount': amount
                })
                
            except Exception as e:
                hp_changes.append({
                    'operation_id': operation_id,
                    'error': str(e)
                })

        # Launch 30 concurrent damage/healing operations
        tasks = [damage_healing_operation(i) for i in range(30)]
        await asyncio.gather(*tasks)
        
        # Verify no data corruption
        assert len(hp_changes) == 30
        
        # Check final HP state is valid
        final_hp_data = await player_mgr.get_player_hp(player_id)
        assert final_hp_data is not None
        assert 0 <= final_hp_data['current_hp'] <= final_hp_data['max_hp']
        
        # No operations should have failed
        failed_operations = [change for change in hp_changes if 'error' in change]
        assert len(failed_operations) == 0
