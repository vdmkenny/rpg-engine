"""
Service for managing ground items (dropped items in the world).

Ground items have:
- Rarity-based despawn timers
- Loot protection period (only dropper can pick up initially)
- Visibility based on chunk range
- Death drop mechanics

Ground items are stored in Valkey (via GSM) and synced to PostgreSQL periodically.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.items import ItemRarity
from ..core.logging_config import get_logger
from ..models.item import Item
from ..schemas.item import (
    DropItemResult,
    PickupItemResult,
    GroundItemInfo,
    GroundItemsResponse,
    ItemInfo,
)
from .game_state_manager import get_game_state_manager

logger = get_logger(__name__)


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
    def _get_rarity_color(rarity: str) -> str:
        """Get hex color for item rarity."""
        try:
            return ItemRarity.from_value(rarity).color
        except ValueError:
            return "#ffffff"  # Default to white

    @staticmethod
    async def create_ground_item(
        item_id: int,
        map_id: str,
        x: int,
        y: int,
        quantity: int = 1,
        dropped_by: Optional[int] = None,
        current_durability: Optional[int] = None,
    ) -> Optional[int]:
        """
        Create a ground item (drop item on the ground).

        Args:
            item_id: Item database ID
            map_id: Map where item is dropped
            x: Tile X position
            y: Tile Y position
            quantity: Number of items in stack
            dropped_by: Player ID who dropped the item (None for world spawns)
            current_durability: Current durability if applicable

        Returns:
            The ground item ID or None if item not found
        """
        gsm = get_game_state_manager()

        # Get item info for rarity-based timers
        async with gsm._db_session() as db:
            result = await db.execute(select(Item).where(Item.id == item_id))
            item = result.scalar_one_or_none()

        if not item:
            logger.warning(
                "Cannot create ground item - item not found",
                extra={"item_id": item_id},
            )
            return None

        ground_item_id = await gsm.add_ground_item(
            item_id=item_id,
            item_name=item.name,
            display_name=item.display_name,
            rarity=item.rarity,
            map_id=map_id,
            x=x,
            y=y,
            quantity=quantity,
            dropped_by_player_id=dropped_by,
            category=item.category,
            rarity_color=GroundItemService._get_rarity_color(item.rarity),
            max_stack_size=item.max_stack_size,
        )

        logger.info(
            "Created ground item",
            extra={
                "ground_item_id": ground_item_id,
                "item_id": item_id,
                "map_id": map_id,
                "x": x,
                "y": y,
                "quantity": quantity,
                "dropped_by": dropped_by,
            },
        )

        return ground_item_id

    @staticmethod
    async def drop_from_inventory(
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
            player_id: Player dropping the item
            inventory_slot: Inventory slot to drop from
            map_id: Current map
            x: Player's tile X position
            y: Player's tile Y position
            quantity: Number to drop (None = entire stack)

        Returns:
            DropItemResult with success status
        """
        gsm = get_game_state_manager()

        # Get the inventory item from GSM
        slot_data = await gsm.get_inventory_slot(player_id, inventory_slot)
        if not slot_data:
            return DropItemResult(
                success=False,
                message="Inventory slot is empty",
            )

        item_id = slot_data["item_id"]
        current_quantity = slot_data["quantity"]
        durability = slot_data.get("durability")

        # Determine quantity to drop
        drop_quantity = quantity if quantity is not None else current_quantity
        if drop_quantity <= 0:
            return DropItemResult(
                success=False,
                message="Quantity must be positive",
            )
        if drop_quantity > current_quantity:
            return DropItemResult(
                success=False,
                message=f"Not enough items (have {current_quantity}, want to drop {drop_quantity})",
            )

        # Get item info for ground item creation
        async with gsm._db_session() as db:
            result = await db.execute(select(Item).where(Item.id == item_id))
            item = result.scalar_one_or_none()

        if not item:
            return DropItemResult(
                success=False,
                message="Item not found",
            )

        # Create ground item
        ground_item_id = await gsm.add_ground_item(
            item_id=item_id,
            item_name=item.name,
            display_name=item.display_name,
            rarity=item.rarity,
            map_id=map_id,
            x=x,
            y=y,
            quantity=drop_quantity,
            dropped_by_player_id=player_id,
            category=item.category,
            rarity_color=GroundItemService._get_rarity_color(item.rarity),
            max_stack_size=item.max_stack_size,
        )

        if not ground_item_id:
            return DropItemResult(
                success=False,
                message="Failed to create ground item",
            )

        # Update or remove from inventory
        if drop_quantity >= current_quantity:
            await gsm.delete_inventory_slot(player_id, inventory_slot)
        else:
            await gsm.set_inventory_slot(
                player_id,
                inventory_slot,
                item_id,
                current_quantity - drop_quantity,
                durability,
            )

        logger.info(
            "Player dropped item",
            extra={
                "player_id": player_id,
                "item_id": item_id,
                "quantity": drop_quantity,
                "ground_item_id": ground_item_id,
            },
        )

        return DropItemResult(
            success=True,
            message="Item dropped",
            ground_item_id=ground_item_id,
        )

    @staticmethod
    async def pickup_item(
        player_id: int,
        ground_item_id: int,
        player_x: int,
        player_y: int,
        player_map_id: str,
    ) -> PickupItemResult:
        """
        Pick up a ground item.

        Player must be on the same map and tile as the item.
        Item must be visible (either owned by player or past protection time).
        Player must have inventory space.

        Args:
            player_id: Player picking up the item
            ground_item_id: Ground item ID
            player_x: Player's current tile X
            player_y: Player's current tile Y
            player_map_id: Player's current map ID

        Returns:
            PickupItemResult with success status
        """
        gsm = get_game_state_manager()
        now = datetime.now(timezone.utc).timestamp()

        # Get the ground item from GSM
        ground_item = await gsm.get_ground_item(ground_item_id)

        if not ground_item:
            return PickupItemResult(
                success=False,
                message="Item not found or already picked up",
            )

        # Check if player is on the same map
        if ground_item["map_id"] != player_map_id:
            return PickupItemResult(
                success=False,
                message="Item not found or already picked up",
            )

        # Check if item has despawned
        if ground_item["despawn_at"] <= now:
            await gsm.remove_ground_item(ground_item_id, ground_item["map_id"])
            return PickupItemResult(
                success=False,
                message="Item has despawned",
            )

        # Check if player is on the same tile
        if ground_item["x"] != player_x or ground_item["y"] != player_y:
            return PickupItemResult(
                success=False,
                message="You must be on the same tile to pick up this item",
            )

        # Check loot protection
        is_owner = ground_item["dropped_by"] == player_id
        is_public = ground_item["public_at"] <= now

        if not is_owner and not is_public:
            return PickupItemResult(
                success=False,
                message="This item is protected",
            )

        # Find free inventory slot
        free_slot = await gsm.get_free_inventory_slot(player_id)
        if free_slot is None:
            return PickupItemResult(
                success=False,
                message="Inventory is full",
            )

        # Add to inventory
        await gsm.set_inventory_slot(
            player_id,
            free_slot,
            ground_item["item_id"],
            ground_item["quantity"],
            ground_item.get("durability"),
        )

        # Remove ground item
        await gsm.remove_ground_item(ground_item_id, ground_item["map_id"])

        logger.info(
            "Player picked up item",
            extra={
                "player_id": player_id,
                "ground_item_id": ground_item_id,
                "item_id": ground_item["item_id"],
                "quantity": ground_item["quantity"],
                "inventory_slot": free_slot,
            },
        )

        return PickupItemResult(
            success=True,
            message="Item picked up",
            inventory_slot=free_slot,
        )

    @staticmethod
    async def get_ground_item(ground_item_id: int) -> Optional[Dict[str, Any]]:
        """Get a ground item by ID."""
        gsm = get_game_state_manager()
        return await gsm.get_ground_item(ground_item_id)

    @staticmethod
    async def get_visible_ground_items(
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
            player_id: Player ID
            map_id: Current map
            center_x: Player's tile X position
            center_y: Player's tile Y position
            tile_radius: Visibility radius in tiles

        Returns:
            GroundItemsResponse with visible items
        """
        gsm = get_game_state_manager()
        all_items = await gsm.get_ground_items_on_map(map_id)
        now = datetime.now(timezone.utc).timestamp()

        items = []
        for gi in all_items:
            # Check distance
            if abs(gi["x"] - center_x) > tile_radius:
                continue
            if abs(gi["y"] - center_y) > tile_radius:
                continue

            # Check visibility (player dropped it or protection expired)
            is_yours = gi["dropped_by"] == player_id
            is_public = gi["public_at"] <= now

            if not is_yours and not is_public:
                continue

            items.append(
                GroundItemInfo(
                    id=gi["id"],
                    item=ItemInfo(
                        id=gi["item_id"],
                        name=gi["item_name"],
                        display_name=gi["display_name"],
                        category=gi["category"],
                        rarity=gi["rarity"],
                        rarity_color=gi["rarity_color"],
                        max_stack_size=gi["max_stack_size"],
                    ),
                    x=gi["x"],
                    y=gi["y"],
                    quantity=gi["quantity"],
                    is_yours=is_yours,
                    is_protected=not is_public and not is_yours,
                )
            )

        return GroundItemsResponse(
            items=items,
            map_id=map_id,
        )

    @staticmethod
    async def cleanup_expired_items(map_id: Optional[str] = None) -> int:
        """
        Clean up expired ground items.

        Args:
            map_id: Optional map to clean up. If None, cleans all maps.

        Returns:
            Number of items cleaned up
        """
        gsm = get_game_state_manager()

        if map_id:
            return await gsm.cleanup_expired_ground_items(map_id)

        # Clean up all maps by getting all items and their maps
        all_items = await gsm.get_all_ground_items()
        maps = set(item["map_id"] for item in all_items)

        total_cleaned = 0
        for m in maps:
            total_cleaned += await gsm.cleanup_expired_ground_items(m)

        return total_cleaned

    @staticmethod
    async def drop_player_items_on_death(
        player_id: int,
        map_id: str,
        x: int,
        y: int,
    ) -> int:
        """
        Drop all player inventory and equipment on death.

        Args:
            player_id: Player who died
            map_id: Map where player died
            x: Death tile X position
            y: Death tile Y position

        Returns:
            Number of items dropped
        """
        gsm = get_game_state_manager()
        items_dropped = 0

        inventory = await gsm.get_inventory(player_id)
        equipment = await gsm.get_equipment(player_id)

        # Collect all item_ids we need to look up
        all_item_ids = set()
        for slot_data in inventory.values():
            all_item_ids.add(slot_data["item_id"])
        for slot_data in equipment.values():
            all_item_ids.add(slot_data["item_id"])

        if not all_item_ids:
            logger.info(
                "Player died with no items to drop",
                extra={"player_id": player_id, "map_id": map_id, "x": x, "y": y},
            )
            return 0

        # Look up item definitions
        items_by_id = {}
        async with gsm._db_session() as db:
            result = await db.execute(
                select(Item).where(Item.id.in_(all_item_ids))
            )
            items_by_id = {item.id: item for item in result.scalars().all()}

        # Drop inventory items
        for slot, slot_data in inventory.items():
            item_id = slot_data["item_id"]
            item = items_by_id.get(item_id)
            if not item:
                continue

            ground_item_id = await gsm.add_ground_item(
                item_id=item_id,
                item_name=item.name,
                display_name=item.display_name,
                rarity=item.rarity,
                map_id=map_id,
                x=x,
                y=y,
                quantity=slot_data["quantity"],
                dropped_by_player_id=player_id,
                category=item.category,
                rarity_color=GroundItemService._get_rarity_color(item.rarity),
                max_stack_size=item.max_stack_size,
            )
            if ground_item_id:
                items_dropped += 1

        # Drop equipped items
        for slot_name, slot_data in equipment.items():
            item_id = slot_data["item_id"]
            item = items_by_id.get(item_id)
            if not item:
                continue

            ground_item_id = await gsm.add_ground_item(
                item_id=item_id,
                item_name=item.name,
                display_name=item.display_name,
                rarity=item.rarity,
                map_id=map_id,
                x=x,
                y=y,
                quantity=slot_data["quantity"],
                dropped_by_player_id=player_id,
                category=item.category,
                rarity_color=GroundItemService._get_rarity_color(item.rarity),
                max_stack_size=item.max_stack_size,
            )
            if ground_item_id:
                items_dropped += 1

        await gsm.clear_inventory(player_id)
        await gsm.clear_equipment(player_id)

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
        map_id: str,
        x: int,
        y: int,
    ) -> List[Dict[str, Any]]:
        """
        Get all ground items at a specific tile position.

        Args:
            map_id: Map ID
            x: Tile X position
            y: Tile Y position

        Returns:
            List of ground items at this position
        """
        gsm = get_game_state_manager()
        all_items = await gsm.get_ground_items_on_map(map_id)
        return [item for item in all_items if item["x"] == x and item["y"] == y]
