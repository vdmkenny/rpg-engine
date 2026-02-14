"""
VisibilityService - Manages player visibility state for efficient diff-based broadcasting.

Tracks which entities each player can see and calculates what has changed since
their last update, enabling efficient network usage by only sending differences.

KEY DESIGN PRINCIPLE:
- player_id (int) is the ONLY internal identifier for players
- Entity keys use the format "player_{player_id}" or "entity_{instance_id}"
"""

from typing import Dict, Optional, Any
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
    - All player identification uses player_id (int)
    """
    
    def __init__(self, max_cache_size: Optional[int] = None):
        """
        Initialize VisibilityService with configurable cache size.
        
        Args:
            max_cache_size: Maximum number of players to track. Defaults to settings.MAX_PLAYERS
        """
        self.max_cache_size = max_cache_size or settings.MAX_PLAYERS
        self._lock = asyncio.Lock()
        
        # Per-player visibility cache: player_id -> {entity_key: entity_data}
        # LRU eviction ensures memory stays bounded even with admin over-capacity
        self._player_visible_cache: Dict[int, Dict[str, Dict[str, Any]]] = {}
        
        logger.info(
            "VisibilityService initialized",
            extra={"max_cache_size": self.max_cache_size}
        )
    
    async def get_player_visible_entities(self, player_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Get currently visible entities for a player.
        
        Args:
            player_id: Player's unique database ID
            
        Returns:
            Dict mapping entity_key to entity data, or empty dict if player not tracked
        """
        async with self._lock:
            return self._player_visible_cache.get(player_id, {}).copy()
    
    async def update_player_visible_entities(
        self, 
        player_id: int, 
        visible_entities: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Update visible entities for a player and return diff information.
        
        Args:
            player_id: Player's unique database ID
            visible_entities: Dict mapping entity_key to current entity data
            
        Returns:
            Dict with 'added', 'updated', 'removed' entity lists for broadcasting
        """
        async with self._lock:
            # Handle cache size limit with LRU eviction
            if player_id not in self._player_visible_cache and len(self._player_visible_cache) >= self.max_cache_size:
                # Remove oldest entry to maintain cache size bounds
                oldest_player_id = next(iter(self._player_visible_cache))
                del self._player_visible_cache[oldest_player_id]
                logger.debug(
                    "Evicted player from visibility cache due to size limit",
                    extra={"evicted_player_id": oldest_player_id, "cache_size": len(self._player_visible_cache)}
                )
            
            # Get previous state
            previous_entities = self._player_visible_cache.get(player_id, {})
            
            # Calculate diffs
            current_entity_keys = set(visible_entities.keys())
            previous_entity_keys = set(previous_entities.keys())
            
            added_keys = current_entity_keys - previous_entity_keys
            removed_keys = previous_entity_keys - current_entity_keys
            potential_updates = current_entity_keys & previous_entity_keys
            
            # DEBUG: Log when player's own entity is added (first time)
            for entity_key in added_keys:
                if entity_key.startswith("player_"):
                    logger.info(
                        f"[DEBUG] Player entity ADDED to visibility: {entity_key}, "
                        f"pos=({visible_entities[entity_key].get('x')}, {visible_entities[entity_key].get('y')})"
                    )
            
            # Check for actual updates (entity data changed)
            updated_keys = set()
            for entity_key in potential_updates:
                current_data = visible_entities[entity_key]
                previous_data = previous_entities.get(entity_key, {})
                if current_data != previous_data:
                    updated_keys.add(entity_key)
                    # DEBUG: Log what changed for player entities
                    if entity_key.startswith("player_"):
                        logger.info(
                            f"[DEBUG] Player entity changed: {entity_key}, "
                            f"old=({previous_data.get('x')}, {previous_data.get('y')}), "
                            f"new=({current_data.get('x')}, {current_data.get('y')})"
                        )
            
            # Update cache with new state
            self._player_visible_cache[player_id] = visible_entities.copy()
            
            # Build diff response
            diff = {
                "added": [visible_entities[entity_key] for entity_key in added_keys],
                "updated": [visible_entities[entity_key] for entity_key in updated_keys], 
                "removed": [{"id": entity_key} for entity_key in removed_keys]
            }
            
            return diff
    
    async def remove_player(self, player_id: int) -> None:
        """
        Remove a player from visibility tracking.
        Should be called when player disconnects to prevent memory leaks.
        
        Args:
            player_id: Player's unique database ID to remove
        """
        async with self._lock:
            if player_id in self._player_visible_cache:
                del self._player_visible_cache[player_id]
                logger.debug(
                    "Removed player from visibility cache",
                    extra={"player_id": player_id, "cache_size": len(self._player_visible_cache)}
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
