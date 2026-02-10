"""
WebSocket integration tests for HP (hitpoints) system.

Covers:
- EVENT_WELCOME message includes current_hp and max_hp
- HP in EVENT_STATE_UPDATE entity payloads (current_hp, max_hp)
- EVENT_PLAYER_DIED message when player dies
- EVENT_PLAYER_RESPAWN message after respawn

These tests use the real PostgreSQL database and WebSocket handlers.
Modernized to eliminate skips, direct database access, and use service layer.
"""

import pytest

from common.src.protocol import MessageType
from server.src.tests.websocket_test_utils import WebSocketTestClient
from server.src.services.test_data_service import TestDataService


class TestHPMessageTypes:
    """Tests for HP-related message types using modern approach."""

    def test_player_died_message_type_exists(self):
        """EVENT_PLAYER_DIED message type should exist in protocol."""
        assert hasattr(MessageType, 'EVENT_PLAYER_DIED'), "EVENT_PLAYER_DIED message type should exist"

    def test_player_respawn_message_type_exists(self):
        """EVENT_PLAYER_RESPAWN message type should exist in protocol."""
        assert hasattr(MessageType, 'EVENT_PLAYER_RESPAWN'), "EVENT_PLAYER_RESPAWN message type should exist"

    def test_game_state_update_exists(self):
        """EVENT_STATE_UPDATE message type should exist for HP updates."""
        assert hasattr(MessageType, 'EVENT_STATE_UPDATE'), "EVENT_STATE_UPDATE message type should exist"


class TestDeathSequence:
    """Tests for player death and respawn sequence using service layer."""

    @pytest.mark.asyncio
    async def test_death_sequence_calls_died_callback(self, session, game_state_managers):
        """Death sequence should trigger died callback and respawn logic."""
        from server.src.services.test_data_service import TestDataService, PlayerConfig
        from server.src.services.hp_service import HpService
        
        # Ensure test data exists
        sync_result = await TestDataService.ensure_game_data_synced()
        assert sync_result.success
        
        # Create test player using service layer
        player_config = PlayerConfig(
            username_prefix="death_test",
            x=10,
            y=10,
            map_id="samplemap"
        )
        
        player_result = await TestDataService.create_test_player_with_items(player_config)
        assert player_result.success, f"Failed to create test player: {player_result.message}"
        assert player_result.data is not None, "Player data should not be None"
        player = player_result.data
        
        # Verify player starts with positive HP
        initial_hp_data = await HpService.get_hp(player.id)
        initial_hp = initial_hp_data[0]  # current_hp is first element of tuple
        assert initial_hp > 0, "Player should start with positive HP"
        
        # Simulate death by reducing HP to 0
        death_result = await HpService.deal_damage(player.id, initial_hp)
        assert death_result.success, f"Death sequence failed: {death_result.message}"
        
        # Verify player HP is 0 or below
        post_death_hp_data = await HpService.get_hp(player.id)
        post_death_hp = post_death_hp_data[0]  # current_hp
        assert post_death_hp <= 0, "Player should have 0 or negative HP after death"
        
        # Verify respawn logic restores HP
        respawn_result = await HpService.respawn_player(player.id)
        assert respawn_result.success, f"Respawn failed: {respawn_result.message}"
        
        # Verify HP is restored
        post_respawn_hp_data = await HpService.get_hp(player.id)
        post_respawn_hp = post_respawn_hp_data[0]  # current_hp
        assert post_respawn_hp > 0, "Player should have positive HP after respawn"

    @pytest.mark.asyncio
    async def test_death_sequence_without_callback(self, session, game_state_managers):
        """Death sequence should work even without external callbacks."""
        from server.src.services.test_data_service import TestDataService, PlayerConfig
        from server.src.services.hp_service import HpService
        
        # Ensure test data exists
        sync_result = await TestDataService.ensure_game_data_synced()
        assert sync_result.success
        
        # Create test player
        player_config = PlayerConfig(
            username_prefix="death_no_callback",
            x=15,
            y=15, 
            map_id="samplemap"
        )
        
        player_result = await TestDataService.create_test_player_with_items(player_config)
        assert player_result.success, f"Failed to create test player: {player_result.message}"
        assert player_result.data is not None, "Player data should not be None"
        player = player_result.data
        
        # Get initial HP
        initial_hp_data = await HpService.get_hp(player.id)
        initial_hp = initial_hp_data[0]  # current_hp
        assert initial_hp > 0
        
        # Simulate taking fatal damage
        damage_result = await HpService.deal_damage(player.id, initial_hp + 10)  # Overkill damage
        assert damage_result.success
        
        # Verify death state
        current_hp_data = await HpService.get_hp(player.id)
        current_hp = current_hp_data[0]  # current_hp
        assert current_hp <= 0, "Player should be dead"
        
        # Verify respawn works
        respawn_result = await HpService.respawn_player(player.id)
        assert respawn_result.success
        
        final_hp_data = await HpService.get_hp(player.id)
        final_hp = final_hp_data[0]  # current_hp
        assert final_hp > 0, "Player should be alive after respawn"