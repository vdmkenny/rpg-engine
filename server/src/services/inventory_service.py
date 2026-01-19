"""
Service for managing player inventory.

Supports both database-only and Valkey-first operations:
- When a player is online, inventory data is in Valkey for fast access
- When a player is offline, inventory data is only in the database
- Pass state_manager parameter to use Valkey-first operations during gameplay
"""

from typing import Optional, TYPE_CHECKING

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.config import settings
from ..core.items import (
    InventorySortType,
    ItemCategory,
    ItemRarity,
    EquipmentSlot,
    CATEGORY_SORT_ORDER,
    RARITY_SORT_ORDER,
    EQUIPMENT_SLOT_SORT_ORDER,
)
from ..models.item import Item, PlayerInventory
from ..schemas.item import (
    AddItemResult,
    RemoveItemResult,
    MoveItemResult,
    InventorySlotInfo,
    InventoryResponse,
    SortInventoryResult,
    MergeStacksResult,
)
from .item_service import ItemService
from ..core.logging_config import get_logger

if TYPE_CHECKING:
    from .game_state_manager import GameStateManager

logger = get_logger(__name__)


class InventoryService:
    """Service for managing player inventory."""

    @staticmethod
    async def get_inventory(
        db: AsyncSession, player_id: int
    ) -> list:
        """
        Get all inventory items for a player from GSM.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            List of inventory item objects with item_id and quantity properties
        """
        from .game_state_manager import get_game_state_manager
        from dataclasses import dataclass
        
        state_manager = get_game_state_manager()
        
        # Get inventory data from GSM (the single source of truth)
        inventory_data = await state_manager.get_inventory(player_id)
        
        @dataclass
        class InventoryItem:
            """Simple data container matching test expectations."""
            player_id: int
            slot: int
            item_id: int
            quantity: int
            durability: Optional[int] = None
        
        # Convert GSM inventory data to simple objects for test compatibility
        inventory_items = []
        for slot, item_data in inventory_data.items():
            inventory_items.append(InventoryItem(
                player_id=player_id,
                slot=int(slot),
                item_id=item_data["item_id"],
                quantity=item_data["quantity"],
                durability=item_data.get("durability")
            ))
        
        return inventory_items

    @staticmethod
    async def get_inventory_response(
        db: AsyncSession, player_id: int
    ) -> InventoryResponse:
        """
        Get full inventory state for API response.

        Args:
            db: Database session
            player_id: Player ID
            state_manager: Optional GameStateManager for consistent state access

        Returns:
            InventoryResponse with all slot info
        """
        inventory = await InventoryService.get_inventory(db, player_id, state_manager)
        max_slots = settings.INVENTORY_MAX_SLOTS

        slots = []
        for inv in inventory:
            item_info = ItemService.item_to_info(inv.item)
            slots.append(
                InventorySlotInfo(
                    slot=inv.slot,
                    item=item_info,
                    quantity=inv.quantity,
                    current_durability=inv.current_durability,
                )
            )

        return InventoryResponse(
            slots=slots,
            max_slots=max_slots,
            used_slots=len(slots),
            free_slots=max_slots - len(slots),
        )

    @staticmethod
    async def get_item_at_slot(
        db: AsyncSession, player_id: int, slot: int
    ) -> Optional[PlayerInventory]:
        """
        Get inventory item at a specific slot.

        Args:
            db: Database session
            player_id: Player ID
            slot: Slot number (0-based)

        Returns:
            PlayerInventory if slot is occupied, None if empty
        """
        from .game_state_manager import get_game_state_manager
        
        state_manager = get_game_state_manager()
        slot_data = await state_manager.get_inventory_slot(player_id, slot)
        if not slot_data:
            return None
        
        # Get item metadata from GameStateManager's cache
        item_meta = state_manager.get_item_meta(slot_data["item_id"])
        if not item_meta:
            return None
        
        # Create PlayerInventory object from state data
        inventory_item = PlayerInventory(
            player_id=player_id,
            item_id=slot_data["item_id"],
            slot=slot,
            quantity=slot_data["quantity"],
            current_durability=slot_data.get("durability")
        )
        
        # Create a mock Item object from cached metadata
        item = Item(
            id=item_meta["id"],
            name=item_meta["name"],
            display_name=item_meta["display_name"],
            category=item_meta["category"],
            equipment_slot=item_meta["equipment_slot"],
            max_durability=item_meta["max_durability"],
            health_bonus=item_meta.get("health_bonus", 0),
            is_two_handed=item_meta.get("is_two_handed", False),
            required_skill=item_meta.get("required_skill"),
            required_level=item_meta.get("required_level", 1),
        )
        inventory_item.item = item
        return inventory_item

    @staticmethod
    async def get_free_slot(db: AsyncSession, player_id: int) -> Optional[int]:
        """
        Find the first empty inventory slot.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            Slot number if available, None if inventory is full
        """
        # Get all occupied slots
        result = await db.execute(
            select(PlayerInventory.slot)
            .where(PlayerInventory.player_id == player_id)
            .order_by(PlayerInventory.slot)
        )
        occupied_slots = set(result.scalars().all())

        # Find first empty slot
        max_slots = settings.INVENTORY_MAX_SLOTS
        for slot in range(max_slots):
            if slot not in occupied_slots:
                return slot

        return None  # Inventory full

    @staticmethod
    async def get_inventory_count(db: AsyncSession, player_id: int) -> int:
        """
        Get number of occupied inventory slots.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            Number of occupied slots
        """
        result = await db.execute(
            select(func.count(PlayerInventory.id))
            .where(PlayerInventory.player_id == player_id)
        )
        return result.scalar() or 0

    @staticmethod
    async def find_stack_slot(
        db: AsyncSession, player_id: int, item_id: int
    ) -> Optional[PlayerInventory]:
        """
        Find an existing stack of the same item with space available.

        Args:
            db: Database session
            player_id: Player ID
            item_id: Item ID to find

        Returns:
            PlayerInventory if a stackable slot found, None otherwise
        """
        result = await db.execute(
            select(PlayerInventory)
            .where(PlayerInventory.player_id == player_id)
            .where(PlayerInventory.item_id == item_id)
            .options(selectinload(PlayerInventory.item))
        )
        inv = result.scalar_one_or_none()

        if inv and inv.item.max_stack_size > 1:
            # Check if there's room in the stack
            if inv.quantity < inv.item.max_stack_size:
                return inv

        return None

    @staticmethod
    async def add_item(
        db: AsyncSession,
        player_id: int,
        item_id: int,
        quantity: int = 1,
        durability: Optional[int] = None,
    ) -> AddItemResult:
        """
        Add an item to a player's inventory.

        Handles stacking automatically for stackable items.
        If the item is stackable and an existing stack has room, adds to it.
        Otherwise, finds an empty slot.

        Args:
            db: Database session
            player_id: Player ID
            item_id: Item database ID
            quantity: Number of items to add
            durability: Current durability (uses max if None)

        Returns:
            AddItemResult with success status and details
        """
        from .game_state_manager import get_game_state_manager
        
        state_manager = get_game_state_manager()
        if quantity <= 0:
            return AddItemResult(
                success=False,
                message="Quantity must be positive",
            )

        # Get item info (always from DB for metadata)
        item = await ItemService.get_item_by_id(db, item_id)
        if not item:
            return AddItemResult(
                success=False,
                message="Item not found",
            )

        # Set durability to max if not specified and item has durability
        if durability is None and item.max_durability is not None:
            durability = item.max_durability

        # Get current player inventory state
        inventory_data = await state_manager.get_inventory(player_id)

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
                await state_manager.set_inventory_slot(
                    player_id, slot_num, item.id, new_quantity, int(durability) if durability is not None else None
                )
                
                remaining = quantity - add_amount
                if remaining == 0:
                    return AddItemResult(
                        success=True,
                        slot=slot_num,
                        message=f"Added {quantity} {item.display_name} to existing stack",
                    )
                else:
                    # Continue with remaining quantity
                    quantity = remaining

        # Find free slots for remaining items - handle multiple stacks if needed
        first_slot_created = None
        
        while quantity > 0:
            free_slot = await state_manager.get_free_inventory_slot(player_id, settings.INVENTORY_MAX_SLOTS)
            if free_slot is None:
                # No more space available
                if first_slot_created is not None:
                    # Some items were added successfully
                    return AddItemResult(
                        success=True,
                        slot=first_slot_created,
                        overflow_quantity=quantity,
                        message=f"Added items to {item.display_name}, {quantity} items couldn't fit",
                    )
                else:
                    # No items were added
                    return AddItemResult(
                        success=False,
                        overflow_quantity=quantity,
                        message="Inventory is full",
                    )
            
            # Determine how much can go in this slot (respect max_stack_size)
            if item.max_stack_size > 1:
                slot_quantity = min(quantity, item.max_stack_size)
            else:
                slot_quantity = 1  # Non-stackable items
            
            await state_manager.set_inventory_slot(
                player_id, free_slot, item.id, slot_quantity, 
                int(durability) if durability is not None else None
            )
            
            # Remember the first slot for return value
            if first_slot_created is None:
                first_slot_created = free_slot
            
            quantity -= slot_quantity

        # All items successfully added
        return AddItemResult(
            success=True,
            slot=first_slot_created,
            message=f"Added items to {item.display_name}",
        )

    @staticmethod
    async def remove_item(
        db: AsyncSession,
        player_id: int,
        slot: int,
        quantity: int = 1,
    ) -> RemoveItemResult:
        """
        Remove items from a specific inventory slot.

        Args:
            db: Database session
            player_id: Player ID
            slot: Slot number to remove from
            quantity: Number of items to remove

        Returns:
            RemoveItemResult with success status
        """
        from .game_state_manager import get_game_state_manager
        
        state_manager = get_game_state_manager()
        if quantity <= 0:
            return RemoveItemResult(
                success=False,
                message="Quantity must be positive",
                removed_quantity=0,
            )

        # Get player inventory to check current slot status
        slot_data = await state_manager.get_inventory_slot(player_id, slot)
        if not slot_data:
            return RemoveItemResult(
                success=False,
                message="Slot is empty",
                removed_quantity=0,
            )
        
        current_qty = slot_data.get("quantity", 1)
        if current_qty < quantity:
            return RemoveItemResult(
                success=False,
                message=f"Not enough items (have {current_qty}, need {quantity})",
                removed_quantity=0,
            )
        
        new_qty = current_qty - quantity
        if new_qty == 0:
            # Remove the slot entirely
            await state_manager.delete_inventory_slot(player_id, slot)
        else:
            # Update with new quantity
            await state_manager.set_inventory_slot(
                player_id, slot, slot_data["item_id"], new_qty, 
                float(slot_data.get("current_durability", 1.0))
            )
        
        return RemoveItemResult(
            success=True,
            message=f"Removed {quantity} items",
            removed_quantity=quantity,
        )
        inv = await InventoryService.get_item_at_slot(db, player_id, slot)
        if not inv:
            return RemoveItemResult(
                success=False,
                message="Slot is empty",
                removed_quantity=0,
            )

        if inv.quantity < quantity:
            return RemoveItemResult(
                success=False,
                message=f"Not enough items (have {inv.quantity}, need {quantity})",
                removed_quantity=0,
            )

        if inv.quantity == quantity:
            # Remove entire stack
            await db.delete(inv)
        else:
            # Reduce quantity
            inv.quantity -= quantity

        await db.commit()

        logger.info(
            "Removed item from inventory",
            extra={
                "player_id": player_id,
                "slot": slot,
                "quantity": quantity,
            },
        )

        return RemoveItemResult(
            success=True,
            message="Item removed",
            removed_quantity=quantity,
        )

    @staticmethod
    async def move_item(
        db: AsyncSession,
        player_id: int,
        from_slot: int,
        to_slot: int,
    ) -> MoveItemResult:
        """
        Move or swap items between inventory slots.

        If the destination slot is empty, moves the item.
        If occupied, swaps the two items.

        Args:
            db: Database session
            player_id: Player ID
            from_slot: Source slot number
            to_slot: Destination slot number

        Returns:
            MoveItemResult with success status
        """
        from .game_state_manager import get_game_state_manager
        
        state_manager = get_game_state_manager()
        max_slots = settings.INVENTORY_MAX_SLOTS

        if from_slot < 0 or from_slot >= max_slots:
            return MoveItemResult(success=False, message="Invalid source slot")

        if to_slot < 0 or to_slot >= max_slots:
            return MoveItemResult(success=False, message="Invalid destination slot")

        if from_slot == to_slot:
            return MoveItemResult(success=True, message="Same slot")

        # Get current inventory state for move operation
        inventory_data = await state_manager.get_inventory(player_id)
        if not inventory_data:
            return MoveItemResult(success=False, message="Inventory not found")
            
        from_data = inventory_data.get(from_slot)
        if not from_data:
            return MoveItemResult(success=False, message="Source slot is empty")
            
        to_data = inventory_data.get(to_slot)
        
        # Handle move/swap operations
        if to_data:
            # Check if we can merge stacks
            if (
                from_data["item_id"] == to_data["item_id"]
                and from_data.get("quantity", 1) > 1  # Assume stackable if quantity > 1
            ):
                # Get item info to check max_stack_size
                result = await db.execute(select(Item).where(Item.id == from_data["item_id"]))
                item = result.scalar_one_or_none()
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
                            await state_manager.delete_inventory_slot(player_id, from_slot)
                        else:
                            # Update from slot
                            await state_manager.set_inventory_slot(
                                player_id, from_slot, from_data["item_id"], new_from_qty, 
                                float(from_data.get("current_durability", 1.0))
                            )
                        
                        # Update to slot
                        await state_manager.set_inventory_slot(
                            player_id, to_slot, to_data["item_id"], new_to_qty, 
                            float(to_data.get("current_durability", 1.0))
                        )
                        
                        return MoveItemResult(success=True, message=f"Merged {transfer_amount} items")
            
            # Swap items
            await state_manager.set_inventory_slot(
                player_id, from_slot, to_data["item_id"], 
                to_data.get("quantity", 1), float(to_data.get("current_durability", 1.0))
            )
            await state_manager.set_inventory_slot(
                player_id, to_slot, from_data["item_id"], 
                from_data.get("quantity", 1), float(from_data.get("current_durability", 1.0))
            )
            return MoveItemResult(success=True, message="Items swapped")
        else:
            # Move item to empty slot
            await state_manager.set_inventory_slot(
                player_id, to_slot, from_data["item_id"], 
                from_data.get("quantity", 1), float(from_data.get("current_durability", 1.0))
            )
            await state_manager.delete_inventory_slot(player_id, from_slot)
            return MoveItemResult(success=True, message="Item moved")

    @staticmethod
    async def has_item(
        db: AsyncSession,
        player_id: int,
        item_id: int,
        quantity: int = 1,
    ) -> bool:
        """
        Check if player has at least the specified quantity of an item.

        Args:
            db: Database session
            player_id: Player ID
            item_id: Item database ID
            quantity: Required quantity

        Returns:
            True if player has enough items
        """
        result = await db.execute(
            select(func.sum(PlayerInventory.quantity))
            .where(PlayerInventory.player_id == player_id)
            .where(PlayerInventory.item_id == item_id)
        )
        total = result.scalar() or 0
        return total >= quantity

    @staticmethod
    async def clear_inventory(db: AsyncSession, player_id: int) -> int:
        """
        Remove all items from a player's inventory.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            Number of slots cleared
        """
        result = await db.execute(
            delete(PlayerInventory).where(PlayerInventory.player_id == player_id)
        )
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def merge_stacks(
        db: AsyncSession, player_id: int
    ) -> MergeStacksResult:
        """
        Merge all split stacks of the same item type.

        Does not reorder items, only consolidates stacks.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            MergeStacksResult with merge statistics
        """
        # Get all inventory items grouped by item_id
        result = await db.execute(
            select(PlayerInventory)
            .where(PlayerInventory.player_id == player_id)
            .options(selectinload(PlayerInventory.item))
            .order_by(PlayerInventory.slot)
        )
        all_items = list(result.scalars().all())

        # Group by item_id for stackable items
        item_stacks: dict[int, list[PlayerInventory]] = {}
        for inv in all_items:
            if inv.item.max_stack_size > 1:
                if inv.item_id not in item_stacks:
                    item_stacks[inv.item_id] = []
                item_stacks[inv.item_id].append(inv)

        stacks_merged = 0
        slots_freed = 0

        for item_id, stacks in item_stacks.items():
            if len(stacks) <= 1:
                continue

            # Get max stack size for this item
            max_stack = stacks[0].item.max_stack_size

            # Merge stacks into the first one, remove empty ones
            primary_stack = stacks[0]
            for secondary_stack in stacks[1:]:
                # Calculate how much can be transferred
                space_available = max_stack - primary_stack.quantity
                transfer_amount = min(secondary_stack.quantity, space_available)

                if transfer_amount > 0:
                    primary_stack.quantity += transfer_amount
                    secondary_stack.quantity -= transfer_amount
                    stacks_merged += 1

                # If secondary stack is empty, delete it
                if secondary_stack.quantity == 0:
                    await db.delete(secondary_stack)
                    slots_freed += 1
                elif primary_stack.quantity >= max_stack:
                    # Primary stack is full, make secondary the new primary
                    primary_stack = secondary_stack

        await db.commit()

        logger.info(
            "Merged inventory stacks",
            extra={
                "player_id": player_id,
                "stacks_merged": stacks_merged,
                "slots_freed": slots_freed,
            },
        )

        return MergeStacksResult(
            success=True,
            message=f"Merged {stacks_merged} stacks, freed {slots_freed} slots",
            stacks_merged=stacks_merged,
            slots_freed=slots_freed,
        )

    @staticmethod
    def _get_sort_key(
        inv: PlayerInventory, sort_type: InventorySortType
    ) -> tuple:
        """
        Get sort key for an inventory item based on sort type.

        Returns a tuple for multi-level sorting.
        Secondary sort is always by rarity (descending), then name (alphabetical).
        """
        item = inv.item

        # Get rarity and name for secondary sort
        rarity_order = RARITY_SORT_ORDER.get(
            ItemRarity.from_value(item.rarity), 99
        )
        item_name = item.display_name.lower()

        if sort_type == InventorySortType.BY_CATEGORY:
            category_order = CATEGORY_SORT_ORDER.get(
                ItemCategory(item.category), 99
            )
            return (category_order, rarity_order, item_name)

        elif sort_type == InventorySortType.BY_RARITY:
            return (rarity_order, item_name)

        elif sort_type == InventorySortType.BY_VALUE:
            # Negative value so higher values come first
            return (-item.value, rarity_order, item_name)

        elif sort_type == InventorySortType.BY_NAME:
            return (item_name, rarity_order)

        elif sort_type == InventorySortType.BY_EQUIPMENT_SLOT:
            if item.equipment_slot:
                slot_order = EQUIPMENT_SLOT_SORT_ORDER.get(
                    EquipmentSlot(item.equipment_slot), 99
                )
                # Equipable items first (0), then by slot order
                return (0, slot_order, rarity_order, item_name)
            else:
                # Non-equipable items last (1), sorted by category
                category_order = CATEGORY_SORT_ORDER.get(
                    ItemCategory(item.category), 99
                )
                return (1, category_order, rarity_order, item_name)

        # Default: by slot (no reordering)
        return (inv.slot,)

    @staticmethod
    async def sort_inventory(
        db: AsyncSession, player_id: int, sort_type: InventorySortType
    ) -> SortInventoryResult:
        """
        Sort inventory by the specified criteria.

        Items are compacted to the front (slots 0-N, empty slots at end).
        Stacks are merged before sorting.

        Args:
            db: Database session
            player_id: Player ID
            sort_type: How to sort the inventory

        Returns:
            SortInventoryResult with sort statistics
        """
        # First, merge stacks
        merge_result = await InventoryService.merge_stacks(db, player_id)
        stacks_merged = merge_result.stacks_merged

        # If STACK_MERGE only, we're done
        if sort_type == InventorySortType.STACK_MERGE:
            return SortInventoryResult(
                success=True,
                message=f"Merged {stacks_merged} stacks",
                items_moved=0,
                stacks_merged=stacks_merged,
            )

        # Get all inventory items
        result = await db.execute(
            select(PlayerInventory)
            .where(PlayerInventory.player_id == player_id)
            .options(selectinload(PlayerInventory.item))
        )
        all_items = list(result.scalars().all())

        if not all_items:
            return SortInventoryResult(
                success=True,
                message="Inventory is empty",
                items_moved=0,
                stacks_merged=stacks_merged,
            )

        # Sort items by the specified criteria
        sorted_items = sorted(
            all_items,
            key=lambda inv: InventoryService._get_sort_key(inv, sort_type),
        )

        # Track original positions for counting moves
        original_slots = {inv.id: inv.slot for inv in sorted_items}

        # Assign new slots (compact to front)
        # First, move all items to temporary negative slots to avoid UNIQUE constraint
        # violations during reordering
        for i, inv in enumerate(sorted_items):
            inv.slot = -(i + 1)  # Use negative slots: -1, -2, -3, ...
        await db.flush()

        # Now assign final slots
        items_moved = 0
        for new_slot, inv in enumerate(sorted_items):
            inv.slot = new_slot
            if original_slots[inv.id] != new_slot:
                items_moved += 1

        await db.commit()

        logger.info(
            "Sorted inventory",
            extra={
                "player_id": player_id,
                "sort_type": sort_type.value,
                "items_moved": items_moved,
                "stacks_merged": stacks_merged,
            },
        )

        return SortInventoryResult(
            success=True,
            message=f"Sorted by {sort_type.value}",
            items_moved=items_moved,
            stacks_merged=stacks_merged,
        )
