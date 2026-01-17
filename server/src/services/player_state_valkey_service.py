"""
Valkey service for managing player state (inventory, equipment, skills).

All gameplay data is cached in Valkey as the primary source of truth during gameplay.
Data is periodically batch-synced to PostgreSQL for persistence.

Key Schema:
- inventory:{player_id} - Hash with slot numbers as fields, JSON values
- equipment:{player_id} - Hash with equipment slot names as fields, JSON values
- skills:{player_id} - Hash with skill names as fields, JSON values
- dirty:inventory - Set of player_ids with unsaved inventory changes
- dirty:equipment - Set of player_ids with unsaved equipment changes
- dirty:skills - Set of player_ids with unsaved skill changes
- dirty:ground_items - Set of map_ids with unsaved ground item changes
"""

import json
from typing import Dict, List, Optional, Set

from glide import GlideClient

from server.src.core.logging_config import get_logger

logger = get_logger(__name__)

# Key patterns
INVENTORY_KEY = "inventory:{player_id}"
EQUIPMENT_KEY = "equipment:{player_id}"
SKILLS_KEY = "skills:{player_id}"

# Dirty tracking keys
DIRTY_INVENTORY_KEY = "dirty:inventory"
DIRTY_EQUIPMENT_KEY = "dirty:equipment"
DIRTY_SKILLS_KEY = "dirty:skills"
DIRTY_GROUND_ITEMS_KEY = "dirty:ground_items"


class PlayerStateValkeyService:
    """Service for managing player state in Valkey."""

    # ==================== INVENTORY ====================

    @staticmethod
    async def load_inventory_to_valkey(
        valkey: GlideClient,
        player_id: int,
        inventory_items: List[Dict],
    ) -> None:
        """
        Load player's inventory from DB format to Valkey on connect.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
            inventory_items: List of dicts with slot, item_id, quantity, current_durability
        """
        key = INVENTORY_KEY.format(player_id=player_id)

        # Clear existing inventory data
        await valkey.delete(key)

        if not inventory_items:
            return

        # Build hash: slot -> JSON data
        hash_data = {}
        for item in inventory_items:
            slot = str(item["slot"])
            hash_data[slot] = json.dumps(
                {
                    "item_id": item["item_id"],
                    "quantity": item["quantity"],
                    "durability": item.get("current_durability"),
                }
            )

        await valkey.hset(key, hash_data)
        logger.debug(
            "Loaded inventory to Valkey",
            extra={"player_id": player_id, "slots": len(hash_data)},
        )

    @staticmethod
    async def get_inventory(
        valkey: GlideClient,
        player_id: int,
    ) -> Dict[int, Dict]:
        """
        Get player's full inventory from Valkey.

        Returns:
            Dict mapping slot number (int) to item data dict
        """
        key = INVENTORY_KEY.format(player_id=player_id)
        raw = await valkey.hgetall(key)

        if not raw:
            return {}

        result = {}
        for slot_bytes, data_bytes in raw.items():
            slot = int(slot_bytes.decode() if isinstance(slot_bytes, bytes) else slot_bytes)
            data = json.loads(data_bytes.decode() if isinstance(data_bytes, bytes) else data_bytes)
            result[slot] = data

        return result

    @staticmethod
    async def get_inventory_slot(
        valkey: GlideClient,
        player_id: int,
        slot: int,
    ) -> Optional[Dict]:
        """
        Get a single inventory slot from Valkey.

        Returns:
            Item data dict or None if slot is empty
        """
        key = INVENTORY_KEY.format(player_id=player_id)
        raw = await valkey.hget(key, str(slot))

        if not raw:
            return None

        return json.loads(raw.decode() if isinstance(raw, bytes) else raw)

    @staticmethod
    async def set_inventory_slot(
        valkey: GlideClient,
        player_id: int,
        slot: int,
        item_id: int,
        quantity: int,
        durability: Optional[int],
    ) -> None:
        """
        Set a single inventory slot and mark as dirty.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
            slot: Inventory slot number (0-27)
            item_id: Item's database ID
            quantity: Stack quantity
            durability: Current durability (None if item has no durability)
        """
        key = INVENTORY_KEY.format(player_id=player_id)
        data = json.dumps(
            {
                "item_id": item_id,
                "quantity": quantity,
                "durability": durability,
            }
        )
        await valkey.hset(key, {str(slot): data})
        await valkey.sadd(DIRTY_INVENTORY_KEY, [str(player_id)])

    @staticmethod
    async def delete_inventory_slot(
        valkey: GlideClient,
        player_id: int,
        slot: int,
    ) -> None:
        """
        Remove an inventory slot and mark as dirty.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
            slot: Inventory slot number to remove
        """
        key = INVENTORY_KEY.format(player_id=player_id)
        await valkey.hdel(key, [str(slot)])
        await valkey.sadd(DIRTY_INVENTORY_KEY, [str(player_id)])

    @staticmethod
    async def clear_inventory(
        valkey: GlideClient,
        player_id: int,
    ) -> None:
        """
        Clear all inventory slots and mark as dirty.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
        """
        key = INVENTORY_KEY.format(player_id=player_id)
        await valkey.delete(key)
        await valkey.sadd(DIRTY_INVENTORY_KEY, [str(player_id)])

    @staticmethod
    async def get_free_inventory_slot(
        valkey: GlideClient,
        player_id: int,
        max_slots: int = 28,
    ) -> Optional[int]:
        """
        Find the first free inventory slot.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
            max_slots: Maximum number of inventory slots

        Returns:
            First free slot number, or None if inventory is full
        """
        inventory = await PlayerStateValkeyService.get_inventory(valkey, player_id)
        used_slots = set(inventory.keys())

        for slot in range(max_slots):
            if slot not in used_slots:
                return slot

        return None

    @staticmethod
    async def get_inventory_count(
        valkey: GlideClient,
        player_id: int,
    ) -> int:
        """
        Get the number of occupied inventory slots.

        Returns:
            Number of slots with items
        """
        key = INVENTORY_KEY.format(player_id=player_id)
        raw = await valkey.hgetall(key)
        return len(raw) if raw else 0

    # ==================== EQUIPMENT ====================

    @staticmethod
    async def load_equipment_to_valkey(
        valkey: GlideClient,
        player_id: int,
        equipment_items: List[Dict],
    ) -> None:
        """
        Load player's equipment from DB format to Valkey on connect.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
            equipment_items: List of dicts with equipment_slot, item_id, quantity, current_durability
        """
        key = EQUIPMENT_KEY.format(player_id=player_id)

        # Clear existing equipment data
        await valkey.delete(key)

        if not equipment_items:
            return

        hash_data = {}
        for item in equipment_items:
            slot = item["equipment_slot"]
            hash_data[slot] = json.dumps(
                {
                    "item_id": item["item_id"],
                    "quantity": item["quantity"],
                    "durability": item.get("current_durability"),
                }
            )

        await valkey.hset(key, hash_data)
        logger.debug(
            "Loaded equipment to Valkey",
            extra={"player_id": player_id, "slots": len(hash_data)},
        )

    @staticmethod
    async def get_equipment(
        valkey: GlideClient,
        player_id: int,
    ) -> Dict[str, Dict]:
        """
        Get player's full equipment from Valkey.

        Returns:
            Dict mapping equipment slot name (str) to item data dict
        """
        key = EQUIPMENT_KEY.format(player_id=player_id)
        raw = await valkey.hgetall(key)

        if not raw:
            return {}

        result = {}
        for slot_bytes, data_bytes in raw.items():
            slot = slot_bytes.decode() if isinstance(slot_bytes, bytes) else slot_bytes
            data = json.loads(data_bytes.decode() if isinstance(data_bytes, bytes) else data_bytes)
            result[slot] = data

        return result

    @staticmethod
    async def get_equipment_slot(
        valkey: GlideClient,
        player_id: int,
        slot: str,
    ) -> Optional[Dict]:
        """
        Get a single equipment slot from Valkey.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
            slot: Equipment slot name (e.g., "head", "weapon")

        Returns:
            Item data dict or None if slot is empty
        """
        key = EQUIPMENT_KEY.format(player_id=player_id)
        raw = await valkey.hget(key, slot)

        if not raw:
            return None

        return json.loads(raw.decode() if isinstance(raw, bytes) else raw)

    @staticmethod
    async def set_equipment_slot(
        valkey: GlideClient,
        player_id: int,
        slot: str,
        item_id: int,
        quantity: int,
        durability: Optional[int],
    ) -> None:
        """
        Set a single equipment slot and mark as dirty.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
            slot: Equipment slot name (e.g., "head", "weapon")
            item_id: Item's database ID
            quantity: Stack quantity (usually 1, higher for ammo)
            durability: Current durability (None if item has no durability)
        """
        key = EQUIPMENT_KEY.format(player_id=player_id)
        data = json.dumps(
            {
                "item_id": item_id,
                "quantity": quantity,
                "durability": durability,
            }
        )
        await valkey.hset(key, {slot: data})
        await valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])

    @staticmethod
    async def delete_equipment_slot(
        valkey: GlideClient,
        player_id: int,
        slot: str,
    ) -> None:
        """
        Remove an equipment slot and mark as dirty.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
            slot: Equipment slot name to remove
        """
        key = EQUIPMENT_KEY.format(player_id=player_id)
        await valkey.hdel(key, [slot])
        await valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])

    @staticmethod
    async def clear_equipment(
        valkey: GlideClient,
        player_id: int,
    ) -> None:
        """
        Clear all equipment slots and mark as dirty.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
        """
        key = EQUIPMENT_KEY.format(player_id=player_id)
        await valkey.delete(key)
        await valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])

    # ==================== SKILLS ====================

    @staticmethod
    async def load_skills_to_valkey(
        valkey: GlideClient,
        player_id: int,
        skills: List[Dict],
    ) -> None:
        """
        Load player's skills from DB format to Valkey on connect.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
            skills: List of dicts with skill_name, skill_id, level, experience
        """
        key = SKILLS_KEY.format(player_id=player_id)

        # Clear existing skills data
        await valkey.delete(key)

        if not skills:
            return

        hash_data = {}
        for skill in skills:
            skill_name = skill["skill_name"]
            hash_data[skill_name] = json.dumps(
                {
                    "skill_id": skill["skill_id"],
                    "level": skill["level"],
                    "experience": skill["experience"],
                }
            )

        await valkey.hset(key, hash_data)
        logger.debug(
            "Loaded skills to Valkey",
            extra={"player_id": player_id, "skills": len(hash_data)},
        )

    @staticmethod
    async def get_skill(
        valkey: GlideClient,
        player_id: int,
        skill_name: str,
    ) -> Optional[Dict]:
        """
        Get a single skill from Valkey.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
            skill_name: Skill name (e.g., "attack", "hitpoints")

        Returns:
            Skill data dict or None if not found
        """
        key = SKILLS_KEY.format(player_id=player_id)
        raw = await valkey.hget(key, skill_name)

        if not raw:
            return None

        return json.loads(raw.decode() if isinstance(raw, bytes) else raw)

    @staticmethod
    async def get_all_skills(
        valkey: GlideClient,
        player_id: int,
    ) -> Dict[str, Dict]:
        """
        Get all skills for a player from Valkey.

        Returns:
            Dict mapping skill name to skill data dict
        """
        key = SKILLS_KEY.format(player_id=player_id)
        raw = await valkey.hgetall(key)

        if not raw:
            return {}

        result = {}
        for name_bytes, data_bytes in raw.items():
            name = name_bytes.decode() if isinstance(name_bytes, bytes) else name_bytes
            data = json.loads(data_bytes.decode() if isinstance(data_bytes, bytes) else data_bytes)
            result[name] = data

        return result

    @staticmethod
    async def set_skill(
        valkey: GlideClient,
        player_id: int,
        skill_name: str,
        skill_id: int,
        level: int,
        experience: int,
    ) -> None:
        """
        Update a skill in Valkey and mark as dirty.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
            skill_name: Skill name (e.g., "attack", "hitpoints")
            skill_id: Skill's database ID
            level: Current skill level
            experience: Total experience points
        """
        key = SKILLS_KEY.format(player_id=player_id)
        data = json.dumps(
            {
                "skill_id": skill_id,
                "level": level,
                "experience": experience,
            }
        )
        await valkey.hset(key, {skill_name: data})
        await valkey.sadd(DIRTY_SKILLS_KEY, [str(player_id)])

    # ==================== DIRTY TRACKING ====================

    @staticmethod
    async def mark_ground_items_dirty(valkey: GlideClient, map_id: str) -> None:
        """
        Mark a map's ground items as dirty (needs sync to DB).

        Args:
            valkey: Valkey client
            map_id: Map identifier
        """
        await valkey.sadd(DIRTY_GROUND_ITEMS_KEY, [map_id])

    @staticmethod
    async def get_dirty_set(valkey: GlideClient, key: str) -> Set[str]:
        """
        Get all members of a dirty tracking set.

        Args:
            valkey: Valkey client
            key: Dirty set key (e.g., DIRTY_INVENTORY_KEY)

        Returns:
            Set of string identifiers (player_ids or map_ids)
        """
        members = await valkey.smembers(key)
        if not members:
            return set()
        return {m.decode() if isinstance(m, bytes) else m for m in members}

    @staticmethod
    async def clear_dirty_set(valkey: GlideClient, key: str) -> None:
        """
        Clear a dirty tracking set after sync.

        Args:
            valkey: Valkey client
            key: Dirty set key to clear
        """
        await valkey.delete(key)

    @staticmethod
    async def remove_from_dirty_set(valkey: GlideClient, key: str, member: str) -> None:
        """
        Remove a single member from a dirty set.

        Args:
            valkey: Valkey client
            key: Dirty set key
            member: Member to remove
        """
        await valkey.srem(key, [member])

    # ==================== CLEANUP ====================

    @staticmethod
    async def delete_player_state(valkey: GlideClient, player_id: int) -> None:
        """
        Delete all player state from Valkey (on disconnect after sync).

        This removes inventory, equipment, and skills data, as well as
        removing the player from all dirty tracking sets.

        Args:
            valkey: Valkey client
            player_id: Player's database ID
        """
        # Delete state keys
        await valkey.delete(INVENTORY_KEY.format(player_id=player_id))
        await valkey.delete(EQUIPMENT_KEY.format(player_id=player_id))
        await valkey.delete(SKILLS_KEY.format(player_id=player_id))

        # Remove from dirty sets
        player_id_str = str(player_id)
        await valkey.srem(DIRTY_INVENTORY_KEY, [player_id_str])
        await valkey.srem(DIRTY_EQUIPMENT_KEY, [player_id_str])
        await valkey.srem(DIRTY_SKILLS_KEY, [player_id_str])

        logger.debug("Deleted player state from Valkey", extra={"player_id": player_id})
