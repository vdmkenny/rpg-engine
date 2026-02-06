"""
Core event bus for internal client communication.

Provides a pub/sub system for decoupled component communication.
"""

from typing import Callable, Dict, List, Any, Optional
from enum import Enum, auto
import asyncio
from dataclasses import dataclass, field


class EventType(Enum):
    """Internal client event types."""
    # Connection events
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTED = auto()
    CONNECTION_ERROR = auto()
    RECONNECTING = auto()
    
    # Authentication events
    AUTHENTICATING = auto()
    AUTHENTICATED = auto()
    AUTH_FAILED = auto()
    
    # State events
    STATE_CHANGED = auto()
    GAME_STARTED = auto()
    GAME_PAUSED = auto()
    
    # Player events
    PLAYER_MOVED = auto()
    PLAYER_ATTACKED = auto()
    PLAYER_DAMAGED = auto()
    PLAYER_DIED = auto()
    PLAYER_RESPAWNED = auto()
    
    # Inventory events
    INVENTORY_UPDATED = auto()
    INVENTORY_ITEM_MOVED = auto()
    INVENTORY_ITEM_EQUIPPED = auto()
    INVENTORY_ITEM_UNEQUIPPED = auto()
    INVENTORY_ITEM_DROPPED = auto()
    INVENTORY_ITEM_PICKED_UP = auto()
    
    # Equipment events
    EQUIPMENT_UPDATED = auto()
    
    # Combat events
    COMBAT_STARTED = auto()
    COMBAT_ENDED = auto()
    COMBAT_ACTION_RECEIVED = auto()
    HIT_SPLAT_RECEIVED = auto()
    
    # Stats events
    STATS_UPDATED = auto()
    APPEARANCE_UPDATED = auto()
    
    # Chat events
    CHAT_MESSAGE_RECEIVED = auto()
    CHAT_SENT = auto()
    
    # Error events
    ERROR_RECEIVED = auto()
    
    # UI events
    PANEL_OPENED = auto()
    PANEL_CLOSED = auto()
    CONTEXT_MENU_OPENED = auto()
    TOOLTIP_SHOWN = auto()
    
    # Entity events
    ENTITY_SPAWNED = auto()
    ENTITY_DESPAWNED = auto()
    ENTITY_MOVED = auto()
    
    # Map events
    CHUNK_RECEIVED = auto()
    MAP_CHANGED = auto()


@dataclass
class Event:
    """Event data structure."""
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None


class EventBus:
    """Central event bus for client communication."""
    
    def __init__(self):
        self._handlers: Dict[EventType, List[Callable]] = {}
        self._once_handlers: Dict[EventType, List[Callable]] = {}
    
    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Subscribe a handler to an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def subscribe_once(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Subscribe a handler that will be called only once."""
        if event_type not in self._once_handlers:
            self._once_handlers[event_type] = []
        self._once_handlers[event_type].append(handler)
    
    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Unsubscribe a handler from an event type."""
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
        
        if event_type in self._once_handlers and handler in self._once_handlers[event_type]:
            self._once_handlers[event_type].remove(handler)
    
    def emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None, source: Optional[str] = None) -> None:
        """
        Emit an event to all subscribers.
        
        Note: Async handlers will be scheduled as tasks on the running event loop.
        For guaranteed async execution, use emit_async() instead.
        """
        event = Event(type=event_type, data=data or {}, source=source)
        
        # Call regular handlers
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    # Schedule async handler as a task
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(handler(event))
                    except RuntimeError:
                        # No running event loop - can't schedule async handler
                        print(f"Warning: async handler {handler} registered but no event loop running")
                else:
                    handler(event)
            except Exception as e:
                print(f"Error in event handler: {e}")
        
        # Call once handlers
        once_handlers = self._once_handlers.get(event_type, [])
        if once_handlers:
            for handler in once_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        # Schedule async handler as a task
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(handler(event))
                        except RuntimeError:
                            # No running event loop - can't schedule async handler
                            print(f"Warning: async once-handler {handler} registered but no event loop running")
                    else:
                        handler(event)
                except Exception as e:
                    print(f"Error in once handler: {e}")
            # Clear once handlers
            self._once_handlers[event_type] = []
    
    async def emit_async(self, event_type: EventType, data: Optional[Dict[str, Any]] = None, source: Optional[str] = None) -> None:
        """Emit an event asynchronously."""
        event = Event(type=event_type, data=data or {}, source=source)
        
        # Call regular handlers
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                print(f"Error in async event handler: {e}")
        
        # Call once handlers
        once_handlers = self._once_handlers.get(event_type, [])
        if once_handlers:
            for handler in once_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    print(f"Error in async once handler: {e}")
            # Clear once handlers
            self._once_handlers[event_type] = []
    
    def clear(self, event_type: Optional[EventType] = None) -> None:
        """Clear all handlers for an event type, or all handlers if None."""
        if event_type:
            self._handlers.pop(event_type, None)
            self._once_handlers.pop(event_type, None)
        else:
            self._handlers.clear()
            self._once_handlers.clear()


# Singleton event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the singleton event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """Reset the event bus (useful for testing)."""
    global _event_bus
    _event_bus = None
