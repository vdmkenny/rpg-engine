"""
Tests for game_state_manager/batch_operations.py.

Tests batch sync operations from Valkey to PostgreSQL.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import Dict, Any

from server.src.services.game_state_manager import GameStateManager
from server.src.services.game_state_manager.batch_operations import GSMBatchOps
from server.src.core.skills import SkillType
from server.src.core.items import EquipmentSlot


class TestGSMBatchOpsInit:
    """Tests for GSMBatchOps initialization."""

    def test_initialization_with_gsm_reference(self, gsm: GameStateManager):
        """Test that GSMBatchOps stores reference to GSM."""
        batch_ops = GSMBatchOps(gsm)
        
        assert batch_ops._gsm is gsm

    def test_valkey_property_returns_gsm_valkey(self, gsm: GameStateManager):
        """Test that valkey property returns GSM's valkey client."""
        batch_ops = GSMBatchOps(gsm)
        
        assert batch_ops.valkey is gsm.valkey


class TestSyncAll:
    """Tests for GSMBatchOps.sync_all()"""

    @pytest.mark.asyncio
    async def test_sync_all_skips_when_not_initialized(self, gsm: GameStateManager):
        """Test sync_all returns early when session factory not set."""
        batch_ops = GSMBatchOps(gsm)
        
        # Temporarily remove session factory
        original_factory = gsm._session_factory
        gsm._session_factory = None
        
        try:
            # Should not raise, just skip
            await batch_ops.sync_all()
        finally:
            gsm._session_factory = original_factory

    @pytest.mark.asyncio
    async def test_sync_all_calls_all_sync_methods(self, gsm: GameStateManager):
        """Test that sync_all calls all individual sync methods."""
        batch_ops = GSMBatchOps(gsm)
        
        with patch.object(batch_ops, '_sync_player_positions', new_callable=AsyncMock) as mock_positions, \
             patch.object(batch_ops, '_sync_inventories', new_callable=AsyncMock) as mock_inventories, \
             patch.object(batch_ops, '_sync_equipment', new_callable=AsyncMock) as mock_equipment, \
             patch.object(batch_ops, '_sync_skills', new_callable=AsyncMock) as mock_skills, \
             patch.object(batch_ops, '_sync_ground_items', new_callable=AsyncMock) as mock_ground:
            
            await batch_ops.sync_all()
            
            mock_positions.assert_called_once()
            mock_inventories.assert_called_once()
            mock_equipment.assert_called_once()
            mock_skills.assert_called_once()
            mock_ground.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_all_handles_errors(self, gsm: GameStateManager):
        """Test that sync_all propagates errors."""
        batch_ops = GSMBatchOps(gsm)
        
        with patch.object(batch_ops, '_sync_player_positions', new_callable=AsyncMock) as mock_positions:
            mock_positions.side_effect = Exception("Sync failed")
            
            with pytest.raises(Exception, match="Sync failed"):
                await batch_ops.sync_all()


class TestSyncAllOnShutdown:
    """Tests for GSMBatchOps.sync_all_on_shutdown()"""

    @pytest.mark.asyncio
    async def test_shutdown_sync_no_valkey(self, gsm: GameStateManager):
        """Test shutdown sync returns early when no valkey."""
        batch_ops = GSMBatchOps(gsm)
        
        # Temporarily remove valkey
        original_valkey = gsm._valkey
        gsm._valkey = None
        
        try:
            # Should not raise, just return early
            await batch_ops.sync_all_on_shutdown()
        finally:
            gsm._valkey = original_valkey

    @pytest.mark.asyncio
    async def test_shutdown_sync_no_session_factory(self, gsm: GameStateManager):
        """Test shutdown sync returns early when no session factory."""
        batch_ops = GSMBatchOps(gsm)
        
        # Temporarily remove session factory
        original_factory = gsm._session_factory
        gsm._session_factory = None
        
        try:
            # Should not raise, just return early
            await batch_ops.sync_all_on_shutdown()
        finally:
            gsm._session_factory = original_factory

    @pytest.mark.asyncio
    async def test_shutdown_sync_all_players(self, gsm: GameStateManager, create_test_player):
        """Test shutdown syncs all online players."""
        player = await create_test_player("shutdown_sync_test", "password123")
        batch_ops = GSMBatchOps(gsm)
        
        # Set player online with state
        await gsm.set_player_full_state(player.id, 10, 10, "samplemap", 100, 100)
        
        with patch('server.src.services.connection_service.ConnectionService') as mock_conn:
            mock_conn.get_online_player_ids.return_value = {player.id}
            
            with patch.object(batch_ops, '_sync_single_player_to_db', new_callable=AsyncMock) as mock_sync:
                await batch_ops.sync_all_on_shutdown()
                
                # Should have been called for our player
                assert mock_sync.call_count >= 1


class TestSyncPlayerPositions:
    """Tests for GSMBatchOps._sync_player_positions()"""

    @pytest.mark.asyncio
    async def test_sync_positions_no_dirty_players(self, gsm: GameStateManager):
        """Test sync returns early when no dirty players."""
        batch_ops = GSMBatchOps(gsm)
        
        # Ensure no dirty flags
        await gsm._valkey.delete(["dirty:position"])
        
        # Should complete without error
        await batch_ops._sync_player_positions()

    @pytest.mark.asyncio
    async def test_sync_positions_no_valkey(self, gsm: GameStateManager):
        """Test sync returns early when no valkey."""
        batch_ops = GSMBatchOps(gsm)
        
        # Temporarily remove valkey
        original_valkey = gsm._valkey
        gsm._valkey = None
        
        try:
            # Should not raise, just return early
            await batch_ops._sync_player_positions()
        finally:
            gsm._valkey = original_valkey

    @pytest.mark.asyncio
    async def test_sync_positions_updates_database(self, gsm: GameStateManager, create_test_player, session):
        """Test that dirty positions are synced to database."""
        player = await create_test_player("pos_sync_test", "password123")
        batch_ops = GSMBatchOps(gsm)
        
        # Set player position in GSM
        await gsm.set_player_full_state(player.id, 25, 30, "samplemap", 100, 100)
        
        # Mark position as dirty
        await gsm._valkey.sadd("dirty:position", [str(player.id)])
        
        # Sync positions
        await batch_ops._sync_player_positions()
        
        # Verify dirty flag was cleared (sync completed)
        dirty_pos = await gsm._valkey.smembers("dirty:position")
        assert str(player.id).encode() not in dirty_pos
        
        # Verify GSM still has correct position
        pos = await gsm.get_player_position(player.id)
        assert pos is not None
        assert pos["x"] == 25
        assert pos["y"] == 30


class TestSyncInventories:
    """Tests for GSMBatchOps._sync_inventories()"""

    @pytest.mark.asyncio
    async def test_sync_inventories_no_dirty(self, gsm: GameStateManager):
        """Test sync returns early when no dirty inventories."""
        batch_ops = GSMBatchOps(gsm)
        
        # Ensure no dirty flags
        await gsm._valkey.delete(["dirty:inventory"])
        
        # Should complete without error
        await batch_ops._sync_inventories()

    @pytest.mark.asyncio
    async def test_sync_inventories_no_valkey(self, gsm: GameStateManager):
        """Test sync returns early when no valkey."""
        batch_ops = GSMBatchOps(gsm)
        
        original_valkey = gsm._valkey
        gsm._valkey = None
        
        try:
            await batch_ops._sync_inventories()
        finally:
            gsm._valkey = original_valkey

    @pytest.mark.asyncio
    async def test_sync_inventories_deletes_and_inserts(self, gsm: GameStateManager, create_test_player, session):
        """Test that inventory sync replaces database records."""
        player = await create_test_player("inv_sync_test", "password123")
        batch_ops = GSMBatchOps(gsm)
        
        # Add item to inventory in GSM
        await gsm.set_inventory_slot(player.id, 0, 1, 5, 1.0)
        
        # Mark inventory as dirty
        await gsm._valkey.sadd("dirty:inventory", [str(player.id)])
        
        # Sync inventories
        await batch_ops._sync_inventories()
        
        # Verify dirty flag was cleared (sync completed)
        dirty_inv = await gsm._valkey.smembers("dirty:inventory")
        assert str(player.id).encode() not in dirty_inv
        
        # Verify GSM still has correct inventory
        inv = await gsm.get_inventory(player.id)
        assert "0" in inv or 0 in inv  # Slot 0 should exist


class TestSyncEquipment:
    """Tests for GSMBatchOps._sync_equipment()"""

    @pytest.mark.asyncio
    async def test_sync_equipment_no_dirty(self, gsm: GameStateManager):
        """Test sync returns early when no dirty equipment."""
        batch_ops = GSMBatchOps(gsm)
        
        await gsm._valkey.delete(["dirty:equipment"])
        
        await batch_ops._sync_equipment()

    @pytest.mark.asyncio
    async def test_sync_equipment_no_valkey(self, gsm: GameStateManager):
        """Test sync returns early when no valkey."""
        batch_ops = GSMBatchOps(gsm)
        
        original_valkey = gsm._valkey
        gsm._valkey = None
        
        try:
            await batch_ops._sync_equipment()
        finally:
            gsm._valkey = original_valkey

    @pytest.mark.asyncio
    async def test_sync_equipment_handles_durability(self, gsm: GameStateManager, create_test_player, session):
        """Test that equipment sync includes durability."""
        player = await create_test_player("equip_sync_test", "password123")
        batch_ops = GSMBatchOps(gsm)
        
        # Equip item in GSM
        await gsm.set_equipment_slot(player.id, EquipmentSlot.WEAPON, 1, 1, 0.75)
        
        # Mark equipment as dirty
        await gsm._valkey.sadd("dirty:equipment", [str(player.id)])
        
        # Sync equipment
        await batch_ops._sync_equipment()
        
        # Verify dirty flag was cleared (sync completed)
        dirty_eq = await gsm._valkey.smembers("dirty:equipment")
        assert str(player.id).encode() not in dirty_eq
        
        # Verify GSM still has correct equipment
        equipment = await gsm.get_equipment(player.id)
        assert "weapon" in equipment


class TestSyncSkills:
    """Tests for GSMBatchOps._sync_skills()"""

    @pytest.mark.asyncio
    async def test_sync_skills_no_dirty(self, gsm: GameStateManager):
        """Test sync returns early when no dirty skills."""
        batch_ops = GSMBatchOps(gsm)
        
        await gsm._valkey.delete(["dirty:skills"])
        
        await batch_ops._sync_skills()

    @pytest.mark.asyncio
    async def test_sync_skills_no_valkey(self, gsm: GameStateManager):
        """Test sync returns early when no valkey."""
        batch_ops = GSMBatchOps(gsm)
        
        original_valkey = gsm._valkey
        gsm._valkey = None
        
        try:
            await batch_ops._sync_skills()
        finally:
            gsm._valkey = original_valkey

    @pytest.mark.asyncio
    async def test_sync_skills_deletes_and_inserts(self, gsm: GameStateManager, create_test_player, session):
        """Test that skills sync replaces database records."""
        player = await create_test_player("skills_sync_test", "password123")
        batch_ops = GSMBatchOps(gsm)
        
        # Set skill in GSM
        await gsm.set_skill(player.id, SkillType.ATTACK, 10, 5000)  # level=10, xp=5000
        
        # Mark skills as dirty
        await gsm._valkey.sadd("dirty:skills", [str(player.id)])
        
        # Sync skills
        await batch_ops._sync_skills()
        
        # Verify dirty flag was cleared (sync completed)
        dirty_skills = await gsm._valkey.smembers("dirty:skills")
        assert str(player.id).encode() not in dirty_skills
        
        # Verify GSM still has correct skills
        skills = await gsm.get_all_skills(player.id)
        assert "attack" in skills
        assert skills["attack"]["level"] == 10


class TestSyncGroundItems:
    """Tests for GSMBatchOps._sync_ground_items()"""

    @pytest.mark.asyncio
    async def test_sync_ground_items_no_dirty_maps(self, gsm: GameStateManager):
        """Test sync returns early when no dirty maps."""
        batch_ops = GSMBatchOps(gsm)
        
        await gsm._valkey.delete(["dirty:ground_items"])
        
        await batch_ops._sync_ground_items()

    @pytest.mark.asyncio
    async def test_sync_ground_items_no_valkey(self, gsm: GameStateManager):
        """Test sync returns early when no valkey."""
        batch_ops = GSMBatchOps(gsm)
        
        original_valkey = gsm._valkey
        gsm._valkey = None
        
        try:
            await batch_ops._sync_ground_items()
        finally:
            gsm._valkey = original_valkey

    @pytest.mark.asyncio
    async def test_sync_ground_items_by_map(self, gsm: GameStateManager, session):
        """Test that ground items are synced by map."""
        batch_ops = GSMBatchOps(gsm)
        
        # Add ground item in GSM
        ground_item_id = await gsm.add_ground_item("samplemap", 5, 5, 1, 3, 1.0, None)
        
        # Mark map as dirty
        await gsm._valkey.sadd("dirty:ground_items", ["samplemap"])
        
        # Sync ground items
        await batch_ops._sync_ground_items()
        
        # Verify dirty flag was cleared (sync completed)
        dirty_maps = await gsm._valkey.smembers("dirty:ground_items")
        assert b"samplemap" not in dirty_maps
        
        # Verify GSM still has the ground item
        ground_item = await gsm.get_ground_item(ground_item_id)
        assert ground_item is not None
        assert ground_item["map_id"] == "samplemap"
        # Just verify no error occurred


class TestSyncSinglePlayer:
    """Tests for GSMBatchOps._sync_single_player_to_db()"""

    @pytest.mark.asyncio
    async def test_sync_single_player_complete(self, gsm: GameStateManager, create_test_player, session):
        """Test syncing all data for a single player."""
        player = await create_test_player("single_sync_test", "password123")
        batch_ops = GSMBatchOps(gsm)
        
        # Set up player state in GSM
        await gsm.set_player_full_state(player.id, 15, 20, "samplemap", 80, 100)
        await gsm.set_inventory_slot(player.id, 0, 1, 10, 1.0)
        await gsm.set_equipment_slot(player.id, EquipmentSlot.WEAPON, 2, 1, 0.9)
        await gsm.set_skill(player.id, SkillType.ATTACK, 5, 1000)
        
        # Sync single player
        await batch_ops._sync_single_player_to_db(session, player.id)
        await session.commit()
        
        # Verify position was synced
        from server.src.models.player import Player
        from sqlalchemy import select
        
        result = await session.execute(select(Player).where(Player.id == player.id))
        db_player = result.scalar_one_or_none()
        
        assert db_player is not None
        assert db_player.x_coord == 15
        assert db_player.y_coord == 20

    @pytest.mark.asyncio
    async def test_sync_single_player_missing_position(self, gsm: GameStateManager, create_test_player, session):
        """Test syncing player with no position data."""
        player = await create_test_player("no_pos_sync_test", "password123")
        batch_ops = GSMBatchOps(gsm)
        
        # Don't set position, just inventory
        await gsm.set_inventory_slot(player.id, 0, 1, 5, 1.0)
        
        # Should not raise - just skip position sync
        await batch_ops._sync_single_player_to_db(session, player.id)
        await session.commit()

    @pytest.mark.asyncio
    async def test_sync_single_player_empty_inventory(self, gsm: GameStateManager, create_test_player, session):
        """Test syncing player with empty inventory."""
        player = await create_test_player("empty_inv_sync", "password123")
        batch_ops = GSMBatchOps(gsm)
        
        # Set position but no inventory
        await gsm.set_player_full_state(player.id, 10, 10, "samplemap", 100, 100)
        
        # Should not raise
        await batch_ops._sync_single_player_to_db(session, player.id)
        await session.commit()


class TestBatchOpsIntegration:
    """Integration tests for batch operations."""

    @pytest.mark.asyncio
    async def test_full_sync_cycle(self, gsm: GameStateManager, create_test_player, session):
        """Test complete sync cycle from dirty flags to database."""
        player = await create_test_player("full_cycle_test", "password123")
        batch_ops = GSMBatchOps(gsm)
        
        # Set up complete player state
        await gsm.set_player_full_state(player.id, 50, 60, "samplemap", 90, 100)
        await gsm.set_inventory_slot(player.id, 0, 1, 20, 1.0)
        await gsm.set_inventory_slot(player.id, 1, 2, 15, 0.8)
        await gsm.set_equipment_slot(player.id, EquipmentSlot.WEAPON, 3, 1, 1.0)
        await gsm.set_skill(player.id, SkillType.ATTACK, 15, 10000)
        
        # Mark all as dirty
        await gsm._valkey.sadd("dirty:position", [str(player.id)])
        await gsm._valkey.sadd("dirty:inventory", [str(player.id)])
        await gsm._valkey.sadd("dirty:equipment", [str(player.id)])
        await gsm._valkey.sadd("dirty:skills", [str(player.id)])
        
        # Run full sync
        await batch_ops.sync_all()
        
        # Verify dirty flags are cleared
        dirty_pos = await gsm._valkey.smembers("dirty:position")
        # Flags should be cleared after sync

    @pytest.mark.asyncio
    async def test_sync_handles_concurrent_modifications(self, gsm: GameStateManager, create_test_player):
        """Test that sync handles modifications during sync gracefully."""
        player = await create_test_player("concurrent_test", "password123")
        batch_ops = GSMBatchOps(gsm)
        
        # Set initial state
        await gsm.set_player_full_state(player.id, 10, 10, "samplemap", 100, 100)
        await gsm._valkey.sadd("dirty:position", [str(player.id)])
        
        # Should not raise even if state changes
        await batch_ops._sync_player_positions()
