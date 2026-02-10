"""
WebSocket Test Framework

Modern test utilities for the WebSocket protocol with proper
correlation ID handling and message pattern support.
"""

import asyncio
import os
import uuid
import msgpack
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
import pytest
import time

from common.src.protocol import (
    WSMessage, MessageType, ErrorCodes,
    COMMAND_TYPES, QUERY_TYPES, EVENT_TYPES,
    get_expected_response_type
)
from common.src.websocket_utils import BroadcastTarget


# =============================================================================
# Test Constants
# =============================================================================

# Skip marker for integration tests that require RUN_INTEGRATION_TESTS=1
SKIP_WS_INTEGRATION = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "").lower() not in ("1", "true", "yes"),
    reason="Integration tests require RUN_INTEGRATION_TESTS=1"
)

# Common sleep durations used in tests
CHAT_RATE_LIMIT_WAIT = 1.1  # Wait for chat rate limit to reset (1.0s limit)
MOVEMENT_COOLDOWN_WAIT = 0.6  # Wait for movement cooldown (0.5s cooldown)
ENTITY_SPAWN_WAIT = 0.2  # Wait for entity to appear in game state
GAME_TICK_WAIT = 0.05  # One game tick at 20 TPS


# =============================================================================
# Test Exceptions
# =============================================================================

class WebSocketTestError(Exception):
    """Base exception for WebSocket test failures"""
    pass


class ResponseTimeoutError(WebSocketTestError):
    """Raised when a response times out"""
    pass


class UnexpectedResponseError(WebSocketTestError):
    """Raised when response doesn't match expected format"""
    pass


class ErrorResponseError(WebSocketTestError):
    """Raised when server returns an error response"""
    def __init__(self, error_payload: Dict[str, Any]):
        self.error_code = error_payload.get("error_code", "UNKNOWN")
        self.error_message = error_payload.get("error", "Unknown error")
        self.error_details = error_payload.get("details", {})
        self.error_category = error_payload.get("category", "system")
        super().__init__(f"{self.error_code}: {self.error_message}")


# =============================================================================
# WebSocket Test Client
# =============================================================================

@dataclass
class PendingResponse:
    """Track pending responses in tests"""
    correlation_id: str
    expected_type: MessageType
    future: asyncio.Future
    timeout_task: asyncio.Task


@dataclass 
class EventCapture:
    """Capture events for testing"""
    event_type: MessageType
    future: asyncio.Future
    timeout_task: asyncio.Task
    filter_func: Optional[Callable[[Dict[str, Any]], bool]] = None


class WebSocketTestClient:
    """
    Async WebSocket test client for httpx-ws
    
    Supports:
    - Command/query correlation with automatic response handling
    - Event capture and filtering
    - Fluent test API
    - Proper timeout handling
    - Error response parsing
    """
    
    def __init__(self, websocket, default_timeout: float = 5.0):
        self.websocket = websocket
        self.default_timeout = default_timeout
        self.pending_responses: Dict[str, PendingResponse] = {}
        self.event_captures: List[EventCapture] = []
        self.message_log: List[WSMessage] = []
        self.running = True
        
        # Start background message processing task
        self._process_task = asyncio.create_task(self._process_messages())
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def disconnect(self):
        """Disconnect the WebSocket connection gracefully.
        
        Closes the websocket connection, stops the background processing task,
        clears pending responses, and sets running to False.
        """
        self.running = False
        
        # Close the websocket connection gracefully
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
        
        # Cancel the background processing task
        if self._process_task and not self._process_task.done():
            self._process_task.cancel()
            try:
                await asyncio.wait_for(self._process_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
                
        # Clear pending responses
        for response in list(self.pending_responses.values()):
            if response.timeout_task and not response.timeout_task.done():
                response.timeout_task.cancel()
            if not response.future.done():
                response.future.set_exception(asyncio.CancelledError())
        self.pending_responses.clear()
                
        for capture in list(self.event_captures):
            if capture.timeout_task and not capture.timeout_task.done():
                capture.timeout_task.cancel()
            if not capture.future.done():
                capture.future.set_exception(asyncio.CancelledError())
        self.event_captures.clear()
        
        # Clear message log
        self.message_log.clear()
        
    async def close(self):
        """Clean up the test client with proper cancellation.
        
        This is an alias for disconnect() for compatibility with async context managers.
        """
        await self.disconnect()
                
    async def _process_messages(self):
        """Process incoming WebSocket messages with timeout protection"""
        try:
            while self.running:
                try:
                    # Add timeout to receive to prevent hanging
                    raw_message = await asyncio.wait_for(
                        self.websocket.receive_bytes(),
                        timeout=30.0  # 30 second timeout for receives
                    )
                    
                    message_data = msgpack.unpackb(raw_message, raw=False)
                    message = WSMessage(**message_data)
                    
                    # Log message for debugging
                    self.message_log.append(message)
                    
                    # Handle correlation-based responses
                    if message.id and message.id in self.pending_responses:
                        pending = self.pending_responses.pop(message.id)
                        pending.timeout_task.cancel()
                        
                        if not pending.future.done():
                            pending.future.set_result(message)
                            
                    # Handle event captures
                    for capture in self.event_captures[:]:  # Copy to avoid modification during iteration
                        if capture.event_type == message.type:
                            # Apply filter if specified
                            if capture.filter_func and not capture.filter_func(message.payload):
                                continue
                                
                            # Remove from captures and resolve future
                            self.event_captures.remove(capture)
                            capture.timeout_task.cancel()
                            
                            if not capture.future.done():
                                capture.future.set_result(message)
                                
                except asyncio.TimeoutError:
                    # Receive timeout - this is expected when no messages are coming
                    # Continue the loop to check if we should still be running
                    continue
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    # Log error but don't break - tests might be checking error conditions
                    print(f"Error processing WebSocket message: {e}")
                    # Only break on severe issues
                    if not self.running:
                        break
                    
        except asyncio.CancelledError:
            pass
            
    async def _send_message(self, message_type: MessageType, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Send a WebSocket message"""
        message = WSMessage(
            id=correlation_id,
            type=message_type,
            payload=payload,
            version="2.0"
        )
        
        raw_message = msgpack.packb(message.model_dump(), use_bin_type=True)
        
        # httpx-ws async send
        await self.websocket.send_bytes(raw_message)
        
    async def _wait_for_response(self, correlation_id: str, expected_type: MessageType, timeout: float) -> WSMessage:
        """Wait for a correlated response using background message processor"""
        future = asyncio.Future()
        timeout_task = asyncio.create_task(self._handle_response_timeout(correlation_id, timeout))
        
        pending = PendingResponse(
            correlation_id=correlation_id,
            expected_type=expected_type,
            future=future,
            timeout_task=timeout_task
        )
        
        self.pending_responses[correlation_id] = pending
        
        try:
            response = await future
            
            # Validate response type
            if response.type == MessageType.RESP_ERROR:
                raise ErrorResponseError(response.payload)
            elif response.type != expected_type:
                raise UnexpectedResponseError(
                    f"Expected {expected_type}, got {response.type}"
                )
                
            return response
            
        except asyncio.TimeoutError:
            raise ResponseTimeoutError(f"Response timeout for {expected_type}")
        finally:
            self.pending_responses.pop(correlation_id, None)
            
    async def _handle_response_timeout(self, correlation_id: str, timeout: float):
        """Handle response timeout"""
        await asyncio.sleep(timeout)
        pending = self.pending_responses.get(correlation_id)
        if pending and not pending.future.done():
            pending.future.set_exception(asyncio.TimeoutError())
            
    # =========================================================================
    # Command Operations (State-Changing)
    # =========================================================================
    
    async def send_command(
        self, 
        command_type: MessageType, 
        payload: Dict[str, Any], 
        timeout: Optional[float] = None
    ) -> WSMessage:
        """
        Send a command and wait for success response.
        Returns the full WSMessage with RESP_SUCCESS or RESP_ERROR.
        """
        if command_type not in COMMAND_TYPES:
            raise ValueError(f"{command_type} is not a command type")
            
        correlation_id = str(uuid.uuid4())
        timeout = timeout or self.default_timeout
        
        await self._send_message(command_type, payload, correlation_id)
        response = await self._wait_for_response(correlation_id, MessageType.RESP_SUCCESS, timeout)
        
        return response
        
    # Command convenience methods
    async def authenticate(self, token: str) -> WSMessage:
        """Authenticate with JWT token"""
        return await self.send_command(MessageType.CMD_AUTHENTICATE, {"token": token})
        
    async def move_player(self, direction: str) -> WSMessage:
        """Move player in specified direction"""
        return await self.send_command(MessageType.CMD_MOVE, {"direction": direction})
        
    async def send_chat(self, message: str, channel: str = "local") -> WSMessage:
        """Send chat message"""
        return await self.send_command(MessageType.CMD_CHAT_SEND, {"message": message, "channel": channel})
        
    async def move_inventory_item(self, from_slot: int, to_slot: int) -> WSMessage:
        """Move item between inventory slots"""
        return await self.send_command(MessageType.CMD_INVENTORY_MOVE, {"from_slot": from_slot, "to_slot": to_slot})
        
    async def sort_inventory(self, sort_by: str = "category") -> WSMessage:
        """Sort inventory by criteria"""
        return await self.send_command(MessageType.CMD_INVENTORY_SORT, {"sort_by": sort_by})
        
    async def drop_item(self, inventory_slot: int, quantity: int = 1) -> WSMessage:
        """Drop item from inventory"""
        return await self.send_command(MessageType.CMD_ITEM_DROP, {"inventory_slot": inventory_slot, "quantity": quantity})
        
    async def pickup_item(self, ground_item_id: str) -> WSMessage:
        """Pick up ground item"""
        return await self.send_command(MessageType.CMD_ITEM_PICKUP, {"ground_item_id": ground_item_id})
        
    async def equip_item(self, inventory_slot: int) -> WSMessage:
        """Equip item from inventory"""
        return await self.send_command(MessageType.CMD_ITEM_EQUIP, {"inventory_slot": inventory_slot})
        
    async def unequip_item(self, equipment_slot: str) -> WSMessage:
        """Unequip item to inventory"""
        return await self.send_command(MessageType.CMD_ITEM_UNEQUIP, {"equipment_slot": equipment_slot})
        
    # =========================================================================
    # Query Operations (Data Retrieval)
    # =========================================================================
    
    async def send_query(
        self, 
        query_type: MessageType, 
        payload: Dict[str, Any], 
        timeout: Optional[float] = None
    ) -> WSMessage:
        """
        Send a query and wait for data response.
        Returns the full WSMessage with RESP_DATA or RESP_ERROR.
        """
        if query_type not in QUERY_TYPES:
            raise ValueError(f"{query_type} is not a query type")
            
        correlation_id = str(uuid.uuid4())
        timeout = timeout or self.default_timeout
        
        await self._send_message(query_type, payload, correlation_id)
        response = await self._wait_for_response(correlation_id, MessageType.RESP_DATA, timeout)
        
        return response
        
    # Query convenience methods
    async def get_inventory(self) -> WSMessage:
        """Get current inventory state"""
        return await self.send_query(MessageType.QUERY_INVENTORY, {})
        
    async def get_equipment(self) -> WSMessage:
        """Get current equipment state"""
        return await self.send_query(MessageType.QUERY_EQUIPMENT, {})
        
    async def get_stats(self) -> WSMessage:
        """Get aggregated equipment stats"""
        return await self.send_query(MessageType.QUERY_STATS, {})
        
    async def get_map_chunks(
        self, 
        map_id: str, 
        center_x: int, 
        center_y: int, 
        radius: int = 1
    ) -> WSMessage:
        """Get map chunk data"""
        return await self.send_query(
            MessageType.QUERY_MAP_CHUNKS,
            {
                "map_id": map_id,
                "center_x": center_x, 
                "center_y": center_y,
                "radius": radius
            }
        )
        
    # =========================================================================
    # Event Handling
    # =========================================================================
    
    async def expect_event(
        self, 
        event_type: MessageType, 
        timeout: Optional[float] = None,
        filter_func: Optional[Callable[[Dict[str, Any]], bool]] = None
    ) -> WSMessage:
        """
        Wait for a specific event type and return the full WSMessage.
        Optionally filter events with a function.
        """
        if event_type not in EVENT_TYPES:
            raise ValueError(f"{event_type} is not an event type")
            
        timeout = timeout or self.default_timeout
        future = asyncio.Future()
        timeout_task = asyncio.create_task(self._handle_event_timeout(future, timeout))
        
        capture = EventCapture(
            event_type=event_type,
            future=future,
            timeout_task=timeout_task,
            filter_func=filter_func
        )
        
        self.event_captures.append(capture)
        
        try:
            event = await future
            return event  # Return full WSMessage, not just payload
        except asyncio.TimeoutError:
            raise ResponseTimeoutError(f"Event timeout for {event_type}")
        finally:
            if capture in self.event_captures:
                self.event_captures.remove(capture)
                
    async def _handle_event_timeout(self, future: asyncio.Future, timeout: float):
        """Handle event timeout"""
        await asyncio.sleep(timeout)
        if not future.done():
            future.set_exception(asyncio.TimeoutError())
            
    # Event convenience methods
    async def expect_welcome(self) -> WSMessage:
        """Expect welcome event after authentication"""
        return await self.expect_event(MessageType.EVENT_WELCOME)
        
    async def expect_state_update(
        self,
        target: Optional[str] = None,
        system: Optional[str] = None
    ) -> WSMessage:
        """Expect state update event with optional filtering"""
        filter_func_to_use: Optional[Callable[[Dict[str, Any]], bool]] = None
        
        if target or system:
            def filter_func(payload: Dict[str, Any]) -> bool:
                if target and payload.get("target") != target:
                    return False
                if system and system not in payload.get("systems", {}):
                    return False
                return True
            filter_func_to_use = filter_func
            
        return await self.expect_event(MessageType.EVENT_STATE_UPDATE, filter_func=filter_func_to_use)
        
    async def expect_game_update(self, map_id: Optional[str] = None) -> WSMessage:
        """Expect game entity update"""
        filter_func_to_use: Optional[Callable[[Dict[str, Any]], bool]] = None
        
        if map_id:
            def filter_func(payload: Dict[str, Any]) -> bool:
                if map_id and payload.get("map_id") != map_id:
                    return False
                return True
            filter_func_to_use = filter_func
            
        return await self.expect_event(MessageType.EVENT_STATE_UPDATE, filter_func=filter_func_to_use)
        
    async def expect_chat_message(
        self, 
        sender: Optional[str] = None, 
        channel: Optional[str] = None
    ) -> WSMessage:
        """Expect chat message with optional filtering"""
        filter_func_to_use: Optional[Callable[[Dict[str, Any]], bool]] = None
        
        if sender or channel:
            def filter_func(payload: Dict[str, Any]) -> bool:
                if sender and payload.get("sender") != sender:
                    return False
                if channel and payload.get("channel") != channel:
                    return False
                return True
            filter_func_to_use = filter_func
            
        return await self.expect_event(MessageType.EVENT_CHAT_MESSAGE, filter_func=filter_func_to_use)
        
    # =========================================================================
    # Test Utilities
    # =========================================================================
    
    def get_message_log(self) -> List[WSMessage]:
        """Get all received messages for debugging"""
        return self.message_log.copy()
        
    def clear_message_log(self):
        """Clear message log"""
        self.message_log.clear()
        
    async def expect_no_events(self, duration: float = 1.0) -> None:
        """Assert that no events are received for a duration"""
        start_log_length = len(self.message_log)
        await asyncio.sleep(duration)
        
        if len(self.message_log) > start_log_length:
            new_messages = self.message_log[start_log_length:]
            raise WebSocketTestError(f"Unexpected events received: {new_messages}")

    # =========================================================================
    # Test Utilities
    # =========================================================================
    
    async def wait_for_event(
        self, 
        event_type: MessageType, 
        timeout: Optional[float] = None
    ) -> WSMessage:
        """
        Wait for a specific event type and return the full WSMessage.
        
        This is a wrapper around expect_event() that returns the full message
        instead of just the payload, for compatibility with existing tests.
        
        Args:
            event_type: The event type to wait for
            timeout: Optional timeout in seconds
            
        Returns:
            The full WSMessage object
        """
        timeout = timeout or self.default_timeout
        future = asyncio.Future()
        timeout_task = asyncio.create_task(self._handle_event_timeout(future, timeout))
        
        capture = EventCapture(
            event_type=event_type,
            future=future,
            timeout_task=timeout_task,
            filter_func=None
        )
        
        self.event_captures.append(capture)
        
        try:
            # Return the full WSMessage object, not just payload
            return await future
        except asyncio.TimeoutError:
                raise ResponseTimeoutError(f"Event timeout for {event_type}")
        finally:
            if capture in self.event_captures:
                self.event_captures.remove(capture)


# =============================================================================
# Test Decorators
# =============================================================================

def protocol_test(func):
    """Decorator for protocol tests"""
    func._protocol_version = "2.0"
    return func