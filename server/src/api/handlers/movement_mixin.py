"""
Movement command handler mixin.

Handles player movement with collision detection and rate limiting.
"""

import traceback
from typing import Any

from server.src.core.logging_config import get_logger
from server.src.core.metrics import metrics
from server.src.services.game_state_manager import get_game_state_manager
from server.src.services.movement_service import MovementService

from common.src.protocol import (
    WSMessage,
    MessageType,
    ErrorCodes,
    MovePayload,
)

logger = get_logger(__name__)


class MovementHandlerMixin:
    """Handles CMD_MOVE for player movement."""
    
    websocket: Any
    username: str
    player_id: int
    
    async def _handle_cmd_move(self, message: WSMessage) -> None:
        """Handle CMD_MOVE - player movement with collision detection."""
        try:
            gsm = get_game_state_manager()
            
            if not gsm.is_online(self.player_id):
                logger.warning(
                    "Player attempted movement while not online",
                    extra={"player_id": self.player_id, "username": self.username}
                )
                await self._send_error_response(
                    message.id,
                    ErrorCodes.MOVE_RATE_LIMITED,
                    "system",
                    "Player not properly initialized - please reconnect"
                )
                return
            
            payload = MovePayload(**message.payload)
            
            movement_result = await MovementService.execute_movement(
                self.player_id, payload.direction
            )
            
            if movement_result["success"]:
                await self._send_success_response(
                    message.id,
                    {
                        "new_position": movement_result["new_position"],
                        "old_position": movement_result["old_position"]
                    }
                )
                metrics.track_player_movement(payload.direction)
                
                logger.debug(
                    "Player movement executed",
                    extra={
                        "username": self.username,
                        "direction": payload.direction,
                        "from_position": movement_result["old_position"],
                        "to_position": movement_result["new_position"]
                    }
                )
            else:
                reason = movement_result.get("reason", "unknown")
                
                if reason == "rate_limited":
                    error_code = ErrorCodes.MOVE_RATE_LIMITED
                    error_category = "rate_limit"
                    error_message = "Movement cooldown active"
                    details = {
                        "current_position": movement_result.get("current_position"),
                        "cooldown_remaining": movement_result.get("cooldown_remaining", 0)
                    }
                    suggested_action = "Wait before moving again"
                elif reason == "blocked":
                    error_code = ErrorCodes.MOVE_COLLISION_DETECTED
                    error_category = "validation"
                    error_message = "Movement blocked by obstacle"
                    details = {"current_position": movement_result.get("current_position")}
                    suggested_action = None
                elif reason == "invalid_direction":
                    error_code = ErrorCodes.MOVE_INVALID_DIRECTION
                    error_category = "validation"
                    error_message = "Invalid movement direction"
                    details = {"current_position": movement_result.get("current_position")}
                    suggested_action = None
                else:
                    error_code = ErrorCodes.MOVE_RATE_LIMITED
                    error_category = "system"
                    error_message = f"Movement failed: {reason}"
                    details = {"current_position": movement_result.get("current_position")}
                    suggested_action = None
                
                await self._send_error_response(
                    message.id,
                    error_code,
                    error_category,
                    error_message,
                    details=details,
                    suggested_action=suggested_action
                )
                
        except Exception as e:
            logger.error(
                "Movement command processing failed",
                extra={
                    "username": self.username,
                    "player_id": self.player_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }
            )
            
            await self._send_error_response(
                message.id,
                ErrorCodes.MOVE_RATE_LIMITED,
                "system",
                "Movement processing failed"
            )
