"""
Atomic Item Operations

Provides transaction-safe item operations that can be composed into complex
multi-step operations while maintaining data consistency via GameStateManager.
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid

from server.src.core.logging_config import get_logger
from server.src.services.game_state_manager import get_game_state_manager

logger = get_logger(__name__)


@dataclass
class AtomicOperation:
    """Represents a single atomic operation with rollback capability."""
    operation_id: str
    operation_type: str
    execute_params: Dict[str, Any]
    rollback_params: Optional[Dict[str, Any]] = None
    executed: bool = False
    can_rollback: bool = True


@dataclass
class AtomicTransaction:
    """Represents a transaction containing multiple atomic operations."""
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    operations: List[AtomicOperation] = field(default_factory=list)
    completed: bool = False
    failed: bool = False
    failure_reason: Optional[str] = None
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


class AtomicOperationExecutor:
    """Executes atomic operations with rollback support."""
    
    def __init__(self):
        self._active_transactions: Dict[str, AtomicTransaction] = {}
    
    async def begin_transaction(self) -> str:
        """Begin a new atomic transaction."""
        transaction = AtomicTransaction()
        self._active_transactions[transaction.transaction_id] = transaction
        
        logger.debug(
            "Started atomic transaction",
            extra={"transaction_id": transaction.transaction_id}
        )
        return transaction.transaction_id
    
    async def add_operation(
        self,
        transaction_id: str,
        operation_type: str,
        execute_params: Dict[str, Any],
        rollback_params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add an operation to a transaction."""
        if transaction_id not in self._active_transactions:
            raise ValueError(f"Transaction {transaction_id} not found")
        
        transaction = self._active_transactions[transaction_id]
        if transaction.completed or transaction.failed:
            raise ValueError(f"Transaction {transaction_id} is already finalized")
        
        operation = AtomicOperation(
            operation_id=str(uuid.uuid4()),
            operation_type=operation_type,
            execute_params=execute_params,
            rollback_params=rollback_params,
        )
        
        transaction.operations.append(operation)
        return operation.operation_id
    
    async def execute_transaction(self, transaction_id: str) -> bool:
        """Execute all operations in a transaction."""
        if transaction_id not in self._active_transactions:
            raise ValueError(f"Transaction {transaction_id} not found")
        
        transaction = self._active_transactions[transaction_id]
        if transaction.completed or transaction.failed:
            raise ValueError(f"Transaction {transaction_id} is already finalized")
        
        gsm = get_game_state_manager()
        executed_operations = []
        
        try:
            # Execute all operations in order
            for operation in transaction.operations:
                success = await self._execute_single_operation(gsm, operation)
                if not success:
                    transaction.failed = True
                    transaction.failure_reason = f"Operation {operation.operation_id} failed"
                    
                    # Rollback executed operations
                    await self._rollback_operations(gsm, executed_operations)
                    return False
                
                executed_operations.append(operation)
                operation.executed = True
            
            # All operations succeeded
            transaction.completed = True
            logger.info(
                "Atomic transaction completed successfully",
                extra={
                    "transaction_id": transaction_id,
                    "operation_count": len(transaction.operations),
                }
            )
            return True
            
        except Exception as e:
            transaction.failed = True
            transaction.failure_reason = str(e)
            
            # Rollback executed operations
            await self._rollback_operations(gsm, executed_operations)
            
            logger.error(
                "Atomic transaction failed with exception",
                extra={
                    "transaction_id": transaction_id,
                    "error": str(e),
                    "executed_operations": len(executed_operations),
                }
            )
            return False
        
        finally:
            # Clean up transaction
            if transaction_id in self._active_transactions:
                del self._active_transactions[transaction_id]
    
    async def _execute_single_operation(
        self, gsm, operation: AtomicOperation
    ) -> bool:
        """Execute a single atomic operation."""
        try:
            if operation.operation_type == "set_inventory_slot":
                await gsm.set_inventory_slot(
                    operation.execute_params["player_id"],
                    operation.execute_params["slot"],
                    operation.execute_params["item_id"],
                    operation.execute_params["quantity"],
                    operation.execute_params.get("durability"),
                )
            
            elif operation.operation_type == "delete_inventory_slot":
                await gsm.delete_inventory_slot(
                    operation.execute_params["player_id"],
                    operation.execute_params["slot"],
                )
            
            elif operation.operation_type == "set_equipment_slot":
                await gsm.set_equipment_slot(
                    operation.execute_params["player_id"],
                    operation.execute_params["slot"],
                    operation.execute_params["item_id"],
                    operation.execute_params["quantity"],
                    operation.execute_params.get("durability"),
                )
            
            elif operation.operation_type == "delete_equipment_slot":
                await gsm.delete_equipment_slot(
                    operation.execute_params["player_id"],
                    operation.execute_params["slot"],
                )
            
            elif operation.operation_type == "add_ground_item":
                await gsm.add_ground_item(
                    operation.execute_params["map_id"],
                    operation.execute_params["x"],
                    operation.execute_params["y"],
                    operation.execute_params["item_id"],
                    operation.execute_params["quantity"],
                    operation.execute_params.get("durability", 1.0),
                    operation.execute_params.get("dropped_by_player_id"),
                )
            
            elif operation.operation_type == "remove_ground_item":
                await gsm.remove_ground_item(
                    operation.execute_params["ground_item_id"],
                    operation.execute_params["map_id"],
                )
            
            elif operation.operation_type == "update_player_hp":
                await gsm.update_player_hp(
                    operation.execute_params["player_id"],
                    operation.execute_params["new_hp"],
                )
            
            else:
                logger.error(
                    "Unknown operation type",
                    extra={
                        "operation_id": operation.operation_id,
                        "operation_type": operation.operation_type,
                    }
                )
                return False
            
            logger.debug(
                "Executed atomic operation",
                extra={
                    "operation_id": operation.operation_id,
                    "operation_type": operation.operation_type,
                }
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to execute atomic operation",
                extra={
                    "operation_id": operation.operation_id,
                    "operation_type": operation.operation_type,
                    "error": str(e),
                }
            )
            return False
    
    async def _rollback_operations(
        self, gsm, operations: List[AtomicOperation]
    ) -> None:
        """Rollback a list of operations in reverse order."""
        for operation in reversed(operations):
            if not operation.can_rollback or not operation.rollback_params:
                logger.warning(
                    "Cannot rollback operation",
                    extra={
                        "operation_id": operation.operation_id,
                        "can_rollback": operation.can_rollback,
                        "has_rollback_params": operation.rollback_params is not None,
                    }
                )
                continue
            
            try:
                # Create rollback operation and execute it
                rollback_op = AtomicOperation(
                    operation_id=f"rollback_{operation.operation_id}",
                    operation_type=operation.rollback_params["operation_type"],
                    execute_params=operation.rollback_params["params"],
                    can_rollback=False,  # Don't rollback rollbacks
                )
                
                await self._execute_single_operation(gsm, rollback_op)
                
                logger.debug(
                    "Rolled back operation",
                    extra={
                        "original_operation_id": operation.operation_id,
                        "rollback_operation_id": rollback_op.operation_id,
                    }
                )
                
            except Exception as e:
                logger.error(
                    "Failed to rollback operation",
                    extra={
                        "operation_id": operation.operation_id,
                        "error": str(e),
                    }
                )


# Singleton instance for the atomic executor
_atomic_executor = None


def get_atomic_executor() -> AtomicOperationExecutor:
    """Get the singleton atomic operation executor."""
    global _atomic_executor
    if _atomic_executor is None:
        _atomic_executor = AtomicOperationExecutor()
    return _atomic_executor
