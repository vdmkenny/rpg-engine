"""
WebSocket integration tests for equipment operations.

Covers:
- REQUEST_EQUIPMENT - Get equipment state
- EQUIP_ITEM - Equip from inventory
- UNEQUIP_ITEM - Unequip to inventory
- REQUEST_STATS - Get aggregated stats

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
class TestEquipmentRequest:
    """Tests for REQUEST_EQUIPMENT message handler."""

    def test_request_equipment_empty(self, integration_client):
        """New player should have no equipment."""
        client = integration_client
        username = unique_username("equip_empty")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Request equipment
            send_ws_message(websocket, MessageType.REQUEST_EQUIPMENT, {})

            # Should receive EQUIPMENT_UPDATE
            response = receive_message_of_type(
                websocket, [MessageType.EQUIPMENT_UPDATE.value]
            )

            assert response["type"] == MessageType.EQUIPMENT_UPDATE.value
            payload = response["payload"]
            assert "slots" in payload
            assert "total_stats" in payload
            # All slots should be present (some empty)
            slots = payload["slots"]
            assert isinstance(slots, list)
            # Should have all equipment slot types represented
            assert len(slots) > 0


@SKIP_WS_INTEGRATION
class TestEquipItem:
    """Tests for EQUIP_ITEM message handler."""

    def test_equip_item_empty_slot_fails(self, integration_client):
        """Equipping from empty inventory slot should fail."""
        client = integration_client
        username = unique_username("equip_empty_slot")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to equip from empty inventory slot
            send_ws_message(
                websocket,
                MessageType.EQUIP_ITEM,
                {"inventory_slot": 0},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "equip_item"
            assert response["payload"]["success"] is False

    def test_equip_item_invalid_slot_fails(self, integration_client):
        """Equipping from invalid inventory slot should fail."""
        client = integration_client
        username = unique_username("equip_invalid_slot")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to equip from invalid slot
            send_ws_message(
                websocket,
                MessageType.EQUIP_ITEM,
                {"inventory_slot": 999},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "equip_item"
            assert response["payload"]["success"] is False


@SKIP_WS_INTEGRATION
class TestUnequipItem:
    """Tests for UNEQUIP_ITEM message handler."""

    def test_unequip_empty_slot_fails(self, integration_client):
        """Unequipping from empty equipment slot should fail."""
        client = integration_client
        username = unique_username("unequip_empty")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to unequip from empty weapon slot
            send_ws_message(
                websocket,
                MessageType.UNEQUIP_ITEM,
                {"equipment_slot": "weapon"},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "unequip_item"
            assert response["payload"]["success"] is False

    def test_unequip_invalid_slot_fails(self, integration_client):
        """Unequipping from invalid equipment slot should fail."""
        client = integration_client
        username = unique_username("unequip_invalid")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            authenticate_websocket(websocket, token)

            # Try to unequip from invalid slot
            send_ws_message(
                websocket,
                MessageType.UNEQUIP_ITEM,
                {"equipment_slot": "invalid_slot_name"},
            )

            # Should receive OPERATION_RESULT with failure
            response = receive_message_of_type(
                websocket, [MessageType.OPERATION_RESULT.value]
            )

            assert response["type"] == MessageType.OPERATION_RESULT.value
            assert response["payload"]["operation"] == "unequip_item"
            assert response["payload"]["success"] is False


@SKIP_WS_INTEGRATION
class TestRequestStats:
    """Tests for REQUEST_STATS message handler."""

    def test_request_stats_base(self, integration_client):
        """New player should have base stats."""
        client = integration_client
        username = unique_username("stats_base")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value

            # Request stats
            send_ws_message(websocket, MessageType.REQUEST_STATS, {})

            # Should receive STATS_UPDATE
            response = receive_message_of_type(
                websocket, [MessageType.STATS_UPDATE.value]
            )

            assert response["type"] == MessageType.STATS_UPDATE.value
            payload = response["payload"]
            
            # Should have basic stat structure (ItemStats fields)
            # All stats default to 0 for new player with no equipment
            assert "attack_bonus" in payload
            assert "strength_bonus" in payload
            assert "physical_defence_bonus" in payload
            assert isinstance(payload["attack_bonus"], int)


class TestEquipUnequipWithRealItems:
    """
    Tests for successful equip/unequip operations with real items.
    
    These tests use a standalone database session to set up items before testing
    the equipment service. This validates the full equip/unequip flow without
    requiring WebSocket integration.
    
    Note: Full WebSocket integration tests for equip/unequip would require a way
    to add items to inventory through the WebSocket protocol (not yet implemented).
    """

    @pytest.mark.asyncio
    async def test_equip_item_from_inventory_success(self):
        """Successfully equip a weapon from inventory."""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from server.src.models.base import Base
        from server.src.models.player import Player
        from server.src.core.security import get_password_hash
        from server.src.services.inventory_service import InventoryService
        from server.src.services.equipment_service import EquipmentService
        from server.src.services.item_service import ItemService
        from server.src.services.skill_service import SkillService
        
        # Set up in-memory database
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        AsyncSessionLocal = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with AsyncSessionLocal() as session:
            # Sync items and skills to database
            await ItemService.sync_items_to_db(session)
            await SkillService.sync_skills_to_db(session)
            
            # Get a weapon item
            bronze_sword = await ItemService.get_item_by_name(session, "bronze_sword")
            if not bronze_sword:
                await engine.dispose()
                pytest.skip("bronze_sword not found in items")
                return
            
            # Create test player
            player = Player(
                username="equip_test_user",
                hashed_password=get_password_hash("test123"),
                x_coord=10,
                y_coord=10,
                map_id="samplemap",
            )
            session.add(player)
            await session.commit()
            await session.refresh(player)
            
            # Grant skills (needed for level requirements)
            await SkillService.grant_all_skills_to_player(session, player.id)
            
            # Add sword to inventory at slot 0
            add_result = await InventoryService.add_item(
                session, player.id, bronze_sword.id
            )
            assert add_result.success is True
            
            # Equip the sword
            equip_result = await EquipmentService.equip_from_inventory(
                session, player.id, 0
            )
            
            assert equip_result.success is True
            assert "equipped" in equip_result.message.lower()
            
            # Verify item is now equipped
            equipment = await EquipmentService.get_equipment(session, player.id)
            assert "weapon" in equipment
            assert equipment["weapon"].item.name == "bronze_sword"
            
            # Verify item was removed from inventory
            inventory = await InventoryService.get_inventory(session, player.id)
            assert len(inventory) == 0
        
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_unequip_item_success(self):
        """Successfully unequip an item back to inventory."""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from server.src.models.base import Base
        from server.src.models.player import Player
        from server.src.core.security import get_password_hash
        from server.src.core.items import EquipmentSlot
        from server.src.services.inventory_service import InventoryService
        from server.src.services.equipment_service import EquipmentService
        from server.src.services.item_service import ItemService
        from server.src.services.skill_service import SkillService
        
        # Set up in-memory database
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        AsyncSessionLocal = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with AsyncSessionLocal() as session:
            # Sync items and skills to database
            await ItemService.sync_items_to_db(session)
            await SkillService.sync_skills_to_db(session)
            
            # Get a weapon item
            bronze_sword = await ItemService.get_item_by_name(session, "bronze_sword")
            if not bronze_sword:
                await engine.dispose()
                pytest.skip("bronze_sword not found in items")
                return
            
            # Create test player
            player = Player(
                username="unequip_test_user",
                hashed_password=get_password_hash("test123"),
                x_coord=10,
                y_coord=10,
                map_id="samplemap",
            )
            session.add(player)
            await session.commit()
            await session.refresh(player)
            
            # Grant skills
            await SkillService.grant_all_skills_to_player(session, player.id)
            
            # Add sword to inventory and equip it
            await InventoryService.add_item(session, player.id, bronze_sword.id)
            equip_result = await EquipmentService.equip_from_inventory(
                session, player.id, 0
            )
            assert equip_result.success is True
            
            # Verify equipped
            equipment = await EquipmentService.get_equipment(session, player.id)
            assert len(equipment) == 1
            
            # Unequip the sword using EquipmentSlot enum
            unequip_result = await EquipmentService.unequip_to_inventory(
                session, player.id, EquipmentSlot.WEAPON
            )
            
            assert unequip_result.success is True
            assert "unequipped" in unequip_result.message.lower()
            
            # Verify item is back in inventory
            inventory = await InventoryService.get_inventory(session, player.id)
            assert len(inventory) == 1
            assert inventory[0].item.name == "bronze_sword"
            
            # Verify equipment slot is empty
            equipment = await EquipmentService.get_equipment(session, player.id)
            assert len(equipment) == 0
        
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_equip_swaps_existing_item(self):
        """Equipping when slot is occupied should swap items."""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from server.src.models.base import Base
        from server.src.models.player import Player
        from server.src.core.security import get_password_hash
        from server.src.services.inventory_service import InventoryService
        from server.src.services.equipment_service import EquipmentService
        from server.src.services.item_service import ItemService
        from server.src.services.skill_service import SkillService
        from server.src.models.skill import PlayerSkill, Skill
        from sqlalchemy.future import select
        
        # Set up in-memory database
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        AsyncSessionLocal = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with AsyncSessionLocal() as session:
            # Sync items and skills to database
            await ItemService.sync_items_to_db(session)
            await SkillService.sync_skills_to_db(session)
            
            # Get two bronze swords (no level requirement)
            # We'll test swap with same item type - the swap mechanism is the same
            bronze_sword = await ItemService.get_item_by_name(session, "bronze_sword")
            
            if not bronze_sword:
                await engine.dispose()
                pytest.skip("bronze_sword not found in items")
                return
            
            # Create test player
            player = Player(
                username="swap_test_user",
                hashed_password=get_password_hash("test123"),
                x_coord=10,
                y_coord=10,
                map_id="samplemap",
            )
            session.add(player)
            await session.commit()
            await session.refresh(player)
            
            # Manually add Attack skill at level 1 (enough for bronze sword)
            # Note: Skills are stored in lowercase (e.g., "attack" not "Attack")
            attack_skill_result = await session.execute(
                select(Skill).where(Skill.name == "attack")
            )
            attack_skill = attack_skill_result.scalar_one_or_none()
            if attack_skill:
                player_skill = PlayerSkill(
                    player_id=player.id,
                    skill_id=attack_skill.id,
                    current_level=1,
                    experience=0,
                )
                session.add(player_skill)
                await session.commit()
            
            # Add first sword to inventory and equip it
            await InventoryService.add_item(session, player.id, bronze_sword.id)
            equip_result = await EquipmentService.equip_from_inventory(
                session, player.id, 0
            )
            assert equip_result.success is True, f"First equip failed: {equip_result.message}"
            
            # Verify equipped
            equipment = await EquipmentService.get_equipment(session, player.id)
            assert "weapon" in equipment
            
            # Add second sword to inventory
            await InventoryService.add_item(session, player.id, bronze_sword.id)
            
            # Equip second sword (should swap - put first back in inventory)
            swap_result = await EquipmentService.equip_from_inventory(
                session, player.id, 0
            )
            
            assert swap_result.success is True, f"Swap equip failed: {swap_result.message}"
            
            # Verify sword is still equipped (same item type)
            equipment = await EquipmentService.get_equipment(session, player.id)
            assert "weapon" in equipment
            assert equipment["weapon"].item.name == "bronze_sword"
            
            # Verify one sword is back in inventory (from the swap)
            inventory = await InventoryService.get_inventory(session, player.id)
            assert len(inventory) == 1
            assert inventory[0].item.name == "bronze_sword"
        
        await engine.dispose()
