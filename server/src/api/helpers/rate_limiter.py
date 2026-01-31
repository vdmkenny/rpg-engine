"""
Rate limiting for WebSocket operations.

Provides per-player, per-operation cooldown tracking.
"""

import time
from typing import Dict


class OperationRateLimiter:
    """
    Rate limiter for specific WebSocket operations.
    
    Tracks the last execution time of operations per player
    and enforces cooldown periods.
    """
    
    def __init__(self):
        self._player_last_operation: Dict[int, Dict[str, float]] = {}
    
    def check_rate_limit(self, user_id: str, operation: str, cooldown: float) -> bool:
        """
        Check if operation is allowed for user.
        
        Args:
            user_id: Player username or ID
            operation: Operation name
            cooldown: Cooldown in seconds
            
        Returns:
            True if allowed, False if rate limited
        """
        try:
            player_id = int(user_id)
        except (ValueError, TypeError):
            player_id = hash(user_id) % 1000000
        
        current_time = time.time()
        
        if player_id not in self._player_last_operation:
            self._player_last_operation[player_id] = {}
        
        # Zero cooldown always allows
        if cooldown == 0:
            self._player_last_operation[player_id][operation] = current_time
            return True
        
        last_operation_time = self._player_last_operation[player_id].get(operation, 0)
        time_since_last = current_time - last_operation_time
        
        if time_since_last >= cooldown:
            self._player_last_operation[player_id][operation] = current_time
            return True
        
        return False
    
    def cleanup_player(self, user_id: str) -> None:
        """
        Clean up rate limiting data for disconnected player.
        
        Args:
            user_id: Player username or ID to clean up
        """
        try:
            player_id = int(user_id)
        except (ValueError, TypeError):
            player_id = hash(user_id) % 1000000
        
        self._player_last_operation.pop(player_id, None)
