"""
Base handler mixin providing shared response and state update methods.

All domain handler mixins inherit from this to access common utilities.
"""

import traceback
from typing import Optional, Dict, Any

import msgpack
from fastapi import WebSocket
from starlette.websockets import WebSocketState

from server.src.core.logging_config import get_logger
from server.src.core.metrics import metrics
from server.src.services.inventory_service import InventoryService
from server.src.services.equipment_service import EquipmentService

from common.src.protocol import (
    WSMessage,
    MessageType,
    ErrorResponsePayload,
    ErrorCategory,
    PROTOCOL_VERSION,
)

logger = get_logger(__name__)


class BaseHandlerMixin:
    """
    Provides shared response utilities for WebSocket handlers.
    
    Expects the following attributes on the composed class:
    - websocket: The WebSocket connection
    - username: Player's username
    - player_id: Player's database ID
    """
    
    websocket: WebSocket
    username: str
    player_id: int
    
    async def _send_success_response(
        self, 
        correlation_id: Optional[str], 
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Send RESP_SUCCESS with correlation ID."""
        response = WSMessage(
            id=correlation_id,
            type=MessageType.RESP_SUCCESS,
            payload=data or {},
            version=PROTOCOL_VERSION
        )
        await self._send_message(response)
    
    async def _send_error_response(
        self,
        correlation_id: Optional[str],
        error_code: str,
        error_category: ErrorCategory,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        retry_after: Optional[float] = None,
        suggested_action: Optional[str] = None
    ) -> None:
        """Send RESP_ERROR with structured error information."""
        error_payload = ErrorResponsePayload(
            error_code=error_code,
            error=message,
            category=error_category,
            details=details,
            retry_after=retry_after,
            suggested_action=suggested_action
        )
        
        response = WSMessage(
            id=correlation_id,
            type=MessageType.RESP_ERROR,
            payload=error_payload.model_dump(),
            version=PROTOCOL_VERSION
        )
        await self._send_message(response)
    
    async def _send_data_response(
        self, 
        correlation_id: Optional[str], 
        data: Dict[str, Any]
    ) -> None:
        """Send RESP_DATA with query results."""
        response = WSMessage(
            id=correlation_id,
            type=MessageType.RESP_DATA,
            payload=data,
            version=PROTOCOL_VERSION
        )
        await self._send_message(response)
    
    async def _send_message(self, message: WSMessage) -> None:
        """
        Send message with serialization and connection health checks.
        
        Raises:
            ConnectionError: If WebSocket is closed/closing, so the message loop can handle disconnection
        """
        message_dump = message.model_dump()
        packed_message = msgpack.packb(message_dump, use_bin_type=True)
        
        # Check connection state before sending
        if hasattr(self.websocket, 'client_state'):
            if self.websocket.client_state == WebSocketState.DISCONNECTED:
                logger.warning(
                    "Attempted to send on closed WebSocket",
                    extra={"username": self.username, "message_type": message.type}
                )
                raise ConnectionError("WebSocket connection is closed")
        
        try:
            await self.websocket.send_bytes(packed_message)
            metrics.track_websocket_message(str(message.type), "outbound")
        except Exception as e:
            logger.error(
                "Error sending WebSocket message",
                extra={
                    "username": self.username,
                    "message_type": message.type,
                    "correlation_id": message.id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }
            )
            raise
    
    async def _send_inventory_state_update(self) -> None:
        """Send personal inventory state update event."""
        try:
            from server.src.schemas.item import InventoryData
            inventory_data = await InventoryService.get_inventory(self.player_id)
            
            state_update = WSMessage(
                id=None,
                type=MessageType.EVENT_STATE_UPDATE,
                payload={
                    "update_type": "full",
                    "target": "personal",
                    "systems": {
                        "inventory": inventory_data.model_dump()
                    }
                },
                version=PROTOCOL_VERSION
            )
            await self._send_message(state_update)
            
        except Exception as e:
            logger.error(
                "Error sending inventory state update",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }
            )
    
    async def _send_equipment_state_update(self) -> None:
        """Send consolidated equipment state update (inventory + equipment + stats)."""
        try:
            from server.src.schemas.item import InventoryData, EquipmentData, ItemStats
            inventory_data = await InventoryService.get_inventory(self.player_id)
            equipment_data = await EquipmentService.get_equipment(self.player_id)
            stats_data = await EquipmentService.get_total_stats(self.player_id)
            
            state_update = WSMessage(
                id=None,
                type=MessageType.EVENT_STATE_UPDATE,
                payload={
                    "update_type": "full",
                    "target": "personal",
                    "systems": {
                        "inventory": inventory_data.model_dump(),
                        "equipment": equipment_data.model_dump(),
                        "stats": stats_data.model_dump()
                    }
                },
                version=PROTOCOL_VERSION
            )
            await self._send_message(state_update)
            
        except Exception as e:
            logger.error(
                "Error sending equipment state update",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }
            )
