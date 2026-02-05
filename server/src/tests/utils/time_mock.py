"""
Deterministic time mocking utilities for tests.

Provides fixtures and context managers for controlling time in tests
to eliminate flaky timing-dependent assertions.
"""

import asyncio
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import patch


class FrozenTime:
    """
    Time controller for deterministic testing.
    
    Allows tests to freeze time at a specific point and advance it
    programmatically, eliminating timing-related flakiness.
    """
    
    def __init__(self, initial_timestamp: float = 1000.0):
        self._timestamp = initial_timestamp
        self._frozen = True
    
    def now(self) -> float:
        """Get current frozen timestamp."""
        return self._timestamp
    
    def advance(self, seconds: float) -> None:
        """Advance time by specified seconds."""
        self._timestamp += seconds
    
    def set_time(self, timestamp: float) -> None:
        """Set time to specific timestamp."""
        self._timestamp = timestamp
    
    def utc_timestamp(self) -> float:
        """Return frozen timestamp (matches BaseManager._utc_timestamp signature)."""
        return self._timestamp
    
    def datetime_now(self) -> datetime:
        """Return frozen datetime."""
        return datetime.fromtimestamp(self._timestamp, tz=timezone.utc)


@contextmanager
def freeze_time(initial_timestamp: float = 1000.0):
    """
    Context manager to freeze time for synchronous code.
    
    Usage:
        with freeze_time(1000.0) as frozen:
            assert time.time() == 1000.0
            frozen.advance(5)
            assert time.time() == 1005.0
    """
    frozen = FrozenTime(initial_timestamp)
    
    with patch('time.time', frozen.now):
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = frozen.datetime_now()
            mock_datetime.utcnow.return_value = frozen.datetime_now()
            yield frozen


@asynccontextmanager
async def afreeze_time(initial_timestamp: float = 1000.0):
    """
    Async context manager to freeze time.
    
    Usage:
        async with afreeze_time(1000.0) as frozen:
            await some_async_operation()
            frozen.advance(5)
    """
    frozen = FrozenTime(initial_timestamp)
    
    with patch('time.time', frozen.now):
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = frozen.datetime_now()
            mock_datetime.utcnow.return_value = frozen.datetime_now()
            yield frozen


def mock_utc_timestamp(frozen_time: FrozenTime):
    """
    Create a mock function that can be used to patch BaseManager._utc_timestamp.
    
    Usage:
        frozen = FrozenTime(1000.0)
        with patch.object(BaseManager, '_utc_timestamp', mock_utc_timestamp(frozen)):
            # All BaseManager instances will use frozen time
            pass
    """
    def _mock_utc_timestamp(self):
        return frozen_time.utc_timestamp()
    return _mock_utc_timestamp


class ControlledRandom:
    """
    Controlled random number generator for deterministic tests.
    
    Replaces random.random() and related functions with deterministic sequences.
    """
    
    def __init__(self, seed: int = 42):
        import random
        self._random = random.Random(seed)
        self._sequence_position = 0
    
    def random(self) -> float:
        """Return next deterministic random float."""
        return self._random.random()
    
    def randint(self, a: int, b: int) -> int:
        """Return deterministic random integer in range [a, b]."""
        return self._random.randint(a, b)
    
    def choice(self, seq):
        """Return deterministic choice from sequence."""
        return self._random.choice(seq)
    
    def reset(self, seed: int = 42) -> None:
        """Reset random sequence to start with new seed."""
        import random
        self._random = random.Random(seed)


@contextmanager
def control_random(seed: int = 42):
    """
    Context manager to control randomness in tests.
    
    Usage:
        with control_random(42) as rand:
            result1 = random.random()  # Deterministic
            result2 = random.random()  # Deterministic sequence
            assert result1 == 0.6394...  # Always same value
    """
    import random
    controlled = ControlledRandom(seed)
    
    with patch('random.random', controlled.random):
        with patch('random.randint', controlled.randint):
            with patch('random.choice', controlled.choice):
                yield controlled


# Predefined time scenarios for common test cases
TIMESTAMP_ZERO = 0.0
TIMESTAMP_START = 1000.0
TIMESTAMP_MID = 2000.0
TIMESTAMP_END = 3000.0


def get_timestamp_mock(scenario: str = "start") -> float:
    """Get predefined timestamp for consistent test scenarios."""
    scenarios = {
        "zero": TIMESTAMP_ZERO,
        "start": TIMESTAMP_START,
        "mid": TIMESTAMP_MID,
        "end": TIMESTAMP_END,
    }
    return scenarios.get(scenario, TIMESTAMP_START)
