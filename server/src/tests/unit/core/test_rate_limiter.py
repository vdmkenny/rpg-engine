"""
Unit tests for the OperationRateLimiter class.

These tests verify the rate limiting behavior for inventory and equipment operations.
"""

import pytest
import time

from server.src.api.websockets import OperationRateLimiter


class TestOperationRateLimiter:
    """Tests for the OperationRateLimiter class."""

    def test_first_operation_allowed(self):
        """First operation for a user should always be allowed."""
        limiter = OperationRateLimiter()
        
        result = limiter.check_rate_limit("testuser", "inventory", 0.1)
        
        assert result is True

    def test_rapid_operations_blocked(self):
        """Rapid operations within cooldown should be blocked."""
        limiter = OperationRateLimiter()
        
        # First operation allowed
        result1 = limiter.check_rate_limit("testuser", "inventory", 0.5)
        assert result1 is True
        
        # Immediate second operation blocked
        result2 = limiter.check_rate_limit("testuser", "inventory", 0.5)
        assert result2 is False

    def test_operation_allowed_after_cooldown(self):
        """Operation should be allowed after cooldown expires."""
        limiter = OperationRateLimiter()
        cooldown = 0.05  # 50ms
        
        # First operation allowed
        result1 = limiter.check_rate_limit("testuser", "inventory", cooldown)
        assert result1 is True
        
        # Wait for cooldown
        time.sleep(cooldown + 0.01)
        
        # Second operation should now be allowed
        result2 = limiter.check_rate_limit("testuser", "inventory", cooldown)
        assert result2 is True

    def test_different_operation_types_independent(self):
        """Different operation types should have independent rate limits."""
        limiter = OperationRateLimiter()
        
        # First inventory operation allowed
        result1 = limiter.check_rate_limit("testuser", "inventory", 0.5)
        assert result1 is True
        
        # First equipment operation also allowed (different type)
        result2 = limiter.check_rate_limit("testuser", "equipment", 0.5)
        assert result2 is True
        
        # Second inventory operation blocked
        result3 = limiter.check_rate_limit("testuser", "inventory", 0.5)
        assert result3 is False
        
        # Second equipment operation also blocked
        result4 = limiter.check_rate_limit("testuser", "equipment", 0.5)
        assert result4 is False

    def test_different_users_independent(self):
        """Different users should have independent rate limits."""
        limiter = OperationRateLimiter()
        
        # First user's operation
        result1 = limiter.check_rate_limit("user1", "inventory", 0.5)
        assert result1 is True
        
        # Second user's operation (independent)
        result2 = limiter.check_rate_limit("user2", "inventory", 0.5)
        assert result2 is True
        
        # First user's second operation blocked
        result3 = limiter.check_rate_limit("user1", "inventory", 0.5)
        assert result3 is False
        
        # Second user's second operation also blocked
        result4 = limiter.check_rate_limit("user2", "inventory", 0.5)
        assert result4 is False

    def test_cleanup_player_removes_tracking(self):
        """Cleanup should remove all rate limit tracking for a player."""
        limiter = OperationRateLimiter()
        
        # Perform some operations
        limiter.check_rate_limit("testuser", "inventory", 0.5)
        limiter.check_rate_limit("testuser", "equipment", 0.5)
        
        # Cleanup the player
        limiter.cleanup_player("testuser")
        
        # Operations should now be allowed (fresh start)
        result1 = limiter.check_rate_limit("testuser", "inventory", 0.5)
        assert result1 is True
        
        result2 = limiter.check_rate_limit("testuser", "equipment", 0.5)
        assert result2 is True

    def test_cleanup_nonexistent_player_no_error(self):
        """Cleaning up a non-existent player should not raise an error."""
        limiter = OperationRateLimiter()
        
        # Should not raise any exception
        limiter.cleanup_player("nonexistent_user")

    def test_zero_cooldown_allows_rapid_operations(self):
        """Zero cooldown should allow all operations."""
        limiter = OperationRateLimiter()
        
        # All operations should be allowed with zero cooldown
        for _ in range(10):
            result = limiter.check_rate_limit("testuser", "inventory", 0)
            assert result is True

    def test_multiple_operation_types_tracked(self):
        """Multiple operation types should be tracked correctly per user."""
        limiter = OperationRateLimiter()
        
        # Track inventory and equipment operations
        limiter.check_rate_limit("testuser", "inventory", 0.5)
        limiter.check_rate_limit("testuser", "equipment", 0.5)
        limiter.check_rate_limit("testuser", "chat", 0.5)
        
        # All should be blocked now
        assert limiter.check_rate_limit("testuser", "inventory", 0.5) is False
        assert limiter.check_rate_limit("testuser", "equipment", 0.5) is False
        assert limiter.check_rate_limit("testuser", "chat", 0.5) is False
