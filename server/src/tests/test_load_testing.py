"""
Load testing for concurrent operations to validate atomic operations under stress.

These tests simulate higher load scenarios with many concurrent players and operations
to ensure our atomic operations scale properly and don't introduce bottlenecks.
"""
import asyncio
import random
import pytest
import time
from typing import List, Dict, Any

from server.src.models.player import Player
from server.src.core.security import get_password_hash


@pytest.mark.asyncio
class TestConcurrencyLoadTesting:
    """Load testing for concurrent operations under high player count."""

    async def test_high_concurrency_inventory_operations(self, session, gsm):
        """Test atomic inventory operations with many concurrent players."""
        # Create 20 test players
        players = []
        for i in range(20):
            player_data = {
                "username": f"load_player_{i}",
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
        
        # Track performance and results
        operation_results = []
        start_time = time.time()

        async def player_operations(player_index: int):
            """Each player performs many concurrent inventory operations."""
            player_id = players[player_index].id
            results = []
            
            try:
                # Phase 1: Fill inventory
                for slot in range(28):  # Full inventory
                    item_id = random.randint(1, 500)
                    quantity = random.randint(1, 10)
                    durability = random.uniform(0.1, 1.0)
                    
                    await gsm.set_inventory_slot(player_id, slot, item_id, quantity, durability)
                    results.append(f"set_slot_{slot}")
                
                # Phase 2: Rapid modifications
                for _ in range(50):
                    slot = random.randint(0, 27)
                    operation = random.choice(["modify", "delete"])
                    
                    if operation == "modify":
                        item_id = random.randint(1, 500)
                        quantity = random.randint(1, 10)
                        durability = random.uniform(0.1, 1.0)
                        await gsm.set_inventory_slot(player_id, slot, item_id, quantity, durability)
                        results.append(f"modify_slot_{slot}")
                    else:
                        await gsm.delete_inventory_slot(player_id, slot)
                        results.append(f"delete_slot_{slot}")
                
                # Phase 3: Final verification
                final_inventory = await gsm.get_inventory(player_id)
                results.append(f"final_items_{len(final_inventory)}")
                
            except Exception as e:
                results.append(f"error: {str(e)}")
                
            operation_results.append({
                'player_index': player_index,
                'player_id': player_id,
                'operations': len(results),
                'results': results
            })

        # Run all players' operations concurrently
        tasks = [player_operations(i) for i in range(20)]
        await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Verify results
        assert len(operation_results) == 20
        
        total_operations = sum(result['operations'] for result in operation_results)
        operations_per_second = total_operations / total_duration
        
        # Should handle at least 100 operations per second
        assert operations_per_second > 100, f"Too slow: {operations_per_second:.2f} ops/sec"
        
        # No player should have errors
        for result in operation_results:
            error_operations = [op for op in result['results'] if 'error:' in op]
            assert len(error_operations) == 0, f"Player {result['player_index']} had errors: {error_operations}"
        
        print(f"Load test completed: {total_operations} operations in {total_duration:.2f}s ({operations_per_second:.2f} ops/sec)")

    async def test_mixed_operations_load_test(self, session, gsm):
        """Test mixed inventory, equipment, and HP operations under load."""
        # Create 15 test players
        players = []
        for i in range(15):
            player_data = {
                "username": f"mixed_load_player_{i}",
                "hashed_password": get_password_hash("testpass"),
                "map_id": "samplemap",
                "x_coord": 30 + i,
                "y_coord": 30 + i
            }
            player = Player(**player_data)
            session.add(player)
            players.append(player)
        
        await session.commit()
        for player in players:
            await session.refresh(player)
            gsm.register_online_player(player.id, player.username)
        
        operation_results = []
        start_time = time.time()

        async def mixed_player_operations(player_index: int):
            """Each player performs mixed operations on different data types."""
            player_id = players[player_index].id
            results = []
            equipment_slots = ["helmet", "chest", "legs", "weapon", "shield"]
            
            try:
                # Perform 100 mixed operations per player
                for i in range(100):
                    operation_type = random.choice(["inventory", "equipment", "hp"])
                    
                    if operation_type == "inventory":
                        slot = random.randint(0, 27)
                        if random.choice([True, False]):
                            item_id = random.randint(1, 300)
                            await gsm.set_inventory_slot(player_id, slot, item_id, 1, 0.9)
                            results.append("inv_set")
                        else:
                            await gsm.delete_inventory_slot(player_id, slot)
                            results.append("inv_delete")
                    
                    elif operation_type == "equipment":
                        slot = random.choice(equipment_slots)
                        if random.choice([True, False]):
                            item_id = random.randint(1, 100)
                            await gsm.set_equipment_slot(player_id, slot, item_id, 1, 0.8)
                            results.append("eq_set")
                        else:
                            await gsm.delete_equipment_slot(player_id, slot)
                            results.append("eq_delete")
                    
                    else:  # HP operation
                        current_hp = random.randint(1, 100)
                        max_hp = random.randint(current_hp, 120)
                        await gsm.set_player_hp(player_id, current_hp, max_hp)
                        results.append("hp_set")
                
                # Final state verification
                final_inventory = await gsm.get_inventory(player_id)
                final_equipment = await gsm.get_equipment(player_id)
                final_hp = await gsm.get_player_hp(player_id)
                
                results.append(f"final_inv_{len(final_inventory)}")
                results.append(f"final_eq_{len(final_equipment)}")
                results.append(f"final_hp_{final_hp['current_hp'] if final_hp else 0}")
                
            except Exception as e:
                results.append(f"error: {str(e)}")
                
            operation_results.append({
                'player_index': player_index,
                'player_id': player_id,
                'operations': len(results),
                'results': results
            })

        # Run all players' mixed operations concurrently
        tasks = [mixed_player_operations(i) for i in range(15)]
        await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Verify results
        assert len(operation_results) == 15
        
        total_operations = sum(result['operations'] for result in operation_results)
        operations_per_second = total_operations / total_duration
        
        # Should handle mixed operations efficiently
        assert operations_per_second > 80, f"Mixed operations too slow: {operations_per_second:.2f} ops/sec"
        
        # No player should have errors
        for result in operation_results:
            error_operations = [op for op in result['results'] if 'error:' in op]
            assert len(error_operations) == 0, f"Player {result['player_index']} had errors: {error_operations}"
        
        print(f"Mixed load test completed: {total_operations} operations in {total_duration:.2f}s ({operations_per_second:.2f} ops/sec)")

    async def test_concurrent_slot_contention(self, session, gsm):
        """Test high contention on a small number of inventory slots."""
        # Create one test player
        player_data = {
            "username": "contention_player",
            "hashed_password": get_password_hash("testpass"),
            "map_id": "samplemap",
            "x_coord": 50,
            "y_coord": 50
        }
        player = Player(**player_data)
        session.add(player)
        await session.commit()
        await session.refresh(player)
        player_id = player.id
        
        gsm.register_online_player(player_id, "contention_player")
        
        # High contention test: many operations on just 3 slots
        contended_slots = [0, 1, 2]
        operation_results = []
        start_time = time.time()

        async def contention_operations(operation_id: int):
            """Operations that all target the same few slots (high contention)."""
            results = []
            
            try:
                # 50 operations per task, all targeting the same 3 slots
                for i in range(50):
                    slot = random.choice(contended_slots)
                    operation = random.choice(["set", "delete"])
                    
                    if operation == "set":
                        item_id = 1000 + operation_id + i
                        await gsm.set_inventory_slot(player_id, slot, item_id, 1, 1.0)
                        results.append(f"set_{slot}_{item_id}")
                    else:
                        await gsm.delete_inventory_slot(player_id, slot)
                        results.append(f"delete_{slot}")
                
            except Exception as e:
                results.append(f"error: {str(e)}")
                
            operation_results.append({
                'operation_id': operation_id,
                'operations': len(results),
                'results': results
            })

        # Run 30 concurrent tasks all competing for the same 3 slots
        tasks = [contention_operations(i) for i in range(30)]
        await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Verify results
        assert len(operation_results) == 30
        
        total_operations = sum(result['operations'] for result in operation_results)
        operations_per_second = total_operations / total_duration
        
        # High contention should still be reasonably fast
        assert operations_per_second > 50, f"High contention too slow: {operations_per_second:.2f} ops/sec"
        
        # No operations should have failed
        for result in operation_results:
            error_operations = [op for op in result['results'] if 'error:' in op]
            assert len(error_operations) == 0, f"Task {result['operation_id']} had errors: {error_operations}"
        
        # Final state should be valid
        final_inventory = await gsm.get_inventory(player_id)
        for slot in contended_slots:
            if slot in final_inventory:
                item_data = final_inventory[slot]
                assert isinstance(item_data['item_id'], int)
                assert isinstance(item_data['quantity'], int)
                assert isinstance(item_data['current_durability'], float)
        
        print(f"Contention test completed: {total_operations} operations on 3 slots in {total_duration:.2f}s ({operations_per_second:.2f} ops/sec)")
        print(f"Final slot states: {[(slot, final_inventory.get(slot, {}).get('item_id', 'empty')) for slot in contended_slots]}")