"""
WebSocket integration tests for HP (hitpoints) system.

Covers:
- WELCOME message includes current_hp and max_hp
- HP in GAME_STATE_UPDATE entity payloads (current_hp, max_hp)
- PLAYER_DIED message when player dies
- PLAYER_RESPAWN message after respawn

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
    receive_message,
    receive_message_of_type,
    integration_client,
    get_player_id_from_welcome,
    get_test_valkey,
)


@SKIP_WS_INTEGRATION
class TestWelcomeHPFields:
    """Tests that WELCOME message includes HP information."""

    def test_welcome_includes_current_hp(self, integration_client):
        """WELCOME message should include current_hp field."""
        client = integration_client
        username = unique_username("hp_welcome")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value
            
            player_data = welcome["payload"]["player"]
            assert "current_hp" in player_data
            assert isinstance(player_data["current_hp"], int)
            assert player_data["current_hp"] > 0

    def test_welcome_includes_max_hp(self, integration_client):
        """WELCOME message should include max_hp field."""
        client = integration_client
        username = unique_username("hp_max")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value
            
            player_data = welcome["payload"]["player"]
            assert "max_hp" in player_data
            assert isinstance(player_data["max_hp"], int)
            assert player_data["max_hp"] > 0

    def test_welcome_current_hp_does_not_exceed_max_hp(self, integration_client):
        """WELCOME current_hp should not exceed max_hp."""
        client = integration_client
        username = unique_username("hp_check")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value
            
            player_data = welcome["payload"]["player"]
            assert player_data["current_hp"] <= player_data["max_hp"]

    def test_new_player_starts_with_full_hp(self, integration_client):
        """Newly registered player should start with full HP."""
        client = integration_client
        username = unique_username("hp_new")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value
            
            player_data = welcome["payload"]["player"]
            # New players start with current_hp == max_hp
            assert player_data["current_hp"] == player_data["max_hp"]


@SKIP_WS_INTEGRATION
class TestHPInValkey:
    """Tests that HP is properly tracked in Valkey cache."""

    def test_hp_stored_in_valkey_after_connect(self, integration_client):
        """Player's HP should be stored in Valkey after connecting."""
        client = integration_client
        username = unique_username("hp_valkey")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value
            
            # Check Valkey has the HP data
            test_valkey = get_test_valkey()
            player_key = f"player:{username}"
            player_data = test_valkey.get_hash_data(player_key)
            
            assert "current_hp" in player_data
            assert "max_hp" in player_data
            assert int(player_data["current_hp"]) > 0
            assert int(player_data["max_hp"]) > 0


@SKIP_WS_INTEGRATION
class TestHPReconnect:
    """Tests for HP persistence across reconnections."""

    def test_hp_persists_after_reconnect(self, integration_client):
        """Player's HP should persist across reconnections."""
        client = integration_client
        username = unique_username("hp_persist")
        token = register_and_login(client, username)

        # First connection - get initial HP
        with client.websocket_connect("/ws") as websocket:
            welcome1 = authenticate_websocket(websocket, token)
            assert welcome1["type"] == MessageType.WELCOME.value
            initial_hp = welcome1["payload"]["player"]["current_hp"]
            max_hp = welcome1["payload"]["player"]["max_hp"]

        # Second connection - HP should be the same
        with client.websocket_connect("/ws") as websocket:
            welcome2 = authenticate_websocket(websocket, token)
            assert welcome2["type"] == MessageType.WELCOME.value
            reconnect_hp = welcome2["payload"]["player"]["current_hp"]
            reconnect_max_hp = welcome2["payload"]["player"]["max_hp"]

        # HP should persist
        assert reconnect_hp == initial_hp
        assert reconnect_max_hp == max_hp


@SKIP_WS_INTEGRATION
class TestHPWithEquipment:
    """Tests for HP interaction with equipment."""

    def test_welcome_hp_reflects_equipment_bonus(self, integration_client):
        """
        WELCOME max_hp should include any equipment bonuses.
        
        Note: This test verifies the structure is correct. Without equipped items,
        max_hp should equal base HP from Hitpoints skill level.
        """
        client = integration_client
        username = unique_username("hp_equip")
        token = register_and_login(client, username)

        with client.websocket_connect("/ws") as websocket:
            welcome = authenticate_websocket(websocket, token)
            assert welcome["type"] == MessageType.WELCOME.value
            
            player_data = welcome["payload"]["player"]
            # Without equipment, max_hp should be base HP (10 for level 10 Hitpoints)
            assert player_data["max_hp"] >= 10  # At least base HP
            assert player_data["current_hp"] == player_data["max_hp"]


class TestHPMessageTypeStructure:
    """
    Tests for HP-related MessageType protocol definitions.
    
    These tests verify the protocol structure without requiring WebSocket integration.
    HP updates are now included in GAME_STATE_UPDATE (each player entity includes
    current_hp and max_hp). PLAYER_DIED and PLAYER_RESPAWN are separate message types
    for death/respawn broadcasts.
    """

    def test_player_died_message_type_exists(self):
        """PLAYER_DIED message type should be defined in protocol."""
        assert hasattr(MessageType, "PLAYER_DIED")
        assert MessageType.PLAYER_DIED.value == "PLAYER_DIED"

    def test_player_respawn_message_type_exists(self):
        """PLAYER_RESPAWN message type should be defined in protocol."""
        assert hasattr(MessageType, "PLAYER_RESPAWN")
        assert MessageType.PLAYER_RESPAWN.value == "PLAYER_RESPAWN"

    def test_game_state_update_exists(self):
        """GAME_STATE_UPDATE message type should be defined in protocol."""
        assert hasattr(MessageType, "GAME_STATE_UPDATE")
        assert MessageType.GAME_STATE_UPDATE.value == "GAME_STATE_UPDATE"


class TestDeathSequenceCallback:
    """
    Tests for the death sequence broadcast callback mechanism.
    
    The full_death_sequence method accepts a broadcast_callback for sending
    PLAYER_DIED and PLAYER_RESPAWN messages. These tests verify the callback
    is invoked correctly with the proper payload structure.
    """

    @pytest.mark.asyncio
    async def test_death_sequence_calls_died_callback(self):
        """Death sequence should call broadcast callback with PLAYER_DIED."""
        import pytest_asyncio
        from server.src.services.hp_service import HpService
        from server.src.tests.conftest import FakeValkey
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from server.src.models.base import Base
        from server.src.models.player import Player
        from server.src.core.security import get_password_hash
        from server.src.core.skills import HITPOINTS_START_LEVEL
        
        # Track broadcast calls
        broadcast_calls = []
        
        async def mock_broadcast(message_type, payload, username):
            broadcast_calls.append({
                "type": message_type,
                "payload": payload,
                "username": username,
            })
        
        # Set up in-memory database
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        AsyncSessionLocal = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with AsyncSessionLocal() as session:
            # Create test player
            player = Player(
                username="death_test_user",
                hashed_password=get_password_hash("test123"),
                x_coord=10,
                y_coord=10,
                map_id="samplemap",
                current_hp=HITPOINTS_START_LEVEL,
            )
            session.add(player)
            await session.commit()
            await session.refresh(player)
            
            # Set up fake Valkey
            fake_valkey = FakeValkey()
            await fake_valkey.hset(
                f"player:{player.username}",
                {
                    "x": "10",
                    "y": "10",
                    "map_id": "samplemap",
                    "current_hp": "0",  # Already at 0 HP (dead)
                    "max_hp": str(HITPOINTS_START_LEVEL),
                    "player_id": str(player.id),
                }
            )
            
            # Mock settings to avoid 5 second delay
            import server.src.core.config as config
            original_delay = config.settings.DEATH_RESPAWN_DELAY
            config.settings.DEATH_RESPAWN_DELAY = 0.0
            
            try:
                # Run death sequence
                result = await HpService.full_death_sequence(
                    session, fake_valkey, player.username, mock_broadcast
                )
                
                assert result.success is True
                
                # Check PLAYER_DIED was broadcast
                died_calls = [c for c in broadcast_calls if c["type"] == "PLAYER_DIED"]
                assert len(died_calls) == 1
                
                died_payload = died_calls[0]["payload"]
                assert died_payload["username"] == player.username
                assert "x" in died_payload
                assert "y" in died_payload
                assert "map_id" in died_payload
                
                # Check PLAYER_RESPAWN was broadcast
                respawn_calls = [c for c in broadcast_calls if c["type"] == "PLAYER_RESPAWN"]
                assert len(respawn_calls) == 1
                
                respawn_payload = respawn_calls[0]["payload"]
                assert respawn_payload["username"] == player.username
                assert "x" in respawn_payload
                assert "y" in respawn_payload
                assert "map_id" in respawn_payload
                assert "current_hp" in respawn_payload
                assert "max_hp" in respawn_payload
                
            finally:
                config.settings.DEATH_RESPAWN_DELAY = original_delay
        
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_death_sequence_without_callback(self):
        """Death sequence should work without broadcast callback."""
        from server.src.services.hp_service import HpService
        from server.src.tests.conftest import FakeValkey
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from server.src.models.base import Base
        from server.src.models.player import Player
        from server.src.core.security import get_password_hash
        from server.src.core.skills import HITPOINTS_START_LEVEL
        
        # Set up in-memory database
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        AsyncSessionLocal = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with AsyncSessionLocal() as session:
            # Create test player
            player = Player(
                username="death_nocb_user",
                hashed_password=get_password_hash("test123"),
                x_coord=10,
                y_coord=10,
                map_id="samplemap",
                current_hp=HITPOINTS_START_LEVEL,
            )
            session.add(player)
            await session.commit()
            await session.refresh(player)
            
            # Set up fake Valkey
            fake_valkey = FakeValkey()
            await fake_valkey.hset(
                f"player:{player.username}",
                {
                    "x": "10",
                    "y": "10",
                    "map_id": "samplemap",
                    "current_hp": "0",
                    "max_hp": str(HITPOINTS_START_LEVEL),
                    "player_id": str(player.id),
                }
            )
            
            # Mock settings
            import server.src.core.config as config
            original_delay = config.settings.DEATH_RESPAWN_DELAY
            config.settings.DEATH_RESPAWN_DELAY = 0.0
            
            try:
                # Run death sequence without callback
                result = await HpService.full_death_sequence(
                    session, fake_valkey, player.username, broadcast_callback=None
                )
                
                # Should still succeed
                assert result.success is True
                assert result.new_hp == HITPOINTS_START_LEVEL
                
            finally:
                config.settings.DEATH_RESPAWN_DELAY = original_delay
        
        await engine.dispose()
