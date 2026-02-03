"""
Tests for item_management/atomic_operations.py.

Tests atomic transaction handling for item operations with rollback support.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from server.src.services.item_management.atomic_operations import (
    AtomicOperation,
    AtomicTransaction,
    AtomicOperationExecutor,
    get_atomic_executor,
)
from server.src.core.items import EquipmentSlot


class TestAtomicOperationDataclass:
    """Tests for AtomicOperation dataclass."""

    def test_operation_defaults(self):
        """Test that AtomicOperation has correct defaults."""
        operation = AtomicOperation(
            operation_id="test-op-1",
            operation_type="set_inventory_slot",
            execute_params={"player_id": 1, "slot": 0},
        )
        
        assert operation.operation_id == "test-op-1"
        assert operation.operation_type == "set_inventory_slot"
        assert operation.execute_params == {"player_id": 1, "slot": 0}
        assert operation.rollback_params is None
        assert operation.executed is False
        assert operation.can_rollback is True

    def test_operation_with_rollback_params(self):
        """Test AtomicOperation with rollback parameters."""
        operation = AtomicOperation(
            operation_id="test-op-2",
            operation_type="set_inventory_slot",
            execute_params={"player_id": 1, "slot": 0, "item_id": 5, "quantity": 1},
            rollback_params={
                "operation_type": "delete_inventory_slot",
                "params": {"player_id": 1, "slot": 0},
            },
            can_rollback=True,
        )
        
        assert operation.rollback_params is not None
        assert operation.rollback_params["operation_type"] == "delete_inventory_slot"

    def test_operation_without_rollback(self):
        """Test AtomicOperation that cannot be rolled back."""
        operation = AtomicOperation(
            operation_id="no-rollback-op",
            operation_type="update_player_hp",
            execute_params={"player_id": 1, "new_hp": 50},
            can_rollback=False,
        )
        
        assert operation.can_rollback is False


class TestAtomicTransactionDataclass:
    """Tests for AtomicTransaction dataclass."""

    def test_transaction_id_generated(self):
        """Test that transaction ID is auto-generated."""
        transaction = AtomicTransaction()
        
        assert transaction.transaction_id is not None
        assert len(transaction.transaction_id) > 0
        # Should be valid UUID format
        uuid.UUID(transaction.transaction_id)

    def test_transaction_defaults(self):
        """Test that AtomicTransaction has correct defaults."""
        transaction = AtomicTransaction()
        
        assert transaction.operations == []
        assert transaction.completed is False
        assert transaction.failed is False
        assert transaction.failure_reason is None

    def test_transaction_created_timestamp(self):
        """Test that created_at timestamp is set."""
        before = datetime.now(timezone.utc).timestamp()
        transaction = AtomicTransaction()
        after = datetime.now(timezone.utc).timestamp()
        
        assert before <= transaction.created_at <= after

    def test_transaction_with_custom_id(self):
        """Test AtomicTransaction with custom transaction ID."""
        custom_id = "custom-tx-12345"
        transaction = AtomicTransaction(transaction_id=custom_id)
        
        assert transaction.transaction_id == custom_id


class TestAtomicOperationExecutorInit:
    """Tests for AtomicOperationExecutor initialization."""

    def test_initialization(self):
        """Test executor initializes with empty transactions dict."""
        executor = AtomicOperationExecutor()
        
        assert executor._active_transactions == {}

    def test_empty_active_transactions(self):
        """Test that new executor has no active transactions."""
        executor = AtomicOperationExecutor()
        
        assert len(executor._active_transactions) == 0


class TestBeginTransaction:
    """Tests for AtomicOperationExecutor.begin_transaction()"""

    @pytest.mark.asyncio
    async def test_begin_transaction_returns_id(self):
        """Test that begin_transaction returns a transaction ID."""
        executor = AtomicOperationExecutor()
        
        tx_id = await executor.begin_transaction()
        
        assert tx_id is not None
        assert len(tx_id) > 0

    @pytest.mark.asyncio
    async def test_begin_transaction_stores_transaction(self):
        """Test that transaction is stored in active transactions."""
        executor = AtomicOperationExecutor()
        
        tx_id = await executor.begin_transaction()
        
        assert tx_id in executor._active_transactions
        assert isinstance(executor._active_transactions[tx_id], AtomicTransaction)

    @pytest.mark.asyncio
    async def test_multiple_concurrent_transactions(self):
        """Test that multiple transactions can be active simultaneously."""
        executor = AtomicOperationExecutor()
        
        tx_id_1 = await executor.begin_transaction()
        tx_id_2 = await executor.begin_transaction()
        tx_id_3 = await executor.begin_transaction()
        
        assert tx_id_1 != tx_id_2 != tx_id_3
        assert len(executor._active_transactions) == 3


class TestAddOperation:
    """Tests for AtomicOperationExecutor.add_operation()"""

    @pytest.mark.asyncio
    async def test_add_operation_success(self):
        """Test adding an operation to a transaction."""
        executor = AtomicOperationExecutor()
        tx_id = await executor.begin_transaction()
        
        op_id = await executor.add_operation(
            tx_id,
            operation_type="set_inventory_slot",
            execute_params={"player_id": 1, "slot": 0, "item_id": 5, "quantity": 1},
        )
        
        assert op_id is not None
        transaction = executor._active_transactions[tx_id]
        assert len(transaction.operations) == 1
        assert transaction.operations[0].operation_type == "set_inventory_slot"

    @pytest.mark.asyncio
    async def test_add_operation_to_unknown_transaction(self):
        """Test that adding operation to unknown transaction raises error."""
        executor = AtomicOperationExecutor()
        
        with pytest.raises(ValueError, match="not found"):
            await executor.add_operation(
                "nonexistent-tx",
                operation_type="set_inventory_slot",
                execute_params={"player_id": 1, "slot": 0},
            )

    @pytest.mark.asyncio
    async def test_add_operation_to_completed_transaction(self, game_state_managers):
        """Test that adding operation to completed transaction raises error."""
        executor = AtomicOperationExecutor()
        tx_id = await executor.begin_transaction()
        
        # Mark as completed
        executor._active_transactions[tx_id].completed = True
        
        with pytest.raises(ValueError, match="already finalized"):
            await executor.add_operation(
                tx_id,
                operation_type="set_inventory_slot",
                execute_params={"player_id": 1, "slot": 0},
            )

    @pytest.mark.asyncio
    async def test_add_operation_to_failed_transaction(self):
        """Test that adding operation to failed transaction raises error."""
        executor = AtomicOperationExecutor()
        tx_id = await executor.begin_transaction()
        
        # Mark as failed
        executor._active_transactions[tx_id].failed = True
        
        with pytest.raises(ValueError, match="already finalized"):
            await executor.add_operation(
                tx_id,
                operation_type="set_inventory_slot",
                execute_params={"player_id": 1, "slot": 0},
            )

    @pytest.mark.asyncio
    async def test_add_multiple_operations(self):
        """Test adding multiple operations to a transaction."""
        executor = AtomicOperationExecutor()
        tx_id = await executor.begin_transaction()
        
        await executor.add_operation(tx_id, "set_inventory_slot", {"player_id": 1, "slot": 0, "item_id": 1, "quantity": 1})
        await executor.add_operation(tx_id, "set_inventory_slot", {"player_id": 1, "slot": 1, "item_id": 2, "quantity": 5})
        await executor.add_operation(tx_id, "delete_inventory_slot", {"player_id": 1, "slot": 2})
        
        transaction = executor._active_transactions[tx_id]
        assert len(transaction.operations) == 3

    @pytest.mark.asyncio
    async def test_add_operation_with_rollback_params(self):
        """Test adding operation with rollback parameters."""
        executor = AtomicOperationExecutor()
        tx_id = await executor.begin_transaction()
        
        op_id = await executor.add_operation(
            tx_id,
            operation_type="set_inventory_slot",
            execute_params={"player_id": 1, "slot": 0, "item_id": 5, "quantity": 1},
            rollback_params={
                "operation_type": "delete_inventory_slot",
                "params": {"player_id": 1, "slot": 0},
            },
        )
        
        transaction = executor._active_transactions[tx_id]
        assert transaction.operations[0].rollback_params is not None


class TestExecuteTransaction:
    """Tests for AtomicOperationExecutor.execute_transaction()"""

    @pytest.mark.asyncio
    async def test_execute_unknown_transaction(self):
        """Test executing unknown transaction raises error."""
        executor = AtomicOperationExecutor()
        
        with pytest.raises(ValueError, match="not found"):
            await executor.execute_transaction("nonexistent-tx")

    @pytest.mark.asyncio
    async def test_execute_already_completed(self):
        """Test executing already completed transaction raises error."""
        executor = AtomicOperationExecutor()
        tx_id = await executor.begin_transaction()
        executor._active_transactions[tx_id].completed = True
        
        with pytest.raises(ValueError, match="already finalized"):
            await executor.execute_transaction(tx_id)

    @pytest.mark.asyncio
    async def test_execute_already_failed(self):
        """Test executing already failed transaction raises error."""
        executor = AtomicOperationExecutor()
        tx_id = await executor.begin_transaction()
        executor._active_transactions[tx_id].failed = True
        
        with pytest.raises(ValueError, match="already finalized"):
            await executor.execute_transaction(tx_id)

    @pytest.mark.asyncio
    async def test_execute_empty_transaction(self, game_state_managers):
        """Test executing transaction with no operations succeeds."""
        executor = AtomicOperationExecutor()
        tx_id = await executor.begin_transaction()
        
        with patch('server.src.services.item_management.atomic_operations.get_game_state_manager', return_value=gsm):
            result = await executor.execute_transaction(tx_id)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_cleans_up_transaction(self, game_state_managers):
        """Test that transaction is removed after execution."""
        executor = AtomicOperationExecutor()
        tx_id = await executor.begin_transaction()
        
        with patch('server.src.services.item_management.atomic_operations.get_game_state_manager', return_value=gsm):
            await executor.execute_transaction(tx_id)
        
        assert tx_id not in executor._active_transactions

    @pytest.mark.asyncio
    async def test_execute_success_with_operations(self, game_state_managers, create_test_player):
        """Test executing transaction with successful operations."""
        player = await create_test_player("atomic_test_player", "password123")
        executor = AtomicOperationExecutor()
        tx_id = await executor.begin_transaction()
        
        # Add a valid operation
        await executor.add_operation(
            tx_id,
            operation_type="set_inventory_slot",
            execute_params={
                "player_id": player.id,
                "slot": 0,
                "item_id": 1,
                "quantity": 5,
                "durability": 1.0,
            },
        )
        
        with patch('server.src.services.item_management.atomic_operations.get_game_state_manager', return_value=gsm):
            result = await executor.execute_transaction(tx_id)
        
        assert result is True


class TestExecuteSingleOperation:
    """Tests for AtomicOperationExecutor._execute_single_operation()"""

    @pytest.mark.asyncio
    async def test_execute_set_inventory_slot(self, game_state_managers, create_test_player):
        """Test executing set_inventory_slot operation."""
        player = await create_test_player("inv_slot_test", "password123")
        executor = AtomicOperationExecutor()
        
        operation = AtomicOperation(
            operation_id="test-set-inv",
            operation_type="set_inventory_slot",
            execute_params={
                "player_id": player.id,
                "slot": 0,
                "item_id": 1,
                "quantity": 10,
                "durability": 1.0,
            },
        )
        
        result = await executor._execute_single_operation(gsm, operation)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_delete_inventory_slot(self, game_state_managers, create_test_player):
        """Test executing delete_inventory_slot operation."""
        player = await create_test_player("del_inv_test", "password123")
        executor = AtomicOperationExecutor()
        
        # First add an item
        await gsm.set_inventory_slot(player.id, 0, 1, 5, 1.0)
        
        operation = AtomicOperation(
            operation_id="test-del-inv",
            operation_type="delete_inventory_slot",
            execute_params={"player_id": player.id, "slot": 0},
        )
        
        result = await executor._execute_single_operation(gsm, operation)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_set_equipment_slot(self, game_state_managers, create_test_player):
        """Test executing set_equipment_slot operation."""
        player = await create_test_player("equip_test", "password123")
        executor = AtomicOperationExecutor()
        
        operation = AtomicOperation(
            operation_id="test-set-equip",
            operation_type="set_equipment_slot",
            execute_params={
                "player_id": player.id,
                "slot": "weapon",
                "item_id": 1,
                "quantity": 1,
                "durability": 1.0,
            },
        )
        
        result = await executor._execute_single_operation(gsm, operation)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_delete_equipment_slot(self, game_state_managers, create_test_player):
        """Test executing delete_equipment_slot operation."""
        player = await create_test_player("del_equip_test", "password123")
        executor = AtomicOperationExecutor()
        
        # First equip an item
        await gsm.set_equipment_slot(player.id, EquipmentSlot.WEAPON, 1, 1, 1.0)
        
        operation = AtomicOperation(
            operation_id="test-del-equip",
            operation_type="delete_equipment_slot",
            execute_params={"player_id": player.id, "slot": "weapon"},
        )
        
        result = await executor._execute_single_operation(gsm, operation)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_update_player_hp(self, game_state_managers, create_test_player):
        """Test executing update_player_hp operation."""
        player = await create_test_player("hp_update_test", "password123")
        executor = AtomicOperationExecutor()
        
        # Player must be online for update_player_hp to work
        await gsm.set_player_full_state(player.id, 10, 10, "samplemap", 100, 100)
        
        operation = AtomicOperation(
            operation_id="test-hp-update",
            operation_type="update_player_hp",
            execute_params={"player_id": player.id, "new_hp": 75},
        )
        
        result = await executor._execute_single_operation(gsm, operation)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_unknown_operation_type(self, game_state_managers):
        """Test executing unknown operation type returns False."""
        executor = AtomicOperationExecutor()
        
        operation = AtomicOperation(
            operation_id="test-unknown",
            operation_type="unknown_operation_type",
            execute_params={"some": "params"},
        )
        
        result = await executor._execute_single_operation(gsm, operation)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_add_ground_item(self, game_state_managers):
        """Test executing add_ground_item operation."""
        executor = AtomicOperationExecutor()
        
        operation = AtomicOperation(
            operation_id="test-add-ground",
            operation_type="add_ground_item",
            execute_params={
                "map_id": "samplemap",
                "x": 10,
                "y": 10,
                "item_id": 1,
                "quantity": 5,
                "durability": 1.0,
                "dropped_by_player_id": None,
            },
        )
        
        result = await executor._execute_single_operation(gsm, operation)
        
        assert result is True


class TestRollbackOperations:
    """Tests for AtomicOperationExecutor._rollback_operations()"""

    @pytest.mark.asyncio
    async def test_rollback_skips_non_rollbackable(self, game_state_managers):
        """Test that operations marked can_rollback=False are skipped."""
        executor = AtomicOperationExecutor()
        
        operations = [
            AtomicOperation(
                operation_id="no-rollback-1",
                operation_type="set_inventory_slot",
                execute_params={"player_id": 1, "slot": 0},
                can_rollback=False,
                executed=True,
            ),
        ]
        
        # Should not raise any errors
        await executor._rollback_operations(gsm, operations)

    @pytest.mark.asyncio
    async def test_rollback_skips_no_rollback_params(self, game_state_managers):
        """Test that operations without rollback_params are skipped."""
        executor = AtomicOperationExecutor()
        
        operations = [
            AtomicOperation(
                operation_id="no-params-1",
                operation_type="set_inventory_slot",
                execute_params={"player_id": 1, "slot": 0},
                rollback_params=None,
                can_rollback=True,
                executed=True,
            ),
        ]
        
        # Should not raise any errors
        await executor._rollback_operations(gsm, operations)

    @pytest.mark.asyncio
    async def test_rollback_in_reverse_order(self, game_state_managers, create_test_player):
        """Test that rollback executes operations in reverse order."""
        player = await create_test_player("rollback_order_test", "password123")
        executor = AtomicOperationExecutor()
        
        rollback_order = []
        
        original_execute = executor._execute_single_operation
        
        async def track_execute(gsm_arg, operation):
            rollback_order.append(operation.operation_id)
            return True
        
        operations = [
            AtomicOperation(
                operation_id="op-1",
                operation_type="set_inventory_slot",
                execute_params={"player_id": player.id, "slot": 0, "item_id": 1, "quantity": 1},
                rollback_params={"operation_type": "delete_inventory_slot", "params": {"player_id": player.id, "slot": 0}},
                executed=True,
            ),
            AtomicOperation(
                operation_id="op-2",
                operation_type="set_inventory_slot",
                execute_params={"player_id": player.id, "slot": 1, "item_id": 2, "quantity": 1},
                rollback_params={"operation_type": "delete_inventory_slot", "params": {"player_id": player.id, "slot": 1}},
                executed=True,
            ),
            AtomicOperation(
                operation_id="op-3",
                operation_type="set_inventory_slot",
                execute_params={"player_id": player.id, "slot": 2, "item_id": 3, "quantity": 1},
                rollback_params={"operation_type": "delete_inventory_slot", "params": {"player_id": player.id, "slot": 2}},
                executed=True,
            ),
        ]
        
        executor._execute_single_operation = track_execute
        await executor._rollback_operations(gsm, operations)
        
        # Should be in reverse order (rollback_op-3, rollback_op-2, rollback_op-1)
        assert rollback_order[0] == "rollback_op-3"
        assert rollback_order[1] == "rollback_op-2"
        assert rollback_order[2] == "rollback_op-1"


class TestGetAtomicExecutor:
    """Tests for get_atomic_executor singleton function."""

    def test_returns_singleton(self):
        """Test that get_atomic_executor returns same instance."""
        # Reset the global to ensure clean state
        import server.src.services.item_management.atomic_operations as module
        module._atomic_executor = None
        
        executor1 = get_atomic_executor()
        executor2 = get_atomic_executor()
        
        assert executor1 is executor2

    def test_returns_executor_instance(self):
        """Test that get_atomic_executor returns AtomicOperationExecutor."""
        import server.src.services.item_management.atomic_operations as module
        module._atomic_executor = None
        
        executor = get_atomic_executor()
        
        assert isinstance(executor, AtomicOperationExecutor)


class TestTransactionWithRollback:
    """Integration tests for full transaction with rollback scenarios."""

    @pytest.mark.asyncio
    async def test_partial_failure_triggers_rollback(self, game_state_managers, create_test_player):
        """Test that partial failure triggers rollback of completed operations."""
        player = await create_test_player("partial_fail_test", "password123")
        executor = AtomicOperationExecutor()
        tx_id = await executor.begin_transaction()
        
        # Add a successful operation
        await executor.add_operation(
            tx_id,
            operation_type="set_inventory_slot",
            execute_params={
                "player_id": player.id,
                "slot": 0,
                "item_id": 1,
                "quantity": 5,
                "durability": 1.0,
            },
            rollback_params={
                "operation_type": "delete_inventory_slot",
                "params": {"player_id": player.id, "slot": 0},
            },
        )
        
        # Add an operation that will fail (unknown type)
        await executor.add_operation(
            tx_id,
            operation_type="invalid_operation_that_will_fail",
            execute_params={"some": "params"},
        )
        
        with patch('server.src.services.item_management.atomic_operations.get_game_state_manager', return_value=gsm):
            result = await executor.execute_transaction(tx_id)
        
        assert result is False
