"""
Integration tests for CMD_ATTACK WebSocket command.

These tests verify the full combat flow including:
- Sending attack commands
- Receiving combat results
- Combat event broadcasting
- XP rewards
- Entity death and respawn
"""

import pytest
import asyncio

from common.src.protocol import MessageType
from server.src.core.entities import EntityType
from server.src.tests.websocket_test_utils import (
    WebSocketTestClient,
    ErrorResponseError,
    ENTITY_SPAWN_WAIT,
)


# Constants for entity spawning (GOBLIN stats)
GOBLIN_MAX_HP = 10


@pytest.mark.integration
@pytest.mark.asyncio
class TestCombatIntegration:
    """Integration tests for player combat via WebSocket."""
    
    async def _spawn_test_entity(self, entity_manager, ref_manager, entity_name, map_id, x, y, max_hp):
        """Helper to spawn an entity by name, looking up the entity ID first."""
        from server.src.core.monsters import MonsterID
        
        # Get entity ID from enum
        entity_enum = getattr(MonsterID, entity_name, None)
        if not entity_enum:
            raise ValueError(f"Unknown entity: {entity_name}")
        
        entity_id = entity_enum.value.value if hasattr(entity_enum.value, 'value') else entity_enum.value
        
        return await entity_manager.spawn_entity_instance(
            entity_id=entity_id,
            map_id=map_id,
            x=x,
            y=y,
            current_hp=max_hp,
            max_hp=max_hp,
            state="idle",
        )
    
    async def test_attack_entity_success(self, spawned_test_entities, test_client: WebSocketTestClient):
        """Test player successfully attacks entity and deals damage."""
        # Use pre-spawned entity from fixture
        instance_id = spawned_test_entities["GOBLIN"]
        
        # Wait for entity to appear in game state
        await asyncio.sleep(ENTITY_SPAWN_WAIT)
        
        # Send attack command
        response = await test_client.send_command(
            MessageType.CMD_ATTACK,
            {
                "target_type": "entity",
                "target_id": instance_id
            }
        )
        
        # Verify response contains expected fields
        assert response.type == MessageType.RESP_SUCCESS
        payload = response.payload
        assert "message" in payload
        assert "hit" in payload
        assert "damage" in payload
        assert "defender_hp" in payload
        assert "defender_died" in payload
        assert "xp_gained" in payload
    
    async def test_attack_entity_kills_it(self, spawned_test_entities, test_client: WebSocketTestClient):
        """Test player kills entity and entity enters dying state."""
        from server.src.services.game_state import get_entity_manager
        
        entity_manager = get_entity_manager()
        
        # Use pre-spawned entity from fixture
        instance_id = spawned_test_entities["GOBLIN"]
        
        # Reduce entity HP to 1 so it dies on first successful hit
        key = f"entity_instance:{instance_id}"
        entity_data = await entity_manager._get_from_valkey(key)
        if entity_data:
            entity_data["current_hp"] = 1
            await entity_manager._cache_in_valkey(key, entity_data, 1800)
        
        await asyncio.sleep(ENTITY_SPAWN_WAIT)
        
        # Attack until entity dies
        entity_died = False
        for attempt in range(100):
            try:
                response = await test_client.send_command(
                    MessageType.CMD_ATTACK,
                    {
                        "target_type": "entity",
                        "target_id": instance_id
                    }
                )
                
                if response.type == MessageType.RESP_SUCCESS:
                    payload = response.payload
                    
                    if payload.get("defender_died"):
                        entity_died = True
                        assert payload["defender_hp"] == 0
                        
                        await asyncio.sleep(ENTITY_SPAWN_WAIT)
                        
                        entity_data = await entity_manager.get_entity_instance(instance_id)
                        assert entity_data is not None
                        assert entity_data["state"] == "dying"
                        assert entity_data["current_hp"] == 0
                        
                        break
                    
            except ErrorResponseError as e:
                if "dead" in str(e).lower():
                    entity_died = True
                    break
                raise
            
            await asyncio.sleep(0.1)
        
        assert entity_died, "Entity did not die after 100 attacks"
    
    async def test_attack_out_of_range_fails(self, spawned_test_entities, test_client: WebSocketTestClient):
        """Test attack fails when target is out of range."""
        from server.src.services.game_state import get_entity_manager
        
        entity_manager = get_entity_manager()
        
        # Use pre-spawned entity from fixture (at 12, 12 - close to player at 10, 10)
        instance_id = spawned_test_entities["GOBLIN"]
        
        # Move entity far away from player to test range check
        key = f"entity_instance:{instance_id}"
        entity_data = await entity_manager._get_from_valkey(key)
        if entity_data:
            entity_data["x"] = 30
            entity_data["y"] = 30  # Far away from player at (10, 10)
            await entity_manager._cache_in_valkey(key, entity_data, 1800)
        
        await asyncio.sleep(ENTITY_SPAWN_WAIT)
        
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_ATTACK,
                {
                    "target_type": "entity",
                    "target_id": instance_id
                }
            )
        
        assert "too far" in str(exc_info.value).lower()
    
    async def test_attack_dead_entity_fails(self, spawned_test_entities, test_client: WebSocketTestClient):
        """Test attack on dead entity fails."""
        from server.src.services.game_state import get_entity_manager
        
        entity_manager = get_entity_manager()
        
        # Use pre-spawned entity from fixture
        instance_id = spawned_test_entities["GOBLIN"]
        
        await asyncio.sleep(ENTITY_SPAWN_WAIT)
        
        # Kill the entity via entity_manager
        key = f"entity_instance:{instance_id}"
        data = await entity_manager._get_from_valkey(key)
        if data:
            data["current_hp"] = 0
            data["state"] = "dying"
            await entity_manager._cache_in_valkey(key, data, 1800)
        
        await asyncio.sleep(ENTITY_SPAWN_WAIT)
        
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_ATTACK,
                {
                    "target_type": "entity",
                    "target_id": instance_id
                }
            )
        
        error_msg = str(exc_info.value).lower()
        assert "dead" in error_msg or "cannot be attacked" in error_msg
    
    async def test_attack_awards_xp(self, spawned_test_entities, test_client: WebSocketTestClient):
        """Test successful attack awards XP."""
        # Use pre-spawned entity from fixture
        instance_id = spawned_test_entities["GOBLIN"]
        
        await asyncio.sleep(ENTITY_SPAWN_WAIT)
        
        hit_with_damage = False
        for attempt in range(50):
            try:
                response = await test_client.send_command(
                    MessageType.CMD_ATTACK,
                    {
                        "target_type": "entity",
                        "target_id": instance_id
                    }
                )
                
                if response.type == MessageType.RESP_SUCCESS:
                    payload = response.payload
                    
                    if payload.get("hit") and payload.get("damage", 0) > 0:
                        hit_with_damage = True
                        xp_gained = payload.get("xp_gained", {})
                        
                        assert "attack" in xp_gained
                        assert "strength" in xp_gained
                        assert "hitpoints" in xp_gained
                        
                        damage = payload["damage"]
                        assert xp_gained["attack"] == damage * 4
                        assert xp_gained["strength"] == damage * 4
                        assert xp_gained["hitpoints"] == int(damage * 4 / 3)
                        
                        break
                        
            except ErrorResponseError as e:
                if "dead" in str(e).lower():
                    pytest.fail("Entity died before we could verify XP gain")
                raise
            
            await asyncio.sleep(0.1)
        
        assert hit_with_damage, "No successful hit after 50 attempts"
    
    async def test_attack_nonexistent_entity_fails(self, test_client: WebSocketTestClient):
        """Test attack on non-existent entity fails."""
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_ATTACK,
                {
                    "target_type": "entity",
                    "target_id": 999999
                }
            )
        
        assert "not found" in str(exc_info.value).lower()
    
    async def test_attack_player_not_implemented(self, test_client: WebSocketTestClient):
        """Test player vs player combat is not yet implemented."""
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_ATTACK,
                {
                    "target_type": "player",
                    "target_id": "other_player"
                }
            )
        
        assert "not" in str(exc_info.value).lower() and "implemented" in str(exc_info.value).lower()
