"""
Service for managing player inventory.

Supports both database-only and Valkey-first operations:
- When a player is online, inventory data is in Valkey for fast access
- When a player is offline, inventory data is only in the database
- Pass state_manager parameter to use Valkey-first operations during gameplay
"""

from typing import Optional, TYPE_CHECKING

from ..core.config import settings
from ..core.concurrency import PlayerLockManager, LockType
from ..core.items import (
    InventorySortType,
    ItemCategory,
    ItemRarity,
    EquipmentSlot,
    CATEGORY_SORT_ORDER,
    RARITY_SORT_ORDER,
    EQUIPMENT_SLOT_SORT_ORDER,
)

from ..schemas.item import (
    OperationResult,
    OperationType,
    InventoryData,
    InventorySlot,
    ItemInfo,
)
from .item_service import ItemService
from ..core.logging_config import get_logger

if TYPE_CHECKING:
    from .game_state import InventoryManager

logger = get_logger(__name__)

# Singleton lock manager instance for inventory operations
_lock_manager = PlayerLockManager()


class InventoryService:
    """Service for managing player inventory."""

    @staticmethod
    async def get_inventory(player_id: int) -> InventoryData:
        """
        Get all inventory items for a player from GSM.

        Args:
            player_id: Player ID

        Returns:
            List of inventory item objects with item_id and quantity properties
        """
        from .game_state import get_inventory_manager
        from dataclasses import dataclass
        
        inventory_mgr = get_inventory_manager()
        
        # Get inventory data from GSM (the single source of truth)
        inventory_data = await inventory_mgr.get_inventory(player_id)
        
        # Convert GSM inventory data to InventorySlot objects
        inventory_slots = []
        for slot_num, item_data in inventory_data.items():
            # Get item details
            item = await ItemService.get_item_by_id(item_data["item_id"])
            if item:
                item_info = ItemService.item_to_info(item)
                inventory_slots.append(InventorySlot(
                    slot=int(slot_num),
                    item=item_info,
                    quantity=item_data["quantity"],
                    current_durability=item_data.get("current_durability")
                ))
        
        return InventoryData(
            slots=inventory_slots,
            max_slots=settings.INVENTORY_MAX_SLOTS,
            used_slots=len(inventory_slots)
        )

    @staticmethod
    async def get_inventory_response(player_id: int) -> InventoryData:
        """
        Get full inventory state for API response.

        Args:
            player_id: Player ID

        Returns:
            InventoryData with all slot info
        """
        return await InventoryService.get_inventory(player_id)

    @staticmethod
    async def get_item_at_slot(
        player_id: int, slot: int
    ) -> Optional[InventorySlot]:
        """
        Get inventory item at a specific slot.

        Args:
            player_id: Player ID
            slot: Slot number (0-based)

        Returns:
            InventorySlot if slot is occupied, None if empty
        """
        from .game_state import get_inventory_manager
        
        inventory_mgr = get_inventory_manager()
        slot_data = await inventory_mgr.get_inventory_slot(player_id, slot)
        if not slot_data:
            return None
        
        # Get item details
        item = await ItemService.get_item_by_id(slot_data["item_id"])
        if not item:
            return None
            
        item_info = ItemService.item_to_info(item)
        
        # Return InventorySlot
        return InventorySlot(
            slot=slot,
            item=item_info,
            quantity=slot_data["quantity"],
            current_durability=slot_data.get("current_durability")
        )

    @staticmethod
    async def get_free_slot(player_id: int) -> Optional[int]:
        """
        Find the first empty inventory slot.

        Args:
            player_id: Player ID

        Returns:
            Slot number if available, None if inventory is full
        """
        from .game_state import get_inventory_manager
        
        inventory_mgr = get_inventory_manager()
        
        # Find next available inventory slot
        max_slots = settings.INVENTORY_MAX_SLOTS
        inventory_data = await inventory_mgr.get_inventory(player_id)
        for i in range(max_slots):
            if i not in inventory_data:
                return i
        return None

    @staticmethod
    async def get_inventory_count(player_id: int) -> int:
        """
        Get number of occupied inventory slots.

        Args:
            player_id: Player ID

        Returns:
            Number of occupied slots
        """
        from .game_state import get_inventory_manager
        
        inventory_mgr = get_inventory_manager()
        
        # Count occupied inventory slots for player
        inventory_data = await inventory_mgr.get_inventory(player_id)
        return len(inventory_data)

    @staticmethod
    async def find_stack_slot(player_id: int, item_id: int) -> Optional[int]:
        """
        Find an existing stack of the same item with space available.

        Args:
            player_id: Player ID
            item_id: Item ID to find

        Returns:
            Slot number if a stackable slot found, None otherwise
        """
        from .game_state import get_inventory_manager
        from .item_service import ItemService
        
        inventory_mgr = get_inventory_manager()
        
        # Get all inventory slots from GSM
        inventory_data = await inventory_mgr.get_inventory(player_id)
        
        # Get item stacking information
        item = await ItemService.get_item_by_id(item_id)
        if not item or item.max_stack_size <= 1:
            return None  # Item is not stackable
        
        max_stack_size = item.max_stack_size
        
        # Look for existing stack with available space
        for slot_str, slot_data in inventory_data.items():
            if slot_data["item_id"] == item_id:
                if slot_data["quantity"] < max_stack_size:
                    return int(slot_str)  # Found stackable slot
        
        return None  # No stackable slot found

    @staticmethod
    async def add_item(
        player_id: int,
        item_id: int,
        quantity: int = 1,
        durability: Optional[int] = None,
    ) -> OperationResult:
        """
        Add an item to a player's inventory.

        Handles stacking automatically for stackable items.
        If the item is stackable and an existing stack has room, adds to it.
        Otherwise, finds an empty slot.

        Args:
            player_id: Player ID
            item_id: Item database ID
            quantity: Number of items to add
            durability: Current durability (uses max if None)

        Returns:
            OperationResult with success status and details
        """
        async with _lock_manager.acquire_player_lock(
            player_id, LockType.INVENTORY, "add_item"
        ):
            from .game_state import get_inventory_manager
            from .item_service import ItemService
            
            inventory_mgr = get_inventory_manager()
            if quantity <= 0:
                return OperationResult(
                    success=False,
                    message="Quantity must be positive",
                    operation=OperationType.ADD,
                )
            # Get item information for adding to inventory
            item = await ItemService.get_item_by_id(item_id)
            if not item:
                return OperationResult(
                    success=False,
                    message="Item not found",
                    operation=OperationType.ADD,
                )

            # Set durability to max if not specified and item has durability
            if durability is None and item.max_durability is not None:
                durability = item.max_durability

            # Get current player inventory state
            inventory_data = await inventory_mgr.get_inventory(player_id)

            # Try to stack with existing items first
            for slot_num, slot_data in inventory_data.items():
                if (
                    slot_data["item_id"] == item.id
                    and item.max_stack_size > 1
                    and slot_data.get("quantity", 1) < item.max_stack_size
                ):
                    # Can add to existing stack
                    current_qty = slot_data.get("quantity", 1)
                    space_available = item.max_stack_size - current_qty
                    add_amount = min(quantity, space_available)
                    
                    new_quantity = current_qty + add_amount
                    await inventory_mgr.set_inventory_slot(
                        player_id, slot_num, item.id, new_quantity, float(durability) if durability is not None else 1.0
                    )
                    
                    remaining = quantity - add_amount
                    if remaining == 0:
                        return OperationResult(
                            success=True,
                            message=f"Added {quantity} {item.display_name} to existing stack",
                            operation=OperationType.ADD,
                            data={"slot": int(slot_num), "quantity": quantity},
                        )
                    else:
                        # Continue with remaining quantity
                        quantity = remaining

            # Find free slots for remaining items - handle multiple stacks if needed
            first_slot_created = None
            
            while quantity > 0:
                inventory_data = await inventory_mgr.get_inventory(player_id)
                free_slot = None
                for i in range(settings.INVENTORY_MAX_SLOTS):
                    if str(i) not in inventory_data:  # Keys are strings in the inventory dict!
                        free_slot = i
                        break
                if free_slot is None:
                    # No more space available
                    if first_slot_created is not None:
                        # Some items were added successfully
                        return OperationResult(
                            success=True,
                            message=f"Added items to {item.display_name}, {quantity} items couldn't fit",
                            operation=OperationType.ADD,
                            data={"slot": first_slot_created, "overflow_quantity": quantity},
                        )
                    else:
                        # No items were added
                        return OperationResult(
                            success=False,
                            message="Inventory is full",
                            operation=OperationType.ADD,
                            data={"overflow_quantity": quantity},
                        )
                
                # Determine how much can go in this slot (respect max_stack_size)
                if item.max_stack_size > 1:
                    slot_quantity = min(quantity, item.max_stack_size)
                else:
                    slot_quantity = 1  # Non-stackable items
                
                await inventory_mgr.set_inventory_slot(
                    player_id, free_slot, item.id, slot_quantity, 
                    float(durability) if durability is not None else 1.0
                )
                
                # Remember the first slot for return value
                if first_slot_created is None:
                    first_slot_created = free_slot
                
                quantity -= slot_quantity

            # All items successfully added
            return OperationResult(
                success=True,
                message=f"Added items to {item.display_name}",
                operation=OperationType.ADD,
                data={"slot": first_slot_created},
            )

    @staticmethod
    async def remove_item(
        player_id: int,
        slot: int,
        quantity: int = 1,
    ) -> OperationResult:
        """
        Remove items from a specific inventory slot.

        Args:
            player_id: Player ID
            slot: Slot number to remove from
            quantity: Number of items to remove

        Returns:
            OperationResult with success status
        """
        async with _lock_manager.acquire_player_lock(
            player_id, LockType.INVENTORY, "remove_item"
        ):
            from .game_state import get_inventory_manager
            
            inventory_mgr = get_inventory_manager()
            
            if quantity <= 0:
                return OperationResult(
                    success=False,
                    message="Quantity must be positive",
                    operation=OperationType.REMOVE,
                    data={"removed_quantity": 0},
                )

            # Get current slot state from GSM
            slot_data = await inventory_mgr.get_inventory_slot(player_id, slot)
            if not slot_data:
                return OperationResult(
                    success=False,
                    message="Slot is empty",
                    operation=OperationType.REMOVE,
                    data={"removed_quantity": 0},
                )
            
            current_qty = slot_data["quantity"]
            if current_qty < quantity:
                return OperationResult(
                    success=False,
                    message=f"Not enough items (have {current_qty}, need {quantity})",
                    operation=OperationType.REMOVE,
                    data={"removed_quantity": 0},
                )
            
            new_qty = current_qty - quantity
            if new_qty == 0:
                # Remove the slot entirely
                await inventory_mgr.delete_inventory_slot(player_id, slot)
            else:
                # Update with new quantity
                await inventory_mgr.set_inventory_slot(
                    player_id, slot, slot_data["item_id"], new_qty, 
                    float(slot_data.get("current_durability", 1.0))
                )
            
            return OperationResult(
                success=True,
                message=f"Removed {quantity} items",
                operation=OperationType.REMOVE,
                data={"slot": slot, "removed_quantity": quantity},
            )

    @staticmethod
    async def move_item(
        player_id: int,
        from_slot: int,
        to_slot: int,
    ) -> OperationResult:
        """
        Move or swap items between inventory slots.

        If the destination slot is empty, moves the item.
        If occupied, swaps the two items.

        Args:
            player_id: Player ID
            from_slot: Source slot number
            to_slot: Destination slot number

        Returns:
            OperationResult with success status
        """
        async with _lock_manager.acquire_player_lock(
            player_id, LockType.INVENTORY, "move_item"
        ):
            from .game_state import get_inventory_manager
            from .item_service import ItemService
            
            inventory_mgr = get_inventory_manager()
            max_slots = settings.INVENTORY_MAX_SLOTS

            if from_slot < 0 or from_slot >= max_slots:
                return OperationResult(
                    success=False, 
                    message="Invalid source slot",
                    operation=OperationType.MOVE,
                )

            if to_slot < 0 or to_slot >= max_slots:
                return OperationResult(
                    success=False, 
                    message="Invalid destination slot",
                    operation=OperationType.MOVE,
                )

            if from_slot == to_slot:
                return OperationResult(
                    success=True, 
                    message="Same slot",
                    operation=OperationType.MOVE,
                )

            # Get current inventory state for move operation
            inventory_data = await inventory_mgr.get_inventory(player_id)
            if not inventory_data:
                return OperationResult(
                    success=False, 
                    message="Inventory not found",
                    operation=OperationType.MOVE,
                )
                
            from_data = inventory_data.get(str(from_slot))
            if not from_data:
                return OperationResult(
                    success=False, 
                    message="Source slot is empty",
                    operation=OperationType.MOVE,
                )
                
            to_data = inventory_data.get(str(to_slot))
            
            # Handle move/swap operations
            if to_data:
                # Check if we can merge stacks
                if (
                    from_data["item_id"] == to_data["item_id"]
                    and from_data.get("quantity", 1) > 1  # Assume stackable if quantity > 1
                ):
                    # Check if items can be stacked together
                    item = await ItemService.get_item_by_id(from_data["item_id"])
                    if item and item.max_stack_size > 1:
                        # Merge stacks
                        space_available = item.max_stack_size - to_data.get("quantity", 1)
                        transfer_amount = min(from_data.get("quantity", 1), space_available)
                        
                        if transfer_amount > 0:
                            # Update quantities
                            new_from_qty = from_data.get("quantity", 1) - transfer_amount
                            new_to_qty = to_data.get("quantity", 1) + transfer_amount
                            
                            if new_from_qty == 0:
                                # Remove from slot
                                await inventory_mgr.delete_inventory_slot(player_id, from_slot)
                            else:
                                # Update from slot
                                await inventory_mgr.set_inventory_slot(
                                    player_id, from_slot, from_data["item_id"], new_from_qty, 
                                    float(from_data.get("current_durability", 1.0))
                                )
                            
                            # Update to slot
                            await inventory_mgr.set_inventory_slot(
                                player_id, to_slot, to_data["item_id"], new_to_qty, 
                                float(to_data.get("current_durability", 1.0))
                            )
                            
                            return OperationResult(
                                success=True, 
                                message=f"Merged {transfer_amount} items",
                                operation=OperationType.MOVE,
                                data={"from_slot": from_slot, "to_slot": to_slot, "merged_amount": transfer_amount},
                            )
                
                # Swap items
                await inventory_mgr.set_inventory_slot(
                    player_id, from_slot, to_data["item_id"], 
                    to_data.get("quantity", 1), float(to_data.get("current_durability", 1.0))
                )
                await inventory_mgr.set_inventory_slot(
                    player_id, to_slot, from_data["item_id"], 
                    from_data.get("quantity", 1), float(from_data.get("current_durability", 1.0))
                )
                return OperationResult(
                    success=True, 
                    message="Items swapped",
                    operation=OperationType.MOVE,
                    data={"from_slot": from_slot, "to_slot": to_slot},
                )
            else:
                # Move item to empty slot
                await inventory_mgr.set_inventory_slot(
                    player_id, to_slot, from_data["item_id"], 
                    from_data.get("quantity", 1), float(from_data.get("current_durability", 1.0))
                )
                await inventory_mgr.delete_inventory_slot(player_id, from_slot)
                return OperationResult(
                    success=True, 
                    message="Item moved",
                    operation=OperationType.MOVE,
                    data={"from_slot": from_slot, "to_slot": to_slot},
                )

    @staticmethod
    async def has_item(
        player_id: int,
        item_id: int,
        quantity: int = 1,
    ) -> bool:
        """
        Check if player has at least the specified quantity of an item.

        Args:
            player_id: Player ID
            item_id: Item database ID
            quantity: Required quantity

        Returns:
            True if player has enough items
        """
        from .game_state import get_inventory_manager
        
        inventory_mgr = get_inventory_manager()
        
        # Get all inventory slots from GSM
        inventory_data = await inventory_mgr.get_inventory(player_id)
        
        # Sum quantities across all stacks of the same item
        total = 0
        for slot_data in inventory_data.values():
            if slot_data["item_id"] == item_id:
                total += slot_data["quantity"]
        
        return total >= quantity

    @staticmethod
    async def clear_inventory(player_id: int) -> int:
        """
        Remove all items from a player's inventory.

        Args:
            player_id: Player ID

        Returns:
            Number of slots cleared
        """
        from .game_state import get_inventory_manager
        
        inventory_mgr = get_inventory_manager()
        
        # Get current inventory count before clearing
        inventory_data = await inventory_mgr.get_inventory(player_id)
        slots_cleared = len(inventory_data)
        
        # Clear all items from inventory
        await inventory_mgr.clear_inventory(player_id)
        
        return slots_cleared

    @staticmethod
    async def merge_stacks(player_id: int) -> OperationResult:
        """
        Merge all split stacks of the same item type.

        Does not reorder items, only consolidates stacks.

        Args:
            player_id: Player ID

        Returns:
            OperationResult with merge statistics
        """
        from .game_state import get_inventory_manager
        
        inventory_mgr = get_inventory_manager()
        
        # Get all inventory items from GSM
        inventory_data = await inventory_mgr.get_inventory(player_id)
        
        # Group by item_id for stackable items
        item_stacks: dict[int, list[tuple[int, dict]]] = {}  # item_id -> [(slot, slot_data), ...]
        
        for slot_str, slot_data in inventory_data.items():
            slot = int(slot_str)
            item_id = slot_data["item_id"]
            
            # Check if item can be stacked
            item = await ItemService.get_item_by_id(item_id)
            if item and item.max_stack_size > 1:
                if item_id not in item_stacks:
                    item_stacks[item_id] = []
                item_stacks[item_id].append((slot, slot_data))

        stacks_merged = 0
        slots_freed = 0

        for item_id, stacks in item_stacks.items():
            if len(stacks) <= 1:
                continue

            # Get maximum stack size for this item type
            item = await ItemService.get_item_by_id(item_id)
            if not item:
                continue
            max_stack = item.max_stack_size

            # Sort stacks by slot to maintain order
            stacks.sort(key=lambda x: x[0])

            # Merge stacks into the first one, remove empty ones
            primary_slot, primary_data = stacks[0]
            primary_quantity = primary_data["quantity"]
            
            for secondary_slot, secondary_data in stacks[1:]:
                secondary_quantity = secondary_data["quantity"]
                
                # Calculate how much can be transferred
                space_available = max_stack - primary_quantity
                transfer_amount = min(secondary_quantity, space_available)

                if transfer_amount > 0:
                    primary_quantity += transfer_amount
                    secondary_quantity -= transfer_amount
                    stacks_merged += 1

                # Update or delete slots based on new quantities
                if secondary_quantity == 0:
                    # Delete empty slot
                    await inventory_mgr.delete_inventory_slot(player_id, secondary_slot)
                    slots_freed += 1
                else:
                    # Update secondary slot with remaining quantity
                    await inventory_mgr.set_inventory_slot(
                        player_id, 
                        secondary_slot, 
                        item_id, 
                        secondary_quantity,
                        float(secondary_data.get("current_durability", 1.0))
                    )
                    
                    # If primary stack is full, make secondary the new primary
                    if primary_quantity >= max_stack:
                        primary_slot = secondary_slot
                        primary_quantity = secondary_quantity

            # Update primary stack with final quantity
            if primary_quantity != primary_data["quantity"]:
                await inventory_mgr.set_inventory_slot(
                    player_id,
                    primary_slot,
                    item_id,
                    primary_quantity,
                    float(primary_data.get("current_durability", 1.0))
                )

        logger.info(
            "Merged inventory stacks",
            extra={
                "player_id": player_id,
                "stacks_merged": stacks_merged,
                "slots_freed": slots_freed,
            },
        )

        return OperationResult(
            success=True,
            message=f"Merged {stacks_merged} stacks, freed {slots_freed} slots",
            operation=OperationType.MERGE,
            data={"stacks_merged": stacks_merged, "slots_freed": slots_freed},
        )

    @staticmethod
    def _get_sort_key(
        slot: int, slot_data: dict, item_meta: dict, sort_type: InventorySortType
    ) -> tuple:
        """
        Get sort key for an inventory item based on sort type.

        Returns a tuple for multi-level sorting.
        Secondary sort is always by rarity (descending), then name (alphabetical).
        """
        # Get rarity and name for secondary sort
        rarity_order = RARITY_SORT_ORDER.get(
            ItemRarity.from_value(item_meta["rarity"]), 99
        )
        item_name = item_meta["display_name"].lower()

        if sort_type == InventorySortType.BY_CATEGORY:
            category_order = CATEGORY_SORT_ORDER.get(
                ItemCategory(item_meta["category"]), 99
            )
            return (category_order, rarity_order, item_name)

        elif sort_type == InventorySortType.BY_RARITY:
            return (rarity_order, item_name)

        elif sort_type == InventorySortType.BY_VALUE:
            # Negative value so higher values come first
            return (-item_meta["value"], rarity_order, item_name)

        elif sort_type == InventorySortType.BY_NAME:
            return (item_name, rarity_order)

        elif sort_type == InventorySortType.BY_EQUIPMENT_SLOT:
            equipment_slot = item_meta.get("equipment_slot")
            if equipment_slot:
                slot_order = EQUIPMENT_SLOT_SORT_ORDER.get(
                    EquipmentSlot(equipment_slot), 99
                )
                # Equipable items first (0), then by slot order
                return (0, slot_order, rarity_order, item_name)
            else:
                # Non-equipable items last (1), sorted by category
                category_order = CATEGORY_SORT_ORDER.get(
                    ItemCategory(item_meta["category"]), 99
                )
                return (1, category_order, rarity_order, item_name)

        # Default: by slot (no reordering)
        return (slot,)

    @staticmethod
    async def sort_inventory(
        player_id: int, sort_type: InventorySortType
    ) -> OperationResult:
        """
        Sort inventory by the specified criteria.

        Items are compacted to the front (slots 0-N, empty slots at end).
        Stacks are merged before sorting.

        Args:
            player_id: Player ID
            sort_type: How to sort the inventory

        Returns:
            OperationResult with sort statistics
        """
        from .game_state import get_inventory_manager, get_reference_data_manager
        
        inventory_mgr = get_inventory_manager()
        ref_mgr = get_reference_data_manager()
        
        # First, merge stacks
        merge_result = await InventoryService.merge_stacks(player_id)
        stacks_merged = merge_result.data.get("stacks_merged", 0) if merge_result.data else 0

        # If STACK_MERGE only, we're done
        if sort_type == InventorySortType.STACK_MERGE:
            return OperationResult(
                success=True,
                message=f"Merged {stacks_merged} stacks",
                operation=OperationType.SORT,
                data={"items_moved": 0, "stacks_merged": stacks_merged},
            )

        # Get all inventory items from GSM
        inventory_data = await inventory_mgr.get_inventory(player_id)

        if not inventory_data:
            return OperationResult(
                success=True,
                message="Inventory is empty",
                operation=OperationType.SORT,
                data={"items_moved": 0, "stacks_merged": stacks_merged},
            )

        # Create list of items with metadata for sorting
        items_with_meta = []
        for slot_str, slot_data in inventory_data.items():
            slot = int(slot_str)
            item_id = slot_data["item_id"]
            item_meta = ref_mgr.get_cached_item_meta(item_id)
            
            if item_meta:  # Skip items without metadata
                items_with_meta.append((slot, slot_data, item_meta))

        if not items_with_meta:
            return OperationResult(
                success=True,
                message="No valid items to sort",
                operation=OperationType.SORT,
                data={"items_moved": 0, "stacks_merged": stacks_merged},
            )

        # Sort items by the specified criteria
        sorted_items = sorted(
            items_with_meta,
            key=lambda x: InventoryService._get_sort_key(x[0], x[1], x[2], sort_type),
        )

        # Track original positions for counting moves
        original_slots = {slot: slot for slot, _, _ in sorted_items}

        # Clear all current slots first to avoid conflicts
        for slot, _, _ in sorted_items:
            await inventory_mgr.delete_inventory_slot(player_id, slot)

        # Reassign slots in sorted order (compact to front)
        items_moved = 0
        for new_slot, (original_slot, slot_data, item_meta) in enumerate(sorted_items):
            # Set item in new slot
            await inventory_mgr.set_inventory_slot(
                player_id,
                new_slot,
                slot_data["item_id"],
                slot_data["quantity"],
                float(slot_data.get("current_durability", 1.0))
            )
            
            # Count as moved if slot changed
            if original_slot != new_slot:
                items_moved += 1

        logger.info(
            "Sorted inventory",
            extra={
                "player_id": player_id,
                "sort_type": sort_type.value,
                "items_moved": items_moved,
                "stacks_merged": stacks_merged,
            },
        )

        return OperationResult(
            success=True,
            message=f"Sorted by {sort_type.value}",
            operation=OperationType.SORT,
            data={"items_moved": items_moved, "stacks_merged": stacks_merged},
        )
