"""
Service for managing player inventory.

Supports both database-only and Valkey-first operations:
- When a player is online, inventory data is in Valkey for fast access
- When a player is offline, inventory data is only in the database
- Pass state_manager parameter to use Valkey-first operations during gameplay
"""

import logging
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

if TYPE_CHECKING:
    from .game_state_manager import GameStateManager

logger = logging.getLogger(__name__)


class InventoryService:
    """Service for managing player inventory."""

    @staticmethod
    async def get_inventory(
        db: AsyncSession, player_id: int
    ) -> list[PlayerInventory]:
        """
        Get all inventory items for a player.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            List of PlayerInventory entries with loaded items
        """
        result = await db.execute(
            select(PlayerInventory)
            .where(PlayerInventory.player_id == player_id)
            .options(selectinload(PlayerInventory.item))
            .order_by(PlayerInventory.slot)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_inventory_response(
        db: AsyncSession, player_id: int
    ) -> InventoryResponse:
        """
        Get full inventory state for API response.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            InventoryResponse with all slot info
        """
        inventory = await InventoryService.get_inventory(db, player_id)
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
        result = await db.execute(
            select(PlayerInventory)
            .where(PlayerInventory.player_id == player_id)
            .where(PlayerInventory.slot == slot)
            .options(selectinload(PlayerInventory.item))
        )
        return result.scalar_one_or_none()

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
        state_manager: Optional["GameStateManager"] = None,
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
            state_manager: Optional GameStateManager for online player operations

        Returns:
            AddItemResult with success status and details
        """
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

        # Use Valkey-first path if player is online
        if state_manager and state_manager.is_online(player_id):
            return await InventoryService._add_item_valkey(
                state_manager, player_id, item, quantity, durability
            )

        # Database-only path (for registration, offline operations, etc.)
        return await InventoryService._add_item_db(
            db, player_id, item, quantity, durability
        )

    @staticmethod
    async def _add_item_valkey(
        state_manager: "GameStateManager",
        player_id: int,
        item: Item,
        quantity: int,
        durability: Optional[int],
    ) -> AddItemResult:
        """Valkey-first implementation of add_item using GameStateManager."""
        remaining_quantity = quantity
        first_slot = None
        max_slots = settings.INVENTORY_MAX_SLOTS

        # Get current inventory from Valkey via state manager
        inventory = await state_manager.get_inventory(player_id)

        # Try to stack with existing items
        if item.max_stack_size > 1:
            for slot, data in inventory.items():
                if data["item_id"] == item.id:
                    space_in_stack = item.max_stack_size - data["quantity"]
                    if space_in_stack > 0:
                        add_to_stack = min(remaining_quantity, space_in_stack)
                        new_quantity = data["quantity"] + add_to_stack
                        await state_manager.set_inventory_slot(
                            player_id, slot,
                            data["item_id"], new_quantity, data.get("durability")
                        )
                        remaining_quantity -= add_to_stack
                        if first_slot is None:
                            first_slot = slot

                        logger.debug(
                            "Added to existing stack (Valkey)",
                            extra={
                                "player_id": player_id,
                                "slot": slot,
                                "added": add_to_stack,
                                "new_quantity": new_quantity,
                            },
                        )

                    if remaining_quantity <= 0:
                        break

        # Add remaining items to new slots
        used_slots = set(inventory.keys())
        slot = 0
        while remaining_quantity > 0:
            # Find next free slot
            while slot in used_slots and slot < max_slots:
                slot += 1

            if slot >= max_slots:
                return AddItemResult(
                    success=remaining_quantity < quantity,
                    message="Inventory full" if remaining_quantity == quantity else "Partial add - inventory full",
                    slot=first_slot,
                    overflow_quantity=remaining_quantity,
                )

            # Determine quantity for this slot
            slot_quantity = min(remaining_quantity, item.max_stack_size)

            await state_manager.set_inventory_slot(
                player_id, slot,
                item.id, slot_quantity, durability
            )

            if first_slot is None:
                first_slot = slot

            used_slots.add(slot)
            remaining_quantity -= slot_quantity
            slot += 1

            logger.debug(
                "Added new inventory slot (Valkey)",
                extra={
                    "player_id": player_id,
                    "slot": slot - 1,
                    "item_id": item.id,
                    "quantity": slot_quantity,
                },
            )

        logger.info(
            "Added item to inventory (Valkey)",
            extra={
                "player_id": player_id,
                "item_id": item.id,
                "quantity": quantity,
                "first_slot": first_slot,
            },
        )

        return AddItemResult(
            success=True,
            message="Item added to inventory",
            slot=first_slot,
            overflow_quantity=0,
        )

    @staticmethod
    async def _add_item_db(
        db: AsyncSession,
        player_id: int,
        item: Item,
        quantity: int,
        durability: Optional[int],
    ) -> AddItemResult:
        """Database-only implementation of add_item (original logic)."""
        remaining_quantity = quantity
        first_slot = None

        # Try to stack with existing items
        if item.max_stack_size > 1:
            # Find all stacks of this item
            result = await db.execute(
                select(PlayerInventory)
                .where(PlayerInventory.player_id == player_id)
                .where(PlayerInventory.item_id == item.id)
                .options(selectinload(PlayerInventory.item))
                .order_by(PlayerInventory.slot)
            )
            existing_stacks = list(result.scalars().all())

            for stack in existing_stacks:
                space_in_stack = item.max_stack_size - stack.quantity
                if space_in_stack > 0:
                    add_to_stack = min(remaining_quantity, space_in_stack)
                    stack.quantity += add_to_stack
                    remaining_quantity -= add_to_stack
                    if first_slot is None:
                        first_slot = stack.slot

                    logger.debug(
                        "Added to existing stack",
                        extra={
                            "player_id": player_id,
                            "slot": stack.slot,
                            "added": add_to_stack,
                            "new_quantity": stack.quantity,
                        },
                    )

                if remaining_quantity <= 0:
                    break

        # Add remaining items to new slots
        while remaining_quantity > 0:
            slot = await InventoryService.get_free_slot(db, player_id)
            if slot is None:
                await db.commit()
                return AddItemResult(
                    success=remaining_quantity < quantity,
                    message="Inventory full" if remaining_quantity == quantity else "Partial add - inventory full",
                    slot=first_slot,
                    overflow_quantity=remaining_quantity,
                )

            # Determine quantity for this slot
            slot_quantity = min(remaining_quantity, item.max_stack_size)

            new_inv = PlayerInventory(
                player_id=player_id,
                item_id=item.id,
                slot=slot,
                quantity=slot_quantity,
                current_durability=durability,
            )
            db.add(new_inv)
            await db.flush()  # Flush so get_free_slot sees this slot as occupied

            if first_slot is None:
                first_slot = slot

            remaining_quantity -= slot_quantity

            logger.debug(
                "Added new inventory slot",
                extra={
                    "player_id": player_id,
                    "slot": slot,
                    "item_id": item.id,
                    "quantity": slot_quantity,
                },
            )

        await db.commit()

        logger.info(
            "Added item to inventory",
            extra={
                "player_id": player_id,
                "item_id": item.id,
                "quantity": quantity,
                "first_slot": first_slot,
            },
        )

        return AddItemResult(
            success=True,
            message="Item added to inventory",
            slot=first_slot,
            overflow_quantity=0,
        )

    @staticmethod
    async def remove_item(
        db: AsyncSession,
        player_id: int,
        slot: int,
        quantity: int = 1,
        state_manager: Optional["GameStateManager"] = None,
    ) -> RemoveItemResult:
        """
        Remove items from a specific inventory slot.

        Args:
            db: Database session
            player_id: Player ID
            slot: Slot number to remove from
            quantity: Number of items to remove
            state_manager: Optional GameStateManager for online player operations

        Returns:
            RemoveItemResult with success status
        """
        if quantity <= 0:
            return RemoveItemResult(
                success=False,
                message="Quantity must be positive",
                removed_quantity=0,
            )

        # Use Valkey-first path if player is online
        if state_manager and state_manager.is_online(player_id):
            return await InventoryService._remove_item_valkey(
                state_manager, player_id, slot, quantity
            )

        # Database-only path
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
    async def _remove_item_valkey(
        state_manager: "GameStateManager",
        player_id: int,
        slot: int,
        quantity: int,
    ) -> RemoveItemResult:
        """Valkey-first implementation of remove_item using GameStateManager."""
        slot_data = await state_manager.get_inventory_slot(player_id, slot)

        if not slot_data:
            return RemoveItemResult(
                success=False,
                message="Slot is empty",
                removed_quantity=0,
            )

        if slot_data["quantity"] < quantity:
            return RemoveItemResult(
                success=False,
                message=f"Not enough items (have {slot_data['quantity']}, need {quantity})",
                removed_quantity=0,
            )

        if slot_data["quantity"] == quantity:
            # Remove entire stack
            await state_manager.delete_inventory_slot(player_id, slot)
        else:
            # Reduce quantity
            new_quantity = slot_data["quantity"] - quantity
            await state_manager.set_inventory_slot(
                player_id, slot,
                slot_data["item_id"], new_quantity, slot_data.get("durability")
            )

        logger.info(
            "Removed item from inventory (Valkey)",
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
        max_slots = settings.INVENTORY_MAX_SLOTS

        if from_slot < 0 or from_slot >= max_slots:
            return MoveItemResult(success=False, message="Invalid source slot")

        if to_slot < 0 or to_slot >= max_slots:
            return MoveItemResult(success=False, message="Invalid destination slot")

        if from_slot == to_slot:
            return MoveItemResult(success=True, message="Same slot")

        from_inv = await InventoryService.get_item_at_slot(db, player_id, from_slot)
        if not from_inv:
            return MoveItemResult(success=False, message="Source slot is empty")

        to_inv = await InventoryService.get_item_at_slot(db, player_id, to_slot)

        if to_inv:
            # Check if we can merge stacks
            if (
                from_inv.item_id == to_inv.item_id
                and from_inv.item.max_stack_size > 1
            ):
                # Merge stacks
                space_available = from_inv.item.max_stack_size - to_inv.quantity
                transfer_amount = min(from_inv.quantity, space_available)

                if transfer_amount > 0:
                    to_inv.quantity += transfer_amount
                    from_inv.quantity -= transfer_amount

                    if from_inv.quantity == 0:
                        await db.delete(from_inv)

                    await db.commit()
                    return MoveItemResult(success=True, message="Stacks merged")

            # Swap items - use temporary slot to avoid UNIQUE constraint violation
            # SQLAlchemy may emit UPDATEs in any order, so we need to avoid
            # having two rows with the same slot at any point
            temp_slot = -1  # Temporary slot (negative to avoid conflicts)
            from_inv.slot = temp_slot
            await db.flush()  # Ensure temp slot is applied
            to_inv.slot = from_slot
            await db.flush()  # Ensure to_inv is moved
            from_inv.slot = to_slot
        else:
            # Move to empty slot
            from_inv.slot = to_slot

        await db.commit()

        logger.info(
            "Moved inventory item",
            extra={
                "player_id": player_id,
                "from_slot": from_slot,
                "to_slot": to_slot,
                "swapped": to_inv is not None,
            },
        )

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
