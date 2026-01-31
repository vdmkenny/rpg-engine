"""
Chat command handler mixin.

Handles chat message processing and broadcasting.
"""

from typing import Any

from pydantic import ValidationError

from server.src.core.logging_config import get_logger
from server.src.services.chat_service import ChatService

from common.src.protocol import (
    WSMessage,
    ErrorCodes,
    ChatSendPayload,
)

logger = get_logger(__name__)


class ChatHandlerMixin:
    """Handles CMD_CHAT_SEND for chat messages."""
    
    websocket: Any
    username: str
    player_id: int
    
    async def _handle_cmd_chat_send(self, message: WSMessage) -> None:
        """Handle CMD_CHAT_SEND - chat message processing."""
        try:
            payload = ChatSendPayload(**message.payload)
            
            from server.src.api.websockets import manager
            
            chat_result = await ChatService.handle_chat_message(
                self.player_id, self.username, payload.model_dump(), manager
            )
            
            if chat_result["success"]:
                await self._send_success_response(
                    message.id,
                    {
                        "channel": chat_result["channel"],
                        "message": chat_result["message_data"]["payload"]["message"] if "message_data" in chat_result else ""
                    }
                )
                
                logger.info(
                    "Chat message processed",
                    extra={
                        "username": self.username,
                        "channel": chat_result["channel"],
                        "recipient_count": len(chat_result.get("recipients", [])),
                        "message_id": chat_result.get("message_id")
                    }
                )
            else:
                await self._send_error_response(
                    message.id,
                    ErrorCodes.CHAT_MESSAGE_TOO_LONG,
                    "validation",
                    chat_result.get("reason", "Chat message rejected"),
                    details={"channel": payload.channel}
                )
                
        except ValidationError as e:
            logger.info(
                "Chat message validation failed",
                extra={"username": self.username, "validation_errors": str(e)}
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.CHAT_MESSAGE_TOO_LONG,
                "validation",
                "Message validation failed"
            )
            
        except Exception as e:
            logger.error(
                "Error handling chat command",
                extra={
                    "username": self.username,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            await self._send_error_response(
                message.id,
                ErrorCodes.CHAT_PERMISSION_DENIED,
                "system",
                "Chat processing failed"
            )
