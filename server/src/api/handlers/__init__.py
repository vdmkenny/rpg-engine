"""
WebSocket message handler mixins.

These mixins provide domain-specific message handling for the WebSocketHandler class.
Compose them together to build the complete handler.
"""

from server.src.api.handlers.base_mixin import BaseHandlerMixin
from server.src.api.handlers.movement_mixin import MovementHandlerMixin
from server.src.api.handlers.chat_mixin import ChatHandlerMixin
from server.src.api.handlers.inventory_mixin import InventoryHandlerMixin
from server.src.api.handlers.ground_item_mixin import GroundItemHandlerMixin
from server.src.api.handlers.equipment_mixin import EquipmentHandlerMixin
from server.src.api.handlers.combat_mixin import CombatHandlerMixin
from server.src.api.handlers.query_mixin import QueryHandlerMixin
from server.src.api.handlers.appearance_mixin import AppearanceHandlerMixin
from server.src.api.handlers.admin_mixin import AdminHandlerMixin

__all__ = [
    "BaseHandlerMixin",
    "MovementHandlerMixin",
    "ChatHandlerMixin",
    "InventoryHandlerMixin",
    "GroundItemHandlerMixin",
    "EquipmentHandlerMixin",
    "CombatHandlerMixin",
    "QueryHandlerMixin",
    "AppearanceHandlerMixin",
    "AdminHandlerMixin",
]
