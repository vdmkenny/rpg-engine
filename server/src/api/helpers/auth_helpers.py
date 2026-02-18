"""
Authentication helper functions for WebSocket connections.

Handles token validation and player authentication.
"""

from datetime import datetime, timezone
from typing import Tuple
import asyncio

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

# Timeout for authentication message (seconds)
AUTH_MESSAGE_TIMEOUT = 10.0


async def receive_auth_message(websocket) -> WSMessage:
    """
    Receive and validate authentication message from client.
    
    Args:
        websocket: The WebSocket connection
        
    Returns:
        Validated WSMessage with authentication payload
        
    Raises:
        WebSocketDisconnect: If message is invalid, not an auth message, or timeout occurs
    """
    try:
        # Use timeout to prevent hanging connections
        auth_bytes = await asyncio.wait_for(
            websocket.receive_bytes(),
            timeout=AUTH_MESSAGE_TIMEOUT
        )
        auth_data = msgpack.unpackb(auth_bytes, raw=False)
        auth_message = WSMessage(**auth_data)
        
        if auth_message.type != MessageType.CMD_AUTHENTICATE:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Authentication message expected"
            )
        
        return auth_message
        
    except asyncio.TimeoutError:
        logger.warning("Authentication message timeout")
        raise WebSocketDisconnect(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication failed"
        )
    except (msgpack.exceptions.UnpackException, ValueError) as e:
        logger.error("Invalid authentication message format", extra={"error": str(e)})
        raise WebSocketDisconnect(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication failed"
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
            logger.warning("Token validation failed - no player data")
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Authentication failed"
            )
        
        username = player_data.get("username")
        
        if not username:
            logger.warning("Token validation failed - username missing")
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Authentication failed"
            )
        
        # Get player from database to validate existence and get player_id
        player_service = PlayerService()
        player = await player_service.get_player_by_username(username)
        
        if not player:
            logger.warning("Player lookup failed during auth", extra={"username": username})
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Authentication failed"
            )
        
        if player.is_banned:
            logger.info("Banned player attempted login", extra={"username": username})
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Account suspended"
            )
        
        timeout_until = player.timeout_until
        if timeout_until:
            if timeout_until.tzinfo is None:
                timeout_until = timeout_until.replace(tzinfo=timezone.utc)
            if timeout_until > datetime.now(timezone.utc):
                logger.info(
                    "Timed-out player attempted login",
                    extra={"username": username, "timeout_until": timeout_until.isoformat()}
                )
                raise WebSocketDisconnect(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="Account temporarily restricted"
                )
        
        logger.info("Player authenticated via WebSocket", extra={"username": username, "player_id": player.id})
        return username, player.id
        
    except ValidationError as e:
        logger.error("Authentication validation error", extra={"error": str(e), "errors": e.errors()})
        raise WebSocketDisconnect(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication failed"
        )
    except JWTError as e:
        logger.error("JWT authentication error", extra={"error": str(e)})
        raise WebSocketDisconnect(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication failed"
        )
