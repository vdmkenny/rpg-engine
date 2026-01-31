"""
Atomic operations for GameStateManager using Redis transactions.

Provides thread-safe, atomic operations for complex game state modifications
that require consistency across multiple operations.
"""

from typing import Dict, List, Optional, Any, Tuple, Callable
from contextlib import asynccontextmanager
import json
import time
import traceback

from server.src.core.logging_config import get_logger
from server.src.core.concurrency import get_valkey_atomic_operations

# Import metrics for monitoring atomic operations
try:
    from server.src.core.concurrency import (
        ATOMIC_OPERATIONS_TOTAL,
        ATOMIC_OPERATION_DURATION, 
        ATOMIC_FALLBACK_RATE
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = get_logger(__name__)


def _track_atomic_operation(operation_type: str, success: bool, duration: float, fallback_reason: Optional[str] = None):
    """
    Track atomic operation metrics for monitoring and performance analysis.
    
    Args:
        operation_type: Type of atomic operation (e.g., 'inventory_move', 'equipment_change')
        success: Whether the atomic operation succeeded
        duration: Time taken for the operation in seconds
        fallback_reason: Reason for fallback if operation failed
    """
    if not METRICS_AVAILABLE:
        return
    
    try:
        # Track total operations
        status = "success" if success else "failure"
        ATOMIC_OPERATIONS_TOTAL.labels(operation_type=operation_type, status=status).inc()
        
        # Track operation duration
        ATOMIC_OPERATION_DURATION.labels(operation_type=operation_type).observe(duration)
        
        # Track fallback if applicable
        if not success and fallback_reason:
            ATOMIC_FALLBACK_RATE.labels(operation_type=operation_type, reason=fallback_reason).inc()
            
    except Exception as e:
        logger.warning(f"Failed to track atomic operation metrics: {e}")


class GSMAtomicOperations:
    """
    Atomic operations for GameStateManager using Redis MULTI/EXEC transactions.
    
    These operations ensure that complex state changes happen atomically,
    preventing race conditions and maintaining data consistency.
    """
    
    def __init__(self, gsm):
        self.gsm = gsm
        self._valkey_ops = None
    
    def _get_valkey_ops(self):
        """Lazy initialization of Valkey operations."""
        if self._valkey_ops is None:
            self._valkey_ops = get_valkey_atomic_operations()
        return self._valkey_ops
    
    # =========================================================================
    # INVENTORY ATOMIC OPERATIONS
    # =========================================================================
    


    # =========================================================================
    # EQUIPMENT ATOMIC OPERATIONS  
    # =========================================================================
    
    
    # =========================================================================
    # HP AND POSITION ATOMIC OPERATIONS
    # =========================================================================
    # HP AND POSITION ATOMIC OPERATIONS
    # =========================================================================
    
    async def atomic_hp_update(
        self,
        player_id: int,
        new_hp: int,
        new_max_hp: Optional[int] = None,
        equipment_changes: Optional[Dict[str, Dict]] = None
    ) -> bool:
        """
        Atomically update player HP and related equipment changes.
        
        Args:
            player_id: Player to update
            new_hp: New current HP
            new_max_hp: New maximum HP (if changed due to equipment)
            equipment_changes: Equipment changes affecting HP
            
        Returns:
            True if update was successful, False otherwise
        """
        valkey_ops = self._get_valkey_ops()
        
        async def _hp_operation(tx):
            player_key = f"player:{player_id}"
            
            # Get current player state
            current_data = await self.gsm.valkey.hgetall(player_key)
            if not current_data:
                return False
                
            player_data = {}
            for key_bytes, value_bytes in current_data.items():
                key = key_bytes.decode()
                player_data[key] = value_bytes.decode()
            
            # Update HP values
            player_data["current_hp"] = str(new_hp)
            if new_max_hp is not None:
                player_data["max_hp"] = str(new_max_hp)
            
            # Write updated player state
            await tx.hset(player_key, player_data)
            
            # Update equipment if changes provided
            if equipment_changes:
                equipment_key = f"equipment:{player_id}"
                for slot, equipment_data in equipment_changes.items():
                    await tx.hset(equipment_key, {slot: json.dumps(equipment_data)})
                await tx.sadd("dirty:equipment", [str(player_id)])
            
            # Mark position as dirty (for HP sync)
            await tx.sadd("dirty:position", [str(player_id)])
            
            return True
        
        try:
            async with valkey_ops.transaction(f"hp_update_player_{player_id}") as tx:
                return await _hp_operation(tx)
                
        except Exception as e:
            logger.error(
                "Atomic HP update failed",
                extra={
                    "player_id": player_id,
                    "new_hp": new_hp,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            return False
    
    async def atomic_position_update(
        self,
        player_id: int,
        x: int,
        y: int,
        map_id: str
    ) -> bool:
        """
        Atomically update player position.
        
        Args:
            player_id: Player to update
            x: New X coordinate
            y: New Y coordinate  
            map_id: New map ID
            
        Returns:
            True if update was successful, False otherwise
        """
        valkey_ops = self._get_valkey_ops()
        
        async def _position_operation(tx):
            player_key = f"player:{player_id}"
            
            # Get current player state
            current_data = await self.gsm.valkey.hgetall(player_key)
            if not current_data:
                return False
                
            player_data = {}
            for key_bytes, value_bytes in current_data.items():
                key = key_bytes.decode()
                player_data[key] = value_bytes.decode()
            
            # Update position
            player_data["x"] = str(x)
            player_data["y"] = str(y)  
            player_data["map_id"] = map_id
            
            # Write updated state
            await tx.hset(player_key, player_data)
            
            # Mark as dirty for database sync
            await tx.sadd("dirty:position", [str(player_id)])
            
            return True
        
        try:
            async with valkey_ops.transaction(f"position_update_player_{player_id}") as tx:
                return await _position_operation(tx)
                
        except Exception as e:
            logger.error(
                "Atomic position update failed",
                extra={
                    "player_id": player_id,
                    "x": x,
                    "y": y,
                    "map_id": map_id,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            return False
