"""
Query handler mixin.

Handles all QUERY_* message types for data retrieval.
"""

from typing import Any

from server.src.core.logging_config import get_logger
from server.src.services.inventory_service import InventoryService
from server.src.services.equipment_service import EquipmentService
from server.src.services.map_service import get_map_manager

from common.src.protocol import (
    WSMessage,
    ErrorCodes,
    MapChunksQueryPayload,
)

logger = get_logger(__name__)


class QueryHandlerMixin:
    """Handles all QUERY_* message types."""
    
    websocket: Any
    username: str
    player_id: int
    
    async def _handle_query_inventory(self, message: WSMessage) -> None:
        """Handle QUERY_INVENTORY - retrieve current inventory state."""
        try:
            inventory_data = await InventoryService.get_inventory_response(self.player_id)
            
            await self._send_data_response(
                message.id,
                {
                    "inventory": inventory_data.model_dump(),
                    "query_type": "inventory"
                }
            )
            
        except Exception as e:
            logger.error(
                "Error handling inventory query",
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
                "Inventory query failed"
            )
    
    async def _handle_query_equipment(self, message: WSMessage) -> None:
        """Handle QUERY_EQUIPMENT - retrieve current equipment state."""
        try:
            equipment_data = await EquipmentService.get_equipment_response(self.player_id)
            
            await self._send_data_response(
                message.id,
                {
                    "equipment": equipment_data.model_dump(),
                    "query_type": "equipment"
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
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.SYS_INTERNAL_ERROR,
                "system",
                "Equipment query failed"
            )
    
    async def _handle_query_stats(self, message: WSMessage) -> None:
        """Handle QUERY_STATS - retrieve aggregated player stats."""
        try:
            stats_data = await EquipmentService.get_total_stats(self.player_id)
            
            await self._send_data_response(
                message.id,
                {
                    "stats": stats_data.model_dump(),
                    "query_type": "stats"
                }
            )
            
        except Exception as e:
            logger.error(
                "Error handling stats query",
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
                "Stats query failed"
            )
    
    async def _handle_query_map_chunks(self, message: WSMessage) -> None:
        """Handle QUERY_MAP_CHUNKS - retrieve map chunk data."""
        try:
            payload = MapChunksQueryPayload(**message.payload)
            
            map_manager = get_map_manager()
            is_valid = await map_manager.validate_chunk_request_security(
                self.player_id,
                payload.map_id,
                payload.center_x,
                payload.center_y,
                payload.radius
            )
            
            if not is_valid:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.MAP_INVALID_COORDS,
                    "validation",
                    "Invalid chunk request parameters",
                    details={
                        "map_id": payload.map_id,
                        "center": (payload.center_x, payload.center_y),
                        "radius": payload.radius
                    }
                )
                return
            
            chunk_data = map_manager.get_chunks_for_player(
                payload.map_id,
                payload.center_x,
                payload.center_y,
                payload.radius
            )
            
            await self._send_data_response(
                message.id,
                {
                    "chunks": chunk_data or [],
                    "map_id": payload.map_id,
                    "center": {"x": payload.center_x, "y": payload.center_y},
                    "radius": payload.radius,
                    "query_type": "map_chunks"
                }
            )
            
            logger.debug(
                "Map chunks query processed",
                extra={
                    "username": self.username,
                    "map_id": payload.map_id,
                    "center": (payload.center_x, payload.center_y),
                    "radius": payload.radius,
                    "chunks_count": len(chunk_data) if chunk_data else 0
                }
            )
            
        except Exception as e:
            logger.error(
                "Error handling map chunks query",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.MAP_NOT_FOUND,
                "system",
                "Map chunks query failed"
            )
