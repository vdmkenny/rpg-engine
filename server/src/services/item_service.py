"""
Service for managing item definitions.
"""

from typing import Optional, Dict, Any, List

from ..core.items import ItemType, ItemRarity
from ..core.logging_config import get_logger
from ..schemas.item import ItemInfo, ItemStats
from .game_state import get_reference_data_manager

logger = get_logger(__name__)


class ItemWrapper:
    """
    Simple wrapper to provide dict compatibility for item data.
    
    Allows dict-based item data to be accessed like an object with .id attribute
    and also supports dict-like methods like .get().
    """
    def __init__(self, item_data: Dict[str, Any]):
        self._data = item_data
    
    def __getattr__(self, name: str) -> Any:
        """Allow accessing dict keys as attributes."""
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def __setattr__(self, name: str, value: Any) -> None:
        """Allow setting attributes."""
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            if not hasattr(self, '_data'):
                super().__setattr__(name, value)
            else:
                self._data[name] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like get method."""
        return self._data.get(key, default)
    
    def __getitem__(self, key: str) -> Any:
        """Dict-like getitem method."""
        return self._data[key]
    
    def __setitem__(self, key: str, value: Any) -> None:
        """Dict-like setitem method."""
        self._data[key] = value
    
    def __contains__(self, key: str) -> bool:
        """Dict-like contains method."""
        return key in self._data
    
    def keys(self):
        """Dict-like keys method."""
        return self._data.keys()
    
    def values(self):
        """Dict-like values method."""
        return self._data.values()
    
    def items(self):
        """Dict-like items method."""
        return self._data.items()


class ItemService:
    """Service for managing item definitions."""

    @staticmethod
    async def sync_items_to_db() -> int:
        """
        Sync items from ItemType enum to database.
        
        Uses ReferenceDataManager to perform UPSERT operations for all items
        defined in the ItemType enum, ensuring database stays in sync with code.
        
        Returns:
            Number of items synced
        """
        ref_mgr = get_reference_data_manager()
        return await ref_mgr.sync_items_to_database()

    @staticmethod
    async def get_item_by_name(name: str) -> Optional[ItemWrapper]:
        """
        Get an item by its internal name using reference data manager.

        Args:
            name: Internal item name (e.g., "bronze_shortsword")

        Returns:
            ItemWrapper object if found, None otherwise
        """
        ref_mgr = get_reference_data_manager()
        
        # Lookup by name in reference data manager
        item_data = ref_mgr.get_cached_item_by_name(name)
        if item_data:
            return ItemWrapper(item_data)
        
        return None

    @staticmethod
    async def get_item_by_id(item_id: int) -> Optional[ItemWrapper]:
        """
        Get an item by its database ID using reference data manager.

        Args:
            item_id: Item database ID

        Returns:
            ItemWrapper object if found, None otherwise
        """
        ref_mgr = get_reference_data_manager()
        
        # Lookup in reference data manager cache
        item_data = ref_mgr.get_cached_item_meta(item_id)
        if item_data:
            return ItemWrapper(item_data)
        
        return None

    @staticmethod
    async def sync_enum_definitions_to_database() -> int:
        """
        Sync all item enum definitions to the database.
        
        This ensures the database has the latest item definitions from code.
        Uses ReferenceDataManager to perform UPSERT operations for all items
        defined in the ItemType enum.
        
        Returns:
            Number of items synced to database
        """
        return await ItemService.sync_items_to_db()

    @staticmethod
    def item_to_info(item_data: Dict[str, Any]) -> ItemInfo:
        """
        Convert item data dict to an ItemInfo schema.

        Args:
            item_data: Item data dictionary

        Returns:
            ItemInfo schema for client
        """
        # Get rarity color using the safe utility method
        rarity_color = ItemRarity.get_color(item_data.get("rarity"), default="#ffffff")

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
            icon_sprite_id=str(item_data.get("icon_sprite_id", "")),
            equipped_sprite_id=item_data.get("equipped_sprite_id"),
        )

    # Item data conversion methods available above
    # Services should work with dict data structures, not ORM models.
    # If model conversion is needed, it should be done at API boundaries using schemas.

