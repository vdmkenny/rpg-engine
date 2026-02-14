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

from ..core.config import settings
from ..core.concurrency import get_player_lock_manager, LockType
from ..core.items import ItemRarity
from ..core.logging_config import get_logger
from ..schemas.item import (
    OperationResult,
    OperationType,
    GroundItem,
    ItemInfo,
)
from .game_state import get_ground_item_manager, get_inventory_manager, get_equipment_manager
from .inventory_service import InventoryService
from .item_service import ItemService

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
        ground_item_mgr = get_ground_item_manager()

        item = await ItemService.get_item_by_id(item_id)

        if not item:
            logger.warning(
                "Cannot create ground item - item not found",
                extra={"item_id": item_id},
            )
            return None

        current_time = datetime.now(timezone.utc).timestamp()
        despawn_seconds = GroundItemService._get_despawn_seconds(item.rarity)

        if dropped_by:
            protection_seconds = GroundItemService._get_protection_seconds(item.rarity)
            loot_protection_expires_at = current_time + protection_seconds
        else:
            loot_protection_expires_at = current_time

        ground_item_id = await ground_item_mgr.add_ground_item(
            map_id=map_id,
            x=x,
            y=y,
            item_id=item_id,
            quantity=quantity,
            durability=float(current_durability) if current_durability is not None else 1.0,
            dropped_by_player_id=dropped_by,
            loot_protection_expires_at=loot_protection_expires_at,
            despawn_at=current_time + despawn_seconds,
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
    ) -> OperationResult:
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
            OperationResult with success status
        """
        async with get_player_lock_manager().acquire_player_lock(
            player_id, LockType.INVENTORY, "drop_from_inventory"
        ):
            inventory_mgr = get_inventory_manager()

            slot_data = await inventory_mgr.get_inventory_slot(player_id, inventory_slot)
            if not slot_data:
                return OperationResult(
                    success=False,
                    message="Inventory slot is empty",
                    operation=OperationType.DROP,
                )

            item_id = slot_data["item_id"]
            current_quantity = slot_data["quantity"]
            durability = slot_data.get("current_durability")

            drop_quantity = quantity if quantity is not None else current_quantity
            if drop_quantity <= 0:
                return OperationResult(
                    success=False,
                    message="Quantity must be positive",
                    operation=OperationType.DROP,
                )
            if drop_quantity > current_quantity:
                return OperationResult(
                    success=False,
                    message=f"Not enough items (have {current_quantity}, want to drop {drop_quantity})",
                    operation=OperationType.DROP,
                )

            item = await ItemService.get_item_by_id(item_id)

            if not item:
                return OperationResult(
                    success=False,
                    message="Item not found",
                    operation=OperationType.DROP,
                )

            current_time = datetime.now(timezone.utc).timestamp()
            protection_seconds = GroundItemService._get_protection_seconds(item.rarity)
            despawn_seconds = GroundItemService._get_despawn_seconds(item.rarity)

            ground_item_mgr = get_ground_item_manager()
            ground_item_id = await ground_item_mgr.add_ground_item(
                map_id=map_id,
                x=x,
                y=y,
                item_id=item_id,
                quantity=drop_quantity,
                durability=durability or 1.0,
                dropped_by_player_id=player_id,
                loot_protection_expires_at=current_time + protection_seconds,
                despawn_at=current_time + despawn_seconds,
            )

            if not ground_item_id:
                return OperationResult(
                    success=False,
                    message="Failed to create ground item",
                    operation=OperationType.DROP,
                )

            # Remove item from inventory using internal variant since we already hold the lock
            remove_result = await InventoryService._remove_item_internal(
                player_id, inventory_slot, drop_quantity
            )

            if not remove_result.success:
                # Rollback: remove the ground item we just created
                await ground_item_mgr.remove_ground_item(ground_item_id, map_id)
                return OperationResult(
                    success=False,
                    message="Failed to remove item from inventory",
                    operation=OperationType.DROP,
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

            return OperationResult(
                success=True,
                message="Item dropped",
                operation=OperationType.DROP,
                data={"ground_item_id": ground_item_id},
            )

    @staticmethod
    async def pickup_item(
        player_id: int,
        ground_item_id: int,
        player_x: int,
        player_y: int,
        player_map_id: str,
    ) -> OperationResult:
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
            OperationResult with success status and detailed error messages
        """
        async with get_player_lock_manager().acquire_player_lock(
            player_id, LockType.INVENTORY, "pickup_item"
        ):
            ground_item_mgr = get_ground_item_manager()
            now = datetime.now(timezone.utc).timestamp()

            ground_item = await ground_item_mgr.get_ground_item(ground_item_id)

            if not ground_item:
                return OperationResult(
                    success=False,
                    message="Item not found or already picked up",
                    operation=OperationType.PICKUP,
                )

            if ground_item["map_id"] != player_map_id:
                return OperationResult(
                    success=False,
                    message="Item not found or already picked up",
                    operation=OperationType.PICKUP,
                )

            if ground_item["despawn_at"] <= now:
                await ground_item_mgr.remove_ground_item(ground_item_id, ground_item["map_id"])
                return OperationResult(
                    success=False,
                    message="Item has despawned",
                    operation=OperationType.PICKUP,
                )

            if ground_item["x"] != player_x or ground_item["y"] != player_y:
                return OperationResult(
                    success=False,
                    message="You must be on the same tile to pick up this item",
                    operation=OperationType.PICKUP,
                )

            is_owner = ground_item.get("dropped_by_player_id") == player_id
            is_public = ground_item.get("loot_protection_expires_at", 0.0) <= now

            if not is_owner and not is_public:
                return OperationResult(
                    success=False,
                    message="This item is protected",
                    operation=OperationType.PICKUP,
                )

            durability_val = ground_item.get("durability")
            
            durability_int = None
            if durability_val is not None:
                durability_int = int(durability_val) if durability_val != 1.0 else None
            
            # Use internal variant since we already hold the inventory lock
            add_result = await InventoryService._add_item_internal(
                player_id=player_id,
                item_id=ground_item["item_id"],
                quantity=ground_item["quantity"],
                durability=durability_int,
            )

            if not add_result.success:
                return OperationResult(
                    success=False,
                    message=add_result.message,
                    operation=OperationType.PICKUP,
                )

            await ground_item_mgr.remove_ground_item(ground_item_id, ground_item["map_id"])

            logger.info(
                "Player picked up item",
                extra={
                    "player_id": player_id,
                    "ground_item_id": ground_item_id,
                    "item_id": ground_item["item_id"],
                    "quantity": ground_item["quantity"],
                    "inventory_slot": add_result.data.get("slot"),
                },
            )

            return OperationResult(
                success=True,
                message="Item picked up",
                operation=OperationType.PICKUP,
                data={"inventory_slot": add_result.data.get("slot")},
            )

    @staticmethod
    async def get_ground_item(ground_item_id: int) -> Optional[GroundItem]:
        """Get a ground item by ID."""
        ground_item_mgr = get_ground_item_manager()
        item_data = await ground_item_mgr.get_ground_item(ground_item_id)
        if not item_data:
            return None
        
        item_wrapper = await ItemService.get_item_by_id(item_data["item_id"])
        if not item_wrapper:
            return None
        
        item_info = ItemService.item_to_info(item_wrapper._data)
        
        return GroundItem(
            id=item_data["ground_item_id"],
            item=item_info,
            x=item_data["x"],
            y=item_data["y"],
            quantity=item_data["quantity"],
            is_yours=False,
            is_protected=False,
        )

    @staticmethod
    async def get_visible_ground_items(
        player_id: int,
        map_id: str,
        center_x: int,
        center_y: int,
        tile_radius: int = 16,
    ) -> List[GroundItem]:
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
            List of visible GroundItem objects
        """
        ground_item_mgr = get_ground_item_manager()
        all_items = await ground_item_mgr.get_ground_items_on_map(map_id)
        now = datetime.now(timezone.utc).timestamp()

        visible_ground_items = []
        unique_item_ids = set()
        
        for gi in all_items:
            if abs(gi["x"] - center_x) > tile_radius:
                continue
            if abs(gi["y"] - center_y) > tile_radius:
                continue
            
            # Skip items that have despawned
            despawn_at = gi.get("despawn_at")
            if despawn_at is not None and despawn_at <= now:
                continue

            is_yours = gi.get("dropped_by_player_id") == player_id
            is_public = gi.get("loot_protection_expires_at", 0.0) <= now

            if not is_yours and not is_public:
                continue

            visible_ground_items.append((gi, is_yours, is_public))
            unique_item_ids.add(gi["item_id"])

        item_metadata = {}
        if unique_item_ids:
            for item_id in unique_item_ids:
                item = await ItemService.get_item_by_id(item_id)
                if item:
                    item_metadata[item_id] = item

        items = []
        for gi, is_yours, is_public in visible_ground_items:
            item_id = gi["item_id"]
            item_wrapper = item_metadata.get(item_id)
            
            if not item_wrapper:
                continue
            
            item_info = ItemService.item_to_info(item_wrapper._data)
                
            items.append(
                GroundItem(
                    id=gi["ground_item_id"],
                    item=item_info,
                    x=gi["x"],
                    y=gi["y"],
                    quantity=gi["quantity"],
                    is_yours=is_yours,
                    is_protected=not is_public and not is_yours,
                )
            )

        return items

    @staticmethod
    async def cleanup_expired_items(map_id: Optional[str] = None) -> int:
        """
        Clean up expired ground items.

        Args:
            map_id: Optional map to clean up. If None, cleans all maps.

        Returns:
            Number of items cleaned up
        """
        ground_item_mgr = get_ground_item_manager()

        if map_id:
            all_items = await ground_item_mgr.get_ground_items_on_map(map_id)
            if not all_items:
                return 0

            import time
            now = time.time()
            cleanup_count = 0

            for item in all_items:
                despawn_at = item.get("despawn_at", 0)
                if despawn_at <= now:
                    success = await ground_item_mgr.remove_ground_item(item["ground_item_id"], map_id)
                    if success:
                        cleanup_count += 1

            if cleanup_count > 0:
                logger.info(
                    "Cleaned up expired ground items",
                    extra={"map_id": map_id, "count": cleanup_count},
                )

            return cleanup_count

        logger.warning("cleanup_expired_items called without map_id - skipping global cleanup")
        return 0

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
        inventory_mgr = get_inventory_manager()
        equipment_mgr = get_equipment_manager()
        items_dropped = 0

        inventory = await inventory_mgr.get_inventory(player_id)
        equipment = await equipment_mgr.get_equipment(player_id)

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

        items_by_id = {}
        for item_id in all_item_ids:
            item = await ItemService.get_item_by_id(item_id)
            if item:
                items_by_id[item_id] = item

        ground_item_mgr = get_ground_item_manager()

        for slot, slot_data in inventory.items():
            item_id = slot_data["item_id"]
            item = items_by_id.get(item_id)
            if not item:
                continue

            ground_item_id = await ground_item_mgr.add_ground_item(
                map_id=map_id,
                x=x,
                y=y,
                item_id=item_id,
                quantity=slot_data["quantity"],
                durability=slot_data.get("current_durability", 1.0),
                dropped_by_player_id=player_id,
            )
            if ground_item_id:
                items_dropped += 1

        for slot_name, slot_data in equipment.items():
            item_id = slot_data["item_id"]
            item = items_by_id.get(item_id)
            if not item:
                continue

            ground_item_id = await ground_item_mgr.add_ground_item(
                map_id=map_id,
                x=x,
                y=y,
                item_id=item_id,
                quantity=slot_data["quantity"],
                durability=slot_data.get("current_durability", 1.0),
                dropped_by_player_id=player_id,
            )
            if ground_item_id:
                items_dropped += 1

        await inventory_mgr.clear_inventory(player_id)
        await equipment_mgr.clear_equipment(player_id)

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
    ) -> List[GroundItem]:
        """
        Get all ground items at a specific tile position.

        Args:
            map_id: Map ID
            x: Tile X position
            y: Tile Y position

        Returns:
            List of GroundItem objects at this position
        """
        ground_item_mgr = get_ground_item_manager()
        all_items = await ground_item_mgr.get_ground_items_on_map(map_id)
        
        items_at_pos = []
        unique_item_ids = set()
        
        for item_data in all_items:
            if item_data["x"] == x and item_data["y"] == y:
                items_at_pos.append(item_data)
                unique_item_ids.add(item_data["item_id"])
        
        item_metadata = {}
        if unique_item_ids:
            for item_id in unique_item_ids:
                item_wrapper = await ItemService.get_item_by_id(item_id)
                if item_wrapper:
                    item_metadata[item_id] = item_wrapper
        
        result = []
        for item_data in items_at_pos:
            item_wrapper = item_metadata.get(item_data["item_id"])
            if not item_wrapper:
                continue
            
            item_info = ItemService.item_to_info(item_wrapper._data)
            
            result.append(
                GroundItem(
                    id=item_data["ground_item_id"],
                    item=item_info,
                    x=item_data["x"],
                    y=item_data["y"],
                    quantity=item_data["quantity"],
                    is_yours=False,
                    is_protected=False,
                )
            )
        
        return result
