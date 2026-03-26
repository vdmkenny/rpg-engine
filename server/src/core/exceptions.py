"""
Domain exceptions for the RPG engine.

Services raise these instead of HTTP exceptions to maintain layer separation.
API routes catch them and convert to appropriate HTTP responses.
"""


class DuplicatePlayerError(Exception):
    """Raised when attempting to create a player with a username that already exists."""
    pass


class ServiceError(Exception):
    """Raised when a service operation fails due to an internal error."""
    pass


class PlayerBannedError(Exception):
    """Raised when a banned player attempts to authenticate."""
    pass


class PlayerTimedOutError(Exception):
    """Raised when a timed-out player attempts to authenticate."""

    def __init__(self, timeout_until):
        self.timeout_until = timeout_until
        super().__init__(f"Player is timed out until {timeout_until}")
