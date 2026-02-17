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
from server.src.services.visual_state_service import VisualStateService
from server.src.services.visual_registry import visual_registry

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
                # Invalidate visual cache and build new visual state
                await visual_registry.invalidate_player(self.player_id)
                visual_data = await VisualStateService.get_player_visual_state(self.player_id)

                # Send success response with visual state for immediate local update
                await self._send_success_response(
                    message.id,
                    {
                        "message": result.message,
                        "visual_hash": visual_data["visual_hash"],
                        "visual_state": visual_data["visual_state"]
                    }
                )

                # Broadcast to nearby players so they see the change immediately
                await self._broadcast_equipment_change()

                # Also send equipment state update
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
                # Invalidate visual cache and build new visual state
                await visual_registry.invalidate_player(self.player_id)
                visual_data = await VisualStateService.get_player_visual_state(self.player_id)

                # Send success response with visual state for immediate local update
                await self._send_success_response(
                    message.id,
                    {
                        "message": result.message,
                        "visual_hash": visual_data["visual_hash"],
                        "visual_state": visual_data["visual_state"]
                    }
                )

                # Broadcast to nearby players so they see the change immediately
                await self._broadcast_equipment_change()

                # Also send equipment state update
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
    async def _broadcast_equipment_change(self) -> None:
        """
        Broadcast equipment change to nearby players.

        This ensures other players see the equipment change immediately
        without waiting for the next game loop tick.
        """
        try:
            from server.src.services.player_service import PlayerService
            player_service = PlayerService()
            nearby_players = await player_service.get_nearby_players(self.player_id, radius=32)

            if not nearby_players:
                return

            # Build full visual state including appearance + equipment
            visual_data = await VisualStateService.get_player_visual_state(self.player_id)

            if not visual_data:
                logger.warning(
                    "No visual data available for equipment broadcast",
                    extra={"player_id": self.player_id}
                )
                return

            # Build the event payload with full visual_state
            event_payload = {
                "player_id": self.player_id,
                "username": self.username,
                "visual_hash": visual_data["visual_hash"],
                "visual_state": visual_data["visual_state"]
            }

            # Create the event message
            from common.src.websocket_utils import create_event
            from common.src.protocol import MessageType
            event_msg = create_event(MessageType.EVENT_APPEARANCE_UPDATE, event_payload)

            # Pack the message
            import msgpack
            message_data = msgpack.packb(event_msg.model_dump())

            # Get list of nearby player IDs
            nearby_player_ids = [player.player_id for player in nearby_players]

            # Broadcast to nearby players
            from server.src.api.websockets import manager as connection_manager
            await connection_manager.broadcast_to_players(nearby_player_ids, message_data)

        except Exception as e:
            logger.error(
                "Failed to broadcast equipment change",
                extra={
                    "player_id": self.player_id,
                    "error": str(e)
                }
            )

