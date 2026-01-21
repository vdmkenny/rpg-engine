"""
WebSocket Test Framework

Modern test utilities for the WebSocket protocol with proper
correlation ID handling and message pattern support.
"""

import asyncio
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
        self.error_message = error_payload.get("message", "Unknown error")
        self.error_details = error_payload.get("details", {})
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
    Enhanced WebSocket test client
    
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
        
        # Detect if WebSocket is sync (TestClient) or async (httpx)
        # TestClient WebSocket has sync methods, httpx has async methods
        self.is_async_websocket = hasattr(websocket, '__aenter__') or asyncio.iscoroutinefunction(getattr(websocket, 'receive_bytes', None))
        
        # Start message processing task
        self._process_task = asyncio.create_task(self._process_messages())
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def close(self):
        """Clean up the test client"""
        self.running = False
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
                
        # Cancel pending operations
        for response in self.pending_responses.values():
            response.timeout_task.cancel()
            if not response.future.done():
                response.future.cancel()
                
        for capture in self.event_captures:
            capture.timeout_task.cancel()
            if not capture.future.done():
                capture.future.cancel()
                
    async def _process_messages(self):
        """Process incoming WebSocket messages"""
        try:
            while self.running:
                try:
                    # Handle both sync (TestClient) and async (httpx) WebSocket interfaces
                    if self.is_async_websocket:
                        raw_message = await self.websocket.receive_bytes()
                    else:
                        # For sync TestClient, we need to run the sync method in an executor
                        raw_message = await asyncio.get_event_loop().run_in_executor(
                            None, self.websocket.receive_bytes
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
                                
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    # Log error but continue processing
                    print(f"Error processing WebSocket message: {e}")
                    
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
        
        # Handle both sync (TestClient) and async (httpx) WebSocket interfaces
        if self.is_async_websocket:
            await self.websocket.send_bytes(raw_message)
        else:
            # For sync TestClient, we need to run the sync method in an executor
            await asyncio.get_event_loop().run_in_executor(
                None, self.websocket.send_bytes, raw_message
            )
        
    async def _wait_for_response(self, correlation_id: str, expected_type: MessageType, timeout: float) -> WSMessage:
        """Wait for a correlated response"""
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
    ) -> Dict[str, Any]:
        """
        Send a command and wait for success response.
        Returns the success payload data.
        """
        if command_type not in COMMAND_TYPES:
            raise ValueError(f"{command_type} is not a command type")
            
        correlation_id = str(uuid.uuid4())
        timeout = timeout or self.default_timeout
        
        await self._send_message(command_type, payload, correlation_id)
        response = await self._wait_for_response(correlation_id, MessageType.RESP_SUCCESS, timeout)
        
        return response.payload
        
    # Command convenience methods
    async def authenticate(self, token: str) -> Dict[str, Any]:
        """Authenticate with JWT token"""
        return await self.send_command(MessageType.CMD_AUTHENTICATE, {"token": token})
        
    async def move_player(self, direction: str) -> Dict[str, Any]:
        """Move player in specified direction"""
        return await self.send_command(MessageType.CMD_MOVE, {"direction": direction})
        
    async def send_chat(self, message: str, channel: str = "local") -> Dict[str, Any]:
        """Send chat message"""
        return await self.send_command(MessageType.CMD_CHAT_SEND, {"message": message, "channel": channel})
        
    async def move_inventory_item(self, from_slot: int, to_slot: int) -> Dict[str, Any]:
        """Move item between inventory slots"""
        return await self.send_command(MessageType.CMD_INVENTORY_MOVE, {"from_slot": from_slot, "to_slot": to_slot})
        
    async def sort_inventory(self, sort_by: str = "category") -> Dict[str, Any]:
        """Sort inventory by criteria"""
        return await self.send_command(MessageType.CMD_INVENTORY_SORT, {"sort_by": sort_by})
        
    async def drop_item(self, inventory_slot: int, quantity: int = 1) -> Dict[str, Any]:
        """Drop item from inventory"""
        return await self.send_command(MessageType.CMD_ITEM_DROP, {"inventory_slot": inventory_slot, "quantity": quantity})
        
    async def pickup_item(self, ground_item_id: str) -> Dict[str, Any]:
        """Pick up ground item"""
        return await self.send_command(MessageType.CMD_ITEM_PICKUP, {"ground_item_id": ground_item_id})
        
    async def equip_item(self, inventory_slot: int) -> Dict[str, Any]:
        """Equip item from inventory"""
        return await self.send_command(MessageType.CMD_ITEM_EQUIP, {"inventory_slot": inventory_slot})
        
    async def unequip_item(self, equipment_slot: str) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        """
        Send a query and wait for data response.
        Returns the response data.
        """
        if query_type not in QUERY_TYPES:
            raise ValueError(f"{query_type} is not a query type")
            
        correlation_id = str(uuid.uuid4())
        timeout = timeout or self.default_timeout
        
        await self._send_message(query_type, payload, correlation_id)
        response = await self._wait_for_response(correlation_id, MessageType.RESP_DATA, timeout)
        
        return response.payload
        
    # Query convenience methods
    async def get_inventory(self) -> Dict[str, Any]:
        """Get current inventory state"""
        return await self.send_query(MessageType.QUERY_INVENTORY, {})
        
    async def get_equipment(self) -> Dict[str, Any]:
        """Get current equipment state"""
        return await self.send_query(MessageType.QUERY_EQUIPMENT, {})
        
    async def get_stats(self) -> Dict[str, Any]:
        """Get aggregated equipment stats"""
        return await self.send_query(MessageType.QUERY_STATS, {})
        
    async def get_map_chunks(
        self, 
        map_id: str, 
        center_x: int, 
        center_y: int, 
        radius: int = 1
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        """
        Wait for a specific event type.
        Optionally filter events with a function.
        Returns the event payload.
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
            return event.payload
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
    async def expect_welcome(self) -> Dict[str, Any]:
        """Expect welcome event after authentication"""
        return await self.expect_event(MessageType.EVENT_WELCOME)
        
    async def expect_state_update(
        self,
        target: Optional[str] = None,
        system: Optional[str] = None
    ) -> Dict[str, Any]:
        """Expect state update event with optional filtering"""
        def filter_func(payload: Dict[str, Any]) -> bool:
            if target and payload.get("target") != target:
                return False
            if system and system not in payload.get("systems", {}):
                return False
            return True
            
        filter_func = filter_func if (target or system) else None
        return await self.expect_event(MessageType.EVENT_STATE_UPDATE, filter_func=filter_func)
        
    async def expect_game_update(self, map_id: Optional[str] = None) -> Dict[str, Any]:
        """Expect game entity update"""
        def filter_func(payload: Dict[str, Any]) -> bool:
            if map_id and payload.get("map_id") != map_id:
                return False
            return True
            
        filter_func = filter_func if map_id else None
        return await self.expect_event(MessageType.EVENT_STATE_UPDATE, filter_func=filter_func)
        
    async def expect_chat_message(
        self, 
        sender: Optional[str] = None, 
        channel: Optional[str] = None
    ) -> Dict[str, Any]:
        """Expect chat message with optional filtering"""
        def filter_func(payload: Dict[str, Any]) -> bool:
            if sender and payload.get("sender") != sender:
                return False
            if channel and payload.get("channel") != channel:
                return False
            return True
            
        filter_func = filter_func if (sender or channel) else None
        return await self.expect_event(MessageType.EVENT_CHAT_MESSAGE, filter_func=filter_func)
        
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
    # Legacy Compatibility Methods (for existing equipment tests)
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
                
    async def add_test_item_to_inventory(self, item_name: str, slot: int) -> None:
        """
        Helper method to add test item to inventory for testing purposes.
        
        This is a test-only utility method that bypasses normal game mechanics
        to directly add items to inventory for test setup.
        
        Args:
            item_name: The name/ID of the item to add (e.g., "wooden_sword")  
            slot: The inventory slot to add the item to
        """
        try:
            # Import here to avoid circular dependencies
            from server.src.services.game_state_manager import get_game_state_manager
            from server.src.services.inventory_service import InventoryService
            
            gsm = get_game_state_manager()
            
            # For now, use a simple approach - find the test user
            # In the test environment, there should only be one online player
            # This is the "testuser" created in the test fixture
            from server.src.services.connection_service import ConnectionService
            online_players = ConnectionService.get_online_player_ids()
            
            if not online_players:
                raise WebSocketTestError("No online players found for test item setup")
                
            # Use the first (and likely only) online player in tests
            player_id = online_players[0] 
            
            # For the simple approach, we'll use a hardcoded item ID mapping
            # In a real implementation, this would look up the item in the database
            item_id_map = {
                "wooden_sword": 1,  # Assuming wooden_sword has ID 1 in test data
                "iron_sword": 2,
                "bronze_arrows": 10,
                "iron_arrows": 11,
            }
            
            item_id = item_id_map.get(item_name)
            if not item_id:
                # Fallback: try to use the name as an ID if it's numeric
                try:
                    item_id = int(item_name)
                except ValueError:
                    raise WebSocketTestError(f"Unknown test item: {item_name}")
            
            # Add the item directly to inventory
            result = await InventoryService.add_item(player_id, item_id, quantity=1)
            
            if not result.success:
                raise WebSocketTestError(f"Failed to add test item {item_name}: {result.message}")
                
        except Exception as e:
            raise WebSocketTestError(f"Failed to add test item to inventory: {str(e)}")


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================

@pytest.fixture
async def websocket_client(authenticated_websocket):
    """Create a WebSocket test client"""
    async with WebSocketTestClient(authenticated_websocket) as client:
        yield client


async def create_test_player(websocket_client: WebSocketTestClient, username: str = None) -> Dict[str, Any]:
    """Create and authenticate a test player"""
    from server.src.tests.conftest import create_test_token
    
    if not username:
        username = f"test_player_{int(time.time() * 1000)}"
        
    token = await create_test_token(username)
    auth_result = await websocket_client.authenticate(token)
    
    return {
        "username": username,
        "token": token,
        "auth_result": auth_result
    }


# =============================================================================
# Test Scenarios
# =============================================================================

class TestScenarios:
    """
    Pre-configured test scenarios to eliminate setup duplication.
    
    Provides common test setups like players with items, multiplayer scenarios,
    and ground item configurations.
    """
    
    @staticmethod
    async def player_with_items(
        integration_client: TestClient, 
        items: List[str],
        username_prefix: str = "itemtest",
        db_session=None
    ) -> WebSocketTestClient:
        """
        Create a player with specific inventory items.
        
        Args:
            integration_client: FastAPI test client
            items: List of item names to add to inventory
            username_prefix: Prefix for generated username
            db_session: Database session for TestDataService
        
        Returns:
            Connected and authenticated WebSocketTestClient
        """
        # Ensure test data exists
        if db_session:
            await TestDataService.ensure_game_data_synced(db_session)
        
        # Create player with items
        client = await WebSocketTestClient.create_player(
            integration_client, 
            username_prefix,
            db_session=db_session,
            inventory_items=items
        )
        
        await client.connect_and_authenticate()
        return client
    
    @staticmethod
    async def player_with_equipment(
        integration_client: TestClient,
        equipment: Dict[str, str],
        username_prefix: str = "equiptest",
        db_session=None
    ) -> WebSocketTestClient:
        """
        Create a player with specific equipment.
        
        Args:
            integration_client: FastAPI test client  
            equipment: Dict of {slot: item_name}
            username_prefix: Prefix for generated username
            db_session: Database session for TestDataService
        
        Returns:
            Connected and authenticated WebSocketTestClient
        """
        # Ensure test data exists
        if db_session:
            await TestDataService.ensure_game_data_synced(db_session)
        
        # Create player with equipment
        client = await WebSocketTestClient.create_player(
            integration_client,
            username_prefix,
            db_session=db_session,
            equipment=equipment
        )
        
        await client.connect_and_authenticate()
        return client
    
    @staticmethod
    async def multiplayer_same_map(
        integration_client: TestClient, 
        count: int = 2,
        map_id: str = "samplemap",
        db_session=None
    ) -> List[WebSocketTestClient]:
        """
        Create multiple players on the same map.
        
        Args:
            integration_client: FastAPI test client
            count: Number of players to create
            map_id: Map to place players on
            db_session: Database session for TestDataService
        
        Returns:
            List of connected WebSocketTestClient instances
        """
        # Ensure test data exists
        if db_session:
            await TestDataService.ensure_game_data_synced(db_session)
        
        clients = []
        for i in range(count):
            client = await WebSocketTestClient.create_player(
                integration_client,
                f"multi{i}",
                db_session=db_session,
                map_id=map_id,
                x=10 + i,  # Spread players out slightly
                y=10 + i
            )
            await client.connect_and_authenticate()
            clients.append(client)
        
        return clients
    
    @staticmethod
    async def ground_items_scenario(
        integration_client: TestClient,
        ground_items: List[GroundItemConfig],
        username_prefix: str = "groundtest",
        db_session=None
    ) -> WebSocketTestClient:
        """
        Create a player with ground items nearby.
        
        Args:
            integration_client: FastAPI test client
            ground_items: List of GroundItemConfig objects
            username_prefix: Prefix for generated username
            db_session: Database session for TestDataService
        
        Returns:
            WebSocketTestClient with scenario_data containing ground item info
        """
        # Ensure test data exists
        if db_session:
            await TestDataService.ensure_game_data_synced(db_session)
        
        # Create player first
        client = await WebSocketTestClient.create_player(
            integration_client,
            username_prefix,
            db_session=db_session,
            x=5, 
            y=5
        )
        
        # Create scenario using TestDataService
        if db_session:
            player_configs = [PlayerConfig(
                username_prefix=f"{username_prefix}_main",
                x=5,
                y=5
            )]
            
            scenario_result = await TestDataService.create_multiplayer_scenario(
                db=db_session,
                player_configs=player_configs,
                ground_items=ground_items
            )
            
            if scenario_result.success:
                # Store scenario data for test use
                client.scenario_data = TestScenarioData(
                    players=[{"username": client.username, "id": client.player_id}],
                    ground_items=scenario_result.data.ground_items,
                    inventory_items={},
                    equipment_items={}
                )
        
        await client.connect_and_authenticate()
        return client


class WebSocketAssertions:
    """
    Standardized assertion helpers for WebSocket test responses.
    
    Provides consistent validation patterns across all WebSocket tests.
    """
    
    @staticmethod
    def operation_success(
        response: WebSocketResponse, 
        operation: str, 
        message_contains: Optional[str] = None
    ):
        """
        Assert that a WebSocket operation succeeded.
        
        Args:
            response: WebSocketResponse object
            operation: Expected operation name
            message_contains: Optional substring to expect in message
        """
        assert response.success, f"Operation {operation} failed: {response.message}"
        
        if message_contains:
            assert message_contains in response.message, (
                f"Expected message to contain '{message_contains}', "
                f"got: {response.message}"
            )
    
    @staticmethod
    def operation_failure(
        response: WebSocketResponse, 
        operation: str, 
        error_code: Optional[str] = None,
        message_contains: Optional[str] = None
    ):
        """
        Assert that a WebSocket operation failed as expected.
        
        Args:
            response: WebSocketResponse object
            operation: Expected operation name
            error_code: Optional error code to expect
            message_contains: Optional substring to expect in error message
        """
        assert not response.success, f"Operation {operation} should have failed but succeeded: {response.message}"
        
        if error_code:
            # This will be used when we implement structured error codes
            pass
        
        if message_contains:
            assert message_contains in response.message, (
                f"Expected error message to contain '{message_contains}', "
                f"got: {response.message}"
            )
    
    @staticmethod
    def message_received(messages: List[Dict], message_type: str) -> Dict:
        """
        Assert that a specific message type was received.
        
        Args:
            messages: List of received messages
            message_type: Expected message type
        
        Returns:
            The matching message
        """
        for msg in reversed(messages):  # Check most recent first
            if msg.get("type") == message_type:
                return msg
        
        received_types = [msg.get("type") for msg in messages]
        raise AssertionError(
            f"Expected {message_type} message not received. "
            f"Got messages: {received_types}"
        )
    
    @staticmethod
    def no_message_received(messages: List[Dict], message_type: str):
        """
        Assert that a specific message type was NOT received.
        
        Args:
            messages: List of received messages
            message_type: Message type that should not be present
        """
        for msg in messages:
            if msg.get("type") == message_type:
                raise AssertionError(f"Unexpected {message_type} message received: {msg}")


# =============================================================================
# Test Decorators and Markers
# =============================================================================

def requires_integration():
    """Mark test as requiring integration test environment"""
    return pytest.mark.skipif(
        not pytest.get_integration_test_flag(),
        reason="Integration tests require RUN_INTEGRATION_TESTS=1"
    )


def protocol_test(func):
    """Decorator for protocol tests"""
    func._protocol_version = "2.0"
    return func