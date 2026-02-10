"""
Query handler mixin.

Handles all QUERY_* message types for data retrieval.
"""

import traceback
from typing import Any

from fastapi import WebSocket

from server.src.core.logging_config import get_logger
from server.src.services.inventory_service import InventoryService
from server.src.services.equipment_service import EquipmentService
from server.src.services.map_service import get_map_manager

from common.src.protocol import (
    WSMessage,
    ErrorCodes,
    ErrorCategory,
    MapChunksQueryPayload,
)

logger = get_logger(__name__)


class QueryHandlerMixin:
    """Handles all QUERY_* message types."""
    
    websocket: WebSocket
    username: str
    player_id: int
    
    async def _handle_query_inventory(self, message: WSMessage) -> None:
        """Handle QUERY_INVENTORY - retrieve current inventory state."""
        try:
            inventory_data = await InventoryService.get_inventory(self.player_id)
            
            await self._send_data_response(
                message.id,
                {
                    "inventory": inventory_data.model_dump()
                }
            )
            
        except Exception as e:
            logger.error(
                "Error handling inventory query",
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
                "Inventory query failed"
            )
    
    async def _handle_query_equipment(self, message: WSMessage) -> None:
        """Handle QUERY_EQUIPMENT - retrieve current equipment state."""
        try:
            equipment_data = await EquipmentService.get_equipment(self.player_id)
            
            await self._send_data_response(
                message.id,
                {
                    "equipment": equipment_data.model_dump()
                }
            )
            
            logger.debug(
                "Equipment query processed",
                extra={
                    "username": self.username,
                    "correlation_id": message.id,
                    "equipment_slots": len(equipment_data.model_dump().get("slots", {}))
                }
            )
            
        except Exception as e:
            logger.error(
                "Error handling equipment query",
                extra={
                    "username": self.username,
                    "correlation_id": message.id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                ErrorCategory.SYSTEM,
                "Equipment query failed"
            )
    
    async def _handle_query_stats(self, message: WSMessage) -> None:
        """Handle QUERY_STATS - retrieve aggregated player stats and skills."""
        try:
            from server.src.services.skill_service import SkillService
            
            stats_data = await EquipmentService.get_total_stats(self.player_id)
            
            # Get skills in list format (consistent with other responses)
            skills_list = await SkillService.get_player_skills(self.player_id)
            total_level = sum(s.current_level for s in skills_list)
            
            await self._send_data_response(
                message.id,
                {
                    "stats": stats_data.model_dump(),
                    "skills": skills_list,
                    "total_level": total_level
                }
            )
            
        except Exception as e:
            logger.error(
                "Error handling stats query",
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
                "Stats query failed"
            )
    
    async def _handle_query_map_chunks(self, message: WSMessage) -> None:
        """Handle QUERY_MAP_CHUNKS - retrieve map chunk data."""
        try:
            from server.src.services.game_state import get_player_state_manager

            try:
                payload = MapChunksQueryPayload(**message.payload)
            except Exception as e:
                logger.error("Invalid chunk query payload", extra={"payload": message.payload, "error": str(e)})
                await self._send_error_response(
                    message.id,
                    ErrorCodes.MAP_INVALID_COORDS,
                    ErrorCategory.VALIDATION,
                    f"Invalid payload: {str(e)}"
                )
                return

            # Get player's current map from their position
            try:
                player_mgr = get_player_state_manager()
                player_pos = await player_mgr.get_player_position(self.player_id)
            except Exception as e:
                logger.error("Error getting player position", extra={"player_id": self.player_id, "error": str(e)})
                await self._send_error_response(
                    message.id,
                    ErrorCodes.MAP_NOT_FOUND,
                    ErrorCategory.SYSTEM,
                    f"Error getting player position: {str(e)}"
                )
                return
                
            if not player_pos:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.MAP_NOT_FOUND,
                    ErrorCategory.VALIDATION,
                    "Player position not found"
                )
                return
            
            map_id = player_pos.get("map_id", "samplemap")
            
            try:
                map_manager = get_map_manager()
                is_valid = await map_manager.validate_chunk_request_security(
                    self.player_id,
                    map_id,
                    payload.center_x,
                    payload.center_y,
                    payload.radius
                )
            except Exception as e:
                logger.error("Error validating chunk request", extra={
                    "player_id": self.player_id,
                    "map_id": map_id,
                    "center": (payload.center_x, payload.center_y),
                    "error": str(e),
                })
                await self._send_error_response(
                    message.id,
                    ErrorCodes.MAP_NOT_FOUND,
                    ErrorCategory.SYSTEM,
                    f"Error validating chunk request: {str(e)}"
                )
                return
            
            if not is_valid:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.MAP_INVALID_COORDS,
                    ErrorCategory.VALIDATION,
                    "Invalid chunk request parameters",
                    details={
                        "map_id": map_id,
                        "center": (payload.center_x, payload.center_y),
                        "radius": payload.radius
                    }
                )
                return
            
            try:
                chunk_data = map_manager.get_chunks_for_player(
                    map_id,
                    payload.center_x,
                    payload.center_y,
                    payload.radius
                )
            except Exception as e:
                logger.error("Error getting chunks for player", extra={
                    "map_id": map_id,
                    "center": (payload.center_x, payload.center_y),
                    "error": str(e),
                })
                await self._send_error_response(
                    message.id,
                    ErrorCodes.MAP_NOT_FOUND,
                    ErrorCategory.SYSTEM,
                    f"Error getting chunks: {str(e)}"
                )
                return
            
            await self._send_data_response(
                message.id,
                {
                    "chunks": chunk_data or [],
                    "map_id": map_id,
                    "center": {"x": payload.center_x, "y": payload.center_y},
                    "radius": payload.radius
                }
            )
            
            logger.debug(
                "Map chunks query processed",
                extra={
                    "username": self.username,
                    "map_id": map_id,
                    "center": (payload.center_x, payload.center_y),
                    "radius": payload.radius,
                    "chunks_count": len(chunk_data) if chunk_data else 0
                }
            )
            
        except Exception as e:
            error_msg = f"Unexpected error in map chunks query: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            await self._send_error_response(
                message.id,
                ErrorCodes.MAP_NOT_FOUND,
                ErrorCategory.SYSTEM,
                f"Map chunks query failed: {str(e)}"
            )
