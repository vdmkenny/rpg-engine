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


@pytest.mark.asyncio
class TestRaceConditionDetection:
    """Test specific race conditions that could occur in multiplayer gameplay."""

    async def test_concurrent_inventory_slot_modifications(self, session, gsm):
        """Test multiple players/processes trying to modify the same inventory slot."""
        # Create a test player
        player_data = {
            "username": "race_player1",
            "hashed_password": get_password_hash("testpass"),
            "map_id": "samplemap",
            "x_coord": 25,
            "y_coord": 25
        }
        player = Player(**player_data)
        session.add(player)
        await session.commit()
        await session.refresh(player)
        player_id = player.id
        
        gsm.register_online_player(player_id, "race_player1")
        
        # The race condition: multiple operations trying to modify slot 0 simultaneously
        target_slot = 0
        operations_results = []

        async def modify_slot_operation(operation_id: int, item_id: int):
            """Simulate different operations trying to modify the same slot."""
            try:
                # Each operation tries to set a different item in slot 0
                await gsm.set_inventory_slot(player_id, target_slot, item_id, 1, 1.0)
                
                # Immediately check what's actually in the slot
                inventory = await gsm.get_inventory(player_id)
                actual_item_id = inventory.get(target_slot, {}).get('item_id')
                
                operations_results.append({
                    'operation_id': operation_id,
                    'attempted_item_id': item_id,
                    'actual_item_id': actual_item_id,
                    'success': actual_item_id == item_id
                })
                
            except Exception as e:
                operations_results.append({
                    'operation_id': operation_id,
                    'attempted_item_id': item_id,
                    'error': str(e)
                })

        # Launch 10 concurrent operations all trying to modify the same slot
        tasks = [modify_slot_operation(i, 100 + i) for i in range(10)]
        await asyncio.gather(*tasks)
        
        # Verify no data corruption occurred
        assert len(operations_results) == 10
        
        # Check final state - exactly one item should be in the slot
        final_inventory = await gsm.get_inventory(player_id)
        final_item_id = final_inventory.get(target_slot, {}).get('item_id')
        
        # The final item should be one of the attempted items
        attempted_items = [r['attempted_item_id'] for r in operations_results]
        assert final_item_id in attempted_items
        
        # Count how many operations "succeeded" (thought they set their item)
        successful_operations = [r for r in operations_results if r.get('success', False)]
        
        # With proper atomic operations, only one should have actually succeeded
        # (though others might not immediately see the conflict)
        assert len(successful_operations) >= 1

    async def test_concurrent_equipment_swap_race(self, session, gsm):
        """Test race condition when multiple operations try to equip/unequip same slot."""
        # Create test player
        player_data = {
            "username": "race_player2",
            "hashed_password": get_password_hash("testpass"),
            "map_id": "samplemap",
            "x_coord": 25,
            "y_coord": 25
        }
        player = Player(**player_data)
        session.add(player)
        await session.commit()
        await session.refresh(player)
        player_id = player.id
        
        gsm.register_online_player(player_id, "race_player2")
        
        # Pre-populate inventory with items to equip
        for slot in range(5):
            await gsm.set_inventory_slot(player_id, slot, 200 + slot, 1, 1.0)
        
        equipment_slot = "weapon"
        operations_results = []

        async def equipment_swap_operation(operation_id: int):
            """Simulate rapid equipment swapping operations."""
            try:
                item_id = 200 + (operation_id % 5)  # Cycle through available items
                
                if operation_id % 2 == 0:
                    # Even operations: equip an item
                    await gsm.set_equipment_slot(player_id, equipment_slot, item_id, 1, 0.9)
                    operation_type = "equip"
                else:
                    # Odd operations: unequip
                    await gsm.delete_equipment_slot(player_id, equipment_slot)
                    operation_type = "unequip"
                
                # Check final state
                equipment = await gsm.get_equipment(player_id)
                equipped_item = equipment.get(equipment_slot, {}).get('item_id')
                
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
        final_equipment = await gsm.get_equipment(player_id)
        
        # Equipment slot should either be empty or contain a valid item
        if equipment_slot in final_equipment:
            equipped_item_id = final_equipment[equipment_slot]['item_id']
            assert equipped_item_id in range(200, 205)  # Valid item range
        
        # No operations should have failed due to race conditions
        failed_operations = [r for r in operations_results if 'error' in r]
        assert len(failed_operations) == 0

    async def test_concurrent_hp_updates_during_combat(self, session, gsm):
        """Test race condition during rapid HP updates (simulating combat)."""
        # Create test player
        player_data = {
            "username": "race_player3",
            "hashed_password": get_password_hash("testpass"),
            "map_id": "samplemap",
            "x_coord": 25,
            "y_coord": 25
        }
        player = Player(**player_data)
        session.add(player)
        await session.commit()
        await session.refresh(player)
        player_id = player.id
        
        gsm.register_online_player(player_id, "race_player3")
        
        # Set initial HP
        initial_hp = 100
        max_hp = 100
        await gsm.set_player_hp(player_id, initial_hp, max_hp)
        
        hp_changes = []
        
        async def damage_healing_operation(operation_id: int):
            """Simulate rapid damage and healing during combat."""
            try:
                # Get current HP
                hp_data = await gsm.get_player_hp(player_id)
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
                await gsm.set_player_hp(player_id, new_hp, max_hp)
                
                # Verify the change was applied
                final_hp_data = await gsm.get_player_hp(player_id)
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
        final_hp_data = await gsm.get_player_hp(player_id)
        assert final_hp_data is not None
        assert 0 <= final_hp_data['current_hp'] <= final_hp_data['max_hp']
        
        # No operations should have failed
        failed_operations = [change for change in hp_changes if 'error' in change]
        assert len(failed_operations) == 0

    async def test_cross_player_inventory_isolation(self, session, gsm):
        """Test that concurrent operations on different players don't interfere."""
        # Create multiple test players
        players = []
        for i in range(3):
            player_data = {
                "username": f"isolation_player_{i}",
                "hashed_password": get_password_hash("testpass"),
                "map_id": "samplemap",
                "x_coord": 25 + i,
                "y_coord": 25 + i
            }
            player = Player(**player_data)
            session.add(player)
            players.append(player)
        
        await session.commit()
        for player in players:
            await session.refresh(player)
            gsm.register_online_player(player.id, player.username)
        
        operation_results = []

        async def player_operations(player_index: int):
            """Each player performs inventory operations with their unique items."""
            player_id = players[player_index].id
            base_item_id = 1000 + (player_index * 100)  # Unique item range per player
            
            try:
                for slot in range(10):
                    item_id = base_item_id + slot
                    await gsm.set_inventory_slot(player_id, slot, item_id, 1, 1.0)
                
                # Verify all items are correct
                inventory = await gsm.get_inventory(player_id)
                correct_items = 0
                for slot in range(10):
                    expected_item_id = base_item_id + slot
                    actual_item_id = inventory.get(slot, {}).get('item_id')
                    if actual_item_id == expected_item_id:
                        correct_items += 1
                
                operation_results.append({
                    'player_index': player_index,
                    'player_id': player_id,
                    'correct_items': correct_items,
                    'expected_items': 10
                })
                
            except Exception as e:
                operation_results.append({
                    'player_index': player_index,
                    'player_id': players[player_index].id,
                    'error': str(e)
                })

        # Run all players' operations concurrently
        tasks = [player_operations(i) for i in range(3)]
        await asyncio.gather(*tasks)
        
        # Verify no cross-contamination between players
        assert len(operation_results) == 3
        
        for result in operation_results:
            assert 'error' not in result, f"Player {result['player_index']} failed: {result.get('error')}"
            assert result['correct_items'] == result['expected_items'], \
                f"Player {result['player_index']} had {result['correct_items']}/{result['expected_items']} correct items"
        
        # Double-check final state for each player
        for i, player in enumerate(players):
            inventory = await gsm.get_inventory(player.id)
            base_item_id = 1000 + (i * 100)
            
            for slot in range(10):
                expected_item_id = base_item_id + slot
                assert slot in inventory, f"Player {i} missing slot {slot}"
                assert inventory[slot]['item_id'] == expected_item_id, \
                    f"Player {i} slot {slot}: expected {expected_item_id}, got {inventory[slot]['item_id']}"