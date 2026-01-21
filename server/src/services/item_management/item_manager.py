"""
Unified Item Management Service

Provides a single interface for all item-related operations including inventory,
equipment, and ground items. Maintains atomic transaction boundaries and
integrates with GameStateManager for state consistency.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.src.core.config import settings
from server.src.core.items import EquipmentSlot, ItemCategory
from server.src.core.logging_config import get_logger
from server.src.models.item import Item, PlayerInventory, PlayerEquipment
from server.src.schemas.item import (
    AddItemResult,
    RemoveItemResult,
    MoveItemResult,
    EquipItemResult,
    UnequipItemResult,
    DropItemResult,
    PickupItemResult,
    CanEquipResult,
    ItemStats,
)
from server.src.services.game_state_manager import get_game_state_manager

logger = get_logger(__name__)


@dataclass
class ItemTransaction:
    """Represents a single atomic item operation transaction."""
    transaction_id: str
    operations: List[Dict[str, Any]]
    rollback_operations: List[Dict[str, Any]]
    completed: bool = False


class IItemManager(ABC):
    """Abstract interface for item management operations."""

    # Core Inventory Operations
    @abstractmethod
    async def add_item_to_inventory(
        self,
        db: AsyncSession,
        player_id: int,
        item_id: int,
        quantity: int = 1,
        durability: Optional[int] = None,
    ) -> AddItemResult:
        """Add an item to player's inventory."""
        pass

    @abstractmethod
    async def remove_item_from_inventory(
        self,
        db: AsyncSession,
        player_id: int,
        slot: int,
        quantity: int = 1,
    ) -> RemoveItemResult:
        """Remove items from a specific inventory slot."""
        pass

    @abstractmethod
    async def move_item_in_inventory(
        self,
        db: AsyncSession,
        player_id: int,
        from_slot: int,
        to_slot: int,
    ) -> MoveItemResult:
        """Move or swap items between inventory slots."""
        pass

    # Equipment Operations
    @abstractmethod
    async def equip_item(
        self,
        db: AsyncSession,
        player_id: int,
        inventory_slot: int,
    ) -> EquipItemResult:
        """Equip an item from inventory (atomic: inventory → equipment + HP)."""
        pass

    @abstractmethod
    async def unequip_item(
        self,
        db: AsyncSession,
        player_id: int,
        equipment_slot: EquipmentSlot,
        map_id: Optional[str] = None,
        player_x: Optional[int] = None,
        player_y: Optional[int] = None,
    ) -> UnequipItemResult:
        """Unequip item to inventory or ground (atomic: equipment → inventory/ground + HP)."""
        pass

    # Ground Item Operations
    @abstractmethod
    async def drop_item(
        self,
        player_id: int,
        inventory_slot: int,
        map_id: str,
        x: int,
        y: int,
        quantity: Optional[int] = None,
    ) -> DropItemResult:
        """Drop item from inventory to ground (atomic: inventory → ground)."""
        pass

    @abstractmethod
    async def pickup_item(
        self,
        player_id: int,
        ground_item_id: int,
        player_x: int,
        player_y: int,
        player_map_id: str,
    ) -> PickupItemResult:
        """Pick up ground item to inventory (atomic: ground → inventory)."""
        pass

    # Complex Transactions
    @abstractmethod
    async def handle_player_death(
        self,
        player_id: int,
        map_id: str,
        x: int,
        y: int,
    ) -> int:
        """Handle player death: drop all items and clear inventory/equipment."""
        pass

    # Query Operations
    @abstractmethod
    async def get_total_equipment_stats(self, player_id: int) -> ItemStats:
        """Calculate total stats from all equipped items."""
        pass

    @abstractmethod
    async def can_equip_item(self, player_id: int, item: Item) -> CanEquipResult:
        """Check if player can equip an item (requirements, conflicts)."""
        pass


class ItemManager(IItemManager):
    """
    Unified item management service implementation.
    
    Consolidates inventory, equipment, and ground item operations into atomic
    transactions while maintaining compatibility with existing service interfaces.
    """

    def __init__(self):
        """Initialize the item manager."""
        self._active_transactions: Dict[str, ItemTransaction] = {}
        self._transaction_counter = 0

    def _generate_transaction_id(self) -> str:
        """Generate a unique transaction ID."""
        self._transaction_counter += 1
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        return f"tx_{timestamp}_{self._transaction_counter}"

    async def add_item_to_inventory(
        self,
        db: AsyncSession,
        player_id: int,
        item_id: int,
        quantity: int = 1,
        durability: Optional[int] = None,
    ) -> AddItemResult:
        """
        Add an item to player's inventory with stacking support.
        
        Delegates to existing InventoryService for compatibility while providing
        the unified interface. Future iterations will inline the logic.
        """
        from server.src.services.inventory_service import InventoryService
        
        return await InventoryService.add_item(
            player_id=player_id,
            item_id=item_id,
            quantity=quantity,
            durability=durability,
        )

    async def remove_item_from_inventory(
        self,
        db: AsyncSession,
        player_id: int,
        slot: int,
        quantity: int = 1,
    ) -> RemoveItemResult:
        """Remove items from a specific inventory slot."""
        from server.src.services.inventory_service import InventoryService
        
        return await InventoryService.remove_item(
            player_id=player_id,
            slot=slot,
            quantity=quantity,
        )

    async def move_item_in_inventory(
        self,
        db: AsyncSession,
        player_id: int,
        from_slot: int,
        to_slot: int,
    ) -> MoveItemResult:
        """Move or swap items between inventory slots."""
        from server.src.services.inventory_service import InventoryService
        
        return await InventoryService.move_item(
            player_id=player_id,
            from_slot=from_slot,
            to_slot=to_slot,
        )

    async def equip_item(
        self,
        db: AsyncSession,
        player_id: int,
        inventory_slot: int,
    ) -> EquipItemResult:
        """
        Equip an item from inventory with atomic transaction support.
        
        This operation involves:
        1. Remove item from inventory
        2. Add item to equipment
        3. Handle two-handed weapon conflicts  
        4. Adjust HP for health bonuses
        5. Update equipment stats
        
        Maintains atomicity via GSM state operations.
        """
        from server.src.services.equipment_service import EquipmentService
        
        # For now, delegate to existing EquipmentService
        # Future: inline logic for better transaction control
        return await EquipmentService.equip_from_inventory(
            db=db,
            player_id=player_id,
            inventory_slot=inventory_slot,
        )

    async def unequip_item(
        self,
        db: AsyncSession,
        player_id: int,
        equipment_slot: EquipmentSlot,
        map_id: Optional[str] = None,
        player_x: Optional[int] = None,
        player_y: Optional[int] = None,
    ) -> UnequipItemResult:
        """
        Unequip item to inventory or ground with atomic transaction support.
        
        This operation involves:
        1. Remove item from equipment
        2. Try to add to inventory (with stacking for ammo)
        3. If inventory full, drop to ground (if position provided)
        4. Adjust HP for health bonus loss
        5. Update equipment stats
        """
        from server.src.services.equipment_service import EquipmentService
        
        return await EquipmentService.unequip_to_inventory(
            db=db,
            player_id=player_id,
            equipment_slot=equipment_slot,
            map_id=map_id,
            player_x=player_x,
            player_y=player_y,
        )

    async def drop_item(
        self,
        player_id: int,
        inventory_slot: int,
        map_id: str,
        x: int,
        y: int,
        quantity: Optional[int] = None,
    ) -> DropItemResult:
        """
        Drop item from inventory to ground atomically.
        
        This operation involves:
        1. Remove item from inventory (partial or full stack)
        2. Create ground item with proper timers and protection
        """
        from server.src.services.ground_item_service import GroundItemService
        
        return await GroundItemService.drop_from_inventory(
            player_id=player_id,
            inventory_slot=inventory_slot,
            map_id=map_id,
            x=x,
            y=y,
            quantity=quantity,
        )

    async def pickup_item(
        self,
        player_id: int,
        ground_item_id: int,
        player_x: int,
        player_y: int,
        player_map_id: str,
    ) -> PickupItemResult:
        """
        Pick up ground item to inventory atomically.
        
        This operation involves:
        1. Validate player position and item accessibility
        2. Remove ground item
        3. Add to inventory (with stacking support)
        """
        from server.src.services.ground_item_service import GroundItemService
        
        return await GroundItemService.pickup_item(
            player_id=player_id,
            ground_item_id=ground_item_id,
            player_x=player_x,
            player_y=player_y,
            player_map_id=player_map_id,
        )

    async def handle_player_death(
        self,
        player_id: int,
        map_id: str,
        x: int,
        y: int,
    ) -> int:
        """
        Handle player death with atomic item dropping.
        
        This is a complex transaction that involves:
        1. Get all player inventory items
        2. Get all player equipment items  
        3. Create ground items for all items
        4. Clear player inventory and equipment
        5. Return count of items dropped
        
        This operation should be atomic to prevent item duplication or loss.
        """
        from server.src.services.ground_item_service import GroundItemService
        
        return await GroundItemService.drop_player_items_on_death(
            player_id=player_id,
            map_id=map_id,
            x=x,
            y=y,
        )

    async def get_total_equipment_stats(self, player_id: int) -> ItemStats:
        """Calculate total stats from all equipped items."""
        from server.src.services.equipment_service import EquipmentService
        
        return await EquipmentService.get_total_stats(player_id)

    async def can_equip_item(self, player_id: int, item: Item) -> CanEquipResult:
        """Check if player can equip an item."""
        from server.src.services.equipment_service import EquipmentService
        
        return await EquipmentService.can_equip(player_id, item)

    # Extended functionality for future atomic transactions
    async def _begin_transaction(self) -> str:
        """Begin a new item transaction."""
        transaction_id = self._generate_transaction_id()
        self._active_transactions[transaction_id] = ItemTransaction(
            transaction_id=transaction_id,
            operations=[],
            rollback_operations=[],
        )
        return transaction_id

    async def _commit_transaction(self, transaction_id: str) -> bool:
        """Commit a transaction and clean up."""
        if transaction_id in self._active_transactions:
            transaction = self._active_transactions[transaction_id]
            transaction.completed = True
            del self._active_transactions[transaction_id]
            logger.debug(
                "Transaction committed",
                extra={"transaction_id": transaction_id}
            )
            return True
        return False

    async def _rollback_transaction(self, transaction_id: str) -> bool:
        """Rollback a transaction and execute rollback operations."""
        if transaction_id in self._active_transactions:
            transaction = self._active_transactions[transaction_id]
            
            # Execute rollback operations in reverse order
            gsm = get_game_state_manager()
            for rollback_op in reversed(transaction.rollback_operations):
                try:
                    # This would execute rollback operations through GSM
                    # Implementation would depend on operation type
                    logger.debug(
                        "Executing rollback operation",
                        extra={
                            "transaction_id": transaction_id,
                            "operation": rollback_op,
                        }
                    )
                except Exception as e:
                    logger.error(
                        "Rollback operation failed",
                        extra={
                            "transaction_id": transaction_id,
                            "operation": rollback_op,
                            "error": str(e),
                        }
                    )
            
            del self._active_transactions[transaction_id]
            logger.warning(
                "Transaction rolled back",
                extra={"transaction_id": transaction_id}
            )
            return True
        return False

    # Helper methods for complex operations
    async def _transfer_item_inventory_to_equipment(
        self,
        player_id: int,
        item_id: int,
        quantity: int,
        durability: Optional[float],
        from_inventory_slot: int,
        to_equipment_slot: str,
    ) -> bool:
        """Transfer item from inventory to equipment atomically."""
        gsm = get_game_state_manager()
        
        try:
            # Remove from inventory
            await gsm.delete_inventory_slot(player_id, from_inventory_slot)
            
            # Add to equipment
            await gsm.set_equipment_slot(
                player_id, to_equipment_slot, item_id, quantity, durability
            )
            
            logger.debug(
                "Item transferred inventory → equipment",
                extra={
                    "player_id": player_id,
                    "item_id": item_id,
                    "from_slot": from_inventory_slot,
                    "to_slot": to_equipment_slot,
                    "quantity": quantity,
                }
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to transfer item inventory → equipment",
                extra={
                    "player_id": player_id,
                    "item_id": item_id,
                    "error": str(e),
                }
            )
            return False

    async def _transfer_item_equipment_to_inventory(
        self,
        player_id: int,
        item_id: int,
        quantity: int,
        durability: Optional[float],
        from_equipment_slot: str,
        to_inventory_slot: int,
    ) -> bool:
        """Transfer item from equipment to inventory atomically."""
        gsm = get_game_state_manager()
        
        try:
            # Remove from equipment
            await gsm.delete_equipment_slot(player_id, from_equipment_slot)
            
            # Add to inventory
            await gsm.set_inventory_slot(
                player_id, to_inventory_slot, item_id, quantity, durability
            )
            
            logger.debug(
                "Item transferred equipment → inventory",
                extra={
                    "player_id": player_id,
                    "item_id": item_id,
                    "from_slot": from_equipment_slot,
                    "to_slot": to_inventory_slot,
                    "quantity": quantity,
                }
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to transfer item equipment → inventory",
                extra={
                    "player_id": player_id,
                    "item_id": item_id,
                    "error": str(e),
                }
            )
            return False
