"""
Service for managing chat operations.

Handles chat message validation, channel routing, permission checking, and broadcasting logic.
"""

from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
import time

from ..core.logging_config import get_logger
from ..core.config import settings
from .game_state_manager import get_game_state_manager
from .player_service import PlayerService

logger = get_logger(__name__)


class ChatService:
    """Service for managing chat operations."""

    @staticmethod
    def get_message_length_limit(channel: str) -> int:
        """
        Get message length limit for specific channel type.
        
        Args:
            channel: Channel type (local, global, dm)
            
        Returns:
            Maximum message length for the channel
        """
        channel = channel.lower()
        if channel == "local":
            return settings.CHAT_MAX_MESSAGE_LENGTH_LOCAL
        elif channel == "global":
            return settings.CHAT_MAX_MESSAGE_LENGTH_GLOBAL
        elif channel == "dm":
            return settings.CHAT_MAX_MESSAGE_LENGTH_DM
        else:
            # Default to local chat limit for unknown channels
            return settings.CHAT_MAX_MESSAGE_LENGTH_LOCAL

    @staticmethod
    def create_system_error_message(error_message: str, channel: str = "system") -> Dict[str, Any]:
        """
        Create standardized system error message for chat UI.
        
        Args:
            error_message: The error message to display
            channel: Channel type for the system message
            
        Returns:
            Formatted system message dict
        """
        return {
            "username": "System",
            "message": error_message,
            "channel": channel,
            "timestamp": time.time()
        }

    @staticmethod
    async def validate_global_chat_permission(
        db: AsyncSession, player_id: int
    ) -> Dict[str, Any]:
        """
        Validate if player has permission to send global chat messages.
        
        Args:
            db: Database session
            player_id: Player ID to check
            
        Returns:
            Dict with validation result and error message if needed
        """
        try:
            # Check if global chat is enabled server-wide
            if not settings.CHAT_GLOBAL_ENABLED:
                return {
                    "valid": False,
                    "error_message": "Global chat is currently disabled.",
                    "system_message": ChatService.create_system_error_message(
                        "Global chat is currently disabled."
                    )
                }
            
            # Check player's role permission
            has_permission = await PlayerService.check_global_chat_permission(db, player_id)
            if not has_permission:
                return {
                    "valid": False,
                    "error_message": "You don't have permission to send global messages.",
                    "system_message": ChatService.create_system_error_message(
                        "You don't have permission to send global messages."
                    )
                }
            
            return {"valid": True}
            
        except Exception as e:
            logger.error(
                "Error validating global chat permission",
                extra={
                    "player_id": player_id,
                    "error": str(e),
                }
            )
            return {
                "valid": False,
                "error_message": "Permission check failed.",
                "system_message": ChatService.create_system_error_message(
                    "Unable to verify chat permissions."
                )
            }

    @staticmethod
    async def validate_message(
        message: str, channel: str, db: AsyncSession, player_id: int
    ) -> Dict[str, Any]:
        """
        Validate a chat message with channel-specific limits and permissions.
        
        Args:
            message: Message content
            channel: Channel type (local, global, dm)
            db: Database session (required for permission checking)
            player_id: Player ID (required for permission checking)
            
        Returns:
            Dict with validation result, processed message, and any error messages
        """
        validation_result = {
            "valid": True,
            "message": message,
            "reason": None,
            "system_message": None
        }

        channel = channel.lower()
        
        # Get channel-specific message length limit
        max_length = ChatService.get_message_length_limit(channel)
        
        # Check message length
        if len(message) == 0:
            validation_result.update({
                "valid": False,
                "reason": "Message too short",
                "system_message": ChatService.create_system_error_message(
                    "Message cannot be empty."
                )
            })
            return validation_result

        if len(message) > max_length:
            # Truncate instead of rejecting
            validation_result["message"] = message[:max_length]
            logger.info(
                "Message truncated to channel maximum length",
                extra={
                    "channel": channel,
                    "original_length": len(message),
                    "max_length": max_length
                }
            )

        # Strip whitespace
        validation_result["message"] = validation_result["message"].strip()

        # Check if message is empty after stripping
        if not validation_result["message"]:
            validation_result.update({
                "valid": False,
                "reason": "Message empty after processing",
                "system_message": ChatService.create_system_error_message(
                    "Message cannot be empty."
                )
            })
            return validation_result

        # Channel-specific validation
        if channel == "global":
            # Check global chat permissions
            permission_result = await ChatService.validate_global_chat_permission(db, player_id)
            if not permission_result["valid"]:
                validation_result.update({
                    "valid": False,
                    "reason": permission_result["error_message"],
                    "system_message": permission_result["system_message"]
                })
                return validation_result

        logger.debug(
            "Message validated successfully",
            extra={
                "channel": channel,
                "message_length": len(validation_result["message"]),
                "original_length": len(message)
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
            # Calculate local chat range in tiles from chunk radius
            # Each chunk is 16x16 tiles, so radius * 16 gives tile range
            local_chat_range = settings.CHAT_LOCAL_CHUNK_RADIUS * 16
            
            # Get nearby players within local chat range
            nearby_players = await PlayerService.get_nearby_players(
                sender_id, local_chat_range
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
                    "recipient_count": len(recipients),
                    "chat_range": local_chat_range
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
            if not PlayerService.is_player_online(recipient.id):
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
            logger.error(
                "Error getting global chat recipients",
                extra={"error": str(e)}
            )
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
        import msgpack
        from common.src.protocol import GameMessage, MessageType
        
        try:
            channel = payload.get("channel", "local").lower()
            message = payload.get("message", "").strip()
            
            # Validate message using enhanced service with permission checking
            validation_result = await ChatService.validate_message(
                message, channel, db, player_id
            )
            
            if not validation_result["valid"]:
                # Send system error message to the sender
                if validation_result.get("system_message"):
                    system_msg = GameMessage(
                        type=MessageType.NEW_CHAT_MESSAGE,
                        payload=validation_result["system_message"]
                    )
                    packed_message = msgpack.packb(system_msg.model_dump(), use_bin_type=True)
                    await connection_manager.send_personal_message(username, packed_message)
                
                return {
                    "success": False,
                    "reason": validation_result["reason"]
                }
                
            # Use the processed message (potentially truncated)
            processed_message = validation_result["message"]
            
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
                    player_id, "current_map"  # TODO: Get actual map_id from player state
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
                        # Send system error message for DM recipient not found
                        error_msg = ChatService.create_system_error_message(
                            f"Player '{target_username}' not found or offline."
                        )
                        system_response = GameMessage(
                            type=MessageType.NEW_CHAT_MESSAGE,
                            payload=error_msg
                        )
                        packed_message = msgpack.packb(system_response.model_dump(), use_bin_type=True)
                        await connection_manager.send_personal_message(username, packed_message)
                        
                        return {
                            "success": False,
                            "reason": "dm_recipient_not_found"
                        }
                else:
                    # DM system notification  
                    dm_response = GameMessage(
                        type=MessageType.NEW_CHAT_MESSAGE,
                        payload=ChatService.create_system_error_message(
                            "Direct messages require a target username.",
                            "system"
                        )
                    )
                    packed_message = msgpack.packb(dm_response.model_dump(), use_bin_type=True)
                    await connection_manager.send_personal_message(username, packed_message)
                    recipients = [username]
                     
            return {
                "success": True,
                "channel": channel,
                "recipients": recipients,
                "message_id": f"{player_id}_{int(time.time())}",
                "message_data": chat_response.model_dump()
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