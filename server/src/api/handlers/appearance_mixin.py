"""
Appearance command handler mixin.

Handles player appearance updates (paperdoll customization).
"""

import traceback
from typing import Any

from server.src.core.logging_config import get_logger
from server.src.services.visual_state_service import VisualStateService
from server.src.services.visual_registry import visual_registry
from server.src.services.game_state import get_player_state_manager
from server.src.services.player_service import PlayerService

from common.src.protocol import (
    WSMessage,
    MessageType,
    ErrorCategory,
    AppearanceUpdatePayload,
)
from common.src.sprites import AppearanceData

logger = get_logger(__name__)


class AppearanceHandlerMixin:
    """Handles CMD_UPDATE_APPEARANCE for player appearance customization."""

    websocket: Any
    username: str
    player_id: int

    async def _handle_cmd_update_appearance(self, message: WSMessage) -> None:
        """Handle CMD_UPDATE_APPEARANCE - update player paperdoll appearance."""
        try:
            player_mgr = get_player_state_manager()

            if not await player_mgr.is_online(self.player_id):
                logger.warning(
                    "Player attempted appearance update while not online",
                    extra={"player_id": self.player_id, "username": self.username}
                )
                await self._send_error_response(
                    message.id,
                    "PLAYER_NOT_ONLINE",
                    ErrorCategory.SYSTEM,
                    "Player not properly initialized - please reconnect"
                )
                return

            # Parse the appearance update payload
            payload = AppearanceUpdatePayload(**message.payload)

            # Get current appearance from database
            current_appearance_dict = await PlayerService.get_player_appearance(self.player_id)
            if current_appearance_dict is None:
                # Use defaults if no appearance set
                current_appearance = AppearanceData()
            else:
                current_appearance = AppearanceData.from_dict(current_appearance_dict)

            # Build new appearance with only the fields that were provided
            appearance_changes = {}
            if payload.body_type is not None:
                appearance_changes["body_type"] = payload.body_type
            if payload.skin_tone is not None:
                appearance_changes["skin_tone"] = payload.skin_tone
            if payload.head_type is not None:
                appearance_changes["head_type"] = payload.head_type
            if payload.hair_style is not None:
                appearance_changes["hair_style"] = payload.hair_style
            if payload.hair_color is not None:
                appearance_changes["hair_color"] = payload.hair_color
            if payload.eye_color is not None:
                appearance_changes["eye_color"] = payload.eye_color
            if payload.facial_hair_style is not None:
                appearance_changes["facial_hair_style"] = payload.facial_hair_style
            if payload.facial_hair_color is not None:
                appearance_changes["facial_hair_color"] = payload.facial_hair_color
            if payload.shirt_style is not None:
                appearance_changes["shirt_style"] = payload.shirt_style
            if payload.shirt_color is not None:
                appearance_changes["shirt_color"] = payload.shirt_color
            if payload.pants_style is not None:
                appearance_changes["pants_style"] = payload.pants_style
            if payload.pants_color is not None:
                appearance_changes["pants_color"] = payload.pants_color
            if payload.shoes_style is not None:
                appearance_changes["shoes_style"] = payload.shoes_style
            if payload.shoes_color is not None:
                appearance_changes["shoes_color"] = payload.shoes_color

            # Create updated appearance
            new_appearance = current_appearance.with_changes(**appearance_changes)

            # Validate the appearance
            validation_result = self._validate_appearance(new_appearance)
            if not validation_result["valid"]:
                await self._send_error_response(
                    message.id,
                    "INVALID_APPEARANCE",
                    ErrorCategory.VALIDATION,
                    validation_result["error"]
                )
                return

            # Save to database
            await PlayerService.update_player_appearance(
                self.player_id,
                new_appearance.to_dict()
            )

            # Invalidate visual cache to force re-render
            visual_registry.invalidate_player(self.player_id)

            # Broadcast appearance change to nearby players
            await self._broadcast_appearance_update(new_appearance)

            # Send success response with new appearance
            await self._send_success_response(
                message.id,
                {
                    "appearance": new_appearance.to_dict(),
                    "visual_hash": new_appearance.compute_hash()
                }
            )

            logger.info(
                "Player appearance updated",
                extra={
                    "player_id": self.player_id,
                    "username": self.username,
                    "changes": list(appearance_changes.keys())
                }
            )

        except Exception as e:
            logger.error(
                "Error handling appearance update",
                extra={
                    "player_id": self.player_id,
                    "username": self.username,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }
            )
            await self._send_error_response(
                message.id,
                "APPEARANCE_UPDATE_FAILED",
                ErrorCategory.SYSTEM,
                "Failed to update appearance - please try again"
            )

    def _validate_appearance(self, appearance: AppearanceData) -> dict:
        """
        Validate appearance data.

        Returns:
            Dict with "valid" (bool) and optional "error" (str)
        """
        try:
            # Check that all enums are valid by attempting to serialize
            _ = appearance.to_dict()

            # Additional business rules can be added here
            # e.g., certain body types can't have certain hair styles, etc.

            return {"valid": True}
        except Exception as e:
            return {"valid": False, "error": f"Invalid appearance value: {str(e)}"}

    async def _broadcast_appearance_update(self, appearance: AppearanceData) -> None:
        """
        Broadcast appearance change to nearby players.

        This ensures other players see the updated appearance immediately.
        """
        try:
            from server.src.services.broadcast_service import broadcast_service

            # Get visual state for hash
            visual_state = await VisualStateService.get_player_visual_state(self.player_id)
            visual_hash = visual_state.compute_hash() if visual_state else None

            # Broadcast to nearby players
            await broadcast_service.broadcast_to_nearby(
                self.player_id,
                MessageType.EVENT_APPEARANCE_UPDATE,
                {
                    "player_id": self.player_id,
                    "username": self.username,
                    "appearance": appearance.to_dict(),
                    "visual_hash": visual_hash
                }
            )

        except Exception as e:
            logger.error(
                "Failed to broadcast appearance update",
                extra={
                    "player_id": self.player_id,
                    "error": str(e)
                }
            )
