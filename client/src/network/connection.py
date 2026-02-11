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
        self._auth_complete = asyncio.Event()
        self._buffered_messages: list = []  # Messages received during auth
        self._intentional_disconnect = False  # Flag to prevent reconnect after intentional disconnect (M9 fix)
    
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
        self._intentional_disconnect = False  # Reset flag for new connection (M9 fix)
        self._event_bus.emit(EventType.CONNECTING)
        
        try:
            # Connect to WebSocket (no headers - auth is via first message)
            uri = self._config.server.websocket_url
            
            logger.info(f"Connecting to {uri}")
            self._websocket = await websockets.connect(uri)
            
            self._state = ConnectionState.CONNECTED
            self._connection_attempts = 0
            self._event_bus.emit(EventType.CONNECTED)
            
            # Clear buffered messages and auth event
            self._buffered_messages.clear()
            self._auth_complete.clear()
            
            # Start message receiver BEFORE sending auth
            # This ensures no messages are missed or delayed
            self._receive_task = asyncio.create_task(self._receive_messages())
            
            # Send authentication message
            auth_success = await self._authenticate()
            
            if not auth_success:
                logger.error("Authentication failed")
                await self.disconnect()
                return False
            
            # Process any buffered messages that arrived during auth
            await self._process_buffered_messages()
            
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._state = ConnectionState.ERROR
            self._event_bus.emit(EventType.CONNECTION_ERROR, {"error": str(e)})
            return False
    
    async def _authenticate(self) -> bool:
        """
        Send authentication message and wait for auth completion.
        
        The receiver task will process auth responses and set _auth_complete when done.
        """
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
            
            # Wait for auth completion signal from receiver (with timeout)
            try:
                await asyncio.wait_for(self._auth_complete.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.error("Authentication timeout")
                self._state = ConnectionState.ERROR
                return False
            
            # Check if auth was successful
            if self._state == ConnectionState.AUTHENTICATED:
                logger.info("Authentication successful")
                return True
            else:
                logger.error("Authentication failed")
                self._event_bus.emit(EventType.AUTH_FAILED, {"error": "Authentication rejected by server"})
                return False
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            self._state = ConnectionState.ERROR
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from the server."""
        self._intentional_disconnect = True  # Mark as intentional to prevent reconnect (M9 fix)
        
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
    
    async def reconnect(self) -> bool:
        """
        Attempt to reconnect with exponential backoff.
        
        Returns:
            True if reconnection successful, False if max attempts reached
        """
        if not self._jwt_token:
            logger.error("Cannot reconnect: no JWT token stored")
            return False
        
        for attempt in range(1, self._max_reconnect_attempts + 1):
            self._state = ConnectionState.RECONNECTING
            self._event_bus.emit(EventType.RECONNECTING)
            
            # Exponential backoff: 1s, 2s, 4s, 8s, etc.
            delay = self._reconnect_delay * (2 ** (attempt - 1))
            logger.info(f"Reconnection attempt {attempt}/{self._max_reconnect_attempts} in {delay:.1f}s")
            
            await asyncio.sleep(delay)
            
            # Try to reconnect
            success = await self.connect(self._jwt_token)
            if success:
                logger.info(f"Reconnected successfully on attempt {attempt}")
                self._connection_attempts = 0
                return True
            else:
                logger.warning(f"Reconnection attempt {attempt} failed")
        
        logger.error(f"Failed to reconnect after {self._max_reconnect_attempts} attempts")
        self._state = ConnectionState.ERROR
        self._event_bus.emit(EventType.CONNECTION_ERROR, {"error": "Max reconnection attempts reached"})
        return False
    
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
                
                # Attempt automatic reconnection if we were authenticated and not intentional disconnect (M9 fix)
                if not self._intentional_disconnect and self._jwt_token and self._connection_attempts < self._max_reconnect_attempts:
                    logger.info("Attempting automatic reconnection...")
                    self._connection_attempts += 1
                    success = await self.reconnect()
                    if not success:
                        logger.error("Automatic reconnection failed after all attempts")
    
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
        
        # During authentication, buffer all messages except auth responses
        if self._state == ConnectionState.AUTHENTICATING:
            if msg_type in (MessageType.RESP_SUCCESS, MessageType.RESP_ERROR, MessageType.EVENT_WELCOME):
                # Auth response - handle immediately
                await self._handle_auth_response(msg_type, message)
                return
            else:
                # Buffer other messages for processing after auth
                logger.debug(f"Buffering message {msg_type.value} received during auth")
                self._buffered_messages.append(message)
                return
        
        # After authentication, process all messages normally
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
    
    async def _handle_auth_response(self, msg_type: MessageType, message: Dict[str, Any]) -> None:
        """Handle authentication response message."""
        if msg_type in (MessageType.RESP_SUCCESS, MessageType.EVENT_WELCOME):
            self._state = ConnectionState.AUTHENTICATED
            self._event_bus.emit(EventType.AUTHENTICATED)
            
            # If we got welcome event, process it immediately via handler
            if msg_type == MessageType.EVENT_WELCOME:
                handler = self._message_handlers.get(MessageType.EVENT_WELCOME)
                if handler:
                    payload = message.get("payload", {})
                    correlation_id = message.get("id")
                    if asyncio.iscoroutinefunction(handler):
                        await handler(payload, correlation_id)
                    else:
                        handler(payload, correlation_id)
            
            # Signal auth completion
            self._auth_complete.set()
            
        elif msg_type == MessageType.RESP_ERROR:
            error = message.get("payload", {}).get("error", "Unknown error")
            logger.error(f"Authentication failed: {error}")
            self._state = ConnectionState.ERROR
            self._event_bus.emit(EventType.AUTH_FAILED, {"error": error})
            # Signal auth completion (as failure)
            self._auth_complete.set()
    
    async def _process_buffered_messages(self) -> None:
        """Process messages that were buffered during authentication."""
        while self._buffered_messages:
            message = self._buffered_messages.pop(0)
            await self._handle_message(message)


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
