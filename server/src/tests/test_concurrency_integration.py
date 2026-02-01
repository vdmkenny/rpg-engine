"""
Integration tests for concurrent operations using real GameStateManager.

These tests use the actual GSM and Valkey to validate that our atomic operations
work correctly under concurrent load conditions.
"""
import asyncio
import random
import pytest

from server.src.models.player import Player
from server.src.core.security import get_password_hash
from server.src.core.items import EquipmentSlot


@pytest.mark.asyncio
class TestConcurrencyIntegration:
    """Test real concurrent operations with GSM and Valkey."""

    async def test_concurrent_inventory_operations_real_gsm(self, session, gsm):
        """Test concurrent inventory operations using real GSM with fake Valkey."""
        # Create a test player
        player_data = {
            "username": "testplayer",
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
        
        # Ensure the player is considered online for hot data operations
        gsm.register_online_player(player_id, "testplayer")
        
        operations_completed = []
        operation_results = {}

        async def concurrent_inventory_ops(operation_id: int):
            """Perform concurrent inventory operations."""
            results = []
            for i in range(10):
                slot = (operation_id * 10 + i) % 28  # Keep within inventory bounds
                item_id = random.randint(1, 100)
                quantity = random.randint(1, 10)
                durability = random.uniform(0.1, 1.0)

                # Set inventory slot using real GSM
                await gsm.set_inventory_slot(player_id, slot, item_id, quantity, durability)
                
                # Verify the item was set
                inventory = await gsm.get_inventory(player_id)
                if slot in inventory:
                    results.append({
                        'slot': slot,
                        'item_id': inventory[slot]['item_id'],
                        'quantity': inventory[slot]['quantity'],
                        'durability': inventory[slot]['current_durability']
                    })

                # Occasionally delete the slot
                if i % 3 == 0:
                    await gsm.delete_inventory_slot(player_id, slot)
                    inventory_after_delete = await gsm.get_inventory(player_id)
                    results.append({
                        'slot': slot,
                        'deleted': slot not in inventory_after_delete
                    })

            operations_completed.append(operation_id)
            operation_results[operation_id] = results

        # Run 5 concurrent tasks performing inventory operations
        tasks = [concurrent_inventory_ops(i) for i in range(5)]
        await asyncio.gather(*tasks)

        # Verify all operations completed
        assert len(operations_completed) == 5
        
        # Verify we have results from all operations
        assert len(operation_results) == 5
        
        # Verify no data corruption - check final inventory state is consistent
        final_inventory = await gsm.get_inventory(player_id)
        
        # All items in final inventory should have valid data
        for slot, item_data in final_inventory.items():
            assert isinstance(item_data['item_id'], int)
            assert isinstance(item_data['quantity'], int)
            assert isinstance(item_data['current_durability'], float)
            assert 0.0 <= item_data['current_durability'] <= 1.0
            assert item_data['quantity'] > 0

    async def test_concurrent_equipment_operations_real_gsm(self, session, gsm):
        """Test concurrent equipment operations using real GSM."""
        # Create a test player
        player_data = {
            "username": "testplayer2",
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
        
        # Ensure the player is considered online
        gsm.register_online_player(player_id, "testplayer2")
        
        equipment_slots = [EquipmentSlot.HEAD, EquipmentSlot.BODY, EquipmentSlot.LEGS, EquipmentSlot.WEAPON, EquipmentSlot.SHIELD]
        operations_completed = []
        operation_results = {}

        async def concurrent_equipment_ops(operation_id: int):
            """Perform concurrent equipment operations."""
            results = []
            for i in range(20):
                slot = equipment_slots[i % len(equipment_slots)]
                slot_name = slot.value
                item_id = random.randint(1, 50)
                quantity = 1  # Equipment typically has quantity 1
                durability = random.uniform(0.5, 1.0)

                # Set equipment slot using real GSM
                await gsm.set_equipment_slot(player_id, slot, item_id, quantity, durability)
                
                # Verify the item was equipped
                equipment = await gsm.get_equipment(player_id)
                if slot_name in equipment:
                    results.append({
                        'slot': slot_name,
                        'item_id': equipment[slot_name]['item_id'],
                        'quantity': equipment[slot_name]['quantity'],
                        'durability': equipment[slot_name]['current_durability']
                    })

                # Occasionally unequip (delete)
                if i % 4 == 0:
                    await gsm.delete_equipment_slot(player_id, slot)
                    equipment_after_delete = await gsm.get_equipment(player_id)
                    results.append({
                        'slot': slot_name,
                        'unequipped': slot_name not in equipment_after_delete
                    })

            operations_completed.append(operation_id)
            operation_results[operation_id] = results

        # Run 3 concurrent tasks performing equipment operations
        tasks = [concurrent_equipment_ops(i) for i in range(3)]
        await asyncio.gather(*tasks)

        # Verify all operations completed
        assert len(operations_completed) == 3
        
        # Verify we have results from all operations
        assert len(operation_results) == 3
        
        # Verify no data corruption in final equipment state
        final_equipment = await gsm.get_equipment(player_id)
        
        # All items in final equipment should have valid data
        for slot, item_data in final_equipment.items():
            assert isinstance(item_data['item_id'], int)
            assert isinstance(item_data['quantity'], int)
            assert isinstance(item_data['current_durability'], float)
            assert 0.0 <= item_data['current_durability'] <= 1.0
            assert item_data['quantity'] > 0

    async def test_concurrent_player_hp_operations_real_gsm(self, session, gsm):
        """Test concurrent HP update operations using real GSM."""
        # Create a test player
        player_data = {
            "username": "testplayer3",
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
        
        # Ensure the player is considered online
        gsm.register_online_player(player_id, "testplayer3")
        
        operations_completed = []
        hp_values = []

        async def concurrent_hp_ops(operation_id: int):
            """Perform concurrent HP update operations."""
            for i in range(50):
                current_hp = random.randint(1, 100)
                max_hp = random.randint(current_hp, 150)

                # Set HP using real GSM
                await gsm.set_player_hp(player_id, current_hp, max_hp)
                
                # Verify HP was set
                hp_data = await gsm.get_player_hp(player_id)
                if hp_data:
                    hp_values.append({
                        'current_hp': hp_data['current_hp'],
                        'max_hp': hp_data['max_hp'],
                        'operation_id': operation_id,
                        'iteration': i
                    })

            operations_completed.append(operation_id)

        # Run 4 concurrent tasks performing HP operations  
        tasks = [concurrent_hp_ops(i) for i in range(4)]
        await asyncio.gather(*tasks)

        # Verify all operations completed
        assert len(operations_completed) == 4
        
        # Verify we collected HP values
        assert len(hp_values) > 0
        
        # Verify final HP state is valid
        final_hp = await gsm.get_player_hp(player_id)
        assert final_hp is not None
        assert isinstance(final_hp['current_hp'], int)
        assert isinstance(final_hp['max_hp'], int)
        assert final_hp['current_hp'] <= final_hp['max_hp']
        assert final_hp['current_hp'] > 0
        assert final_hp['max_hp'] > 0

    async def test_cross_operation_isolation(self, session, gsm):
        """Test that concurrent operations on different data types don't interfere."""
        # Create test players
        player1_data = {
            "username": "player1",
            "hashed_password": get_password_hash("testpass"),
            "map_id": "samplemap",
            "x_coord": 25,
            "y_coord": 25
        }
        player2_data = {
            "username": "player2",
            "hashed_password": get_password_hash("testpass"),
            "map_id": "samplemap",
            "x_coord": 26,
            "y_coord": 26
        }
        player1 = Player(**player1_data)
        player2 = Player(**player2_data)
        session.add_all([player1, player2])
        await session.commit()
        await session.refresh(player1)
        await session.refresh(player2)
        
        # Ensure players are considered online
        gsm.register_online_player(player1.id, "player1")
        gsm.register_online_player(player2.id, "player2")
        
        results = []

        async def mixed_operations_player1():
            """Perform mixed operations on player1."""
            for i in range(20):
                # Inventory operation
                await gsm.set_inventory_slot(player1.id, i % 28, i + 1, 1, 0.9)
                
                # Equipment operation
                if i % 5 == 0:
                    await gsm.set_equipment_slot(player1.id, EquipmentSlot.WEAPON, i + 100, 1, 0.8)
                
                # HP operation
                if i % 3 == 0:
                    await gsm.set_player_hp(player1.id, 50 + i, 100 + i)
            
            results.append("player1_done")

        async def mixed_operations_player2():
            """Perform mixed operations on player2."""
            for i in range(20):
                # Inventory operation (different items)
                await gsm.set_inventory_slot(player2.id, i % 28, i + 200, 2, 0.7)
                
                # Equipment operation (different items)
                if i % 4 == 0:
                    await gsm.set_equipment_slot(player2.id, EquipmentSlot.HEAD, i + 300, 1, 0.6)
                
                # HP operation (different values)
                if i % 2 == 0:
                    await gsm.set_player_hp(player2.id, 30 + i, 80 + i)
            
            results.append("player2_done")

        # Run operations concurrently
        await asyncio.gather(mixed_operations_player1(), mixed_operations_player2())
        
        # Verify both players completed their operations
        assert "player1_done" in results
        assert "player2_done" in results
        
        # Verify data integrity for both players
        p1_inventory = await gsm.get_inventory(player1.id)
        p2_inventory = await gsm.get_inventory(player2.id)
        
        # Players should have different items (no cross-contamination)
        for slot, item_data in p1_inventory.items():
            assert item_data['item_id'] >= 1 and item_data['item_id'] <= 20
            assert item_data['quantity'] == 1
            
        for slot, item_data in p2_inventory.items():
            assert item_data['item_id'] >= 200 and item_data['item_id'] <= 220
            assert item_data['quantity'] == 2
            
        # Verify equipment separation
        p1_equipment = await gsm.get_equipment(player1.id)
        p2_equipment = await gsm.get_equipment(player2.id)
        
        if "weapon" in p1_equipment:
            assert p1_equipment["weapon"]["item_id"] >= 100 and p1_equipment["weapon"]["item_id"] <= 120
            
        if "helmet" in p2_equipment:
            assert p2_equipment["helmet"]["item_id"] >= 300 and p2_equipment["helmet"]["item_id"] <= 320