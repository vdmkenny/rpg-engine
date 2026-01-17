"""
Valkey (Redis) service for ground item hot data.

Ground items are stored in Valkey for fast game loop access.
They are synced to the database for persistence on shutdown and periodically.

Valkey key patterns:
- ground_item:{id} - Hash with ground item data
- ground_items:map:{map_id} - Set of ground item IDs on a map
- ground_items:next_id - Counter for generating unique IDs
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from glide import GlideClient

from server.src.core.logging_config import get_logger
from server.src.core.config import settings

logger = get_logger(__name__)


def _utc_timestamp() -> float:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).timestamp()


class GroundItemValkeyService:
    """Service for managing ground items in Valkey."""

    @staticmethod
    async def get_next_id(valkey: GlideClient) -> int:
        """Get the next unique ground item ID."""
        result = await valkey.incr("ground_items:next_id")
        return int(result)

    @staticmethod
    async def add_ground_item(
        valkey: GlideClient,
        ground_item_id: int,
        item_id: int,
        item_name: str,
        display_name: str,
        rarity: str,
        map_id: str,
        x: int,
        y: int,
        quantity: int,
        dropped_by_player_id: Optional[int] = None,
        public_at: Optional[float] = None,
        despawn_at: Optional[float] = None,
    ) -> None:
        """
        Add a ground item to Valkey.

        Args:
            valkey: Valkey client
            ground_item_id: Unique ID for this ground item
            item_id: Database item ID
            item_name: Item internal name
            display_name: Item display name
            rarity: Item rarity (for display)
            map_id: Map where item is located
            x: Tile X position
            y: Tile Y position
            quantity: Stack quantity
            dropped_by_player_id: Player ID who dropped it (for loot protection)
            public_at: Timestamp when loot protection ends
            despawn_at: Timestamp when item despawns
        """
        now = _utc_timestamp()
        
        # Default timers based on rarity
        protection_seconds = settings.GROUND_ITEMS_LOOT_PROTECTION_TIMES.get(rarity, 45)
        despawn_seconds = settings.GROUND_ITEMS_DESPAWN_TIMES.get(rarity, 120)
        
        if public_at is None:
            public_at = now + protection_seconds
        if despawn_at is None:
            despawn_at = now + despawn_seconds

        item_key = f"ground_item:{ground_item_id}"
        map_key = f"ground_items:map:{map_id}"

        # Store ground item data as hash
        await valkey.hset(
            item_key,
            {
                "id": str(ground_item_id),
                "item_id": str(item_id),
                "item_name": item_name,
                "display_name": display_name,
                "rarity": rarity,
                "map_id": map_id,
                "x": str(x),
                "y": str(y),
                "quantity": str(quantity),
                "dropped_by": str(dropped_by_player_id) if dropped_by_player_id else "",
                "dropped_at": str(now),
                "public_at": str(public_at),
                "despawn_at": str(despawn_at),
            },
        )

        # Add to map index
        await valkey.sadd(map_key, [str(ground_item_id)])

        logger.debug(
            "Added ground item to Valkey",
            extra={
                "ground_item_id": ground_item_id,
                "item_id": item_id,
                "map_id": map_id,
                "position": {"x": x, "y": y},
            },
        )

    @staticmethod
    async def remove_ground_item(
        valkey: GlideClient,
        ground_item_id: int,
        map_id: str,
    ) -> bool:
        """
        Remove a ground item from Valkey.

        Args:
            valkey: Valkey client
            ground_item_id: Ground item ID to remove
            map_id: Map where item was located

        Returns:
            True if item was removed, False if not found
        """
        item_key = f"ground_item:{ground_item_id}"
        map_key = f"ground_items:map:{map_id}"

        # Check if item exists
        exists = await valkey.exists([item_key])
        if not exists:
            return False

        # Remove from map index and delete item
        await valkey.srem(map_key, [str(ground_item_id)])
        await valkey.delete([item_key])

        logger.debug(
            "Removed ground item from Valkey",
            extra={"ground_item_id": ground_item_id, "map_id": map_id},
        )
        return True

    @staticmethod
    async def get_ground_item(
        valkey: GlideClient,
        ground_item_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a ground item by ID.

        Args:
            valkey: Valkey client
            ground_item_id: Ground item ID

        Returns:
            Ground item data dict or None if not found
        """
        item_key = f"ground_item:{ground_item_id}"
        data = await valkey.hgetall(item_key)
        
        if not data:
            return None

        # Convert bytes to proper types
        return {
            "id": int(data[b"id"]),
            "item_id": int(data[b"item_id"]),
            "item_name": data[b"item_name"].decode(),
            "display_name": data[b"display_name"].decode(),
            "rarity": data[b"rarity"].decode(),
            "map_id": data[b"map_id"].decode(),
            "x": int(data[b"x"]),
            "y": int(data[b"y"]),
            "quantity": int(data[b"quantity"]),
            "dropped_by": int(data[b"dropped_by"]) if data[b"dropped_by"] else None,
            "dropped_at": float(data[b"dropped_at"]),
            "public_at": float(data[b"public_at"]),
            "despawn_at": float(data[b"despawn_at"]),
        }

    @staticmethod
    async def get_ground_items_on_map(
        valkey: GlideClient,
        map_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all ground items on a map.

        Args:
            valkey: Valkey client
            map_id: Map ID

        Returns:
            List of ground item data dicts
        """
        map_key = f"ground_items:map:{map_id}"
        item_ids = await valkey.smembers(map_key)
        
        if not item_ids:
            return []

        now = _utc_timestamp()
        items = []
        expired_ids = []

        for item_id_bytes in item_ids:
            item_id = int(item_id_bytes)
            item = await GroundItemValkeyService.get_ground_item(valkey, item_id)
            
            if item is None:
                # Item was removed but still in index - clean up
                expired_ids.append(str(item_id))
                continue
                
            # Check if despawned
            if item["despawn_at"] <= now:
                expired_ids.append(str(item_id))
                await valkey.delete([f"ground_item:{item_id}"])
                continue
                
            items.append(item)

        # Clean up expired items from index
        if expired_ids:
            await valkey.srem(map_key, expired_ids)

        return items

    @staticmethod
    async def get_visible_ground_items(
        valkey: GlideClient,
        map_id: str,
        player_x: int,
        player_y: int,
        player_id: Optional[int],
        tile_radius: int = 32,
    ) -> List[Dict[str, Any]]:
        """
        Get ground items visible to a player.

        An item is visible if:
        - It's within tile_radius of the player
        - Either the player dropped it, or loot protection has expired

        Args:
            valkey: Valkey client
            map_id: Current map
            player_x: Player's tile X position
            player_y: Player's tile Y position
            player_id: Player's database ID (for loot protection check)
            tile_radius: Visibility radius in tiles

        Returns:
            List of visible ground item data dicts with is_protected flag
        """
        all_items = await GroundItemValkeyService.get_ground_items_on_map(valkey, map_id)
        now = _utc_timestamp()
        visible = []

        for item in all_items:
            # Check distance
            if abs(item["x"] - player_x) > tile_radius:
                continue
            if abs(item["y"] - player_y) > tile_radius:
                continue

            # Check visibility (player dropped it or protection expired)
            is_owner = item["dropped_by"] == player_id
            is_public = item["public_at"] <= now

            if not is_owner and not is_public:
                continue

            # Add visibility metadata
            item_copy = item.copy()
            item_copy["is_protected"] = not is_public and not is_owner
            item_copy["is_yours"] = is_owner
            visible.append(item_copy)

        return visible

    @staticmethod
    async def cleanup_expired_items(valkey: GlideClient, map_id: str) -> int:
        """
        Remove expired ground items from a map.

        Args:
            valkey: Valkey client
            map_id: Map ID

        Returns:
            Number of items cleaned up
        """
        map_key = f"ground_items:map:{map_id}"
        item_ids = await valkey.smembers(map_key)
        
        if not item_ids:
            return 0

        now = _utc_timestamp()
        cleaned = 0

        for item_id_bytes in item_ids:
            item_id = int(item_id_bytes)
            item_key = f"ground_item:{item_id}"
            
            data = await valkey.hgetall(item_key)
            if not data:
                await valkey.srem(map_key, [str(item_id)])
                cleaned += 1
                continue
                
            despawn_at = float(data.get(b"despawn_at", b"0"))
            if despawn_at <= now:
                await valkey.delete([item_key])
                await valkey.srem(map_key, [str(item_id)])
                cleaned += 1

        if cleaned > 0:
            logger.info(
                "Cleaned up expired ground items",
                extra={"map_id": map_id, "count": cleaned},
            )

        return cleaned

    @staticmethod
    async def get_all_ground_items(valkey: GlideClient) -> List[Dict[str, Any]]:
        """
        Get all ground items across all maps (for DB sync).

        Args:
            valkey: Valkey client

        Returns:
            List of all ground item data dicts
        """
        # Scan for all map keys
        all_items = []
        cursor = "0"
        
        while True:
            # Use SCAN to find all ground_items:map:* keys
            cursor, keys = await valkey.scan(cursor, match="ground_items:map:*", count=100)
            
            for key in keys:
                map_id = key.decode().replace("ground_items:map:", "")
                items = await GroundItemValkeyService.get_ground_items_on_map(valkey, map_id)
                all_items.extend(items)
            
            if cursor == b"0" or cursor == "0":
                break
        
        return all_items

    @staticmethod
    async def set_next_id(valkey: GlideClient, next_id: int) -> None:
        """
        Set the next ground item ID counter (used when loading from DB).

        Args:
            valkey: Valkey client
            next_id: The next ID to use
        """
        await valkey.set("ground_items:next_id", str(next_id))
