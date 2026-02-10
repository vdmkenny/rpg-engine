"""
Message sender for client-to-server communication.

Provides type-safe methods for sending all commands and queries.
"""

import uuid
from typing import Dict, Any, Optional, Callable
import asyncio

from .connection import get_connection_manager
from ..logging_config import get_logger

import sys
from pathlib import Path
common_path = Path(__file__).parent.parent.parent.parent / "common" / "src"
if str(common_path) not in sys.path:
    sys.path.insert(0, str(common_path))

from protocol import MessageType, Direction, ChatChannel, InventorySortCriteria

logger = get_logger(__name__)


class MessageSender:
    """Sends messages to the server with proper formatting."""
    
    def __init__(self):
        self.connection = get_connection_manager()
    
    def _generate_id(self) -> str:
        """Generate a unique correlation ID."""
        return str(uuid.uuid4())
    
    async def _send(self, msg_type: MessageType, payload: Dict[str, Any]) -> bool:
        """Send a message to the server."""
        correlation_id = self._generate_id()
        return await self.connection.send_command(msg_type, payload, correlation_id)
    
    # =========================================================================
    # COMMANDS
    # =========================================================================
    
    async def authenticate(self, token: str) -> bool:
        """Send authentication command."""
        return await self._send(
            MessageType.CMD_AUTHENTICATE,
            {"token": token}
        )
    
    async def move(self, direction: Direction) -> bool:
        """Send move command."""
        return await self._send(
            MessageType.CMD_MOVE,
            {"direction": direction.value}
        )
    
    async def chat_send(self, message: str, channel: ChatChannel = ChatChannel.LOCAL, recipient: Optional[str] = None) -> bool:
        """Send chat message."""
        payload = {"message": message, "channel": channel.value}
        if recipient:
            payload["recipient"] = recipient
        return await self._send(MessageType.CMD_CHAT_SEND, payload)
    
    async def inventory_move(self, from_slot: int, to_slot: int) -> bool:
        """Move item between inventory slots."""
        return await self._send(
            MessageType.CMD_INVENTORY_MOVE,
            {"from_slot": from_slot, "to_slot": to_slot}
        )
    
    async def inventory_sort(self, sort_by) -> bool:
        """Sort inventory by criteria."""
        # Handle both enum and string values
        if isinstance(sort_by, str):
            sort_value = sort_by
        else:
            sort_value = sort_by.value
        return await self._send(
            MessageType.CMD_INVENTORY_SORT,
            {"sort_by": sort_value}
        )
    
    async def item_drop(self, inventory_slot: int, quantity: int = 1) -> bool:
        """Drop item from inventory to ground."""
        return await self._send(
            MessageType.CMD_ITEM_DROP,
            {"inventory_slot": inventory_slot, "quantity": quantity}
        )
    
    async def item_pickup(self, ground_item_id: str) -> bool:
        """Pick up item from ground."""
        return await self._send(
            MessageType.CMD_ITEM_PICKUP,
            {"ground_item_id": ground_item_id}
        )
    
    async def item_equip(self, inventory_slot: int) -> bool:
        """Equip item from inventory."""
        return await self._send(
            MessageType.CMD_ITEM_EQUIP,
            {"inventory_slot": inventory_slot}
        )
    
    async def item_unequip(self, equipment_slot: str) -> bool:
        """Unequip item to inventory."""
        return await self._send(
            MessageType.CMD_ITEM_UNEQUIP,
            {"equipment_slot": equipment_slot}
        )
    
    async def attack(self, target_type: str, target_id: int) -> bool:
        """Attack a target (entity or player)."""
        return await self._send(
            MessageType.CMD_ATTACK,
            {"target_type": target_type, "target_id": target_id}
        )
    
    async def toggle_auto_retaliate(self, enabled: bool) -> bool:
        """Toggle auto-retaliation setting."""
        return await self._send(
            MessageType.CMD_TOGGLE_AUTO_RETALIATE,
            {"enabled": enabled}
        )
    
    async def update_appearance(self, appearance_data: Dict[str, Any]) -> bool:
        """Update player appearance."""
        return await self._send(
            MessageType.CMD_UPDATE_APPEARANCE,
            appearance_data
        )
    
    # =========================================================================
    # QUERIES
    # =========================================================================
    
    async def query_inventory(self) -> bool:
        """Request inventory data."""
        return await self._send(MessageType.QUERY_INVENTORY, {})
    
    async def query_equipment(self) -> bool:
        """Request equipment data."""
        return await self._send(MessageType.QUERY_EQUIPMENT, {})
    
    async def query_stats(self) -> bool:
        """Request player stats and skills."""
        return await self._send(MessageType.QUERY_STATS, {})
    
    async def query_map_chunks(self, center_x: int, center_y: int, radius: int = 2) -> bool:
        """Request map chunk data."""
        return await self._send(
            MessageType.QUERY_MAP_CHUNKS,
            {"center_x": center_x, "center_y": center_y, "radius": radius}
        )


# Singleton
_message_sender: Optional[MessageSender] = None


def get_message_sender() -> MessageSender:
    """Get the singleton message sender."""
    global _message_sender
    if _message_sender is None:
        _message_sender = MessageSender()
    return _message_sender
