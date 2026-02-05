"""
WebSocket connection management.

Handles connection lifecycle, authentication, and message handling.
"""

import asyncio
from enum import Enum, auto
from typing import Optional, Dict, Callable, Any, Coroutine
import logging

import msgpack
import websockets
from websockets.exceptions import ConnectionClosed

from ..config import get_config
from ..core.event_bus import get_event_bus, EventType
from ..logging_config import get_logger

# Protocol types from common module
import sys
from pathlib import Path
common_path = Path(__file__).parent.parent.parent.parent / "common" / "src"
if str(common_path) not in sys.path:
    sys.path.insert(0, str(common_path))

from protocol import MessageType, WSMessage

logger = get_logger(__name__)


class ConnectionState(Enum):
    """WebSocket connection states."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    AUTHENTICATING = auto()
    AUTHENTICATED = auto()
    ERROR = auto()
    RECONNECTING = auto()


class ConnectionManager:
    """Manages WebSocket connection and message handling."""
    
    def __init__(self):
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._state = ConnectionState.DISCONNECTED
        self._jwt_token: Optional[str] = None
        self._message_handlers: Dict[MessageType, Callable] = {}
        self._receive_task: Optional[asyncio.Task] = None
        self._event_bus = get_event_bus()
        self._config = get_config()
        self._connection_attempts = 0
        self._max_reconnect_attempts = 5
        self._reconnect_delay = 1.0
    
    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """Check if websocket is connected."""
        return self._websocket is not None and self._state in {
            ConnectionState.CONNECTED,
            ConnectionState.AUTHENTICATING,
            ConnectionState.AUTHENTICATED
        }
    
    @property
    def is_authenticated(self) -> bool:
        """Check if authenticated."""
        return self._state == ConnectionState.AUTHENTICATED
    
    async def connect(self, jwt_token: str) -> bool:
        """
        Connect to the WebSocket server and authenticate.
        
        Args:
            jwt_token: JWT token for authentication
            
        Returns:
            True if connection and authentication successful
        """
        if self.is_connected:
            logger.warning("Already connected, disconnecting first")
            await self.disconnect()
        
        self._jwt_token = jwt_token
        self._state = ConnectionState.CONNECTING
        self._event_bus.emit(EventType.CONNECTING)
        
        try:
            # Connect to WebSocket
            uri = self._config.server.websocket_url
            extra_headers = {"Authorization": f"Bearer {jwt_token}"}
            
            logger.info(f"Connecting to {uri}")
            self._websocket = await websockets.connect(uri, extra_headers=extra_headers)
            
            self._state = ConnectionState.CONNECTED
            self._connection_attempts = 0
            self._event_bus.emit(EventType.CONNECTED)
            
            # Start message receiver
            self._receive_task = asyncio.create_task(self._receive_messages())
            
            # Authenticate
            await self._authenticate()
            
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._state = ConnectionState.ERROR
            self._event_bus.emit(EventType.CONNECTION_ERROR, {"error": str(e)})
            return False
    
    async def _authenticate(self) -> bool:
        """Send authentication message."""
        if not self._websocket or not self._jwt_token:
            return False
        
        self._state = ConnectionState.AUTHENTICATING
        self._event_bus.emit(EventType.AUTHENTICATING)
        
        try:
            auth_msg = {
                "type": MessageType.CMD_AUTHENTICATE.value,
                "payload": {"token": self._jwt_token}
            }
            
            await self._websocket.send(msgpack.packb(auth_msg))
            
            # Wait for authentication response
            response_data = await self._websocket.recv()
            response = msgpack.unpackb(response_data, raw=False)
            
            msg_type = response.get("type")
            
            if msg_type == MessageType.RESP_SUCCESS.value:
                self._state = ConnectionState.AUTHENTICATED
                self._event_bus.emit(EventType.AUTHENTICATED)
                logger.info("Authentication successful")
                return True
            else:
                self._state = ConnectionState.ERROR
                error = response.get("payload", {}).get("error", "Unknown error")
                logger.error(f"Authentication failed: {error}")
                self._event_bus.emit(EventType.AUTH_FAILED, {"error": error})
                return False
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            self._state = ConnectionState.ERROR
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from the server."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as e:
                logger.warning(f"Error closing websocket: {e}")
            self._websocket = None
        
        self._state = ConnectionState.DISCONNECTED
        self._jwt_token = None
        self._event_bus.emit(EventType.DISCONNECTED)
        logger.info("Disconnected from server")
    
    async def send(self, message: Dict[str, Any]) -> bool:
        """
        Send a message to the server.
        
        Args:
            message: Message dictionary with type and payload
            
        Returns:
            True if message sent successfully
        """
        if not self.is_connected or not self._websocket:
            logger.warning("Cannot send message: not connected")
            return False
        
        try:
            packed = msgpack.packb(message)
            await self._websocket.send(packed)
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    async def send_command(self, msg_type: MessageType, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> bool:
        """
        Send a command message.
        
        Args:
            msg_type: The message type
            payload: Command payload
            correlation_id: Optional correlation ID for request/response tracking
            
        Returns:
            True if message sent successfully
        """
        message = {
            "type": msg_type.value,
            "payload": payload
        }
        if correlation_id:
            message["id"] = correlation_id
        
        return await self.send(message)
    
    def register_handler(self, msg_type: MessageType, handler: Callable[[Dict], None]) -> None:
        """Register a handler for a message type."""
        self._message_handlers[msg_type] = handler
        logger.debug(f"Registered handler for {msg_type.value}")
    
    def unregister_handler(self, msg_type: MessageType) -> None:
        """Unregister a handler for a message type."""
        if msg_type in self._message_handlers:
            del self._message_handlers[msg_type]
    
    async def _receive_messages(self) -> None:
        """Background task to receive and route messages."""
        logger.info("Message receiver started")
        
        try:
            while self._websocket and self.is_connected:
                try:
                    message_data = await self._websocket.recv()
                    message = msgpack.unpackb(message_data, raw=False)
                    
                    await self._handle_message(message)
                    
                except ConnectionClosed:
                    logger.warning("Connection closed by server")
                    break
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    
        except asyncio.CancelledError:
            logger.info("Message receiver cancelled")
        except Exception as e:
            logger.error(f"Message receiver error: {e}")
        finally:
            if self._state != ConnectionState.DISCONNECTED:
                self._state = ConnectionState.DISCONNECTED
                self._event_bus.emit(EventType.DISCONNECTED)
    
    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Route a received message to its handler."""
        msg_type_str = message.get("type")
        
        if not msg_type_str:
            logger.warning("Received message without type")
            return
        
        try:
            msg_type = MessageType(msg_type_str)
        except ValueError:
            logger.warning(f"Unknown message type: {msg_type_str}")
            return
        
        handler = self._message_handlers.get(msg_type)
        
        if handler:
            try:
                payload = message.get("payload", {})
                correlation_id = message.get("id")
                
                if asyncio.iscoroutinefunction(handler):
                    await handler(payload, correlation_id)
                else:
                    handler(payload, correlation_id)
            except Exception as e:
                logger.error(f"Error in message handler for {msg_type.value}: {e}")
        else:
            # No handler registered, might be normal for events
            logger.debug(f"No handler for message type: {msg_type.value}")


# Singleton instance
_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """Get the singleton connection manager."""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager


def reset_connection_manager() -> None:
    """Reset the connection manager."""
    global _connection_manager
    _connection_manager = None
