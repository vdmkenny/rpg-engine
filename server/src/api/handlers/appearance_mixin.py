"""
Appearance command handler mixin.

Handles player appearance updates (paperdoll customization).
"""

import traceback
from typing import Any

from fastapi import WebSocket

from server.src.core.logging_config import get_logger
from server.src.services.visual_state_service import VisualStateService
from server.src.services.visual_registry import visual_registry
from server.src.services.game_state import get_player_state_manager
from server.src.services.player_service import PlayerService

from common.src.protocol import (
    WSMessage,
    MessageType,
    ErrorCodes,
    ErrorCategory,
    AppearanceUpdatePayload,
)
from common.src.sprites import AppearanceData

logger = get_logger(__name__)


class AppearanceHandlerMixin:
    """Handles CMD_UPDATE_APPEARANCE for player appearance customization."""

    websocket: WebSocket
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
                    ErrorCodes.SYS_INTERNAL_ERROR,
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

            # Validate the appearance changes before applying
            validation_result = self._validate_appearance_changes(appearance_changes, current_appearance)
            if not validation_result["valid"]:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.APPEARANCE_INVALID_VALUE,
                    ErrorCategory.VALIDATION,
                    validation_result["error"]
                )
                return

            # Create updated appearance
            new_appearance = current_appearance.with_changes(**appearance_changes)

            # Save to database
            await PlayerService.update_player_appearance(
                self.player_id,
                new_appearance.to_dict()
            )

            # Invalidate visual cache to force re-render
            await visual_registry.invalidate_player(self.player_id)

            # Build full visual state for response and broadcast
            from server.src.services.visual_state_service import VisualStateService
            visual_data = await VisualStateService.get_player_visual_state(self.player_id)

            # Broadcast appearance change to nearby players
            await self._broadcast_appearance_update()

            # Send success response with full visual state
            await self._send_success_response(
                message.id,
                {
                    "appearance": new_appearance.to_dict(),
                    "visual_hash": visual_data["visual_hash"],
                    "visual_state": visual_data["visual_state"]
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
                ErrorCodes.APPEARANCE_UPDATE_FAILED,
                ErrorCategory.SYSTEM,
                "Failed to update appearance - please try again"
            )

    def _validate_appearance_changes(self, changes: dict, current_appearance: AppearanceData) -> dict:
        """
        Validate raw appearance change values before applying them.
        
        First checks enum membership, then verifies against player allowlist.
        Then performs cross-field validation (e.g., gender-restricted clothing).
        This prevents players from using options restricted to NPCs or admins.
        
        Args:
            changes: Dictionary of field changes from the payload
            current_appearance: The player's current appearance for context
            
        Returns:
            Dict with "valid" (bool) and optional "error" (str)
        """
        from common.src.sprites import BodyType, SkinTone, HeadType, HairStyle, HairColor, EyeColor
        from common.src.sprites.enums import FacialHairStyle, ClothingStyle, PantsStyle, ShoesStyle, ClothingColor
        from server.src.services.appearance_options_service import is_value_allowed_for_player, RESTRICTIONS
        
        # Mapping of field names to their enum classes
        enum_fields = {
            "body_type": BodyType,
            "skin_tone": SkinTone,
            "head_type": HeadType,
            "hair_style": HairStyle,
            "hair_color": HairColor,
            "eye_color": EyeColor,
            "facial_hair_style": FacialHairStyle,
            "facial_hair_color": HairColor,
            "shirt_style": ClothingStyle,
            "shirt_color": ClothingColor,
            "pants_style": PantsStyle,
            "pants_color": ClothingColor,
            "shoes_style": ShoesStyle,
            "shoes_color": ClothingColor,
        }
        
        for field_name, value in changes.items():
            if field_name in enum_fields:
                enum_cls = enum_fields[field_name]
                try:
                    enum_cls(value)
                except (ValueError, KeyError):
                    return {
                        "valid": False,
                        "error": f"Invalid value for {field_name}: '{value}'. Must be one of: {[e.value for e in enum_cls]}"
                    }
                
                # Check player allowlist (server-side enforcement)
                if not is_value_allowed_for_player(field_name, value):
                    return {
                        "valid": False,
                        "error": f"Value '{value}' is not available for players. "
                                  f"Field '{field_name}' has restricted options."
                    }
        
        # Cross-field validation: check gender-restricted clothing
        # Get effective body_type (from changes or current appearance)
        effective_body_type = changes.get("body_type", current_appearance.body_type.value)
        effective_shirt_style = changes.get("shirt_style", current_appearance.shirt_style.value)
        effective_shirt_color = changes.get("shirt_color", current_appearance.shirt_color.value)
        
        # Validate shirt_style against body_type restrictions
        shirt_restrictions = RESTRICTIONS.get("shirt_style", {})
        body_type_filter = shirt_restrictions.get("body_type_filter", {})
        
        if effective_shirt_style in body_type_filter:
            allowed_body_types = body_type_filter[effective_shirt_style]
            if effective_body_type not in allowed_body_types:
                gender_name = "female" if effective_body_type == "male" else "male"
                return {
                    "valid": False,
                    "error": f"'{effective_shirt_style}' is only available for {gender_name} characters."
                }
        
        # Validate shirt_color against shirt_style restrictions (robe limited palette)
        if effective_shirt_style == "robe":
            robe_valid_colors = RESTRICTIONS.get("shirt_color", {}).get("shirt_style_filter", {}).get("robe", [])
            if effective_shirt_color not in robe_valid_colors:
                return {
                    "valid": False,
                    "error": f"Color '{effective_shirt_color}' is not available for the robe style. "
                              f"Robe has a limited color palette."
                }
        
        return {"valid": True}

    async def _broadcast_appearance_update(self) -> None:
        """
        Broadcast appearance change to nearby players.

        This ensures other players see the updated appearance immediately.
        """
        try:
            # Use PlayerService to find nearby players and ConnectionManager to broadcast
            player_service = PlayerService()
            nearby_players = await player_service.get_nearby_players(self.player_id, radius=32)

            if not nearby_players:
                return

            # Build full visual state including appearance + equipment
            from server.src.services.visual_state_service import VisualStateService
            visual_data = await VisualStateService.get_player_visual_state(self.player_id)

            if not visual_data:
                logger.warning(
                    "No visual data available for appearance broadcast",
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
                "Failed to broadcast appearance update",
                extra={
                    "player_id": self.player_id,
                    "error": str(e)
                }
            )
