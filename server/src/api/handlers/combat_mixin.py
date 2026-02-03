"""
Combat command handler mixin.

Handles attack and auto-retaliate commands.
"""

from typing import Any

import msgpack
from pydantic import ValidationError

from server.src.core.config import settings, game_config
from server.src.core.logging_config import get_logger
from server.src.services.game_state import (
    get_player_state_manager,
    get_entity_manager,
    get_equipment_manager,
    get_reference_data_manager,
)
from server.src.services.combat_service import CombatService
from server.src.api.helpers.rate_limiter import OperationRateLimiter

from common.src.protocol import (
    WSMessage,
    MessageType,
    ErrorCodes,
    ErrorCategory,
    AttackPayload,
    ToggleAutoRetaliatePayload,
    PROTOCOL_VERSION,
    CombatTargetType,
    PlayerSettingKey,
)

logger = get_logger(__name__)


class CombatHandlerMixin:
    """Handles CMD_ATTACK and CMD_TOGGLE_AUTO_RETALIATE."""
    
    websocket: Any
    username: str
    player_id: int
    
    async def _handle_cmd_attack(self, message: WSMessage) -> None:
        """Handle CMD_ATTACK - player attacks entity or player."""
        try:
            operation_rate_limiter = OperationRateLimiter()
            combat_cooldown = game_config.get("game", {}).get("security", {}).get("combat_attack_cooldown", 0.6)
            if not operation_rate_limiter.check_rate_limit(
                self.username,
                "combat_attack",
                combat_cooldown
            ):
                await self._send_error_response(
                    message.id,
                    ErrorCodes.MOVE_RATE_LIMITED,
                    ErrorCategory.RATE_LIMIT,
                    "Attack on cooldown"
                )
                return
            
            payload = AttackPayload(**message.payload)
            player_mgr = get_player_state_manager()
            entity_mgr = get_entity_manager()
            equipment_mgr = get_equipment_manager()
            reference_mgr = get_reference_data_manager()
            
            # Validate attacker state
            attacker_pos = await player_mgr.get_player_position(self.player_id)
            if not attacker_pos:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.SYS_INTERNAL_ERROR,
                    ErrorCategory.SYSTEM,
                    "Could not determine player position"
                )
                return
            
            attacker_hp = await player_mgr.get_player_hp(self.player_id)
            if not attacker_hp or attacker_hp["current_hp"] <= 0:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.SYS_INTERNAL_ERROR,
                    ErrorCategory.VALIDATION,
                    "You cannot attack while dead"
                )
                return
            
            # Validate target
            if payload.target_type == CombatTargetType.ENTITY:
                entity_id = int(payload.target_id)
                entity_data = await entity_mgr.get_entity_instance(entity_id)
                
                if not entity_data:
                    await self._send_error_response(
                        message.id,
                        ErrorCodes.SYS_INTERNAL_ERROR,
                        ErrorCategory.VALIDATION,
                        "Target entity not found"
                    )
                    return
                
                if not entity_data.get("is_attackable", True):
                    await self._send_error_response(
                        message.id,
                        ErrorCodes.SYS_INTERNAL_ERROR,
                        ErrorCategory.VALIDATION,
                        "Target cannot be attacked"
                    )
                    return
                
                if entity_data["map_id"] != attacker_pos["map_id"]:
                    await self._send_error_response(
                        message.id,
                        ErrorCodes.SYS_INTERNAL_ERROR,
                        ErrorCategory.VALIDATION,
                        "Target is not on the same map"
                    )
                    return
                
                defender_pos = {
                    "x": entity_data["x"],
                    "y": entity_data["y"],
                    "map_id": entity_data["map_id"]
                }
                
            else:  # player target
                await self._send_error_response(
                    message.id,
                    ErrorCodes.SYS_INTERNAL_ERROR,
                    ErrorCategory.VALIDATION,
                    "Player vs player combat is not yet implemented"
                )
                return
            
            # Check range - must be adjacent (within 1 tile)
            dx = abs(attacker_pos["x"] - defender_pos["x"])
            dy = abs(attacker_pos["y"] - defender_pos["y"])
            
            if dx > 1 or dy > 1:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.SYS_INTERNAL_ERROR,
                    ErrorCategory.VALIDATION,
                    "Target is too far away (must be within 1 tile)",
                    details={
                        "distance": {"x": dx, "y": dy},
                        "your_position": {"x": attacker_pos["x"], "y": attacker_pos["y"]},
                        "target_position": {"x": defender_pos["x"], "y": defender_pos["y"]}
                    }
                )
                return
            
            # Perform combat
            result = await CombatService.perform_attack(
                attacker_type=CombatTargetType.PLAYER,
                attacker_id=self.player_id,
                defender_type=payload.target_type,
                defender_id=int(payload.target_id),
            )
            
            if result.success:
                await self._send_success_response(
                    message.id,
                    {
                        "message": result.message,
                        "hit": result.hit,
                        "damage": result.damage,
                        "defender_hp": result.defender_hp,
                        "defender_died": result.defender_died,
                        "xp_gained": {skill.name.lower(): xp for skill, xp in result.xp_gained.items()}
                    }
                )
                
                # Broadcast combat event
                from server.src.api.websockets import manager
                combat_event = WSMessage(
                    id=None,
                    type=MessageType.EVENT_COMBAT_ACTION,
                    payload={
                        "attacker_type": CombatTargetType.PLAYER.value,
                        "attacker_id": self.player_id,
                        "attacker_name": self.username,
                        "defender_type": payload.target_type.value,
                        "defender_id": int(payload.target_id),
                        "defender_name": entity_data.get("display_name", "Unknown"),
                        "hit": result.hit,
                        "damage": result.damage,
                        "defender_hp": result.defender_hp,
                        "defender_died": result.defender_died,
                        "message": result.message
                    },
                    version=PROTOCOL_VERSION
                )
                
                packed_event = msgpack.packb(combat_event.model_dump(), use_bin_type=True)
                await manager.broadcast_to_map(attacker_pos["map_id"], packed_event)
                
                # Set combat state for auto-attack
                from server.src.game.game_loop import get_game_loop_state
                
                game_state = get_game_loop_state()
                
                equipment = await equipment_mgr.get_equipment(self.player_id)
                weapon_item = equipment.get("weapon")
                base_attack_speed = game_config.get("game", {}).get("combat", {}).get("base_attack_speed", 3.0)
                
                if weapon_item and weapon_item.get("item_id"):
                    weapon_meta = reference_mgr.get_cached_item_meta(weapon_item["item_id"])
                    attack_speed = weapon_meta.get("attack_speed", base_attack_speed) if weapon_meta else base_attack_speed
                else:
                    attack_speed = base_attack_speed
                
                await player_mgr.set_player_combat_state(
                    self.player_id,
                    payload.target_type.value,
                    int(payload.target_id)
                )
                
                logger.debug(
                    "Combat action executed",
                    extra={
                        "attacker": self.username,
                        "target_type": payload.target_type.value,
                        "target_id": payload.target_id,
                        "damage": result.damage,
                        "defender_died": result.defender_died
                    }
                )
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.SYS_INTERNAL_ERROR,
                    ErrorCategory.VALIDATION,
                    result.error or "Attack failed"
                )
                
        except ValidationError as e:
            logger.debug(
                "Attack command validation failed",
                extra={"username": self.username}
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                ErrorCategory.VALIDATION,
                "Invalid attack command"
            )
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(
                "Attack command failed",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": tb
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                ErrorCategory.SYSTEM,
                "Attack processing failed"
            )
    
    async def _handle_cmd_toggle_auto_retaliate(self, message: WSMessage) -> None:
        """Handle CMD_TOGGLE_AUTO_RETALIATE - toggle auto-retaliation setting."""
        try:
            payload = ToggleAutoRetaliatePayload(**message.payload)
            
            player_mgr = get_player_state_manager()
            await player_mgr.set_player_setting(self.player_id, PlayerSettingKey.AUTO_RETALIATE, payload.enabled)
            
            await self._send_success_response(
                message.id,
                {
                    "message": f"Auto-retaliate {'enabled' if payload.enabled else 'disabled'}",
                    "auto_retaliate": payload.enabled
                }
            )
            
            logger.debug(
                "Auto-retaliate toggled",
                extra={"username": self.username, "enabled": payload.enabled}
            )
            
        except ValidationError as e:
            logger.debug(
                "Toggle auto-retaliate validation failed",
                extra={"username": self.username}
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                ErrorCategory.VALIDATION,
                "Invalid toggle command"
            )
            
        except Exception as e:
            import traceback
            logger.error(
                "Error handling toggle auto-retaliate command",
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
                "Toggle auto-retaliate failed"
            )
