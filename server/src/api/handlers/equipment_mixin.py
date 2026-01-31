"""
Equipment command handler mixin.

Handles equipping and unequipping items.
"""

from typing import Any

from server.src.core.logging_config import get_logger
from server.src.core.items import EquipmentSlot
from server.src.services.equipment_service import EquipmentService

from common.src.protocol import (
    WSMessage,
    ErrorCodes,
    ItemEquipPayload,
    ItemUnequipPayload,
)

logger = get_logger(__name__)


class EquipmentHandlerMixin:
    """Handles CMD_ITEM_EQUIP and CMD_ITEM_UNEQUIP."""
    
    websocket: Any
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
                    "validation",
                    result.message,
                    details={"inventory_slot": payload.inventory_slot}
                )
                
        except Exception as e:
            logger.error(
                "Error handling item equip command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.EQ_REQUIREMENTS_NOT_MET,
                "system",
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
                    "validation",
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
                    "validation",
                    result.message,
                    details={"equipment_slot": payload.equipment_slot}
                )
                
        except Exception as e:
            logger.error(
                "Error handling item unequip command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                "system",
                "Item unequip failed"
            )
