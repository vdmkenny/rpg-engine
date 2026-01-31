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
    
    async def test_attack_entity_success(self, test_client: WebSocketTestClient):
        """Test player successfully attacks entity and deals damage."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        # test_client player is at position (10, 10) on "samplemap"
        spawn_x, spawn_y = 11, 10  # Adjacent to player
        
        # Spawn an entity near the player
        instance_id = await gsm.spawn_entity_instance(
            entity_name="GOBLIN",
            map_id="samplemap",
            x=spawn_x,
            y=spawn_y,
            spawn_x=spawn_x,
            spawn_y=spawn_y,
            max_hp=GOBLIN_MAX_HP,
            wander_radius=0,  # Don't wander away
            spawn_point_id=1
        )
        
        assert instance_id is not None, "Failed to spawn entity"
        
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
    
    async def test_attack_entity_kills_it(self, test_client: WebSocketTestClient):
        """Test player kills entity and entity enters dying state."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        spawn_x, spawn_y = 11, 10  # Adjacent to player at (10, 10)
        
        # Spawn a very weak entity (1 HP) so it dies on first successful hit
        # This makes the test reliable regardless of player's combat stats
        instance_id = await gsm.spawn_entity_instance(
            entity_name="GOBLIN",
            map_id="samplemap",
            x=spawn_x,
            y=spawn_y,
            spawn_x=spawn_x,
            spawn_y=spawn_y,
            max_hp=1,  # 1 HP - dies on first hit
            wander_radius=0,
            spawn_point_id=1
        )
        
        await asyncio.sleep(ENTITY_SPAWN_WAIT)
        
        # Attack until entity dies (with low stats, may need multiple attempts to hit)
        entity_died = False
        for attempt in range(100):  # Max 100 attacks (plenty for random hit chance)
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
                    
                    # Check if entity died
                    if payload.get("defender_died"):
                        entity_died = True
                        assert payload["defender_hp"] == 0
                        
                        # Wait for dying state to appear
                        await asyncio.sleep(ENTITY_SPAWN_WAIT)
                        
                        # Verify entity enters dying state
                        entity_data = await gsm.get_entity_instance(instance_id)
                        assert entity_data is not None
                        assert entity_data["state"] == "dying"
                        assert entity_data["current_hp"] == 0
                        
                        break
                    
            except ErrorResponseError as e:
                # Check if entity is already dead
                if "dead" in str(e).lower():
                    entity_died = True
                    break
                raise
            
            await asyncio.sleep(0.1)
        
        assert entity_died, "Entity did not die after 100 attacks"
    
    async def test_attack_out_of_range_fails(self, test_client: WebSocketTestClient):
        """Test attack fails when target is out of range."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        spawn_x, spawn_y = 30, 30  # Far away from player at (10, 10)
        
        # Spawn entity far away
        instance_id = await gsm.spawn_entity_instance(
            entity_name="GOBLIN",
            map_id="samplemap",
            x=spawn_x,
            y=spawn_y,
            spawn_x=spawn_x,
            spawn_y=spawn_y,
            max_hp=GOBLIN_MAX_HP,
            wander_radius=0,
            spawn_point_id=1
        )
        
        await asyncio.sleep(ENTITY_SPAWN_WAIT)
        
        # Try to attack - should fail with range error
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_ATTACK,
                {
                    "target_type": "entity",
                    "target_id": instance_id
                }
            )
        
        assert "too far" in str(exc_info.value).lower()
    
    async def test_attack_dead_entity_fails(self, test_client: WebSocketTestClient):
        """Test attack on dead entity fails."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        spawn_x, spawn_y = 11, 10  # Adjacent to player
        
        # Spawn entity adjacent to player
        instance_id = await gsm.spawn_entity_instance(
            entity_name="GOBLIN",
            map_id="samplemap",
            x=spawn_x,
            y=spawn_y,
            spawn_x=spawn_x,
            spawn_y=spawn_y,
            max_hp=GOBLIN_MAX_HP,
            wander_radius=0,
            spawn_point_id=1
        )
        
        await asyncio.sleep(ENTITY_SPAWN_WAIT)
        
        # Kill the entity by setting HP to 0
        await gsm.update_entity_hp(instance_id, 0)
        await gsm.despawn_entity(instance_id, death_tick=0, respawn_delay_seconds=60)
        
        await asyncio.sleep(ENTITY_SPAWN_WAIT)
        
        # Try to attack dead entity - should fail
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
    
    async def test_attack_awards_xp(self, test_client: WebSocketTestClient):
        """Test successful attack awards XP."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        spawn_x, spawn_y = 11, 10  # Adjacent to player
        
        # Spawn entity adjacent to player
        instance_id = await gsm.spawn_entity_instance(
            entity_name="GOBLIN",
            map_id="samplemap",
            x=spawn_x,
            y=spawn_y,
            spawn_x=spawn_x,
            spawn_y=spawn_y,
            max_hp=GOBLIN_MAX_HP,
            wander_radius=0,
            spawn_point_id=1
        )
        
        await asyncio.sleep(ENTITY_SPAWN_WAIT)
        
        # Attack entity until we get a hit that deals damage
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
                    
                    # Check if we hit and dealt damage
                    if payload.get("hit") and payload.get("damage", 0) > 0:
                        hit_with_damage = True
                        xp_gained = payload.get("xp_gained", {})
                        
                        # Verify XP was awarded
                        assert "attack" in xp_gained
                        assert "strength" in xp_gained
                        assert "hitpoints" in xp_gained
                        
                        # Verify XP values are correct (4 XP per damage for attack/strength, 4/3 for HP)
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
        # Try to attack non-existent entity
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
        # Try to attack another player
        with pytest.raises(ErrorResponseError) as exc_info:
            await test_client.send_command(
                MessageType.CMD_ATTACK,
                {
                    "target_type": "player",
                    "target_id": "other_player"
                }
            )
        
        assert "not" in str(exc_info.value).lower() and "implemented" in str(exc_info.value).lower()
