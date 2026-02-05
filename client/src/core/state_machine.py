"""
Game state machine.

Manages the current state of the client and handles transitions.
"""

from enum import Enum, auto
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass

from .event_bus import get_event_bus, EventType


class GameState(Enum):
    """Client game states."""
    SERVER_SELECT = auto()    # Select server to connect to
    LOGIN = auto()            # Login form
    REGISTER = auto()         # Registration form
    CONNECTING = auto()         # Connecting to server
    AUTHENTICATING = auto()   # Authenticating with server
    LOADING = auto()          # Loading game data
    PLAYING = auto()          # Main game state
    DISCONNECTED = auto()     # Disconnected/error state
    CHARACTER_EDITOR = auto() # Character appearance editor
    SETTINGS = auto()         # Settings screen


@dataclass
class StateTransition:
    """Represents a state transition."""
    from_state: Optional[GameState]
    to_state: GameState
    data: Optional[dict]


class StateMachine:
    """Manages client state transitions."""
    
    # Valid state transitions
    VALID_TRANSITIONS: Dict[GameState, List[GameState]] = {
        GameState.SERVER_SELECT: [GameState.LOGIN, GameState.REGISTER, GameState.SETTINGS],
        GameState.LOGIN: [GameState.CONNECTING, GameState.SERVER_SELECT, GameState.REGISTER],
        GameState.REGISTER: [GameState.LOGIN, GameState.SERVER_SELECT],
        GameState.CONNECTING: [GameState.AUTHENTICATING, GameState.DISCONNECTED, GameState.SERVER_SELECT],
        GameState.AUTHENTICATING: [GameState.LOADING, GameState.DISCONNECTED, GameState.LOGIN],
        GameState.LOADING: [GameState.PLAYING, GameState.DISCONNECTED],
        GameState.PLAYING: [GameState.DISCONNECTED, GameState.CHARACTER_EDITOR, GameState.SETTINGS, GameState.SERVER_SELECT],
        GameState.DISCONNECTED: [GameState.SERVER_SELECT, GameState.LOGIN],
        GameState.CHARACTER_EDITOR: [GameState.PLAYING],
        GameState.SETTINGS: [GameState.SERVER_SELECT, GameState.LOGIN, GameState.PLAYING],
    }
    
    def __init__(self):
        self._current_state: GameState = GameState.SERVER_SELECT
        self._previous_state: Optional[GameState] = None
        self._transition_listeners: Dict[GameState, List[Callable]] = {}
        self._any_transition_listeners: List[Callable] = []
        self._state_data: Dict[str, any] = {}
    
    @property
    def current_state(self) -> GameState:
        """Get the current state."""
        return self._current_state
    
    @property
    def previous_state(self) -> Optional[GameState]:
        """Get the previous state."""
        return self._previous_state
    
    @property
    def is_connected(self) -> bool:
        """Check if in a connected state."""
        return self._current_state in {
            GameState.AUTHENTICATING,
            GameState.LOADING,
            GameState.PLAYING,
            GameState.CHARACTER_EDITOR,
            GameState.SETTINGS
        }
    
    @property
    def is_in_game(self) -> bool:
        """Check if actively playing."""
        return self._current_state == GameState.PLAYING
    
    def can_transition_to(self, state: GameState) -> bool:
        """Check if transition to given state is valid."""
        valid_states = self.VALID_TRANSITIONS.get(self._current_state, [])
        return state in valid_states
    
    def transition_to(self, state: GameState, data: Optional[dict] = None) -> bool:
        """
        Transition to a new state.
        
        Args:
            state: The state to transition to
            data: Optional data to pass to the new state
            
        Returns:
            True if transition was successful, False otherwise
        """
        if not self.can_transition_to(state):
            return False
        
        # Store transition data
        if data:
            self._state_data.update(data)
        
        # Perform transition
        self._previous_state = self._current_state
        self._current_state = state
        
        # Notify listeners
        transition = StateTransition(
            from_state=self._previous_state,
            to_state=state,
            data=data
        )
        
        # Call specific listeners
        for listener in self._transition_listeners.get(state, []):
            try:
                listener(transition)
            except Exception as e:
                print(f"Error in state transition listener: {e}")
        
        # Call any-transition listeners
        for listener in self._any_transition_listeners:
            try:
                listener(transition)
            except Exception as e:
                print(f"Error in any-transition listener: {e}")
        
        # Emit event
        event_bus = get_event_bus()
        event_bus.emit(
            EventType.STATE_CHANGED,
            {
                "from": self._previous_state.name if self._previous_state else None,
                "to": state.name,
                "data": data
            },
            "state_machine"
        )
        
        return True
    
    def on_transition_to(self, state: GameState, callback: Callable[[StateTransition], None]) -> None:
        """Register a callback for transitions to a specific state."""
        if state not in self._transition_listeners:
            self._transition_listeners[state] = []
        self._transition_listeners[state].append(callback)
    
    def on_any_transition(self, callback: Callable[[StateTransition], None]) -> None:
        """Register a callback for any state transition."""
        self._any_transition_listeners.append(callback)
    
    def get_state_data(self, key: str, default=None):
        """Get data associated with the current state."""
        return self._state_data.get(key, default)
    
    def set_state_data(self, key: str, value) -> None:
        """Set data for the current state."""
        self._state_data[key] = value
    
    def clear_state_data(self) -> None:
        """Clear all state data."""
        self._state_data.clear()


# Singleton instance
_state_machine: Optional[StateMachine] = None


def get_state_machine() -> StateMachine:
    """Get the singleton state machine instance."""
    global _state_machine
    if _state_machine is None:
        _state_machine = StateMachine()
    return _state_machine


def reset_state_machine() -> None:
    """Reset the state machine (useful for testing)."""
    global _state_machine
    _state_machine = None
