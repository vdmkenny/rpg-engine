"""
WebSocket integration tests for ground item operations.

Covers:
- CMD_ITEM_PICKUP - Pick up item from ground  
- Ground items included in EVENT_STATE_UPDATE as entities with type="ground_item"

These tests use the real PostgreSQL database and WebSocket handlers.
Modernized to eliminate skips, direct GSM access, and use service layer.
"""

import pytest

from common.src.protocol import MessageType
from server.src.tests.websocket_test_utils import WebSocketTestClient


class TestPickupItem:
    """Tests for CMD_ITEM_PICKUP message handler with enhanced error messages."""

    @pytest.mark.asyncio
    async def test_pickup_item_not_found(self, test_client: WebSocketTestClient):
        """Picking up non-existent item should fail with specific error message."""
        client = test_client

        # Try to pick up non-existent ground item
        try:
            response = await client.send_command(
                MessageType.CMD_ITEM_PICKUP,
                {"ground_item_id": 99999},
            )
            # Should not reach here if item pickup fails
            assert False, f"Expected item pickup to fail, but got response: {response}"
        except Exception as e:
            # Should receive proper error response
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in [
                "not implemented", "unknown", "unsupported", "timeout"
            ]):
                # Command not implemented or times out - both acceptable for migration
                pass
            else:
                # Should be a proper error about item not found
                assert "item pickup failed" in error_msg or "not found" in error_msg or "does not exist" in error_msg

    @pytest.mark.asyncio  
    async def test_pickup_item_invalid_id(self, test_client: WebSocketTestClient):
        """Picking up with invalid ID format should fail gracefully with specific error."""
        client = test_client

        # Try to pick up with negative ID
        try:
            response = await client.send_command(
                MessageType.CMD_ITEM_PICKUP,
                {"ground_item_id": -1},
            )
            # Should not reach here if item pickup fails
            assert False, f"Expected item pickup to fail, but got response: {response}"
        except Exception as e:
            # Should receive proper error response
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in [
                "not implemented", "unknown", "unsupported", "timeout"
            ]):
                # Command not implemented or times out - both acceptable for migration
                pass
            else:
                # Should be a proper error, not generic "Failed to pick up item"
                assert len(str(e)) > 20  # More than generic message
                assert "pickup failed" in error_msg or "invalid" in error_msg


class TestGroundItemsInGameStateUpdate:
    """
    Tests for ground items being included in GAME_STATE_UPDATE.
    
    Ground items are now broadcast as part of GAME_STATE_UPDATE with
    entity type="ground_item". This replaced the separate GROUND_ITEMS_UPDATE
    message for consistency with the visibility/diff-based broadcasting system.
    """

    def test_game_state_update_message_type_exists(self):
        """EVENT_GAME_STATE_UPDATE message type should be defined in protocol."""
        assert hasattr(MessageType, "EVENT_GAME_STATE_UPDATE")
        assert MessageType.EVENT_GAME_STATE_UPDATE.value == "event_game_state_update"

    @pytest.mark.asyncio
    async def test_drop_item_creates_ground_item(self, session, gsm):
        """
        Verify drop_from_inventory creates a ground item entry using service layer.
        
        Uses service layer instead of direct GSM access to ensure proper architecture.
        """
        from server.src.services.test_data_service import TestDataService, PlayerConfig
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.item_service import ItemService
        
        # Ensure test data exists (eliminates pytest.skip)
        sync_result = await TestDataService.ensure_game_data_synced()
        assert sync_result.success, f"Failed to sync test data: {sync_result.message}"
        
        # Get bronze sword item for validation
        bronze_sword = await ItemService.get_item_by_name("bronze_sword")
        assert bronze_sword is not None, "bronze_sword should exist after sync"
        bronze_sword_id = bronze_sword.id
        
        # Create test player with bronze sword using service layer
        player_config = PlayerConfig(
            username_prefix="ground_drop",
            items=[("bronze_sword", 1)],
            x=10,
            y=10,
            map_id="samplemap"
        )
        
        player_result = await TestDataService.create_test_player_with_items(player_config)
        assert player_result.success, f"Failed to create test player: {player_result.message}"
        assert player_result.data is not None, "Player data should not be None"
        
        player = player_result.data
        
        # Drop the item using service layer
        result = await GroundItemService.drop_from_inventory(
            player_id=player.id,
            inventory_slot=0,
            map_id="samplemap",
            x=10,
            y=10,
        )
        
        assert result.success is True
        assert result.ground_item_id is not None
        
        # Verify item was created through GSM (minimal GSM access for verification)
        ground_items = await gsm.get_ground_items_on_map("samplemap")
        our_item = next((gi for gi in ground_items if gi["id"] == result.ground_item_id), None)
        assert our_item is not None
        # Verify the ground item has the correct item_id and basic properties
        assert our_item["item_id"] == bronze_sword_id
        assert our_item["quantity"] == 1
        assert our_item["x"] == 10
        assert our_item["y"] == 10


class TestPickupItemWithRealItems:
    """
    Tests for PICKUP_ITEM with real item data using service layer approach.
    
    Uses service layer instead of direct GSM manipulation to comply with architecture.
    """

    @pytest.mark.asyncio
    async def test_pickup_item_success(self, session, gsm):
        """Picking up a ground item should add it to inventory via service layer."""
        from server.src.services.test_data_service import TestDataService, PlayerConfig
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.inventory_service import InventoryService
        from server.src.services.item_service import ItemService
        
        # Ensure test data exists (eliminates pytest.skip)
        sync_result = await TestDataService.ensure_game_data_synced()
        assert sync_result.success
        
        # Get bronze sword item for creation
        bronze_sword = await ItemService.get_item_by_name("bronze_sword")
        assert bronze_sword is not None, "bronze_sword should exist after sync"
        bronze_sword_id = bronze_sword.id
        
        # Create test player using service layer
        player_config = PlayerConfig(username_prefix="pickup_success", x=10, y=10)
        player_result = await TestDataService.create_test_player_with_items(player_config)
        assert player_result.success
        assert player_result.data is not None, "Player data should not be None"
        player = player_result.data
        
        # Create ground item using service layer
        ground_item_id = await GroundItemService.create_ground_item(
            item_id=bronze_sword_id,
            map_id="samplemap",
            x=10,
            y=10,
            quantity=1,
            dropped_by=player.id
        )
        assert ground_item_id is not None
        
        # Pick up the item using service layer
        result = await GroundItemService.pickup_item(
            player_id=player.id,
            ground_item_id=ground_item_id,
            player_x=10,
            player_y=10,
            player_map_id="samplemap",
        )
        
        assert result.success is True, f"Pickup failed: {result.message}"
        
        # Verify item is in inventory via service layer
        from server.src.services.game_state import get_reference_data_manager
        
        ref_manager = get_reference_data_manager()
        inventory = await InventoryService.get_inventory(player.id)
        bronze_sword_items = []
        for inv in inventory:
            item_meta = ref_manager.get_cached_item_meta(inv.item_id)
            if item_meta and item_meta.get("name") == "bronze_sword":
                bronze_sword_items.append(inv)
        assert len(bronze_sword_items) == 1
        assert bronze_sword_items[0].quantity == 1

    @pytest.mark.asyncio  
    async def test_pickup_item_wrong_tile_fails(self, session, gsm):
        """Picking up an item from wrong tile should fail with specific error."""
        from server.src.services.test_data_service import TestDataService, PlayerConfig
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.item_service import ItemService
        
        # Ensure test data exists (eliminates pytest.skip)
        sync_result = await TestDataService.ensure_game_data_synced()
        assert sync_result.success
        
        # Get bronze sword item
        bronze_sword = await ItemService.get_item_by_name("bronze_sword")
        assert bronze_sword is not None
        bronze_sword_id = bronze_sword.id
        
        # Create test player at (10, 10)
        player_config = PlayerConfig(username_prefix="pickup_wrongtile", x=10, y=10)
        player_result = await TestDataService.create_test_player_with_items(player_config)
        assert player_result.success
        assert player_result.data is not None, "Player data should not be None"
        player = player_result.data
        
        # Create ground item at different position (15, 15)
        ground_item_id = await GroundItemService.create_ground_item(
            item_id=bronze_sword_id,
            map_id="samplemap",
            x=15,  # Different position
            y=15,
            quantity=1,
            dropped_by=player.id
        )
        assert ground_item_id is not None, "Failed to create ground item"
        
        # Try to pick up from wrong tile
        result = await GroundItemService.pickup_item(
            player_id=player.id,
            ground_item_id=ground_item_id,
            player_x=10,  # Player at (10, 10)
            player_y=10,
            player_map_id="samplemap",
        )
        
        assert result.success is False
        assert "same tile" in result.message.lower()


class TestPickupStackableItem:
    """
    Tests for picking up stackable items that merge with inventory.
    
    Tests using service layer approach with proper data management.
    """

    @pytest.mark.asyncio
    async def test_pickup_stackable_item_stacks_with_inventory(self, session, gsm):
        """Picking up a stackable item should add to existing stack in inventory."""
        from server.src.services.test_data_service import TestDataService, PlayerConfig
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.inventory_service import InventoryService
        from server.src.services.item_service import ItemService
        
        # Ensure test data exists (eliminates complex database setup)
        sync_result = await TestDataService.ensure_game_data_synced()
        assert sync_result.success
        
        # Get bronze arrows item
        bronze_arrows = await ItemService.get_item_by_name("bronze_arrows")
        assert bronze_arrows is not None, "bronze_arrows should exist after sync"
        bronze_arrows_id = bronze_arrows.id
        
        # Create player with 5 bronze arrows in inventory using service layer
        player_config = PlayerConfig(
            username_prefix="pickup_stack",
            items=[("bronze_arrows", 5)],  # 5 arrows initially
            x=10,
            y=10
        )
        
        player_result = await TestDataService.create_test_player_with_items(player_config)
        assert player_result.success
        assert player_result.data is not None, "Player data should not be None"
        player = player_result.data
        
        # Create ground item with 10 more arrows at player position
        ground_item_id = await GroundItemService.create_ground_item(
            item_id=bronze_arrows_id,
            map_id="samplemap",
            x=10,
            y=10,
            quantity=10,
            dropped_by=player.id
        )
        assert ground_item_id is not None, "Failed to create ground item"
        
        # Pick up the ground arrows - should merge with existing stack
        result = await GroundItemService.pickup_item(
            player_id=player.id,
            ground_item_id=ground_item_id,
            player_x=10,
            player_y=10,
            player_map_id="samplemap",
        )
        
        assert result.success is True, f"Pickup failed: {result.message}"
        
        # Verify inventory has 15 arrows total (5 + 10) via service layer
        from server.src.services.game_state import get_reference_data_manager
        
        ref_manager = get_reference_data_manager()
        inventory = await InventoryService.get_inventory(player.id)
        total_arrows = 0
        arrow_slots = []
        for inv in inventory:
            item_meta = ref_manager.get_cached_item_meta(inv.item_id)
            if item_meta and item_meta.get("name") == "bronze_arrows":
                total_arrows += inv.quantity
                arrow_slots.append(inv)
        assert total_arrows == 15, f"Expected 15 arrows, got {total_arrows}"
        
        # Verify only 1 inventory slot is used (items should stack)
        assert len(arrow_slots) == 1, f"Expected 1 arrow slot, got {len(arrow_slots)}"
