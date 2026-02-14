"""
Admin command handler mixin.

Handles admin-only commands like giving items to players.
"""

import traceback

import msgpack
from fastapi import WebSocket

from pydantic import ValidationError

from server.src.core.constants import PlayerRole
from server.src.core.logging_config import get_logger
from server.src.services.player_service import PlayerService
from server.src.services.inventory_service import InventoryService
from server.src.services.item_service import ItemService

from common.src.protocol import (
    WSMessage,
    MessageType,
    ErrorCodes,
    ErrorCategory,
    AdminGivePayload,
    PROTOCOL_VERSION,
)

logger = get_logger(__name__)

MAX_GIVE_QUANTITY = 1000


class AdminHandlerMixin:
    """Handles CMD_ADMIN_GIVE for admin item grants."""

    websocket: WebSocket
    username: str
    player_id: int

    async def _handle_cmd_admin_give(self, message: WSMessage) -> None:
        """Handle CMD_ADMIN_GIVE - grant items to a player's inventory."""
        try:
            payload = AdminGivePayload(**message.payload)
        except ValidationError:
            await self._send_error_response(
                message.id,
                ErrorCodes.ADMIN_INVALID_QUANTITY,
                ErrorCategory.VALIDATION,
                "Invalid admin give payload",
            )
            return

        try:
            # Validate quantity
            if payload.quantity < 1 or payload.quantity > MAX_GIVE_QUANTITY:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.ADMIN_INVALID_QUANTITY,
                    ErrorCategory.VALIDATION,
                    f"Quantity must be between 1 and {MAX_GIVE_QUANTITY}",
                    details={"quantity": payload.quantity},
                )
                return

            # Check caller has admin role
            caller_role = await PlayerService.get_player_role(self.player_id)
            if caller_role != PlayerRole.ADMIN:
                logger.warning(
                    "Non-admin attempted admin give command",
                    extra={
                        "player_id": self.player_id,
                        "username": self.username,
                        "role": caller_role.value if caller_role else None,
                    },
                )
                await self._send_error_response(
                    message.id,
                    ErrorCodes.ADMIN_NOT_AUTHORIZED,
                    ErrorCategory.PERMISSION,
                    "You do not have permission to use this command",
                )
                return

            # Resolve target player username to ID
            target_player = await PlayerService.get_player_by_username(
                payload.target_username
            )
            if not target_player:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.ADMIN_PLAYER_NOT_FOUND,
                    ErrorCategory.VALIDATION,
                    f"Player '{payload.target_username}' not found",
                    details={"target_username": payload.target_username},
                )
                return

            target_player_id = target_player.id

            # Look up item by internal name
            item = await ItemService.get_item_by_name(payload.item_name)
            if not item:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.ADMIN_ITEM_NOT_FOUND,
                    ErrorCategory.VALIDATION,
                    f"Item '{payload.item_name}' not found",
                    details={"item_name": payload.item_name},
                )
                return

            # Add item to target player's inventory via InventoryService
            result = await InventoryService.add_item(
                player_id=target_player_id,
                item_id=item.id,
                quantity=payload.quantity,
            )

            if not result.success:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.ADMIN_INVENTORY_FULL,
                    ErrorCategory.VALIDATION,
                    result.message,
                    details={
                        "target_player_id": target_player_id,
                        "item_name": payload.item_name,
                        "quantity": payload.quantity,
                    },
                )
                return

            # Send success response to admin caller
            await self._send_success_response(
                message.id,
                {
                    "message": f"Gave {payload.quantity}x {item.display_name} to {payload.target_username}",
                    "target_player_id": target_player_id,
                    "item_name": item.display_name,
                    "quantity": payload.quantity,
                },
            )

            logger.info(
                "Admin gave items to player",
                extra={
                    "admin_player_id": self.player_id,
                    "admin_username": self.username,
                    "target_player_id": target_player_id,
                    "target_username": payload.target_username,
                    "item_name": payload.item_name,
                    "quantity": payload.quantity,
                },
            )

            # If the target player is online, push an inventory state update
            await self._send_target_inventory_update(target_player_id)

        except Exception as e:
            logger.error(
                "Error handling admin give command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                },
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                ErrorCategory.SYSTEM,
                "Admin give command failed",
            )

    async def _send_target_inventory_update(self, target_player_id: int) -> None:
        """
        Send inventory state update to a target player if they are online.

        If the target is offline, their updated inventory will be loaded
        from the GSM automatically when they next connect.
        """
        try:
            from server.src.api.websockets import manager

            from server.src.schemas.item import InventoryData

            inventory_data = await InventoryService.get_inventory(target_player_id)

            state_update = WSMessage(
                id=None,
                type=MessageType.EVENT_STATE_UPDATE,
                payload={
                    "update_type": "full",
                    "target": "personal",
                    "systems": {"inventory": inventory_data.model_dump()},
                },
                version=PROTOCOL_VERSION,
            )

            packed = msgpack.packb(state_update.model_dump(), use_bin_type=True)
            await manager.send_personal_message(target_player_id, packed)

        except Exception as e:
            # Target may be offline — this is expected and not an error
            logger.debug(
                "Could not send inventory update to target player",
                extra={
                    "target_player_id": target_player_id,
                    "error": str(e),
                },
            )
