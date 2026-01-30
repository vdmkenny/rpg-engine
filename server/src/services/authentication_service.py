"""
Service for managing WebSocket authentication operations.

Handles JWT validation, player authentication, and session management.
"""

from typing import Dict, Optional, Any
from datetime import datetime, timezone

from ..core.security import verify_token, verify_password
from ..core.logging_config import get_logger
from ..models.player import Player
from .player_service import PlayerService
from .game_state_manager import get_game_state_manager

logger = get_logger(__name__)


class AuthenticationService:
    """Service for managing authentication operations."""

    @staticmethod
    async def authenticate_with_password(
        username: str, password: str
    ) -> Optional[Player]:
        """
        Authenticate a user with username and password.

        Args:
            username: User's username
            password: User's password

        Returns:
            Player instance if authenticated, None otherwise
            
        Raises:
            PermissionError: If player is banned
            ValueError: If player is timed out
        """
        try:
            # Get player by username
            player = await PlayerService.get_player_by_username(username)
            if not player:
                logger.debug(
                    "Authentication failed - player not found",
                    extra={"username": username}
                )
                return None

            # Verify password
            if not verify_password(password, player.hashed_password):
                logger.debug(
                    "Authentication failed - invalid password",
                    extra={"username": username}
                )
                return None

            # Check if player is banned
            if player.is_banned:
                logger.warning(
                    "Authentication failed - player banned",
                    extra={"username": username, "player_id": player.id}
                )
                raise PermissionError("Player is banned")

            # Check if player is timed out
            if player.timeout_until:
                # Handle both timezone-aware and naive datetimes
                timeout_until = player.timeout_until
                if timeout_until.tzinfo is None:
                    timeout_until = timeout_until.replace(tzinfo=timezone.utc)
                if timeout_until > datetime.now(timezone.utc):
                    logger.warning(
                        "Authentication failed - player timed out",
                        extra={
                            "username": username,
                            "player_id": player.id,
                            "timeout_until": str(player.timeout_until)
                        }
                    )
                    raise ValueError(f"Player is timed out until {player.timeout_until}")

            logger.info(
                "User authentication successful",
                extra={"username": username, "player_id": player.id}
            )

            return player

        except (PermissionError, ValueError):
            # Re-raise permission and timeout errors 
            raise
        except Exception as e:
            logger.error(
                "Error during user authentication",
                extra={"username": username, "error": str(e)}
            )
            return None

    @staticmethod
    async def validate_jwt_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a JWT token and extract user information.

        Args:
            token: JWT token to validate

        Returns:
            Dict with user data or None if invalid
        """
        try:
            # Verify the JWT token
            token_data = verify_token(token)
            if not token_data:
                logger.debug("JWT token validation failed - invalid token")
                return None

            # Extract username from token
            username = token_data.username
            if not username:
                logger.debug("JWT token validation failed - missing username")
                return None

            logger.debug(
                "JWT token validated successfully",
                extra={"username": username}
            )

            return {
                "username": username,
                "token_data": token_data
            }

        except Exception as e:
            logger.warning(
                "JWT token validation failed with exception",
                extra={"error": str(e)}
            )
            return None

    @staticmethod
    async def authenticate_websocket_connection(
        token: str
    ) -> Optional[Player]:
        """
        Authenticate a WebSocket connection and return player data.

        Args:
            token: JWT authentication token

        Returns:
            Player instance if authenticated, None otherwise
        """
        try:
            # Validate JWT token
            token_validation = await AuthenticationService.validate_jwt_token(token)
            if not token_validation:
                return None

            username = token_validation["username"]

            # Use PlayerService to get player data
            player = await PlayerService.get_player_by_username(username)
            if not player:
                logger.warning(
                    "WebSocket authentication failed - player not found",
                    extra={"username": username}
                )
                return None

            # Check if player is banned
            if player.is_banned:
                logger.warning(
                    "WebSocket authentication failed - player banned",
                    extra={"username": username, "player_id": player.id}
                )
                return None

            # Check if player is timed out (timeout_until is a datetime)
            if player.timeout_until and player.timeout_until > datetime.now(timezone.utc):
                logger.warning(
                    "WebSocket authentication failed - player timed out",
                    extra={"username": username, "player_id": player.id}
                )
                return None

            logger.info(
                "WebSocket authentication successful",
                extra={"username": username, "player_id": player.id}
            )

            return player

        except Exception as e:
            logger.error(
                "Error during WebSocket authentication",
                extra={"error": str(e)}
            )
            return None

    @staticmethod
    async def load_player_for_session(
        player: Player
    ) -> Dict[str, Any]:
        """
        Load complete player data for WebSocket session initialization.

        Args:
            player: Authenticated player

        Returns:
            Dict with complete player session data
        """
        try:
            # Register player as online and load state
            await PlayerService.login_player(player)

            # Get initial position data
            position_data = await PlayerService.get_player_position(player.id)
            
            # Get basic stats (HP, etc.)
            state_manager = get_game_state_manager()
            hp_data = await state_manager.get_player_hp(player.id)

            session_data = {
                "player_id": player.id,
                "username": player.username,
                "position": position_data or {
                    "x": player.x_coord,
                    "y": player.y_coord,
                    "map_id": player.map_id
                },
                "hp": hp_data or {
                    "current_hp": 100,
                    "max_hp": 100
                },
                "authenticated": True
            }

            logger.info(
                "Player session loaded successfully",
                extra={
                    "player_id": player.id,
                    "username": player.username
                }
            )

            return session_data

        except Exception as e:
            logger.error(
                "Error loading player session data",
                extra={
                    "player_id": player.id,
                    "username": player.username,
                    "error": str(e)
                }
            )
            # Return minimal session data on error
            return {
                "player_id": player.id,
                "username": player.username,
                "position": {
                    "x": player.x_coord,
                    "y": player.y_coord,
                    "map_id": player.map_id
                },
                "hp": {
                    "current_hp": 100,
                    "max_hp": 100
                },
                "authenticated": True
            }

    @staticmethod
    def create_authentication_error_response(reason: str) -> Dict[str, Any]:
        """
        Create standardized authentication error response.

        Args:
            reason: Reason for authentication failure

        Returns:
            Dict with error response data
        """
        return {
            "type": "authentication_error",
            "payload": {
                "error": reason,
                "authenticated": False
            }
        }

    @staticmethod
    def validate_websocket_message_auth(
        session_data: Optional[Dict[str, Any]]
    ) -> bool:
        """
        Validate that a WebSocket session is properly authenticated.

        Args:
            session_data: Current session data

        Returns:
            True if session is authenticated
        """
        if not session_data:
            return False

        return session_data.get("authenticated", False) and session_data.get("player_id") is not None

    @staticmethod
    async def handle_authentication_failure(reason: str) -> Dict[str, Any]:
        """
        Handle authentication failure and return appropriate response.

        Args:
            reason: Reason for failure

        Returns:
            Dict with failure response
        """
        logger.info(
            "WebSocket authentication failed",
            extra={"reason": reason}
        )

        return AuthenticationService.create_authentication_error_response(reason)