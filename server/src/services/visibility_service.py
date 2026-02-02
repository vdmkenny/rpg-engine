"""
VisibilityService - Manages player visibility state for efficient diff-based broadcasting.

Tracks which entities each player can see and calculates what has changed since
their last update, enabling efficient network usage by only sending differences.
"""

from functools import lru_cache
from typing import Dict, Set, Optional, Any, List
import asyncio
from server.src.core.config import settings
from server.src.core.logging_config import get_logger

logger = get_logger(__name__)


class VisibilityService:
    """
    Manages per-player visibility state with bounded memory usage.
    
    Tracks what entities each player can see and provides efficient diff calculations
    for network broadcasting. Uses bounded cache to prevent excessive memory usage.
    
    Key features:
    - Bounded cache size matching server capacity
    - Thread-safe operations with asyncio Lock
    - Automatic cleanup on player disconnect
    - Efficient diff-based updates to minimize network traffic
    """
    
    def __init__(self, max_cache_size: Optional[int] = None):
        """
        Initialize VisibilityService with configurable cache size.
        
        Args:
            max_cache_size: Maximum number of players to track. Defaults to settings.MAX_PLAYERS
        """
        self.max_cache_size = max_cache_size or settings.MAX_PLAYERS
        self._lock = asyncio.Lock()
        
        # Per-player visibility cache: player_username -> {entity_id: entity_data}
        # LRU eviction ensures memory stays bounded even with admin over-capacity
        self._player_visible_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
        
        logger.info(
            "VisibilityService initialized",
            extra={"max_cache_size": self.max_cache_size}
        )
    
    async def get_player_visible_entities(self, username: str) -> Dict[str, Dict[str, Any]]:
        """
        Get currently visible entities for a player.
        
        Args:
            username: Player's username
            
        Returns:
            Dict mapping entity_id to entity data, or empty dict if player not tracked
        """
        async with self._lock:
            return self._player_visible_cache.get(username, {}).copy()
    
    async def update_player_visible_entities(
        self, 
        username: str, 
        visible_entities: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Update visible entities for a player and return diff information.
        
        Args:
            username: Player's username
            visible_entities: Dict mapping entity_id to current entity data
            
        Returns:
            Dict with 'added', 'updated', 'removed' entity lists for broadcasting
        """
        async with self._lock:
            # Handle cache size limit with LRU eviction
            if username not in self._player_visible_cache and len(self._player_visible_cache) >= self.max_cache_size:
                # Remove oldest entry to maintain cache size bounds
                oldest_player = next(iter(self._player_visible_cache))
                del self._player_visible_cache[oldest_player]
                logger.debug(
                    "Evicted player from visibility cache due to size limit",
                    extra={"evicted_player": oldest_player, "cache_size": len(self._player_visible_cache)}
                )
            
            # Get previous state
            previous_entities = self._player_visible_cache.get(username, {})
            
            # Calculate diffs
            current_entity_ids = set(visible_entities.keys())
            previous_entity_ids = set(previous_entities.keys())
            
            added_ids = current_entity_ids - previous_entity_ids
            removed_ids = previous_entity_ids - current_entity_ids
            potential_updates = current_entity_ids & previous_entity_ids
            
            # DEBUG: Log when player's own entity is added (first time)
            for entity_id in added_ids:
                if entity_id.startswith("player_"):
                    logger.info(
                        f"[DEBUG] Player entity ADDED to visibility: {entity_id}, "
                        f"pos=({visible_entities[entity_id].get('x')}, {visible_entities[entity_id].get('y')})"
                    )
            
            # Check for actual updates (entity data changed)
            updated_ids = set()
            for entity_id in potential_updates:
                current_data = visible_entities[entity_id]
                previous_data = previous_entities.get(entity_id, {})
                if current_data != previous_data:
                    updated_ids.add(entity_id)
                    # DEBUG: Log what changed for player entities
                    if entity_id.startswith("player_"):
                        logger.info(
                            f"[DEBUG] Player entity changed: {entity_id}, "
                            f"old=({previous_data.get('x')}, {previous_data.get('y')}), "
                            f"new=({current_data.get('x')}, {current_data.get('y')})"
                        )
            
            # Update cache with new state
            self._player_visible_cache[username] = visible_entities.copy()
            
            # Build diff response
            diff = {
                "added": [visible_entities[entity_id] for entity_id in added_ids],
                "updated": [visible_entities[entity_id] for entity_id in updated_ids], 
                "removed": [{"id": entity_id} for entity_id in removed_ids]
            }
            
            logger.debug(
                "Updated player visibility state",
                extra={
                    "username": username,
                    "added_count": len(added_ids),
                    "updated_count": len(updated_ids), 
                    "removed_count": len(removed_ids),
                    "total_visible": len(current_entity_ids)
                }
            )
            
            return diff
    
    async def remove_player(self, username: str) -> None:
        """
        Remove a player from visibility tracking.
        Should be called when player disconnects to prevent memory leaks.
        
        Args:
            username: Player's username to remove
        """
        async with self._lock:
            if username in self._player_visible_cache:
                del self._player_visible_cache[username]
                logger.debug(
                    "Removed player from visibility cache",
                    extra={"username": username, "cache_size": len(self._player_visible_cache)}
                )
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get visibility cache statistics for monitoring.
        
        Returns:
            Dict with cache size, utilization, and capacity info
        """
        async with self._lock:
            current_size = len(self._player_visible_cache)
            utilization_percent = (current_size / self.max_cache_size * 100) if self.max_cache_size > 0 else 0
            
            return {
                "current_size": current_size,
                "max_size": self.max_cache_size,
                "utilization_percent": round(utilization_percent, 1),
                "available_slots": max(0, self.max_cache_size - current_size)
            }
    
    async def clear_cache(self) -> None:
        """
        Clear all visibility cache data.
        Used for testing and emergency cleanup scenarios.
        """
        async with self._lock:
            cleared_count = len(self._player_visible_cache)
            self._player_visible_cache.clear()
            logger.info(
                "Visibility cache cleared",
                extra={"cleared_entries": cleared_count}
            )


# Singleton instance management
_visibility_service: Optional[VisibilityService] = None


def get_visibility_service() -> VisibilityService:
    """
    Get the singleton VisibilityService instance.
    
    Returns:
        VisibilityService singleton instance
    """
    global _visibility_service
    if _visibility_service is None:
        _visibility_service = VisibilityService()
    return _visibility_service


def init_visibility_service(max_cache_size: Optional[int] = None) -> VisibilityService:
    """
    Initialize the VisibilityService singleton with custom configuration.
    
    Args:
        max_cache_size: Override default cache size
        
    Returns:
        VisibilityService singleton instance
    """
    global _visibility_service
    _visibility_service = VisibilityService(max_cache_size)
    return _visibility_service