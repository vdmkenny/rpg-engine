"""
Tests for the unified ItemManager service.

Validates that the new interface provides the same functionality as the
existing individual services while preparing for atomic transaction support.
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from server.src.core.items import EquipmentSlot
from server.src.services.item_management import get_item_manager
from server.src.schemas.item import AddItemResult, EquipItemResult, DropItemResult
from server.src.models.item import Item
from server.src.tests.conftest import FakeValkey


class TestUnifiedItemManager:
    """Test the unified ItemManager interface."""

    @pytest_asyncio.fixture
    async def item_manager(self):
        """Get ItemManager instance for testing."""
        return get_item_manager()

    @pytest_asyncio.fixture
    async def sample_item(self, session, gsm):
        """Create a sample item for testing."""
        from server.src.services.item_service import ItemService
        
        # Sync items to ensure we have test items
        await ItemService.sync_items_to_db()
        
        # Get an item from the service
        item = await ItemService.get_item_by_name("bronze_sword")
        return item

    @pytest.mark.asyncio
    async def test_add_item_to_inventory_delegates_correctly(
        self, item_manager, session: AsyncSession, sample_item: Item
    ):
        """Test that add_item_to_inventory delegates to InventoryService correctly."""
        if not sample_item:
            pytest.skip("No sample item available")

        with patch('server.src.services.inventory_service.InventoryService.add_item') as mock_add:
            mock_add.return_value = AddItemResult(
                success=True,
                message="Item added",
                slot=0,
            )

            # Test adding item to player inventory
            result = await item_manager.add_item_to_inventory(
                player_id=1,
                item_id=sample_item.id,
                quantity=1,
            )

            # Verify service method was called with correct parameters
            mock_add.assert_called_once_with(
                player_id=1,
                item_id=sample_item.id,
                quantity=1,
                durability=None,
            )

            # Verify result
            assert result.success is True
            assert result.message == "Item added"
            assert result.slot == 0

    @pytest.mark.asyncio
    async def test_equip_item_delegates_correctly(
        self, item_manager, session: AsyncSession
    ):
        """Test that equip_item delegates to EquipmentService correctly."""
        
        with patch('server.src.services.equipment_service.EquipmentService.equip_from_inventory') as mock_equip:
            mock_equip.return_value = EquipItemResult(
                success=True,
                message="Item equipped",
            )

            # Test equipping item from inventory
            result = await item_manager.equip_item(
                player_id=1,
                inventory_slot=0,
            )

            # Verify equipment service was called
            # Service handles database operations internally
            mock_equip.assert_called_once()

            # Verify result
            assert result.success is True
            assert result.message == "Item equipped"

    @pytest.mark.asyncio
    async def test_drop_item_delegates_correctly(self, item_manager):
        """Test that drop_item delegates to GroundItemService correctly."""
        
        with patch('server.src.services.ground_item_service.GroundItemService.drop_from_inventory') as mock_drop:
            mock_drop.return_value = DropItemResult(
                success=True,
                message="Item dropped",
                ground_item_id=123,
            )

            result = await item_manager.drop_item(
                player_id=1,
                inventory_slot=0,
                map_id="test_map",
                x=5,
                y=10,
                quantity=1,
            )

            # Verify delegation occurred
            mock_drop.assert_called_once_with(
                player_id=1,
                inventory_slot=0,
                map_id="test_map",
                x=5,
                y=10,
                quantity=1,
            )

            # Verify result
            assert result.success is True
            assert result.message == "Item dropped"
            assert result.ground_item_id == 123

    @pytest.mark.asyncio
    async def test_handle_player_death_delegates_correctly(self, item_manager):
        """Test that handle_player_death delegates correctly."""
        
        with patch('server.src.services.ground_item_service.GroundItemService.drop_player_items_on_death') as mock_death:
            mock_death.return_value = 5  # 5 items dropped

            result = await item_manager.handle_player_death(
                player_id=1,
                map_id="test_map",
                x=5,
                y=10,
            )

            # Verify delegation occurred
            mock_death.assert_called_once_with(
                player_id=1,
                map_id="test_map",
                x=5,
                y=10,
            )

            # Verify result
            assert result == 5

    @pytest.mark.asyncio
    async def test_unified_interface_consistency(self, item_manager):
        """Test that the unified interface provides consistent method signatures."""
        
        # Verify all required methods exist
        assert hasattr(item_manager, 'add_item_to_inventory')
        assert hasattr(item_manager, 'remove_item_from_inventory')
        assert hasattr(item_manager, 'move_item_in_inventory')
        assert hasattr(item_manager, 'equip_item')
        assert hasattr(item_manager, 'unequip_item')
        assert hasattr(item_manager, 'drop_item')
        assert hasattr(item_manager, 'pickup_item')
        assert hasattr(item_manager, 'handle_player_death')
        assert hasattr(item_manager, 'get_total_equipment_stats')
        assert hasattr(item_manager, 'can_equip_item')

        # Verify methods are callable
        assert callable(getattr(item_manager, 'add_item_to_inventory'))
        assert callable(getattr(item_manager, 'equip_item'))
        assert callable(getattr(item_manager, 'handle_player_death'))

    def test_singleton_pattern(self):
        """Test that get_item_manager returns the same instance."""
        manager1 = get_item_manager()
        manager2 = get_item_manager()
        
        assert manager1 is manager2, "ItemManager should be a singleton"

    @pytest.mark.asyncio
    async def test_unequip_item_with_ground_drop(self, item_manager, session: AsyncSession):
        """Test unequip_item with ground drop parameters."""
        
        with patch('server.src.services.equipment_service.EquipmentService.unequip_to_inventory') as mock_unequip:
            mock_unequip.return_value = EquipItemResult(
                success=True,
                message="Item unequipped and dropped",
            )

            # Test unequipping item to inventory with ground drop fallback
            result = await item_manager.unequip_item(
                player_id=1,
                equipment_slot=EquipmentSlot.WEAPON,
                map_id="test_map",
                player_x=5,
                player_y=10,
            )

            # Verify equipment service was called
            # Service handles database operations internally
            mock_unequip.assert_called_once()

            assert result.success is True


class TestAtomicOperations:
    """Test atomic operation infrastructure."""

    @pytest.mark.asyncio 
    async def test_atomic_executor_imports(self):
        """Test that atomic operation modules import correctly."""
        from server.src.services.item_management.atomic_operations import (
            get_atomic_executor,
            AtomicTransaction,
            AtomicOperation,
        )
        
        # Verify we can get an executor instance
        executor = get_atomic_executor()
        assert executor is not None
        
        # Verify singleton behavior
        executor2 = get_atomic_executor()
        assert executor is executor2

    @pytest.mark.asyncio
    async def test_transaction_lifecycle(self):
        """Test basic transaction creation and management."""
        from server.src.services.item_management.atomic_operations import get_atomic_executor
        
        executor = get_atomic_executor()
        
        # Begin transaction
        tx_id = await executor.begin_transaction()
        assert tx_id is not None
        assert len(tx_id) > 0
        
        # Add operation
        op_id = await executor.add_operation(
            tx_id,
            "test_operation",
            {"param1": "value1"},
            {"operation_type": "rollback_test", "params": {"param1": "rollback_value1"}},
        )
        assert op_id is not None
        assert len(op_id) > 0


class TestMigrationCompatibility:
    """Test that migration maintains backward compatibility."""

    @pytest.mark.asyncio
    async def test_existing_service_imports_still_work(self):
        """Test that existing service imports continue to work."""
        # These imports should not fail during migration
        from server.src.services.inventory_service import InventoryService
        from server.src.services.equipment_service import EquipmentService
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.item_service import ItemService
        
        # Verify services are still available
        assert InventoryService is not None
        assert EquipmentService is not None
        assert GroundItemService is not None
        assert ItemService is not None

    @pytest.mark.asyncio
    async def test_unified_service_coexists_with_existing(self, session: AsyncSession):
        """Test that unified service can coexist with existing services."""
        # Both old and new patterns should work
        from server.src.services.inventory_service import InventoryService
        from server.src.services.item_management import get_item_manager
        
        # Get instances
        item_manager = get_item_manager()
        
        # Both should be available
        assert InventoryService is not None
        assert item_manager is not None
        
        # Both should have their respective methods
        assert hasattr(InventoryService, 'add_item')
        assert hasattr(item_manager, 'add_item_to_inventory')
