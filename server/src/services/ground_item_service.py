"""
Service for managing ground items (dropped items in the world).

Ground items have:
- Rarity-based despawn timers
- Loot protection period (only dropper can pick up initially)
- Visibility based on chunk range
- Death drop mechanics
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.config import settings
from ..core.items import ItemRarity
from ..models.item import Item, GroundItem, PlayerInventory, PlayerEquipment
from ..schemas.item import (
    DropItemResult,
    PickupItemResult,
    GroundItemInfo,
    GroundItemsResponse,
)
from .item_service import ItemService
from .inventory_service import InventoryService


def _utc_now_naive() -> datetime:
    """
    Get current UTC time as a naive datetime.
    
    SQLite doesn't preserve timezone info, so we use naive datetimes
    for consistency across both SQLite (tests) and PostgreSQL (production).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

logger = logging.getLogger(__name__)


class GroundItemService:
    """Service for managing items dropped on the ground."""

    @staticmethod
    def _get_despawn_seconds(rarity: str) -> int:
        """Get despawn time in seconds for item rarity."""
        return settings.GROUND_ITEMS_DESPAWN_TIMES.get(rarity, 120)

    @staticmethod
    def _get_protection_seconds(rarity: str) -> int:
        """Get loot protection time in seconds for item rarity."""
        return settings.GROUND_ITEMS_LOOT_PROTECTION_TIMES.get(rarity, 45)

    @staticmethod
    async def create_ground_item(
        db: AsyncSession,
        item_id: int,
        map_id: str,
        x: int,
        y: int,
        quantity: int = 1,
        dropped_by: Optional[int] = None,
        current_durability: Optional[int] = None,
    ) -> Optional[GroundItem]:
        """
        Create a ground item (drop item on the ground).

        Args:
            db: Database session
            item_id: Item database ID
            map_id: Map where item is dropped
            x: Tile X position
            y: Tile Y position
            quantity: Number of items in stack
            dropped_by: Player ID who dropped the item (None for world spawns)
            current_durability: Current durability if applicable

        Returns:
            The created GroundItem or None if item not found
        """
        # Get item info for rarity-based timers
        item = await ItemService.get_item_by_id(db, item_id)
        if not item:
            logger.warning(
                "Cannot create ground item - item not found",
                extra={"item_id": item_id},
            )
            return None

        now = _utc_now_naive()
        rarity = item.rarity

        # Calculate protection and despawn times based on rarity
        protection_seconds = GroundItemService._get_protection_seconds(rarity)
        despawn_seconds = GroundItemService._get_despawn_seconds(rarity)

        public_at = now + timedelta(seconds=protection_seconds)
        despawn_at = now + timedelta(seconds=despawn_seconds)

        ground_item = GroundItem(
            item_id=item_id,
            map_id=map_id,
            x=x,
            y=y,
            quantity=quantity,
            current_durability=current_durability,
            dropped_by=dropped_by,
            public_at=public_at,
            despawn_at=despawn_at,
        )

        db.add(ground_item)
        await db.commit()
        await db.refresh(ground_item)

        logger.info(
            "Created ground item",
            extra={
                "ground_item_id": ground_item.id,
                "item_id": item_id,
                "map_id": map_id,
                "x": x,
                "y": y,
                "quantity": quantity,
                "dropped_by": dropped_by,
                "despawn_at": despawn_at.isoformat(),
            },
        )

        return ground_item

    @staticmethod
    async def drop_from_inventory(
        db: AsyncSession,
        player_id: int,
        inventory_slot: int,
        map_id: str,
        x: int,
        y: int,
        quantity: Optional[int] = None,
    ) -> DropItemResult:
        """
        Drop an item from player's inventory onto the ground.

        Args:
            db: Database session
            player_id: Player dropping the item
            inventory_slot: Inventory slot to drop from
            map_id: Current map
            x: Player's tile X position
            y: Player's tile Y position
            quantity: Number to drop (None = entire stack)

        Returns:
            DropItemResult with success status
        """
        # Get the inventory item
        inv_item = await InventoryService.get_item_at_slot(db, player_id, inventory_slot)
        if not inv_item:
            return DropItemResult(
                success=False,
                message="Inventory slot is empty",
            )

        # Determine quantity to drop
        drop_quantity = quantity if quantity is not None else inv_item.quantity
        if drop_quantity <= 0:
            return DropItemResult(
                success=False,
                message="Quantity must be positive",
            )
        if drop_quantity > inv_item.quantity:
            return DropItemResult(
                success=False,
                message=f"Not enough items (have {inv_item.quantity}, want to drop {drop_quantity})",
            )

        # Create ground item
        ground_item = await GroundItemService.create_ground_item(
            db=db,
            item_id=inv_item.item_id,
            map_id=map_id,
            x=x,
            y=y,
            quantity=drop_quantity,
            dropped_by=player_id,
            current_durability=inv_item.current_durability,
        )

        if not ground_item:
            return DropItemResult(
                success=False,
                message="Failed to create ground item",
            )

        # Remove from inventory
        remove_result = await InventoryService.remove_item(
            db, player_id, inventory_slot, drop_quantity
        )

        if not remove_result.success:
            # Rollback ground item creation
            await db.delete(ground_item)
            await db.commit()
            return DropItemResult(
                success=False,
                message=f"Failed to remove from inventory: {remove_result.message}",
            )

        logger.info(
            "Player dropped item",
            extra={
                "player_id": player_id,
                "item_id": inv_item.item_id,
                "quantity": drop_quantity,
                "ground_item_id": ground_item.id,
            },
        )

        return DropItemResult(
            success=True,
            message="Item dropped",
            ground_item_id=ground_item.id,
        )

    @staticmethod
    async def pickup_item(
        db: AsyncSession,
        player_id: int,
        ground_item_id: int,
        player_x: int,
        player_y: int,
    ) -> PickupItemResult:
        """
        Pick up a ground item.

        Player must be on the same tile as the item.
        Item must be visible (either owned by player or past protection time).
        Player must have inventory space.

        Uses SELECT FOR UPDATE to prevent race conditions when multiple
        players try to pick up the same item simultaneously.

        Args:
            db: Database session
            player_id: Player picking up the item
            ground_item_id: Ground item ID
            player_x: Player's current tile X
            player_y: Player's current tile Y

        Returns:
            PickupItemResult with success status
        """
        # Get the ground item with a row lock to prevent race conditions
        # If another transaction has already locked this row, we wait for it
        # If the item was deleted, we get None
        result = await db.execute(
            select(GroundItem)
            .where(GroundItem.id == ground_item_id)
            .options(selectinload(GroundItem.item))
            .with_for_update(skip_locked=False)
        )
        ground_item = result.scalar_one_or_none()

        if not ground_item:
            return PickupItemResult(
                success=False,
                message="Item not found or already picked up",
            )

        # Check if item has despawned
        now = _utc_now_naive()
        if ground_item.despawn_at <= now:
            await db.delete(ground_item)
            await db.commit()
            return PickupItemResult(
                success=False,
                message="Item has despawned",
            )

        # Check if player is on the same tile
        if ground_item.x != player_x or ground_item.y != player_y:
            return PickupItemResult(
                success=False,
                message="You must be on the same tile to pick up this item",
            )

        # Check loot protection
        is_owner = ground_item.dropped_by == player_id
        is_public = ground_item.public_at <= now

        if not is_owner and not is_public:
            return PickupItemResult(
                success=False,
                message="This item is protected",
            )

        # Try to add to inventory
        add_result = await InventoryService.add_item(
            db=db,
            player_id=player_id,
            item_id=ground_item.item_id,
            quantity=ground_item.quantity,
            durability=ground_item.current_durability,
        )

        if not add_result.success:
            return PickupItemResult(
                success=False,
                message=add_result.message,
            )

        # Handle partial pickup (inventory was partially full)
        if add_result.overflow_quantity and add_result.overflow_quantity > 0:
            # Update ground item with remaining quantity
            ground_item.quantity = add_result.overflow_quantity
            await db.commit()
            
            logger.info(
                "Partial item pickup",
                extra={
                    "player_id": player_id,
                    "ground_item_id": ground_item_id,
                    "picked_up": ground_item.quantity - add_result.overflow_quantity,
                    "remaining": add_result.overflow_quantity,
                },
            )
            
            return PickupItemResult(
                success=True,
                message="Picked up partial stack (inventory full)",
                inventory_slot=add_result.slot,
            )

        # Remove ground item completely
        await db.delete(ground_item)
        await db.commit()

        logger.info(
            "Player picked up item",
            extra={
                "player_id": player_id,
                "ground_item_id": ground_item_id,
                "item_id": ground_item.item_id,
                "quantity": ground_item.quantity,
                "inventory_slot": add_result.slot,
            },
        )

        return PickupItemResult(
            success=True,
            message="Item picked up",
            inventory_slot=add_result.slot,
        )

    @staticmethod
    async def get_ground_item(
        db: AsyncSession, ground_item_id: int
    ) -> Optional[GroundItem]:
        """Get a ground item by ID."""
        result = await db.execute(
            select(GroundItem)
            .where(GroundItem.id == ground_item_id)
            .options(selectinload(GroundItem.item))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_visible_ground_items(
        db: AsyncSession,
        player_id: int,
        map_id: str,
        center_x: int,
        center_y: int,
        tile_radius: int = 16,
    ) -> GroundItemsResponse:
        """
        Get all ground items visible to a player.

        Visible items are:
        - Items dropped by this player (regardless of protection)
        - Items past their protection time (public)

        Args:
            db: Database session
            player_id: Player ID
            map_id: Current map
            center_x: Player's tile X position
            center_y: Player's tile Y position
            tile_radius: Visibility radius in tiles

        Returns:
            GroundItemsResponse with visible items
        """
        now = _utc_now_naive()

        # Query for visible items in range
        # Items are visible if: dropped by player OR public_at <= now
        # AND not yet despawned
        min_x = center_x - tile_radius
        max_x = center_x + tile_radius
        min_y = center_y - tile_radius
        max_y = center_y + tile_radius

        result = await db.execute(
            select(GroundItem)
            .where(
                and_(
                    GroundItem.map_id == map_id,
                    GroundItem.x >= min_x,
                    GroundItem.x <= max_x,
                    GroundItem.y >= min_y,
                    GroundItem.y <= max_y,
                    GroundItem.despawn_at > now,
                    # Visible if owned by player OR public
                    (GroundItem.dropped_by == player_id) | (GroundItem.public_at <= now),
                )
            )
            .options(selectinload(GroundItem.item))
        )
        ground_items = list(result.scalars().all())

        items = []
        for gi in ground_items:
            item_info = ItemService.item_to_info(gi.item)
            is_yours = gi.dropped_by == player_id
            is_protected = gi.public_at > now

            items.append(
                GroundItemInfo(
                    id=gi.id,
                    item=item_info,
                    x=gi.x,
                    y=gi.y,
                    quantity=gi.quantity,
                    is_yours=is_yours,
                    is_protected=is_protected and not is_yours,
                )
            )

        return GroundItemsResponse(
            items=items,
            map_id=map_id,
        )

    @staticmethod
    async def cleanup_expired_items(db: AsyncSession) -> int:
        """
        Delete all ground items past their despawn time.

        Should be called periodically by a background task.

        Args:
            db: Database session

        Returns:
            Number of items cleaned up
        """
        now = _utc_now_naive()

        result = await db.execute(
            delete(GroundItem).where(GroundItem.despawn_at <= now)
        )
        await db.commit()

        count = result.rowcount or 0
        if count > 0:
            logger.info(
                "Cleaned up expired ground items",
                extra={"count": count},
            )

        return count

    @staticmethod
    async def drop_player_items_on_death(
        db: AsyncSession,
        player_id: int,
        map_id: str,
        x: int,
        y: int,
    ) -> int:
        """
        Drop all player inventory and equipment on death.

        Hardcore mode: everything drops.

        Args:
            db: Database session
            player_id: Player who died
            map_id: Map where player died
            x: Death tile X position
            y: Death tile Y position

        Returns:
            Number of items dropped
        """
        items_dropped = 0

        # Get all inventory items
        result = await db.execute(
            select(PlayerInventory)
            .where(PlayerInventory.player_id == player_id)
            .options(selectinload(PlayerInventory.item))
        )
        inventory_items = list(result.scalars().all())

        # Drop each inventory item
        for inv in inventory_items:
            ground_item = await GroundItemService.create_ground_item(
                db=db,
                item_id=inv.item_id,
                map_id=map_id,
                x=x,
                y=y,
                quantity=inv.quantity,
                dropped_by=player_id,
                current_durability=inv.current_durability,
            )
            if ground_item:
                items_dropped += 1

        # Clear inventory
        await db.execute(
            delete(PlayerInventory).where(PlayerInventory.player_id == player_id)
        )

        # Get all equipment items
        result = await db.execute(
            select(PlayerEquipment)
            .where(PlayerEquipment.player_id == player_id)
            .options(selectinload(PlayerEquipment.item))
        )
        equipment_items = list(result.scalars().all())

        # Drop each equipped item
        for equip in equipment_items:
            ground_item = await GroundItemService.create_ground_item(
                db=db,
                item_id=equip.item_id,
                map_id=map_id,
                x=x,
                y=y,
                quantity=equip.quantity,  # Preserve quantity for stackable items (ammo)
                dropped_by=player_id,
                current_durability=equip.current_durability,
            )
            if ground_item:
                items_dropped += 1

        # Clear equipment
        await db.execute(
            delete(PlayerEquipment).where(PlayerEquipment.player_id == player_id)
        )

        await db.commit()

        logger.info(
            "Dropped player items on death",
            extra={
                "player_id": player_id,
                "items_dropped": items_dropped,
                "map_id": map_id,
                "x": x,
                "y": y,
            },
        )

        return items_dropped

    @staticmethod
    async def get_items_at_position(
        db: AsyncSession,
        map_id: str,
        x: int,
        y: int,
    ) -> list[GroundItem]:
        """
        Get all ground items at a specific tile position.

        Args:
            db: Database session
            map_id: Map ID
            x: Tile X position
            y: Tile Y position

        Returns:
            List of ground items at this position
        """
        now = _utc_now_naive()

        result = await db.execute(
            select(GroundItem)
            .where(
                and_(
                    GroundItem.map_id == map_id,
                    GroundItem.x == x,
                    GroundItem.y == y,
                    GroundItem.despawn_at > now,
                )
            )
            .options(selectinload(GroundItem.item))
        )
        return list(result.scalars().all())
