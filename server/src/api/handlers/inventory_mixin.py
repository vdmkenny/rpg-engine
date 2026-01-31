"""
Inventory command handler mixin.

Handles inventory management operations like moving and sorting items.
"""

from typing import Any

from server.src.core.logging_config import get_logger
from server.src.core.items import InventorySortType
from server.src.services.inventory_service import InventoryService

from common.src.protocol import (
    WSMessage,
    ErrorCodes,
    InventoryMovePayload,
    InventorySortPayload,
)

logger = get_logger(__name__)


class InventoryHandlerMixin:
    """Handles CMD_INVENTORY_MOVE and CMD_INVENTORY_SORT."""
    
    websocket: Any
    username: str
    player_id: int
    
    async def _handle_cmd_inventory_move(self, message: WSMessage) -> None:
        """Handle CMD_INVENTORY_MOVE - move items within inventory."""
        try:
            payload = InventoryMovePayload(**message.payload)
            
            result = await InventoryService.move_item(
                self.player_id, payload.from_slot, payload.to_slot
            )
            
            if result.success:
                await self._send_success_response(
                    message.id,
                    {"message": result.message}
                )
                await self._send_inventory_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.INV_SLOT_EMPTY,
                    "validation",
                    result.message,
                    details={"from_slot": payload.from_slot, "to_slot": payload.to_slot}
                )
                
        except Exception as e:
            logger.error(
                "Error handling inventory move command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.INV_INVENTORY_FULL,
                "system",
                "Inventory move failed"
            )
    
    async def _handle_cmd_inventory_sort(self, message: WSMessage) -> None:
        """Handle CMD_INVENTORY_SORT - sort inventory by criteria."""
        try:
            payload = InventorySortPayload(**message.payload)
            
            try:
                sort_type = InventorySortType(payload.sort_by)
            except ValueError:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.INV_INVALID_SLOT,
                    "validation",
                    f"Invalid sort type: {payload.sort_by}"
                )
                return
            
            result = await InventoryService.sort_inventory(self.player_id, sort_type)
            
            if result.success:
                await self._send_success_response(
                    message.id,
                    {
                        "message": result.message,
                        "items_moved": result.items_moved,
                        "stacks_merged": result.stacks_merged
                    }
                )
                await self._send_inventory_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.INV_SLOT_EMPTY,
                    "validation",
                    result.message
                )
                
        except Exception as e:
            logger.error(
                "Error handling inventory sort command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.INV_INVENTORY_FULL,
                "system",
                "Inventory sort failed"
            )
