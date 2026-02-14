"""
Ground item command handler mixin.

Handles dropping and picking up items from the ground.
"""

import traceback
from typing import Any

from fastapi import WebSocket

from server.src.core.logging_config import get_logger
from server.src.services.game_state import get_player_state_manager
from server.src.services.ground_item_service import GroundItemService

from common.src.protocol import (
    WSMessage,
    ErrorCodes,
    ErrorCategory,
    ItemDropPayload,
    ItemPickupPayload,
)

logger = get_logger(__name__)


class GroundItemHandlerMixin:
    """Handles CMD_ITEM_DROP and CMD_ITEM_PICKUP."""
    
    websocket: WebSocket
    username: str
    player_id: int
    
    async def _handle_cmd_item_drop(self, message: WSMessage) -> None:
        """Handle CMD_ITEM_DROP - drop items to ground."""
        try:
            payload = ItemDropPayload(**message.payload)
            
            player_mgr = get_player_state_manager()
            position = await player_mgr.get_player_position(self.player_id)
            
            if not position:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.SYS_INTERNAL_ERROR,
                    ErrorCategory.SYSTEM,
                    "Could not determine player position"
                )
                return
            
            result = await GroundItemService.drop_from_inventory(
                player_id=self.player_id,
                inventory_slot=payload.inventory_slot,
                map_id=position["map_id"],
                x=position["x"],
                y=position["y"],
                quantity=payload.quantity,
            )
            
            if result.success:
                # Drop action breaks combat
                await player_mgr.clear_player_combat_state(self.player_id)
                
                await self._send_success_response(
                    message.id,
                    {
                        "message": result.message,
                        "ground_item_id": result.data.get("ground_item_id")
                    }
                )
                await self._send_inventory_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.INV_INSUFFICIENT_QUANTITY,
                    ErrorCategory.VALIDATION,
                    result.message,
                    details={"inventory_slot": payload.inventory_slot}
                )
                
        except Exception as e:
            logger.error(
                "Error handling item drop command",
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
                "Item drop failed"
            )
    
    async def _handle_cmd_item_pickup(self, message: WSMessage) -> None:
        """Handle CMD_ITEM_PICKUP - pickup ground items."""
        try:
            payload = ItemPickupPayload(**message.payload)
            
            player_mgr = get_player_state_manager()
            position = await player_mgr.get_player_position(self.player_id)
            
            if not position:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.SYS_INTERNAL_ERROR,
                    ErrorCategory.SYSTEM,
                    "Could not determine player position"
                )
                return
            
            result = await GroundItemService.pickup_item(
                player_id=self.player_id,
                ground_item_id=payload.ground_item_id,
                player_x=position["x"],
                player_y=position["y"],
                player_map_id=position["map_id"],
            )
            
            if result.success:
                # Pickup action breaks combat
                await player_mgr.clear_player_combat_state(self.player_id)
                
                await self._send_success_response(
                    message.id,
                    {"message": result.message}
                )
                await self._send_inventory_state_update()
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.GROUND_ITEM_NOT_FOUND,
                    ErrorCategory.VALIDATION,
                    result.message,
                    details={"ground_item_id": payload.ground_item_id}
                )
                
        except Exception as e:
            logger.error(
                "Error handling item pickup command",
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
                "Item pickup failed"
            )
