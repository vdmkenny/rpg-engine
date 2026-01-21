"""
Unified Item Management Service

Consolidates all item-related operations including:
- Inventory management (add, remove, move, stack operations)
- Equipment management (equip, unequip, stat calculations)
- Ground item operations (drop, pickup, death drops)
- Multi-step atomic transactions

This service provides a single interface for all item operations while
maintaining the existing GameStateManager (GSM) pattern for state management.
"""

from .item_manager import ItemManager

__all__ = ["ItemManager", "get_item_manager"]


_item_manager_instance = None


def get_item_manager() -> ItemManager:
    """Get the singleton ItemManager instance."""
    global _item_manager_instance
    if _item_manager_instance is None:
        _item_manager_instance = ItemManager()
    return _item_manager_instance
