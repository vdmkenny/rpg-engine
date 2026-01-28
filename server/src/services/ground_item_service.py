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
from ..schemas.service_results import (
    GroundItemServiceResult,
    ServiceErrorCodes
)
from .game_state_manager import get_game_state_manager
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
        item = await ItemService.get_item_by_id(item_id)

        if not item:
            logger.warning(
                "Cannot create ground item - item not found",
                extra={"item_id": item_id},
            )
            return None

        # Calculate timers based on business rules (STAYS IN SERVICE LAYER)
        current_time = datetime.now(timezone.utc).timestamp()
        despawn_seconds = GroundItemService._get_despawn_seconds(item.rarity)

        # World spawns vs player drops (BUSINESS RULE)
        if dropped_by:
            # Player dropped - apply loot protection
            protection_seconds = GroundItemService._get_protection_seconds(item.rarity)
            loot_protection_expires_at = current_time + protection_seconds
        else:
            # World spawn - immediately public
            loot_protection_expires_at = current_time

        ground_item_id = await gsm.add_ground_item(
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
        durability = slot_data.get("current_durability")

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
        item = await ItemService.get_item_by_id(item_id)

        if not item:
            return DropItemResult(
                success=False,
                message="Item not found",
            )

        # Calculate timers for player drops (STAYS IN SERVICE LAYER)
        current_time = datetime.now(timezone.utc).timestamp()
        protection_seconds = GroundItemService._get_protection_seconds(item.rarity)
        despawn_seconds = GroundItemService._get_despawn_seconds(item.rarity)

        # Create ground item
        ground_item_id = await gsm.add_ground_item(
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
                durability or 1.0,
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
            PickupItemResult with success status and detailed error messages
        """
        from .inventory_service import InventoryService
        
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
        is_owner = ground_item.get("dropped_by_player_id") == player_id
        is_public = ground_item.get("loot_protection_expires_at", 0.0) <= now

        if not is_owner and not is_public:
            return PickupItemResult(
                success=False,
                message="This item is protected",
            )

        # Use InventoryService for adding items instead of direct GSM calls
        durability_val = ground_item.get("durability")
        
        # Convert GSM's float durability to InventoryService's int durability
        durability_int = None
        if durability_val is not None:
            # Round float durability to integer for InventoryService compatibility
            durability_int = int(durability_val) if durability_val != 1.0 else None
        
        add_result = await InventoryService.add_item(
            player_id=player_id,
            item_id=ground_item["item_id"],
            quantity=ground_item["quantity"],
            durability=durability_int,
        )
        
        if not add_result.success:
            return PickupItemResult(
                success=False,
                message=add_result.message or "Failed to add item to inventory",
            )

        # Remove ground item after successful inventory addition
        await gsm.remove_ground_item(ground_item_id, ground_item["map_id"])

        logger.info(
            "Player picked up item",
            extra={
                "player_id": player_id,
                "ground_item_id": ground_item_id,
                "item_id": ground_item["item_id"],
                "quantity": ground_item["quantity"],
                "inventory_slot": add_result.slot,
            },
        )

        return PickupItemResult(
            success=True,
            message="Item picked up",
            inventory_slot=add_result.slot,
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

        # Collect visible ground items first
        visible_ground_items = []
        unique_item_ids = set()
        
        for gi in all_items:
            # Check distance
            if abs(gi["x"] - center_x) > tile_radius:
                continue
            if abs(gi["y"] - center_y) > tile_radius:
                continue

            # Check visibility (player dropped it or protection expired)
            is_yours = gi.get("dropped_by_player_id") == player_id
            is_public = gi.get("loot_protection_expires_at", 0.0) <= now

            if not is_yours and not is_public:
                continue

            visible_ground_items.append((gi, is_yours, is_public))
            unique_item_ids.add(gi["item_id"])

        # Look up item metadata for all unique items
        item_metadata = {}
        if unique_item_ids:
            for item_id in unique_item_ids:
                item = await ItemService.get_item_by_id(item_id)
                if item:
                    item_metadata[item_id] = item

        # Build response with merged data
        items = []
        for gi, is_yours, is_public in visible_ground_items:
            item_id = gi["item_id"]
            item = item_metadata.get(item_id)
            
            if not item:
                # Skip items we couldn't find metadata for
                continue
                
            items.append(
                GroundItemInfo(
                    id=gi["id"],
                    item=ItemInfo(
                        id=item_id,
                        name=item.name,
                        display_name=item.display_name,
                        category=item.category,
                        rarity=item.rarity,
                        rarity_color=GroundItemService._get_rarity_color(item.rarity),
                        max_stack_size=item.max_stack_size,
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
    async def get_visible_ground_items_raw(
        player_id: int,
        map_id: str,
        center_x: int,
        center_y: int,
        tile_radius: int = 16,
    ) -> List[Dict[str, Any]]:
        """
        Get raw ground item data visible to a player (for game loop).
        
        This method returns raw ground item data with item metadata merged in,
        suitable for the game loop's entity diff system.
        
        Args:
            player_id: Player ID
            map_id: Current map
            center_x: Player's tile X position
            center_y: Player's tile Y position
            tile_radius: Visibility radius in tiles
            
        Returns:
            List of raw ground item dicts with visibility filtering applied
        """
        gsm = get_game_state_manager()
        all_items = await gsm.get_ground_items_on_map(map_id)
        now = datetime.now(timezone.utc).timestamp()

        # Apply visibility filtering (BUSINESS LOGIC STAYS IN SERVICE)
        visible_items = []
        unique_item_ids = set()
        
        for item in all_items:
            # Distance check
            if abs(item["x"] - center_x) > tile_radius:
                continue
            if abs(item["y"] - center_y) > tile_radius:
                continue

            # Visibility check (ownership or protection expired)
            is_owner = item.get("dropped_by_player_id") == player_id
            loot_protection_expires_at = item.get("loot_protection_expires_at", 0)
            is_public = loot_protection_expires_at <= now

            if not is_owner and not is_public:
                continue

            # Add visibility metadata
            item_with_metadata = item.copy()
            item_with_metadata["is_protected"] = not is_public and not is_owner
            item_with_metadata["is_yours"] = is_owner
            visible_items.append(item_with_metadata)
            unique_item_ids.add(item["item_id"])

        # Get item metadata for all unique items
        item_metadata = {}
        if unique_item_ids:
            for item_id in unique_item_ids:
                item = await ItemService.get_item_by_id(item_id)
                if item:
                    item_metadata[item_id] = item

        # Merge item metadata into ground item data
        for item in visible_items:
            item_id = item["item_id"]
            metadata = item_metadata.get(item_id)
            if metadata:
                item["item_name"] = metadata.name
                item["display_name"] = metadata.display_name
                item["rarity"] = metadata.rarity
        
        return visible_items

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
            # Get all ground items on this map
            all_items = await gsm.get_ground_items_on_map(map_id)
            if not all_items:
                return 0

            import time
            now = time.time()
            cleanup_count = 0

            # Check and remove expired items
            for item in all_items:
                despawn_at = item.get("despawn_at", 0)
                if despawn_at <= now:
                    success = await gsm.remove_ground_item(item["id"], map_id)
                    if success:
                        cleanup_count += 1

            if cleanup_count > 0:
                logger.info(
                    "Cleaned up expired ground items",
                    extra={"map_id": map_id, "count": cleanup_count},
                )

            return cleanup_count

        # For now, when map_id is None, we just return 0 since we don't have
        # a way to enumerate all maps with ground items. This functionality
        # could be improved later by tracking active maps.
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

        # Replace bulk DB query with individual service calls (no bulk method available)
        items_by_id = {}
        for item_id in all_item_ids:
            item = await ItemService.get_item_by_id(item_id)
            if item:  # Only add if found
                items_by_id[item_id] = item
            # Skip missing items (don't fail entire death drop for missing items)

        # Drop inventory items
        for slot, slot_data in inventory.items():
            item_id = slot_data["item_id"]
            item = items_by_id.get(item_id)
            if not item:
                continue

            ground_item_id = await gsm.add_ground_item(
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

        # Drop equipped items
        for slot_name, slot_data in equipment.items():
            item_id = slot_data["item_id"]
            item = items_by_id.get(item_id)
            if not item:
                continue

            ground_item_id = await gsm.add_ground_item(
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
