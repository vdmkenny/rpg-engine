"""
Visual Registry Service - Hash-based visual state caching.

This service manages the mapping between visual hashes and VisualState objects,
enabling efficient network broadcasting. Instead of sending full visual data
every tick, we only send a hash - observers lookup the full data from cache.

Key concepts:
- Visual hash: 12-char hex string uniquely identifying a visual state
- Observer tracking: Track which hashes each player has seen
- First-sight data: Send full visual state only when observer hasn't seen hash

Usage:
    from server.src.services.visual_registry import get_visual_registry
    
    registry = get_visual_registry()
    
    # Register a player's current visual state
    visual_hash = await registry.register_visual_state(player_id, visual_state)
    
    # Check if observer needs full visual data
    if registry.observer_needs_full_visual(observer_id, visual_hash):
        # Send full visual_state in payload
        pass
    else:
        # Send only visual_hash in payload
        pass
"""

from typing import Dict, Optional, Set
from collections import OrderedDict
import asyncio

from common.src.sprites import VisualState, AppearanceData, EquippedVisuals
from server.src.core.logging_config import get_logger

logger = get_logger(__name__)


class VisualRegistry:
    """
    Registry for visual state hashes and observer tracking.
    
    Thread-safe via asyncio locks. Stores:
    1. Hash -> VisualState mapping (LRU cache)
    2. Observer -> seen hashes mapping (per-observer cache)
    3. Entity -> current hash mapping (for change detection)
    
    The registry uses an LRU cache to bound memory usage while keeping
    recently-used visual states available for quick lookup.
    """
    
    # Maximum number of visual states to cache
    MAX_CACHE_SIZE = 10000
    
    # Maximum number of hashes to track per observer
    MAX_OBSERVER_CACHE_SIZE = 500
    
    def __init__(self):
        self._lock = asyncio.Lock()
        
        # Hash -> VisualState mapping (LRU cache using OrderedDict)
        self._visual_cache: OrderedDict[str, VisualState] = OrderedDict()
        
        # Observer ID -> set of seen hashes
        self._observer_seen: Dict[str, Set[str]] = {}
        
        # Entity ID -> current visual hash
        self._entity_hashes: Dict[str, str] = {}
    
    async def register_visual_state(
        self,
        entity_id: str,
        visual_state: VisualState,
    ) -> str:
        """
        Register a visual state and return its hash.
        
        Stores the visual state in the cache and updates the entity's
        current hash. Returns the hash for network transmission.
        
        Args:
            entity_id: Unique identifier for the entity (e.g., "player_123" or "entity_456")
            visual_state: The complete visual state to register.
            
        Returns:
            12-character hexadecimal hash string.
        """
        visual_hash = visual_state.compute_hash()
        
        async with self._lock:
            # Update entity's current hash
            old_hash = self._entity_hashes.get(entity_id)
            self._entity_hashes[entity_id] = visual_hash
            
            # Only cache if hash changed or not cached
            if visual_hash not in self._visual_cache:
                # Add to cache with LRU eviction
                self._visual_cache[visual_hash] = visual_state
                
                # Evict oldest entries if over capacity
                while len(self._visual_cache) > self.MAX_CACHE_SIZE:
                    self._visual_cache.popitem(last=False)
                    
            else:
                # Move to end of LRU queue
                self._visual_cache.move_to_end(visual_hash)
        
        return visual_hash
    
    async def get_visual_state(self, visual_hash: str) -> Optional[VisualState]:
        """
        Retrieve a visual state by its hash.
        
        Args:
            visual_hash: The hash to look up.
            
        Returns:
            VisualState if found, None otherwise.
        """
        async with self._lock:
            state = self._visual_cache.get(visual_hash)
            if state is not None:
                # Move to end of LRU queue
                self._visual_cache.move_to_end(visual_hash)
            return state
    
    async def get_entity_hash(self, entity_id: str) -> Optional[str]:
        """
        Get the current visual hash for an entity.
        
        Args:
            entity_id: The entity identifier.
            
        Returns:
            Current visual hash or None if entity not registered.
        """
        async with self._lock:
            return self._entity_hashes.get(entity_id)
    
    async def has_hash_changed(self, entity_id: str, new_hash: str) -> bool:
        """
        Check if an entity's visual hash has changed.
        
        Args:
            entity_id: The entity identifier.
            new_hash: The new hash to compare.
            
        Returns:
            True if the hash differs from the stored value (or entity is new).
        """
        async with self._lock:
            old_hash = self._entity_hashes.get(entity_id)
            return old_hash != new_hash
    
    async def observer_needs_full_visual(
        self,
        observer_id: str,
        visual_hash: str,
    ) -> bool:
        """
        Check if an observer needs the full visual state for a hash.
        
        Returns True if the observer hasn't seen this hash before,
        meaning we need to send the full VisualState data.
        
        Args:
            observer_id: The observing player's identifier.
            visual_hash: The hash to check.
            
        Returns:
            True if full visual data should be sent.
        """
        async with self._lock:
            seen_hashes = self._observer_seen.get(observer_id)
            if seen_hashes is None:
                return True
            return visual_hash not in seen_hashes
    
    async def mark_hash_seen(
        self,
        observer_id: str,
        visual_hash: str,
    ) -> None:
        """
        Mark a visual hash as seen by an observer.
        
        Called after sending full visual state to an observer.
        
        Args:
            observer_id: The observing player's identifier.
            visual_hash: The hash that was sent.
        """
        async with self._lock:
            if observer_id not in self._observer_seen:
                self._observer_seen[observer_id] = set()
            
            seen_set = self._observer_seen[observer_id]
            seen_set.add(visual_hash)
            
            # Evict oldest entries if over capacity
            # Note: Sets don't preserve order, so we just clear half if too big
            if len(seen_set) > self.MAX_OBSERVER_CACHE_SIZE:
                # Convert to list, keep recent half
                hashes_list = list(seen_set)
                half = len(hashes_list) // 2
                self._observer_seen[observer_id] = set(hashes_list[half:])
    
    async def get_visual_for_observer(
        self,
        observer_id: str,
        entity_id: str,
        visual_state: VisualState,
    ) -> tuple[str, Optional[dict]]:
        """
        Get visual data to send to an observer for an entity.
        
        This is the main method for the game loop. It:
        1. Computes/gets the visual hash
        2. Checks if observer needs full data
        3. Returns (hash, full_data_or_none)
        
        Args:
            observer_id: The observing player's identifier.
            entity_id: The entity being observed.
            visual_state: The entity's current visual state.
            
        Returns:
            Tuple of (visual_hash, visual_dict_or_none).
            visual_dict is only set if observer needs full data.
        """
        visual_hash = await self.register_visual_state(entity_id, visual_state)
        
        needs_full = await self.observer_needs_full_visual(observer_id, visual_hash)
        
        if needs_full:
            await self.mark_hash_seen(observer_id, visual_hash)
            return (visual_hash, visual_state.to_dict())
        else:
            return (visual_hash, None)
    
    async def remove_observer(self, observer_id: str) -> None:
        """
        Remove all tracking data for a disconnected observer.
        
        Called when a player disconnects to free memory.
        
        Args:
            observer_id: The observer's identifier.
        """
        async with self._lock:
            self._observer_seen.pop(observer_id, None)
    
    async def remove_entity(self, entity_id: str) -> None:
        """
        Remove tracking data for a despawned entity.
        
        Note: Does NOT remove the visual state from cache (other entities
        may share the same visual state).
        
        Args:
            entity_id: The entity's identifier.
        """
        async with self._lock:
            self._entity_hashes.pop(entity_id, None)
    
    async def get_stats(self) -> dict:
        """
        Get statistics about the registry for monitoring.
        
        Returns:
            Dictionary with cache sizes and counts.
        """
        async with self._lock:
            return {
                "visual_cache_size": len(self._visual_cache),
                "entity_count": len(self._entity_hashes),
                "observer_count": len(self._observer_seen),
                "max_cache_size": self.MAX_CACHE_SIZE,
                "max_observer_cache_size": self.MAX_OBSERVER_CACHE_SIZE,
            }
    
    async def clear_all(self) -> None:
        """
        Clear all cached data.
        
        Used for testing and server restart.
        """
        async with self._lock:
            self._visual_cache.clear()
            self._observer_seen.clear()
            self._entity_hashes.clear()


# Singleton instance
_visual_registry: Optional[VisualRegistry] = None


def get_visual_registry() -> VisualRegistry:
    """
    Get or create the singleton VisualRegistry instance.
    
    Returns:
        The global VisualRegistry instance.
    """
    global _visual_registry
    if _visual_registry is None:
        _visual_registry = VisualRegistry()
    return _visual_registry


def reset_visual_registry() -> None:
    """
    Reset the singleton instance.
    
    Used for testing to ensure clean state between tests.
    """
    global _visual_registry
    _visual_registry = None


# Module-level singleton instance for convenient imports
visual_registry = get_visual_registry()
