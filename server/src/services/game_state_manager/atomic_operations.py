"""
Atomic operations for GameStateManager using Redis transactions.

Provides thread-safe, atomic operations for complex game state modifications
that require consistency across multiple operations.
"""

from typing import Dict, List, Optional, Any, Tuple, Callable
from contextlib import asynccontextmanager
import json

from server.src.core.logging_config import get_logger
from server.src.core.concurrency import get_redis_atomic_operations

logger = get_logger(__name__)


class GSMAtomicOperations:
    """
    Atomic operations for GameStateManager using Redis MULTI/EXEC transactions.
    
    These operations ensure that complex state changes happen atomically,
    preventing race conditions and maintaining data consistency.
    """
    
    def __init__(self, gsm):
        self.gsm = gsm
        self._redis_ops = None
    
    def _get_redis_ops(self):
        """Lazy initialization of Redis operations."""
        if self._redis_ops is None:
            self._redis_ops = get_redis_atomic_operations()
        return self._redis_ops
    
    # =========================================================================
    # INVENTORY ATOMIC OPERATIONS
    # =========================================================================
    
    async def atomic_inventory_move(
        self, 
        player_id: int, 
        from_slot: int, 
        to_slot: int
    ) -> bool:
        """
        Atomically move item between inventory slots.
        
        Args:
            player_id: Player performing the move
            from_slot: Source slot number
            to_slot: Destination slot number
            
        Returns:
            True if move was successful, False otherwise
        """
        redis_ops = self._get_redis_ops()
        
        async def _move_operation(tx):
            inventory_key = f"inventory:{player_id}"
            
            # Get current inventory state
            current_inventory = await self.gsm.valkey.hgetall(inventory_key)
            inventory_dict = {}
            
            # Decode current inventory
            for slot_bytes, data_bytes in current_inventory.items():
                slot_num = int(slot_bytes.decode())
                inventory_dict[slot_num] = json.loads(data_bytes.decode())
            
            # Validate move
            if from_slot not in inventory_dict:
                logger.warning(
                    "Atomic inventory move failed - source slot empty",
                    extra={"player_id": player_id, "from_slot": from_slot, "to_slot": to_slot}
                )
                return False
            
            from_item = inventory_dict[from_slot]
            to_item = inventory_dict.get(to_slot)
            
            # Perform atomic move
            if to_item is None:
                # Simple move to empty slot
                await tx.hset(inventory_key, {str(to_slot): json.dumps(from_item)})
                await tx.hdel(inventory_key, [str(from_slot)])
            else:
                # Swap items
                await tx.hset(inventory_key, {
                    str(from_slot): json.dumps(to_item),
                    str(to_slot): json.dumps(from_item)
                })
            
            # Mark inventory as dirty
            await tx.sadd("dirty:inventory", [str(player_id)])
            
            return True
        
        try:
            async with redis_ops.transaction(f"inventory_move_player_{player_id}") as tx:
                return await _move_operation(tx)
                
        except Exception as e:
            logger.error(
                "Atomic inventory move failed",
                extra={
                    "player_id": player_id,
                    "from_slot": from_slot,
                    "to_slot": to_slot,
                    "error": str(e)
                }
            )
            return False
    
    async def atomic_inventory_stack(
        self, 
        player_id: int, 
        from_slot: int, 
        to_slot: int, 
        max_stack_size: int = 2147483647
    ) -> bool:
        """
        Atomically stack items between inventory slots.
        
        Args:
            player_id: Player performing the stack
            from_slot: Source slot number  
            to_slot: Destination slot number
            max_stack_size: Maximum items per stack
            
        Returns:
            True if stack was successful, False otherwise
        """
        redis_ops = self._get_redis_ops()
        
        async def _stack_operation(tx):
            inventory_key = f"inventory:{player_id}"
            
            # Get current inventory state
            current_inventory = await self.gsm.valkey.hgetall(inventory_key)
            inventory_dict = {}
            
            # Decode current inventory
            for slot_bytes, data_bytes in current_inventory.items():
                slot_num = int(slot_bytes.decode())
                inventory_dict[slot_num] = json.loads(data_bytes.decode())
            
            # Validate stack operation
            if from_slot not in inventory_dict or to_slot not in inventory_dict:
                return False
                
            from_item = inventory_dict[from_slot]
            to_item = inventory_dict[to_slot]
            
            # Check if items can stack
            if from_item["item_id"] != to_item["item_id"]:
                return False
                
            # Calculate new quantities
            total_quantity = from_item["quantity"] + to_item["quantity"]
            
            if total_quantity <= max_stack_size:
                # Stack completely into to_slot
                to_item["quantity"] = total_quantity
                await tx.hset(inventory_key, {str(to_slot): json.dumps(to_item)})
                await tx.hdel(inventory_key, [str(from_slot)])
            else:
                # Partial stack
                to_item["quantity"] = max_stack_size
                from_item["quantity"] = total_quantity - max_stack_size
                await tx.hset(inventory_key, {
                    str(from_slot): json.dumps(from_item),
                    str(to_slot): json.dumps(to_item)
                })
            
            # Mark inventory as dirty
            await tx.sadd("dirty:inventory", [str(player_id)])
            
            return True
        
        try:
            async with redis_ops.transaction(f"inventory_stack_player_{player_id}") as tx:
                return await _stack_operation(tx)
                
        except Exception as e:
            logger.error(
                "Atomic inventory stack failed",
                extra={
                    "player_id": player_id,
                    "from_slot": from_slot,
                    "to_slot": to_slot,
                    "error": str(e)
                }
            )
            return False
    
    # =========================================================================
    # EQUIPMENT ATOMIC OPERATIONS  
    # =========================================================================
    
    async def atomic_equipment_change(
        self,
        player_id: int,
        equipment_slot: str,
        new_item_id: Optional[int],
        new_quantity: int = 1,
        new_durability: float = 100.0,
        inventory_slot: Optional[int] = None,
        inventory_item_id: Optional[int] = None,
        inventory_quantity: int = 0,
        inventory_durability: float = 100.0
    ) -> bool:
        """
        Atomically change equipment and update inventory.
        
        This handles equip/unequip operations that need to be atomic across
        both equipment and inventory states.
        
        Args:
            player_id: Player making the change
            equipment_slot: Equipment slot being modified
            new_item_id: New item to equip (None to unequip)
            new_quantity: Quantity of new item
            new_durability: Durability of new item
            inventory_slot: Inventory slot to modify (if any)
            inventory_item_id: Item to place in inventory
            inventory_quantity: Quantity for inventory
            inventory_durability: Durability for inventory
            
        Returns:
            True if operation was successful, False otherwise
        """
        redis_ops = self._get_redis_ops()
        
        async def _equipment_operation(tx):
            equipment_key = f"equipment:{player_id}"
            inventory_key = f"inventory:{player_id}"
            
            # Update equipment
            if new_item_id is not None:
                equipment_data = {
                    "item_id": new_item_id,
                    "quantity": new_quantity,
                    "durability": new_durability
                }
                await tx.hset(equipment_key, {equipment_slot: json.dumps(equipment_data)})
            else:
                # Unequip - remove the slot
                await tx.hdel(equipment_key, [equipment_slot])
            
            # Update inventory if needed
            if inventory_slot is not None:
                if inventory_item_id is not None:
                    inventory_data = {
                        "item_id": inventory_item_id,
                        "quantity": inventory_quantity,
                        "durability": inventory_durability
                    }
                    await tx.hset(inventory_key, {str(inventory_slot): json.dumps(inventory_data)})
                else:
                    # Remove from inventory
                    await tx.hdel(inventory_key, [str(inventory_slot)])
            
            # Mark both as dirty
            await tx.sadd("dirty:equipment", [str(player_id)])
            if inventory_slot is not None:
                await tx.sadd("dirty:inventory", [str(player_id)])
            
            return True
        
        try:
            async with redis_ops.transaction(f"equipment_change_player_{player_id}") as tx:
                return await _equipment_operation(tx)
                
        except Exception as e:
            logger.error(
                "Atomic equipment change failed",
                extra={
                    "player_id": player_id,
                    "equipment_slot": equipment_slot,
                    "error": str(e)
                }
            )
            return False
    
    # =========================================================================
    # HP AND POSITION ATOMIC OPERATIONS
    # =========================================================================
    
    async def atomic_hp_update(
        self,
        player_id: int,
        new_hp: int,
        new_max_hp: Optional[int] = None,
        equipment_changes: Optional[Dict[str, Dict]] = None
    ) -> bool:
        """
        Atomically update player HP and related equipment changes.
        
        Args:
            player_id: Player to update
            new_hp: New current HP
            new_max_hp: New maximum HP (if changed due to equipment)
            equipment_changes: Equipment changes affecting HP
            
        Returns:
            True if update was successful, False otherwise
        """
        redis_ops = self._get_redis_ops()
        
        async def _hp_operation(tx):
            player_key = f"player:{player_id}"
            
            # Get current player state
            current_data = await self.gsm.valkey.hgetall(player_key)
            if not current_data:
                return False
                
            player_data = {}
            for key_bytes, value_bytes in current_data.items():
                key = key_bytes.decode()
                player_data[key] = value_bytes.decode()
            
            # Update HP values
            player_data["current_hp"] = str(new_hp)
            if new_max_hp is not None:
                player_data["max_hp"] = str(new_max_hp)
            
            # Write updated player state
            await tx.hset(player_key, player_data)
            
            # Update equipment if changes provided
            if equipment_changes:
                equipment_key = f"equipment:{player_id}"
                for slot, equipment_data in equipment_changes.items():
                    await tx.hset(equipment_key, {slot: json.dumps(equipment_data)})
                await tx.sadd("dirty:equipment", [str(player_id)])
            
            # Mark position as dirty (for HP sync)
            await tx.sadd("dirty:position", [str(player_id)])
            
            return True
        
        try:
            async with redis_ops.transaction(f"hp_update_player_{player_id}") as tx:
                return await _hp_operation(tx)
                
        except Exception as e:
            logger.error(
                "Atomic HP update failed",
                extra={
                    "player_id": player_id,
                    "new_hp": new_hp,
                    "error": str(e)
                }
            )
            return False
    
    async def atomic_position_update(
        self,
        player_id: int,
        x: int,
        y: int,
        map_id: str
    ) -> bool:
        """
        Atomically update player position.
        
        Args:
            player_id: Player to update
            x: New X coordinate
            y: New Y coordinate  
            map_id: New map ID
            
        Returns:
            True if update was successful, False otherwise
        """
        redis_ops = self._get_redis_ops()
        
        async def _position_operation(tx):
            player_key = f"player:{player_id}"
            
            # Get current player state
            current_data = await self.gsm.valkey.hgetall(player_key)
            if not current_data:
                return False
                
            player_data = {}
            for key_bytes, value_bytes in current_data.items():
                key = key_bytes.decode()
                player_data[key] = value_bytes.decode()
            
            # Update position
            player_data["x"] = str(x)
            player_data["y"] = str(y)  
            player_data["map_id"] = map_id
            
            # Write updated state
            await tx.hset(player_key, player_data)
            
            # Mark as dirty for database sync
            await tx.sadd("dirty:position", [str(player_id)])
            
            return True
        
        try:
            async with redis_ops.transaction(f"position_update_player_{player_id}") as tx:
                return await _position_operation(tx)
                
        except Exception as e:
            logger.error(
                "Atomic position update failed",
                extra={
                    "player_id": player_id,
                    "x": x,
                    "y": y,
                    "map_id": map_id,
                    "error": str(e)
                }
            )
            return False
    
    # =========================================================================
    # SKILL ATOMIC OPERATIONS
    # =========================================================================
    
    async def atomic_skill_update(
        self,
        player_id: int,
        skill_name: str,
        skill_id: int,
        new_level: int,
        new_experience: int,
        hp_changes: Optional[Dict[str, int]] = None
    ) -> bool:
        """
        Atomically update skill and related HP changes.
        
        Args:
            player_id: Player to update
            skill_name: Name of skill being updated
            skill_id: ID of skill
            new_level: New skill level
            new_experience: New experience amount
            hp_changes: HP changes due to skill level (for hitpoints skill)
            
        Returns:
            True if update was successful, False otherwise
        """
        redis_ops = self._get_redis_ops()
        
        async def _skill_operation(tx):
            skills_key = f"skills:{player_id}"
            
            # Update skill
            skill_data = {
                "skill_id": skill_id,
                "level": new_level,
                "experience": new_experience
            }
            await tx.hset(skills_key, {skill_name: json.dumps(skill_data)})
            
            # Update HP if this is hitpoints skill
            if hp_changes:
                player_key = f"player:{player_id}"
                current_data = await self.gsm.valkey.hgetall(player_key)
                
                if current_data:
                    player_data = {}
                    for key_bytes, value_bytes in current_data.items():
                        key = key_bytes.decode()
                        player_data[key] = value_bytes.decode()
                    
                    # Update HP values
                    player_data.update({k: str(v) for k, v in hp_changes.items()})
                    await tx.hset(player_key, player_data)
                    
                    # Mark position dirty for HP sync
                    await tx.sadd("dirty:position", [str(player_id)])
            
            # Mark skills as dirty
            await tx.sadd("dirty:skills", [str(player_id)])
            
            return True
        
        try:
            async with redis_ops.transaction(f"skill_update_player_{player_id}") as tx:
                return await _skill_operation(tx)
                
        except Exception as e:
            logger.error(
                "Atomic skill update failed",
                extra={
                    "player_id": player_id,
                    "skill_name": skill_name,
                    "new_level": new_level,
                    "error": str(e)
                }
            )
            return False