"""
Authentication helper functions for WebSocket connections.

Handles token validation and player authentication.
"""

from datetime import datetime, timezone
from typing import Tuple

import msgpack
from fastapi import WebSocketDisconnect, status
from jose import JWTError
from pydantic import ValidationError

from server.src.core.logging_config import get_logger
from server.src.services.authentication_service import AuthenticationService
from server.src.services.player_service import PlayerService

from common.src.protocol import (
    WSMessage,
    MessageType,
    AuthenticatePayload,
)

logger = get_logger(__name__)


async def receive_auth_message(websocket) -> WSMessage:
    """
    Receive and validate authentication message from client.
    
    Args:
        websocket: The WebSocket connection
        
    Returns:
        Validated WSMessage with authentication payload
        
    Raises:
        WebSocketDisconnect: If message is invalid or not an auth message
    """
    try:
        auth_bytes = await websocket.receive_bytes()
        auth_data = msgpack.unpackb(auth_bytes, raw=False)
        auth_message = WSMessage(**auth_data)
        
        if auth_message.type != MessageType.CMD_AUTHENTICATE:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Authentication message expected"
            )
        
        return auth_message
        
    except (msgpack.exceptions.UnpackException, ValueError) as e:
        logger.error("Invalid authentication message", extra={"error": str(e)})
        raise WebSocketDisconnect(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=f"Invalid authentication message: {str(e)}"
        )


async def authenticate_player(auth_message: WSMessage) -> Tuple[str, int]:
    """
    Authenticate player and return username and player_id.
    
    Args:
        auth_message: The authentication message
        
    Returns:
        Tuple of (username, player_id)
        
    Raises:
        WebSocketDisconnect: If authentication fails
    """
    try:
        auth_payload = AuthenticatePayload(**auth_message.payload)
        
        auth_service = AuthenticationService()
        player_data = await auth_service.validate_jwt_token(auth_payload.token)
        
        if not player_data:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid token"
            )
        
        username = player_data.get("username")
        
        if not username:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid token: username missing"
            )
        
        # Get player from database to validate existence and get player_id
        player_service = PlayerService()
        player = await player_service.get_player_by_username(username)
        
        if not player:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Player not found"
            )
        
        if player.is_banned:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Account is banned"
            )
        
        timeout_until = player.timeout_until
        if timeout_until:
            if timeout_until.tzinfo is None:
                timeout_until = timeout_until.replace(tzinfo=timezone.utc)
            if timeout_until > datetime.now(timezone.utc):
                raise WebSocketDisconnect(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason=f"Account is timed out until {timeout_until.isoformat()}"
                )
        
        logger.info("Player authenticated via WebSocket", extra={"username": username, "player_id": player.id})
        return username, player.id
        
    except ValidationError as e:
        logger.error("Authentication validation error", extra={"error": str(e), "errors": e.errors()})
        raise WebSocketDisconnect(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid authentication payload"
        )
    except JWTError as e:
        logger.error("JWT authentication error", extra={"error": str(e)})
        raise WebSocketDisconnect(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid authentication token"
        )
