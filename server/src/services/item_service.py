"""
Service for managing item definitions.
"""

from typing import Optional, Dict, Any, List

from ..core.items import ItemType, ItemRarity
from ..core.logging_config import get_logger
from ..schemas.item import ItemInfo, ItemStats
from .game_state_manager import get_game_state_manager

logger = get_logger(__name__)


class ItemService:
    """Service for managing item definitions."""

    @staticmethod
    async def sync_items_to_db() -> list[Item]:
        """
        DEPRECATED: Architectural violation - direct database access in service layer.
        
        This method violates GSM architecture by accessing internal database sessions.
        It should be moved to GSM or removed entirely. Currently disabled.
        
        TODO: Refactor this as a GSM method for reference data management.
        """
        raise NotImplementedError(
            "sync_items_to_db() violates GSM architecture and is disabled. "
            "Reference data sync should be handled by GSM."
        )

    @staticmethod
    async def get_item_by_name(name: str) -> Optional[Dict[str, Any]]:
        """
        Get an item by its internal name using GSM cached methods.
        
        Note: This iterates through cached items since GSM doesn't have
        a direct get_item_by_name method. This should be optimized
        if performance becomes an issue.

        Args:
            name: Internal item name (e.g., "bronze_sword")

        Returns:
            Item data dict if found, None otherwise
        """
        gsm = get_game_state_manager()
        
        gsm = get_game_state_manager()
        name_lower = name.lower()
        
        # Check item reference data for name lookup
        if hasattr(gsm, '_item_cache') and gsm._item_cache:
            # Search through reference items by name
            for item_id, item_data in gsm._item_cache.items():
                if item_data.get("name") == name_lower:
                    return item_data  # Return item reference data directly
        
        # Item not found in reference data
        logger.warning(
            "Item not found by name in reference data",
            extra={"item_name": name, "cache_size": len(getattr(gsm, '_item_cache', {}))}
        )
        return None

    @staticmethod
    async def get_item_by_id(item_id: int) -> Optional[Dict[str, Any]]:
        """
        Get an item by its database ID using GSM cached methods.

        Args:
            item_id: Item database ID

        Returns:
            Item data dict if found, None otherwise
        """
        gsm = get_game_state_manager()
        
        # Check item reference data first (fastest lookup)
        cached_item = gsm.get_cached_item_meta(item_id)
        if cached_item:
            # Return reference data directly
            return cached_item
        
        # Retrieve item data from persistent storage
        item_data = await gsm.get_item_meta(item_id)
        if item_data:
            return item_data
        
        return None

    @staticmethod
    async def sync_enum_definitions_to_database():
        """
        Sync all item enum definitions to the database.
        
        This ensures the database has the latest item definitions from code.
        Maintains separation between reference data and player data.

        Note: This method currently requires implementation of reference data sync.
        For now, it logs the intent and returns empty list.

        Returns:
            Empty list (placeholder until sync methods are implemented)
        """
        logger.info(
            "Item sync requested - requires reference data sync implementation",
            extra={"enum_items": len(ItemType)},
        )
        
        # Reference item system not yet implemented
        return []

    @staticmethod
    def item_to_info(item_data: Dict[str, Any]) -> ItemInfo:
        """
        Convert item data dict to an ItemInfo schema.

        Args:
            item_data: Item data dictionary

        Returns:
            ItemInfo schema for client
        """
        # Get rarity color from enum
        try:
            rarity_value = item_data.get("rarity")
            if rarity_value:
                rarity_enum = ItemRarity.from_value(rarity_value)
                rarity_color = rarity_enum.color
            else:
                rarity_color = "#ffffff"  # Default to white
        except ValueError:
            rarity_color = "#ffffff"  # Default to white

        stats = ItemStats(
            attack_bonus=item_data.get("attack_bonus", 0),
            strength_bonus=item_data.get("strength_bonus", 0),
            ranged_attack_bonus=item_data.get("ranged_attack_bonus", 0),
            ranged_strength_bonus=item_data.get("ranged_strength_bonus", 0),
            magic_attack_bonus=item_data.get("magic_attack_bonus", 0),
            magic_damage_bonus=item_data.get("magic_damage_bonus", 0),
            physical_defence_bonus=item_data.get("physical_defence_bonus", 0),
            magic_defence_bonus=item_data.get("magic_defence_bonus", 0),
            health_bonus=item_data.get("health_bonus", 0),
            speed_bonus=item_data.get("speed_bonus", 0),
            mining_bonus=item_data.get("mining_bonus", 0),
            woodcutting_bonus=item_data.get("woodcutting_bonus", 0),
            fishing_bonus=item_data.get("fishing_bonus", 0),
        )

        return ItemInfo(
            id=int(item_data.get("id", 0)),
            name=str(item_data.get("name", "")),
            display_name=str(item_data.get("display_name", "")),
            description=str(item_data.get("description", "")),
            category=str(item_data.get("category", "")),
            rarity=str(item_data.get("rarity", "common")),
            rarity_color=rarity_color,
            equipment_slot=item_data.get("equipment_slot"),
            max_stack_size=int(item_data.get("max_stack_size", 1)),
            is_two_handed=bool(item_data.get("is_two_handed", False)),
            max_durability=item_data.get("max_durability"),
            is_indestructible=bool(item_data.get("is_indestructible", False)),
            required_skill=item_data.get("required_skill"),
            required_level=int(item_data.get("required_level", 1)),
            is_tradeable=bool(item_data.get("is_tradeable", True)),
            value=int(item_data.get("value", 0)),
            stats=stats,
        )

        return ItemInfo(
            id=item.id,
            name=item.name,
            display_name=item.display_name,
            description=item.description or "",
            category=item.category,
            rarity=item.rarity,
            rarity_color=rarity_color,
            equipment_slot=item.equipment_slot,
            max_stack_size=item.max_stack_size,
            is_two_handed=item_data.get("is_two_handed", False),
            max_durability=item_data.get("max_durability"),
            is_indestructible=item_data.get("is_indestructible", False),
            required_skill=item_data.get("required_skill"),
            required_level=item_data.get("required_level"),
            is_tradeable=item_data.get("is_tradeable", True),
            value=item_data.get("value", 0),
            stats=stats,
        )

    # Item data conversion methods available above
    # Services should work with dict data structures, not ORM models.
    # If model conversion is needed, it should be done at API boundaries using schemas.

