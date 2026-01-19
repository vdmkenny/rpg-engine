"""
Service for managing chat operations.

Handles chat message validation, channel routing, and broadcasting logic.
"""

from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from .game_state_manager import get_game_state_manager
from .player_service import PlayerService

logger = get_logger(__name__)


class ChatService:
    """Service for managing chat operations."""

    # Chat message limits
    MAX_MESSAGE_LENGTH = 280
    MIN_MESSAGE_LENGTH = 1

    # Chat ranges in tiles
    LOCAL_CHAT_RANGE = 80  # 5 chunks = 80 tiles

    @staticmethod
    async def validate_message(message: str, channel_type: str) -> Dict[str, Any]:
        """
        Validate a chat message for content and channel appropriateness.

        Args:
            message: Message content
            channel_type: Type of chat channel (local, global, dm)

        Returns:
            Dict with validation result and processed message
        """
        validation_result = {
            "valid": True,
            "message": message,
            "reason": None
        }

        # Check message length
        if len(message) < ChatService.MIN_MESSAGE_LENGTH:
            validation_result.update({
                "valid": False,
                "reason": "Message too short"
            })
            return validation_result

        if len(message) > ChatService.MAX_MESSAGE_LENGTH:
            # Truncate instead of rejecting
            validation_result["message"] = message[:ChatService.MAX_MESSAGE_LENGTH]
            logger.info(
                "Message truncated to maximum length",
                extra={
                    "original_length": len(message),
                    "max_length": ChatService.MAX_MESSAGE_LENGTH
                }
            )

        # Strip whitespace
        validation_result["message"] = validation_result["message"].strip()

        # Check if message is empty after stripping
        if not validation_result["message"]:
            validation_result.update({
                "valid": False,
                "reason": "Message empty after processing"
            })
            return validation_result

        # Basic content filtering could be added here
        # For now, we accept all non-empty messages

        logger.debug(
            "Message validated successfully",
            extra={
                "channel_type": channel_type,
                "message_length": len(validation_result["message"])
            }
        )

        return validation_result

    @staticmethod
    async def get_local_chat_recipients(
        sender_id: int, sender_map_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get list of players who should receive a local chat message.

        Args:
            sender_id: Player ID sending the message
            sender_map_id: Map where sender is located

        Returns:
            List of recipient player data
        """
        try:
            # Get nearby players within local chat range
            nearby_players = await PlayerService.get_nearby_players(
                sender_id, ChatService.LOCAL_CHAT_RANGE
            )

            recipients = []
            for player in nearby_players:
                recipients.append({
                    "player_id": player["player_id"],
                    "username": player["username"],
                    "distance": abs(player["x"] - player.get("sender_x", 0)) + 
                               abs(player["y"] - player.get("sender_y", 0))
                })

            logger.debug(
                "Found local chat recipients",
                extra={
                    "sender_id": sender_id,
                    "recipient_count": len(recipients)
                }
            )

            return recipients

        except Exception as e:
            logger.error(
                "Error getting local chat recipients",
                extra={
                    "sender_id": sender_id,
                    "error": str(e)
                }
            )
            return []

    @staticmethod
    async def get_dm_recipient(
        db: AsyncSession, recipient_username: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get recipient information for direct message.

        Args:
            db: Database session
            recipient_username: Target username for DM

        Returns:
            Recipient data or None if not found/not online
        """
        from .player_service import PlayerService
        
        try:
            # Get player from database
            recipient = await PlayerService.get_player_by_username(db, recipient_username)
            if not recipient:
                logger.debug(
                    "DM recipient not found",
                    extra={"recipient_username": recipient_username}
                )
                return None

            # Check if player is online
            state_manager = get_game_state_manager()
            if not state_manager.is_player_online(recipient.id):
                logger.debug(
                    "DM recipient not online",
                    extra={"recipient_username": recipient_username}
                )
                return None

            return {
                "player_id": recipient.id,
                "username": recipient.username
            }

        except Exception as e:
            logger.error(
                "Error getting DM recipient",
                extra={
                    "recipient_username": recipient_username,
                    "error": str(e)
                }
            )
            return None

    @staticmethod
    async def get_global_chat_recipients() -> List[Dict[str, Any]]:
        """
        Get all online players for global chat broadcast.

        Returns:
            List of all online player data
        """
        try:
            state_manager = get_game_state_manager()
            online_players = state_manager.get_online_players()

            recipients = []
            for player_id in online_players:
                username = state_manager.get_username_by_id(player_id)
                if username:
                    recipients.append({
                        "player_id": player_id,
                        "username": username
                    })

            logger.debug(
                "Found global chat recipients",
                extra={"recipient_count": len(recipients)}
            )

            return recipients

        except Exception as e:
            return []

    @staticmethod
    async def handle_chat_message(
        db: AsyncSession, 
        player_id: int, 
        username: str, 
        payload: Dict[str, Any],
        connection_manager
    ) -> Dict[str, Any]:
        """
        Handle a complete chat message from a player.
        
        Args:
            db: Database session
            player_id: Sender's player ID
            username: Sender's username
            payload: Chat message payload
            connection_manager: WebSocket connection manager
            
        Returns:
            Dict with result status and message details
        """
        import time
        import msgpack
        from common.src.protocol import GameMessage, MessageType
        
        try:
            channel = payload.get("channel", "local").lower()
            message = payload.get("message", "").strip()
            
            # Validate message using service
            validation_result = await ChatService.validate_message(message)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "reason": validation_result["reason"]
                }
                
            # Use the processed message (potentially truncated)
            processed_message = validation_result["processed_message"]
            
            logger.info(
                "Processing chat message via service",
                extra={
                    "username": username,
                    "channel": channel,
                    "message_length": len(processed_message)
                }
            )
            
            # Create the chat message response
            chat_response = GameMessage(
                type=MessageType.NEW_CHAT_MESSAGE,
                payload={
                    "username": username,
                    "message": processed_message,
                    "channel": channel,
                    "timestamp": time.time()
                }
            )
            
            recipients = []
            
            if channel == "global":
                # Broadcast to all connected players
                packed_message = msgpack.packb(chat_response.model_dump(), use_bin_type=True)
                await connection_manager.broadcast_to_all(packed_message)
                recipients = ["all_players"]  # Placeholder for metrics
                
            elif channel == "local":
                # Get nearby players for local chat
                nearby_players = await ChatService.get_local_chat_recipients(
                    db, player_id, username
                )
                
                if nearby_players:
                    recipient_usernames = [p["username"] for p in nearby_players]
                    packed_message = msgpack.packb(chat_response.model_dump(), use_bin_type=True)
                    await connection_manager.broadcast_to_users(recipient_usernames, packed_message)
                    recipients = recipient_usernames
                    
            elif channel == "dm":
                # Handle direct message
                target_username = payload.get("target")
                if target_username:
                    recipient_data = await ChatService.get_dm_recipient(db, target_username)
                    if recipient_data:
                        packed_message = msgpack.packb(chat_response.model_dump(), use_bin_type=True)
                        await connection_manager.send_personal_message(target_username, packed_message)
                        recipients = [target_username]
                    else:
                        return {
                            "success": False,
                            "reason": "dm_recipient_not_found"
                        }
                else:
                    # DM system notification  
                    dm_response = GameMessage(
                        type=MessageType.NEW_CHAT_MESSAGE,
                        payload={
                            "username": "System",
                            "message": "Direct messages not yet implemented",
                            "channel": "dm",
                            "timestamp": time.time()
                        }
                    )
                    packed_message = msgpack.packb(dm_response.model_dump(), use_bin_type=True)
                    await connection_manager.send_personal_message(username, packed_message)
                    recipients = [username]
                    
            return {
                "success": True,
                "channel": channel,
                "recipients": recipients,
                "message_id": f"{player_id}_{int(time.time())}"
            }
            
        except Exception as e:
            logger.error(
                "Error in handle_chat_message service",
                extra={
                    "player_id": player_id,
                    "username": username,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            return {
                "success": False,
                "reason": "service_error",
                "error": str(e)
            }

    @staticmethod
    def format_chat_message(
        sender_username: str, 
        message: str, 
        channel_type: str,
        recipient_username: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Format a chat message for broadcasting.

        Args:
            sender_username: Username of sender
            message: Message content
            channel_type: Chat channel type
            recipient_username: Target username for DMs

        Returns:
            Formatted message data
        """
        formatted_message = {
            "sender": sender_username,
            "message": message,
            "channel": channel_type,
            "timestamp": None  # Will be set by WebSocket handler
        }

        if channel_type == "dm" and recipient_username:
            formatted_message["recipient"] = recipient_username

        return formatted_message

    @staticmethod
    def is_valid_channel_type(channel_type: str) -> bool:
        """
        Check if the channel type is supported.

        Args:
            channel_type: Channel type to validate

        Returns:
            True if valid channel type
        """
        valid_channels = {"local", "global", "dm"}
        return channel_type in valid_channels