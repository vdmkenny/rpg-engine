"""
Protocol handler for WebSocket communication.
Handles correlation IDs, message routing, and Protocol 2.0 compliance.
"""

import uuid
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
import time

import sys
import os
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(workspace_root)

from common.src.protocol import (
    MessageType, WSMessage, Direction, ChatChannel,
    COMMAND_TYPES, QUERY_TYPES, EVENT_TYPES, RESPONSE_TYPES
)


@dataclass
class PendingRequest:
    """Tracks a pending request awaiting response."""
    correlation_id: str
    message_type: MessageType
    timestamp: float
    callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    future: Optional[asyncio.Future] = None


class ProtocolHandler:
    """
    Manages Protocol 2.0 compliance for the client.
    
    Handles:
    - Correlation ID generation and tracking
    - Request/response matching
    - Event routing
    - Timeout handling
    """
    
    def __init__(self):
        # Pending requests waiting for responses
        self._pending_requests: Dict[str, PendingRequest] = {}
        
        # Event handlers (type -> list of callbacks)
        self._event_handlers: Dict[MessageType, list] = {}
        
        # Response handlers for untracked responses
        self._response_handlers: Dict[MessageType, list] = {}
        
        # Request timeout in seconds
        self.request_timeout = 10.0
    
    def generate_correlation_id(self) -> str:
        """Generate a unique correlation ID."""
        return str(uuid.uuid4())
    
    def create_command(
        self,
        command_type: MessageType,
        payload: Dict[str, Any],
        callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ) -> WSMessage:
        """
        Create a command message with correlation ID.
        
        Args:
            command_type: The MessageType for this command
            payload: Command payload data
            callback: Optional async callback for response
            
        Returns:
            WSMessage ready to send
        """
        correlation_id = self.generate_correlation_id()
        
        message = WSMessage(
            id=correlation_id,
            type=command_type,
            payload=payload
        )
        
        # Track the pending request
        self._pending_requests[correlation_id] = PendingRequest(
            correlation_id=correlation_id,
            message_type=command_type,
            timestamp=time.time(),
            callback=callback
        )
        
        return message
    
    def create_query(
        self,
        query_type: MessageType,
        payload: Dict[str, Any],
        callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ) -> WSMessage:
        """
        Create a query message with correlation ID.
        
        Args:
            query_type: The MessageType for this query
            payload: Query payload data
            callback: Optional async callback for response
            
        Returns:
            WSMessage ready to send
        """
        correlation_id = self.generate_correlation_id()
        
        message = WSMessage(
            id=correlation_id,
            type=query_type,
            payload=payload
        )
        
        # Track the pending request
        self._pending_requests[correlation_id] = PendingRequest(
            correlation_id=correlation_id,
            message_type=query_type,
            timestamp=time.time(),
            callback=callback
        )
        
        return message
    
    def register_event_handler(
        self,
        event_type: MessageType,
        handler: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Register a handler for an event type."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    def unregister_event_handler(
        self,
        event_type: MessageType,
        handler: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Unregister a handler for an event type."""
        if event_type in self._event_handlers:
            self._event_handlers[event_type].remove(handler)
    
    async def handle_message(self, message: Dict[str, Any]) -> None:
        """
        Route an incoming message to appropriate handlers.
        
        Args:
            message: Parsed message dictionary
        """
        msg_type_str = message.get("type", "")
        payload = message.get("payload", {})
        correlation_id = message.get("id")
        
        # Parse message type
        try:
            msg_type = MessageType(msg_type_str)
        except ValueError:
            print(f"Unknown message type: {msg_type_str}")
            return
        
        # Handle responses (match to pending requests)
        if msg_type in RESPONSE_TYPES:
            if correlation_id and correlation_id in self._pending_requests:
                pending = self._pending_requests.pop(correlation_id)
                if pending.callback:
                    await pending.callback(payload)
                if pending.future and not pending.future.done():
                    pending.future.set_result(payload)
            
            # Also invoke any event handlers registered for this response type
            # This allows the client to handle responses generically (e.g., RESP_DATA)
            handlers = self._event_handlers.get(msg_type, [])
            for handler in handlers:
                try:
                    await handler(payload)
                except Exception as e:
                    print(f"Error in response handler for {msg_type}: {e}")
            return
        
        # Handle events
        if msg_type in EVENT_TYPES or msg_type in self._event_handlers:
            handlers = self._event_handlers.get(msg_type, [])
            for handler in handlers:
                try:
                    await handler(payload)
                except Exception as e:
                    print(f"Error in event handler for {msg_type}: {e}")
    
    def cleanup_expired_requests(self) -> None:
        """Remove requests that have timed out."""
        current_time = time.time()
        expired = [
            cid for cid, req in self._pending_requests.items()
            if current_time - req.timestamp > self.request_timeout
        ]
        for cid in expired:
            pending = self._pending_requests.pop(cid)
            if pending.future and not pending.future.done():
                pending.future.set_exception(TimeoutError("Request timed out"))
    
    def get_pending_count(self) -> int:
        """Get count of pending requests."""
        return len(self._pending_requests)
