"""
Concurrency control infrastructure for RPG Engine.

Provides player-level locking and Valkey atomic operations to prevent race conditions
and ensure data consistency in multiplayer scenarios.
"""

import asyncio
import time
import traceback
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Set, Any, AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging

from glide import GlideClient
from prometheus_client import Counter, Histogram, Gauge

from server.src.core.logging_config import get_logger

logger = get_logger(__name__)

# Metrics
PLAYER_LOCK_ACQUISITIONS = Counter(
    "player_lock_acquisitions_total", 
    "Total number of player lock acquisitions",
    ["player_id", "operation_type"]
)
PLAYER_LOCK_WAIT_TIME = Histogram(
    "player_lock_wait_seconds", 
    "Time spent waiting to acquire player locks"
)
PLAYER_LOCK_HOLD_TIME = Histogram(
    "player_lock_hold_seconds", 
    "Time player locks are held"
)
VALKEY_TRANSACTION_DURATION = Histogram(
    "valkey_transaction_seconds", 
    "Duration of Valkey atomic transactions"
)
LOCK_CONTENTIONS = Counter(
    "lock_contentions_total", 
    "Number of times lock acquisition was delayed due to contention"
)
ACTIVE_PLAYER_LOCKS = Gauge(
    "active_player_locks", 
    "Number of currently active player locks"
)
DEADLOCK_DETECTIONS = Counter(
    "deadlock_detections_total", 
    "Number of potential deadlocks detected and avoided"
)

# Atomic Operation Metrics
ATOMIC_OPERATIONS_TOTAL = Counter(
    "atomic_operations_total",
    "Total number of atomic operations attempted",
    ["operation_type", "status"]  # status: success, failure, fallback
)
ATOMIC_OPERATION_DURATION = Histogram(
    "atomic_operation_seconds",
    "Duration of atomic operations",
    ["operation_type"]
)
ATOMIC_FALLBACK_RATE = Counter(
    "atomic_fallbacks_total",
    "Number of times atomic operations fell back to direct operations",
    ["operation_type", "reason"]
)


class LockType(Enum):
    """Types of locks for categorizing operations."""
    INVENTORY = "inventory"
    EQUIPMENT = "equipment" 
    POSITION = "position"
    HP = "hp"
    SKILLS = "skills"
    GROUND_ITEMS = "ground_items"
    CONNECTION = "connection"
    GAME_LOOP = "game_loop"


@dataclass
class LockAcquisitionContext:
    """Context information for lock acquisition."""
    player_id: int
    lock_type: LockType
    operation_name: str
    timeout: float = 30.0
    acquired_at: Optional[float] = None
    released_at: Optional[float] = None
    wait_time: Optional[float] = None


class PlayerLockManager:
    """
    Manages per-player locks to prevent race conditions in player state modifications.
    
    Features:
    - Per-player locking with deadlock prevention
    - Lock timeout handling
    - Performance monitoring
    - Multiple player lock acquisition with consistent ordering
    """
    
    def __init__(self):
        self._player_locks: Dict[int, asyncio.Lock] = {}
        self._lock_creation_lock = asyncio.Lock()
        self._active_contexts: Dict[int, Set[LockAcquisitionContext]] = {}
        self._lock_timeout = 30.0  # Default timeout in seconds
        
    async def _get_or_create_player_lock(self, player_id: int) -> asyncio.Lock:
        """Get existing lock or create new one for player (thread-safe)."""
        if player_id not in self._player_locks:
            async with self._lock_creation_lock:
                # Double-check pattern
                if player_id not in self._player_locks:
                    self._player_locks[player_id] = asyncio.Lock()
                    logger.debug(
                        "Created new player lock", 
                        extra={"player_id": player_id}
                    )
        
        return self._player_locks[player_id]
    
    @asynccontextmanager
    async def acquire_player_lock(
        self, 
        player_id: int, 
        lock_type: LockType, 
        operation_name: str,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[LockAcquisitionContext, None]:
        """
        Acquire a lock for a specific player with monitoring and timeout.
        
        Args:
            player_id: The player to lock
            lock_type: Type of operation requiring lock
            operation_name: Descriptive name for monitoring
            timeout: Lock acquisition timeout (uses default if None)
        
        Raises:
            asyncio.TimeoutError: If lock cannot be acquired within timeout
        """
        context = LockAcquisitionContext(
            player_id=player_id,
            lock_type=lock_type,
            operation_name=operation_name,
            timeout=timeout or self._lock_timeout
        )
        
        start_time = time.time()
        lock = await self._get_or_create_player_lock(player_id)
        
        # Track active contexts for deadlock detection
        if player_id not in self._active_contexts:
            self._active_contexts[player_id] = set()
        
        try:
            # Check for potential deadlock (same operation already running for player)
            for active_context in self._active_contexts[player_id]:
                if active_context.operation_name == operation_name:
                    DEADLOCK_DETECTIONS.inc()
                    logger.warning(
                        "Potential deadlock detected - same operation already active",
                        extra={
                            "player_id": player_id,
                            "operation": operation_name,
                            "lock_type": lock_type.value
                        }
                    )
            
            # Acquire lock with timeout
            acquired = False
            try:
                await asyncio.wait_for(lock.acquire(), timeout=context.timeout)
                acquired = True
                
                context.acquired_at = time.time()
                context.wait_time = context.acquired_at - start_time
                
                # Update metrics
                PLAYER_LOCK_ACQUISITIONS.labels(
                    player_id=str(player_id), 
                    operation_type=lock_type.value
                ).inc()
                PLAYER_LOCK_WAIT_TIME.observe(context.wait_time)
                ACTIVE_PLAYER_LOCKS.inc()
                
                # Track contention if we had to wait
                if context.wait_time > 0.001:  # 1ms threshold
                    LOCK_CONTENTIONS.inc()
                
                self._active_contexts[player_id].add(context)
                
                logger.debug(
                    "Player lock acquired",
                    extra={
                        "player_id": player_id,
                        "operation": operation_name,
                        "lock_type": lock_type.value,
                        "wait_time": context.wait_time
                    }
                )
                
                yield context
                
            except asyncio.TimeoutError:
                logger.error(
                    "Failed to acquire player lock within timeout",
                    extra={
                        "player_id": player_id,
                        "operation": operation_name,
                        "lock_type": lock_type.value,
                        "timeout": context.timeout,
                        "traceback": traceback.format_exc()
                    }
                )
                raise
                
        finally:
            if acquired:
                context.released_at = time.time()
                hold_time = context.released_at - context.acquired_at
                
                PLAYER_LOCK_HOLD_TIME.observe(hold_time)
                ACTIVE_PLAYER_LOCKS.dec()
                
                self._active_contexts[player_id].discard(context)
                lock.release()
                
                logger.debug(
                    "Player lock released",
                    extra={
                        "player_id": player_id,
                        "operation": operation_name,
                        "lock_type": lock_type.value,
                        "hold_time": hold_time
                    }
                )
    
    @asynccontextmanager  
    async def acquire_multiple_player_locks(
        self,
        player_ids: List[int],
        lock_type: LockType,
        operation_name: str,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[List[LockAcquisitionContext], None]:
        """
        Acquire locks for multiple players in consistent order to prevent deadlocks.
        
        Args:
            player_ids: List of player IDs to lock (will be sorted)
            lock_type: Type of operation requiring locks
            operation_name: Descriptive name for monitoring
            timeout: Lock acquisition timeout per player
            
        Yields:
            List of lock contexts in player_id order
        """
        # Sort player IDs to ensure consistent lock ordering and prevent deadlocks
        sorted_player_ids = sorted(set(player_ids))
        
        if len(sorted_player_ids) != len(player_ids):
            logger.warning(
                "Duplicate player IDs detected in multi-lock request",
                extra={
                    "original_ids": player_ids,
                    "deduplicated_ids": sorted_player_ids,
                    "operation": operation_name
                }
            )
        
        contexts = []
        acquired_locks = []
        
        try:
            # Acquire locks in order
            for player_id in sorted_player_ids:
                async with self.acquire_player_lock(
                    player_id, lock_type, f"{operation_name}_multi", timeout
                ) as context:
                    contexts.append(context)
                    acquired_locks.append(context)
                    
                    # Keep reference to prevent early release
                    if len(acquired_locks) < len(sorted_player_ids):
                        continue
                        
            logger.debug(
                "Multiple player locks acquired",
                extra={
                    "player_ids": sorted_player_ids,
                    "operation": operation_name,
                    "lock_count": len(contexts)
                }
            )
            
            yield contexts
            
        except Exception as e:
            logger.error(
                "Error during multiple player lock acquisition",
                extra={
                    "player_ids": sorted_player_ids,
                    "operation": operation_name,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }
            )
            raise
    
    def get_lock_stats(self) -> Dict[str, Any]:
        """Get current lock statistics for monitoring."""
        return {
            "total_player_locks": len(self._player_locks),
            "active_contexts": sum(len(contexts) for contexts in self._active_contexts.values()),
            "players_with_active_locks": len([pid for pid, contexts in self._active_contexts.items() if contexts])
        }
    
    async def cleanup_player_lock(self, player_id: int) -> bool:
        """
        Clean up lock resources for a disconnected player.
        
        Should be called when a player disconnects to prevent memory leaks.
        Only removes the lock if it's not currently held.
        
        Args:
            player_id: The player ID to clean up
            
        Returns:
            True if lock was cleaned up, False if lock was held or didn't exist
        """
        async with self._lock_creation_lock:
            # Check if lock exists
            if player_id not in self._player_locks:
                return False
            
            lock = self._player_locks[player_id]
            
            # Only remove if not currently held
            if lock.locked():
                logger.warning(
                    "Cannot cleanup player lock - still held",
                    extra={"player_id": player_id}
                )
                return False
            
            # Clean up lock and active contexts
            del self._player_locks[player_id]
            self._active_contexts.pop(player_id, None)
            
            logger.debug(
                "Player lock cleaned up",
                extra={"player_id": player_id}
            )
            return True
    
    async def cleanup_all_stale_locks(self, active_player_ids: Set[int]) -> int:
        """
        Clean up locks for players who are no longer online.
        
        Args:
            active_player_ids: Set of currently online player IDs
            
        Returns:
            Number of locks cleaned up
        """
        async with self._lock_creation_lock:
            stale_ids = [
                pid for pid in self._player_locks.keys() 
                if pid not in active_player_ids and not self._player_locks[pid].locked()
            ]
            
            cleaned = 0
            for player_id in stale_ids:
                del self._player_locks[player_id]
                self._active_contexts.pop(player_id, None)
                cleaned += 1
            
            if cleaned > 0:
                logger.info(
                    "Cleaned up stale player locks",
                    extra={"cleaned_count": cleaned, "remaining_locks": len(self._player_locks)}
                )
            
            return cleaned


class ValkeyAtomicOperations:
    """
    Provides atomic Valkey operations using transactions to ensure consistency.
    Includes retry logic and timeout handling for improved robustness.
    """
    
    def __init__(self, valkey_client: GlideClient, max_retries: int = 3, base_retry_delay: float = 0.01):
        self.valkey = valkey_client
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay  # Base delay for exponential backoff
    
    @asynccontextmanager
    async def transaction(self, description: str = "valkey_transaction") -> AsyncGenerator[GlideClient, None]:
        """
        Execute Valkey operations within a transaction (MULTI/EXEC) with retry logic.
        
        Args:
            description: Description for monitoring purposes
            
        Yields:
            Valkey client configured for transaction mode
        """
        start_time = time.time()
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                # Add delay for retries (exponential backoff)
                if attempt > 0:
                    delay = self.base_retry_delay * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
                    logger.debug(
                        "Retrying Valkey transaction",
                        extra={
                            "description": description,
                            "attempt": attempt + 1,
                            "delay": delay
                        }
                    )
                
                # Start Valkey transaction
                transaction_client = self.valkey.multi()
                
                logger.debug(
                    "Valkey transaction started",
                    extra={
                        "description": description,
                        "attempt": attempt + 1
                    }
                )
                
                yield transaction_client
                
                # Execute transaction
                results = await transaction_client.exec()
                
                duration = time.time() - start_time
                VALKEY_TRANSACTION_DURATION.observe(duration)
                
                logger.debug(
                    "Valkey transaction completed",
                    extra={
                        "description": description,
                        "duration": duration,
                        "operations_count": len(results) if results else 0,
                        "attempts": attempt + 1
                    }
                )
                
                # Success - exit retry loop
                return
                
            except Exception as e:
                last_error = e
                duration = time.time() - start_time
                
                if attempt < self.max_retries:
                    logger.warning(
                        "Valkey transaction failed, retrying",
                        extra={
                            "description": description,
                            "duration": duration,
                            "error": str(e),
                            "attempt": attempt + 1,
                            "max_retries": self.max_retries
                        }
                    )
                    continue
                else:
                    # Final attempt failed
                    logger.error(
                        "Valkey transaction failed after all retries",
                        extra={
                            "description": description,
                            "duration": duration,
                            "error": str(e),
                            "total_attempts": attempt + 1,
                            "traceback": traceback.format_exc()
                        }
                    )
                    raise
        
        # This should never be reached due to the raise above, but just in case
        if last_error:
            raise last_error
    
    async def atomic_player_update(
        self, 
        player_id: int, 
        operations: List[Callable],
        description: str = "player_update"
    ) -> List[Any]:
        """
        Execute multiple player state updates atomically.
        
        Args:
            player_id: Player being updated
            operations: List of async functions that take a transaction client
            description: Description for monitoring
            
        Returns:
            Results from all operations
        """
        async with self.transaction(f"{description}_player_{player_id}") as tx:
            results = []
            for operation in operations:
                result = await operation(tx)
                results.append(result)
            return results


# Singleton instances (initialized by application startup)
_player_lock_manager: Optional[PlayerLockManager] = None
_valkey_atomic_operations: Optional[ValkeyAtomicOperations] = None


def initialize_concurrency_infrastructure(valkey_client: GlideClient, 
                                         transaction_max_retries: int = 3, 
                                         transaction_retry_delay: float = 0.01) -> None:
    """Initialize the concurrency infrastructure. Called during app startup."""
    global _player_lock_manager, _valkey_atomic_operations
    
    _player_lock_manager = PlayerLockManager()
    _valkey_atomic_operations = ValkeyAtomicOperations(
        valkey_client, 
        max_retries=transaction_max_retries,
        base_retry_delay=transaction_retry_delay
    )
    
    logger.info(
        "Concurrency infrastructure initialized",
        extra={
            "features": ["player_locking", "valkey_transactions"], 
            "transaction_max_retries": transaction_max_retries,
            "transaction_retry_delay": transaction_retry_delay
        }
    )


def get_player_lock_manager() -> PlayerLockManager:
    """Get the global player lock manager instance."""
    if _player_lock_manager is None:
        raise RuntimeError("Concurrency infrastructure not initialized. Call initialize_concurrency_infrastructure() first.")
    return _player_lock_manager


def get_valkey_atomic_operations() -> ValkeyAtomicOperations:
    """Get the global Valkey atomic operations instance.""" 
    if _valkey_atomic_operations is None:
        raise RuntimeError("Concurrency infrastructure not initialized. Call initialize_concurrency_infrastructure() first.")
    return _valkey_atomic_operations