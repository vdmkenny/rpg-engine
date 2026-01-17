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

    def test_drop_item_creates_ground_item(self):
        """
        Verify drop_from_inventory creates a ground item entry.
        
        Ground items are included in GAME_STATE_UPDATE broadcasts as entities
        with type="ground_item" for visibility-based updates.
        """
        import pytest
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from server.src.models.base import Base
        from server.src.models.player import Player
        from server.src.models.item import Item, PlayerInventory, GroundItem
        from server.src.core.security import get_password_hash
        from server.src.services.inventory_service import InventoryService
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.item_service import ItemService
        
        async def run_test():
            # Set up in-memory database
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            AsyncSessionLocal = sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            
            async with AsyncSessionLocal() as session:
                # Sync items to database first
                await ItemService.sync_items_to_db(session)
                
                # Get a droppable item
                bronze_sword = await ItemService.get_item_by_name(session, "bronze_sword")
                if not bronze_sword:
                    await engine.dispose()
                    pytest.skip("bronze_sword not found in items")
                    return
                
                # Create test player
                player = Player(
                    username="ground_drop_user",
                    hashed_password=get_password_hash("test123"),
                    x_coord=10,
                    y_coord=10,
                    map_id="samplemap",
                )
                session.add(player)
                await session.commit()
                await session.refresh(player)
                
                # Add item to inventory
                await InventoryService.add_item(session, player.id, bronze_sword.id)
                
                # Drop the item
                result = await GroundItemService.drop_from_inventory(
                    db=session,
                    player_id=player.id,
                    inventory_slot=0,
                    map_id="samplemap",
                    x=10,
                    y=10,
                )
                
                assert result.success is True
                assert result.ground_item_id is not None
                
                # Verify ground item was created
                from sqlalchemy.future import select
                ground_items = await session.execute(
                    select(GroundItem).where(GroundItem.map_id == "samplemap")
                )
                items_list = ground_items.scalars().all()
                assert len(items_list) >= 1
            
            await engine.dispose()
        
        asyncio.get_event_loop().run_until_complete(run_test())


class TestPickupItemWithRealItems:
    """
    Tests for PICKUP_ITEM with real item data.
    
    Uses in-memory SQLite to test the GroundItemService.pickup_item directly
    without requiring integration test infrastructure.
    """

    @pytest.mark.asyncio
    async def test_pickup_item_success(self):
        """Picking up a ground item should add it to inventory."""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from server.src.models.base import Base
        from server.src.models.player import Player
        from server.src.models.item import GroundItem
        from server.src.core.security import get_password_hash
        from server.src.services.inventory_service import InventoryService
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.item_service import ItemService
        from datetime import datetime, timedelta
        
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
            
            # Get a droppable item
            bronze_sword = await ItemService.get_item_by_name(session, "bronze_sword")
            if not bronze_sword:
                await engine.dispose()
                pytest.skip("bronze_sword not found in items")
                return
            
            # Create test player
            player = Player(
                username="pickup_success_user",
                hashed_password=get_password_hash("test123"),
                x_coord=10,
                y_coord=10,
                map_id="samplemap",
            )
            session.add(player)
            await session.commit()
            await session.refresh(player)
            
            # Create a ground item at player's position (owned by player, so no loot protection)
            now = datetime.now()
            ground_item = GroundItem(
                item_id=bronze_sword.id,
                map_id="samplemap",
                x=10,
                y=10,
                quantity=1,
                dropped_by=player.id,  # Owned by player
                dropped_at=now,
                public_at=now,  # Already public
                despawn_at=now + timedelta(minutes=5),  # Won't expire
                current_durability=bronze_sword.max_durability,
            )
            session.add(ground_item)
            await session.commit()
            await session.refresh(ground_item)
            
            ground_item_id = ground_item.id
            
            # Pick up the item
            result = await GroundItemService.pickup_item(
                db=session,
                player_id=player.id,
                ground_item_id=ground_item_id,
                player_x=10,
                player_y=10,
                player_map_id="samplemap",
            )
            
            assert result.success is True, f"Pickup failed: {result.message}"
            assert "picked up" in result.message.lower() or result.success
            
            # Verify item is in inventory
            inventory = await InventoryService.get_inventory(session, player.id)
            assert len(inventory) == 1
            assert inventory[0].item.name == "bronze_sword"
            
            # Verify ground item was removed
            from sqlalchemy.future import select
            remaining = await session.execute(
                select(GroundItem).where(GroundItem.id == ground_item_id)
            )
            assert remaining.scalar_one_or_none() is None
        
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_pickup_item_wrong_tile_fails(self):
        """Picking up an item from wrong tile should fail."""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from server.src.models.base import Base
        from server.src.models.player import Player
        from server.src.models.item import GroundItem
        from server.src.core.security import get_password_hash
        from server.src.services.ground_item_service import GroundItemService
        from server.src.services.item_service import ItemService
        from datetime import datetime, timedelta
        
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
            
            bronze_sword = await ItemService.get_item_by_name(session, "bronze_sword")
            if not bronze_sword:
                await engine.dispose()
                pytest.skip("bronze_sword not found in items")
                return
            
            # Create test player at (10, 10)
            player = Player(
                username="pickup_wrongtile_user",
                hashed_password=get_password_hash("test123"),
                x_coord=10,
                y_coord=10,
                map_id="samplemap",
            )
            session.add(player)
            await session.commit()
            await session.refresh(player)
            
            # Create ground item at different position (15, 15)
            now = datetime.now()
            ground_item = GroundItem(
                item_id=bronze_sword.id,
                map_id="samplemap",
                x=15,
                y=15,
                quantity=1,
                dropped_by=player.id,
                dropped_at=now,
                public_at=now,
                despawn_at=now + timedelta(minutes=5),
            )
            session.add(ground_item)
            await session.commit()
            await session.refresh(ground_item)
            
            # Try to pick up from wrong tile
            result = await GroundItemService.pickup_item(
                db=session,
                player_id=player.id,
                ground_item_id=ground_item.id,
                player_x=10,  # Player at (10, 10)
                player_y=10,
                player_map_id="samplemap",
            )
            
            assert result.success is False
            assert "same tile" in result.message.lower()
        
        await engine.dispose()


@SKIP_WS_INTEGRATION
class TestPickupStackableItem:
    """
    Integration tests for picking up stackable items.
    
    These tests require PostgreSQL due to the FOR UPDATE clause used
    to prevent race conditions during pickup.
    """

    def test_pickup_stackable_item_stacks_with_inventory(self, integration_client):
        """Picking up a stackable item should add to existing stack in inventory."""
        import time
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select
        from server.src.core.database import AsyncSessionLocal
        from server.src.models.item import GroundItem
        from server.src.services.item_service import ItemService
        from server.src.services.inventory_service import InventoryService
        import asyncio
        
        client = integration_client
        username = unique_username("pickup_stack")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value
            
            player_data = welcome["payload"]["player"]
            player_x = player_data["x"]
            player_y = player_data["y"]
            map_id = player_data["map_id"]
            
            # Get player_id from welcome message
            player_id = get_player_id_from_welcome(welcome)
            
            async def setup_and_test():
                async with AsyncSessionLocal() as session:
                    # Get bronze_arrow item
                    bronze_arrow = await ItemService.get_item_by_name(session, "bronze_arrow")
                    if not bronze_arrow:
                        return None, "bronze_arrow not found"
                    
                    # Add 5 arrows to player's inventory
                    await InventoryService.add_item(session, player_id, bronze_arrow.id, quantity=5)
                    
                    # Create ground item with 10 arrows at player's position
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    ground_item = GroundItem(
                        item_id=bronze_arrow.id,
                        map_id=map_id,
                        x=player_x,
                        y=player_y,
                        quantity=10,
                        dropped_by=player_id,  # Owned by player (no loot protection)
                        dropped_at=now,
                        public_at=now,
                        despawn_at=now + timedelta(minutes=5),
                    )
                    session.add(ground_item)
                    await session.commit()
                    await session.refresh(ground_item)
                    
                    return ground_item.id, None
            
            # Run setup
            loop = asyncio.new_event_loop()
            ground_item_id, error = loop.run_until_complete(setup_and_test())
            loop.close()
            
            if error:
                pytest.skip(error)
                return
            
            # Send PICKUP_ITEM message
            send_ws_message(
                websocket,
                MessageType.PICKUP_ITEM,
                {"ground_item_id": ground_item_id},
            )

            # Should receive OPERATION_RESULT with success
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "pickup_item"
            assert response["payload"]["success"] is True, f"Pickup failed: {response['payload']['message']}"
            
            # Verify inventory has 15 arrows total (5 + 10)
            async def verify_inventory():
                async with AsyncSessionLocal() as session:
                    inventory = await InventoryService.get_inventory(session, player_id)
                    total_arrows = sum(
                        inv.quantity for inv in inventory if inv.item.name == "bronze_arrow"
                    )
                    return total_arrows
            
            loop = asyncio.new_event_loop()
            total_arrows = loop.run_until_complete(verify_inventory())
            loop.close()
            
            assert total_arrows == 15, f"Expected 15 arrows, got {total_arrows}"
