"""
WebSocket integration tests for ground item operations.

Covers:
- PICKUP_ITEM - Pick up item from ground
- Ground items included in GAME_STATE_UPDATE as entities with type="ground_item"

These tests use the real PostgreSQL database and WebSocket handlers.
"""

import pytest

from common.src.protocol import MessageType
from server.src.tests.ws_test_helpers import (
    SKIP_WS_INTEGRATION,
    unique_username,
    register_and_login,
    authenticate_websocket,
    send_ws_message,
    receive_message_of_type,
    integration_client,
)


@SKIP_WS_INTEGRATION
class TestPickupItem:
    """Tests for PICKUP_ITEM message handler."""

    def test_pickup_item_not_found(self, integration_client):
        """Picking up non-existent item should fail."""
        client = integration_client
        username = unique_username("pickup_notfound")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to pick up non-existent ground item
            send_ws_message(
                websocket,
                MessageType.PICKUP_ITEM,
                {"ground_item_id": 99999},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "pickup_item"
            assert response["payload"]["success"] is False
            # Message should indicate item not found
            assert "not found" in response["payload"]["message"].lower() or \
                   "does not exist" in response["payload"]["message"].lower()

    def test_pickup_item_invalid_id(self, integration_client):
        """Picking up with invalid ID format should fail gracefully."""
        client = integration_client
        username = unique_username("pickup_invalid")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to pick up with negative ID
            send_ws_message(
                websocket,
                MessageType.PICKUP_ITEM,
                {"ground_item_id": -1},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "pickup_item"
            assert response["payload"]["success"] is False


class TestGroundItemsInGameStateUpdate:
    """
    Tests for ground items being included in GAME_STATE_UPDATE.
    
    Ground items are now broadcast as part of GAME_STATE_UPDATE with
    entity type="ground_item". This replaced the separate GROUND_ITEMS_UPDATE
    message for consistency with the visibility/diff-based broadcasting system.
    """

    def test_game_state_update_message_type_exists(self):
        """GAME_STATE_UPDATE message type should be defined in protocol."""
        assert hasattr(MessageType, "GAME_STATE_UPDATE")
        assert MessageType.GAME_STATE_UPDATE.value == "GAME_STATE_UPDATE"

    @pytest.mark.asyncio
    async def test_drop_item_creates_ground_item(self, session, gsm):
        """
        Verify drop_from_inventory creates a ground item entry.
        
        Ground items are included in GAME_STATE_UPDATE broadcasts as entities
        with type="ground_item" for visibility-based updates.
        """
        from server.src.models.player import Player
        from server.src.core.security import get_password_hash
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.item_service import ItemService
        import uuid
        
        # Get a droppable item
        bronze_sword = await ItemService.get_item_by_name(session, "bronze_sword")
        if not bronze_sword:
            pytest.skip("bronze_sword not found in items")
            return
        
        # Create test player
        username = f"ground_drop_{uuid.uuid4().hex[:8]}"
        player = Player(
            
            hashed_password=get_password_hash("test123"),
            x_coord=10,
            y_coord=10,
            map_id="samplemap",
        )
        session.add(player)
        await session.commit()
        await session.refresh(player)
        
        # Register player in GSM
        gsm.register_online_player(player_id=player.id, username=username)
        await gsm.set_player_full_state(
            player_id=player.id,
            x=10,
            y=10,
            map_id="samplemap",
            current_hp=10,
            max_hp=10,
        )
        
        # Add item to inventory via GSM
        await gsm.set_inventory_slot(player.id, 0, bronze_sword.id, 1, None)
        
        # Drop the item
        result = await GroundItemService.drop_from_inventory(
            player_id=player.id,
            inventory_slot=0,
            map_id="samplemap",
            x=10,
            y=10,
        )
        
        assert result.success is True
        assert result.ground_item_id is not None
        
        # Verify ground item was created in GSM
        ground_items = await gsm.get_ground_items_on_map("samplemap")
        assert len(ground_items) >= 1
        
        # Find our item
        our_item = next((gi for gi in ground_items if gi["id"] == result.ground_item_id), None)
        assert our_item is not None
        assert our_item["item_id"] == bronze_sword.id


class TestPickupItemWithRealItems:
    """
    Tests for PICKUP_ITEM with real item data.
    
    Uses GSM fixtures to test the GroundItemService.pickup_item directly.
    """

    @pytest.mark.asyncio
    async def test_pickup_item_success(self, session, gsm):
        """Picking up a ground item should add it to inventory."""
        from server.src.models.player import Player
        from server.src.core.security import get_password_hash
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.item_service import ItemService
        import uuid
        
        # Get a droppable item
        bronze_sword = await ItemService.get_item_by_name(session, "bronze_sword")
        if not bronze_sword:
            pytest.skip("bronze_sword not found in items")
            return
        
        # Create test player
        username = f"pickup_success_{uuid.uuid4().hex[:8]}"
        player = Player(
            
            hashed_password=get_password_hash("test123"),
            x_coord=10,
            y_coord=10,
            map_id="samplemap",
        )
        session.add(player)
        await session.commit()
        await session.refresh(player)
        
        # Register player in GSM
        gsm.register_online_player(player_id=player.id, username=username)
        await gsm.set_player_full_state(
            player_id=player.id,
            x=10,
            y=10,
            map_id="samplemap",
            current_hp=10,
            max_hp=10,
        )
        
        # Create a ground item via GSM at player's position
        ground_item_id = await GroundItemService.create_ground_item(
            item_id=bronze_sword.id,
            map_id="samplemap",
            x=10,
            y=10,
            quantity=1,
            dropped_by=player.id,
        )
        assert ground_item_id is not None
        
        # Pick up the item
        result = await GroundItemService.pickup_item(
            player_id=player.id,
            ground_item_id=ground_item_id,
            player_x=10,
            player_y=10,
            player_map_id="samplemap",
        )
        
        assert result.success is True, f"Pickup failed: {result.message}"
        
        # Verify item is in inventory via GSM
        inventory = await gsm.get_inventory(player.id)
        assert len(inventory) == 1
        slot_data = list(inventory.values())[0]
        assert slot_data["item_id"] == bronze_sword.id
        
        # Verify ground item was removed from GSM
        remaining = await gsm.get_ground_item(ground_item_id)
        assert remaining is None

    @pytest.mark.asyncio
    async def test_pickup_item_wrong_tile_fails(self, session, gsm):
        """Picking up an item from wrong tile should fail."""
        from server.src.models.player import Player
        from server.src.core.security import get_password_hash
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.item_service import ItemService
        import uuid
        
        bronze_sword = await ItemService.get_item_by_name(session, "bronze_sword")
        if not bronze_sword:
            pytest.skip("bronze_sword not found in items")
            return
        
        # Create test player at (10, 10)
        username = f"pickup_wrongtile_{uuid.uuid4().hex[:8]}"
        player = Player(
            
            hashed_password=get_password_hash("test123"),
            x_coord=10,
            y_coord=10,
            map_id="samplemap",
        )
        session.add(player)
        await session.commit()
        await session.refresh(player)
        
        # Register player in GSM
        gsm.register_online_player(player_id=player.id, username=username)
        await gsm.set_player_full_state(
            player_id=player.id,
            x=10,
            y=10,
            map_id="samplemap",
            current_hp=10,
            max_hp=10,
        )
        
        # Create ground item at different position (15, 15)
        ground_item_id = await GroundItemService.create_ground_item(
            item_id=bronze_sword.id,
            map_id="samplemap",
            x=15,
            y=15,
            quantity=1,
            dropped_by=player.id,
        )
        assert ground_item_id is not None
        
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


@SKIP_WS_INTEGRATION
class TestPickupStackableItem:
    """
    Tests for picking up stackable items that merge with inventory.
    
    Tests the service layer directly with async/await pattern.
    Note: Stacking behavior works with SQLite for unit tests, but
    the FOR UPDATE clause in pickup_item requires PostgreSQL for
    race condition safety in production.
    """

    @pytest.mark.asyncio
    async def test_pickup_stackable_item_stacks_with_inventory(self):
        """Picking up a stackable item should add to existing stack in inventory."""
        from datetime import datetime, timedelta
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from server.src.models.base import Base
        from server.src.models.player import Player
        from server.src.models.item import GroundItem
        from server.src.core.security import get_password_hash
        from server.src.services.inventory_service import InventoryService
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.item_service import ItemService
        from server.src.services.game_state_manager import get_game_state_manager
        
        # Set up in-memory database
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        AsyncSessionLocal = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with AsyncSessionLocal() as session:
            # Sync items to database
            await ItemService.sync_items_to_db(session)
            
            # Get a stackable item (arrows)
            bronze_arrows = await ItemService.get_item_by_name(session, "bronze_arrows")
            if not bronze_arrows:
                await engine.dispose()
                pytest.skip("bronze_arrows not found in items")
                return
            
            # Create test player
            player = Player(
                username="pickup_stack_user",
                hashed_password=get_password_hash("test123"),
                x_coord=10,
                y_coord=10,
                map_id="samplemap",
            )
            session.add(player)
            await session.commit()
            await session.refresh(player)
            
            # Add 5 arrows to player's inventory first
            gsm = get_game_state_manager()
            await InventoryService.add_item(session, player.id, bronze_arrows.id, quantity=5)
            
            # Create a ground item with 10 arrows at player's position
            now = datetime.now()
            ground_item = GroundItem(
                item_id=bronze_arrows.id,
                map_id="samplemap",
                x=10,
                y=10,
                quantity=10,
                dropped_by=player.id,  # Owned by player (no loot protection)
                dropped_at=now,
                public_at=now,  # Already public
                despawn_at=now + timedelta(minutes=5),  # Won't expire
            )
            session.add(ground_item)
            await session.commit()
            await session.refresh(ground_item)
            
            ground_item_id = ground_item.id
            
            # Pick up the ground item - should merge with existing stack
            result = await GroundItemService.pickup_item(
                player_id=player.id,
                ground_item_id=ground_item_id,
                player_x=10,
                player_y=10,
                player_map_id="samplemap",
            )
            
            assert result.success is True, f"Pickup failed: {result.message}"
            
            # Verify inventory has 15 arrows total (5 + 10)
            inventory = await InventoryService.get_inventory(session, player.id)
            total_arrows = sum(
                inv.quantity for inv in inventory if inv.item.name == "bronze_arrows"
            )
            assert total_arrows == 15, f"Expected 15 arrows, got {total_arrows}"
            
            # Verify only 1 inventory slot is used (items should stack)
            arrow_slots = [inv for inv in inventory if inv.item.name == "bronze_arrows"]
            assert len(arrow_slots) == 1, f"Expected 1 arrow slot, got {len(arrow_slots)}"
            
            # Verify ground item was removed
            from sqlalchemy.future import select
            remaining = await session.execute(
                select(GroundItem).where(GroundItem.id == ground_item_id)
            )
            assert remaining.scalar_one_or_none() is None
        
        await engine.dispose()
