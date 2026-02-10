"""
Equipment command handler mixin.

Handles equipping and unequipping items.
"""

import traceback
from typing import Any

from fastapi import WebSocket

from server.src.core.logging_config import get_logger
from server.src.core.items import EquipmentSlot
from server.src.services.equipment_service import EquipmentService

from common.src.protocol import (
    WSMessage,
    ErrorCodes,
    ErrorCategory,
    ItemEquipPayload,
    ItemUnequipPayload,
)

logger = get_logger(__name__)


class EquipmentHandlerMixin:
    """Handles CMD_ITEM_EQUIP and CMD_ITEM_UNEQUIP."""
    
    websocket: WebSocket
    username: str
    player_id: int
    
    async def _handle_cmd_item_equip(self, message: WSMessage) -> None:
        """Handle CMD_ITEM_EQUIP - equip items from inventory."""
        try:
            payload = ItemEquipPayload(**message.payload)
            
            result = await EquipmentService.equip_from_inventory(
                self.player_id, payload.inventory_slot
            )
            
            if result.success:
                await self._send_success_response(
                    message.id,
                    {"message": result.message}
                )
                await self._send_equipment_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.EQ_ITEM_NOT_EQUIPABLE,
                    ErrorCategory.VALIDATION,
                    result.message,
                    details={"inventory_slot": payload.inventory_slot}
                )
                
        except Exception as e:
            logger.error(
                "Error handling item equip command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                ErrorCategory.SYSTEM,
                "Item equip failed"
            )
    
    async def _handle_cmd_item_unequip(self, message: WSMessage) -> None:
        """Handle CMD_ITEM_UNEQUIP - unequip items to inventory."""
        try:
            payload = ItemUnequipPayload(**message.payload)
            
            try:
                slot = EquipmentSlot(payload.equipment_slot)
            except ValueError:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.EQ_INVALID_SLOT,
                    ErrorCategory.VALIDATION,
                    f"Invalid equipment slot: {payload.equipment_slot}"
                )
                return
            
            result = await EquipmentService.unequip_to_inventory(self.player_id, slot)
            
            if result.success:
                await self._send_success_response(
                    message.id,
                    {"message": result.message}
                )
                await self._send_equipment_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.EQ_CANNOT_UNEQUIP_FULL_INV,
                    ErrorCategory.VALIDATION,
                    result.message,
                    details={"equipment_slot": payload.equipment_slot}
                )
                
        except Exception as e:
            logger.error(
                "Error handling item unequip command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                ErrorCategory.SYSTEM,
                "Item unequip failed"
            )
