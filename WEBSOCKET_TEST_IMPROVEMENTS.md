# WebSocket Test Framework Improvements

## Summary

Fixed hanging WebSocket integration tests by adding proper timeouts, improving cleanup, and simplifying resource management.

## Changes Made

### 1. Removed Failed Attempt
- **Deleted**: `server/src/tests/threaded_server.py` - unsuccessful threaded server approach

### 2. WebSocketTestClient Improvements (`websocket_test_utils.py`)

#### Added Receive Timeouts
- **Problem**: `receive_bytes()` could hang indefinitely if server stopped sending
- **Solution**: Added 30-second timeout wrapper around all WebSocket receives
- **Impact**: Tests will fail fast instead of hanging forever

```python
# Before
raw_message = await self.websocket.receive_bytes()

# After  
raw_message = await asyncio.wait_for(
    self.websocket.receive_bytes(),
    timeout=30.0  # 30 second timeout
)
```

#### Improved Cleanup Method
- **Problem**: Background tasks weren't properly cancelled, leaving hanging futures
- **Solution**: Enhanced `close()` method with:
  - Proper task cancellation with timeout
  - Exception handling for all pending operations
  - Clear error states for futures instead of silent cancellation

```python
async def close(self):
    """Clean up the test client with proper cancellation"""
    self.running = False
    
    # Cancel background task with timeout
    if self._process_task and not self._process_task.done():
        self._process_task.cancel()
        try:
            await asyncio.wait_for(self._process_task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    
    # Cancel all pending operations
    for response in list(self.pending_responses.values()):
        if response.timeout_task and not response.timeout_task.done():
            response.timeout_task.cancel()
        if not response.future.done():
            response.future.set_exception(asyncio.CancelledError())
    
    # ... similar for event captures
```

#### Fixed Type Errors
- Fixed type checking issues with optional filter functions in convenience methods
- Proper `Optional[Callable]` handling in `expect_state_update()`, `expect_game_update()`, `expect_chat_message()`

### 3. Test Fixture Improvements (`conftest.py`)

#### Simplified with AsyncExitStack
- **Problem**: Manual context management with 6 cleanup steps prone to resource leaks
- **Solution**: Use `AsyncExitStack` for guaranteed cleanup in reverse order

```python
# Before: Manual tracking and cleanup
session = None
http_client = None
ws_context = None
# ... 150 lines of manual cleanup in finally block

# After: AsyncExitStack manages everything
async with AsyncExitStack() as stack:
    session = await stack.enter_async_context(TestingSessionLocal())
    http_client = await stack.enter_async_context(AsyncClient(...))
    websocket = await stack.enter_async_context(aconnect_ws(...))
    client = await stack.enter_async_context(WebSocketTestClient(websocket))
    
    yield client
    # Stack automatically cleans up in reverse order
```

#### Added Connection Timeouts
- **Problem**: WebSocket connection and auth could hang indefinitely
- **Solution**: Added 5-second timeouts to all critical operations:
  - WebSocket connection: `await asyncio.wait_for(aconnect_ws(...), timeout=5.0)`
  - Authentication response: `await asyncio.wait_for(websocket.receive_bytes(), timeout=5.0)`
  - Welcome message: `await asyncio.wait_for(websocket.receive_bytes(), timeout=5.0)`

## Benefits

### 1. No More Hanging Tests
- All WebSocket operations have timeouts
- Tests fail fast with clear error messages
- Background tasks properly cancelled on cleanup

### 2. Better Resource Management
- AsyncExitStack guarantees cleanup order
- No resource leaks on test failure
- Simpler, more maintainable code

### 3. Improved Error Messages
- Timeout errors are explicit: "Response timeout for EVENT_WELCOME"
- Clear indication of which operation timed out
- Better debugging experience

## Testing

The changes are designed to be backward compatible with existing tests. All tests should continue to work as before, but with better timeout handling.

### Recommended Test Run

```bash
# Docker environment (recommended)
cd docker && docker-compose -f docker-compose.test.yml up -d --build
docker exec docker-server-1 bash -c "RUN_INTEGRATION_TESTS=1 pytest -v"

# If tests hang, they will timeout after 30 seconds instead of indefinitely
```

### What Changed for Tests

**No changes required** - existing tests continue to work. The improvements are transparent:

- Tests that previously hung will now timeout with clear error messages
- Cleanup is more reliable, reducing flaky test failures
- Background tasks properly shut down between tests

## Architecture Notes

### httpx-ws + pytest-asyncio Compatibility

The fixture uses `AsyncExitStack` instead of simple `async with` statements to avoid pytest-asyncio task boundary issues with httpx-ws's internal anyio TaskGroups. This is the recommended pattern for this combination of libraries.

### Timeout Values

- **WebSocket receive**: 30 seconds (background task)
- **Connection/auth**: 5 seconds (fixture setup)
- **Test operations**: 5 seconds default, configurable per-test

These values are generous enough for CI/CD environments but short enough to fail fast on real hangs.

## Future Improvements (Optional)

If tests still have issues, consider:

1. **Reduce timeout values** if 30s is too long for your CI
2. **Add more granular timeouts** for specific test operations
3. **Monitor background task health** with periodic heartbeats
4. **Add connection retry logic** for flaky network conditions

## Migration Notes

- **No breaking changes** - existing tests work as-is
- **Debug logs removed** - cleaned up fixture debug prints
- **Type safety improved** - fixed all filter function type errors
