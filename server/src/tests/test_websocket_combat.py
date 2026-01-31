"""
Integration tests for CMD_ATTACK WebSocket command.

These tests verify the full combat flow including:
- Sending attack commands
- Receiving combat results
- Combat event broadcasting
- XP rewards
- Entity death and respawn
"""

import os
import pytest
import asyncio
from server.src.tests.websocket_test_utils import (
    create_test_player,
    WebSocketTestClient,
)
from common.src.protocol import MessageType


# Skip if RUN_INTEGRATION_TESTS is not set
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="Integration tests require RUN_INTEGRATION_TESTS=1"
)


@pytest.mark.asyncio
class TestCombatIntegration:
    """Integration tests for player combat via WebSocket."""
    
    async def test_attack_entity_hit_success(self, test_client):
        """Test player successfully attacks entity and deals damage."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        # Create player and connect
        player_data = await create_test_player(
            test_client,
            username="combat_test_player",
            password="testpass123"
        )
        
        async with test_client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {player_data['access_token']}"}
        ) as websocket:
            async with WebSocketTestClient(websocket, default_timeout=5.0) as ws_client:
                # Wait for initial state update
                await ws_client.wait_for_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=3.0
                )
                
                # Spawn an entity adjacent to the player (player spawns at 25, 25)
                gsm = get_game_state_manager()
                instance_id = await gsm.spawn_entity_instance(
                    map_id="samplemap",
                    entity_name="GOBLIN",
                    spawn_x=26,  # Adjacent to player
                    spawn_y=25,
                    wander_radius=0,  # Don't wander away
                    spawn_point_id=1
                )
                
                assert instance_id is not None, "Failed to spawn entity"
                
                # Wait for entity to appear in game state
                await asyncio.sleep(0.2)
                
                # Send attack command
                response = await ws_client.send_command(
                    MessageType.CMD_ATTACK,
                    {
                        "target_type": "entity",
                        "target_id": instance_id
                    }
                )
                
                # Verify response
                assert response["type"] == MessageType.RESP_SUCCESS
                payload = response["payload"]
                assert "message" in payload
                assert "hit" in payload
                assert "damage" in payload
                assert "defender_hp" in payload
                assert "defender_died" in payload
                assert "xp_gained" in payload
                
                # Check combat event was broadcast
                try:
                    combat_event = await ws_client.wait_for_event(
                        MessageType.EVENT_COMBAT_ACTION,
                        timeout=1.0
                    )
                    
                    assert combat_event["attacker_type"] == "player"
                    assert combat_event["attacker_name"] == "combat_test_player"
                    assert combat_event["defender_type"] == "entity"
                    assert combat_event["defender_id"] == instance_id
                    assert "hit" in combat_event
                    assert "damage" in combat_event
                    assert "message" in combat_event
                except asyncio.TimeoutError:
                    pytest.fail("Combat event was not broadcast")
    
    async def test_attack_entity_kills_it(self, test_client):
        """Test player kills entity and entity enters dying state."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        # Create player with high combat stats
        player_data = await create_test_player(
            test_client,
            username="strong_player",
            password="testpass123"
        )
        
        async with test_client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {player_data['access_token']}"}
        ) as websocket:
            async with WebSocketTestClient(websocket, default_timeout=5.0) as ws_client:
                # Wait for initial state update
                await ws_client.wait_for_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=3.0
                )
                
                # Give player high combat stats
                gsm = get_game_state_manager()
                await gsm.set_player_skill(player_data["player_id"], "attack", level=99, xp=13034431)
                await gsm.set_player_skill(player_data["player_id"], "strength", level=99, xp=13034431)
                await gsm.set_player_skill(player_data["player_id"], "defence", level=99, xp=13034431)
                
                # Spawn a weak entity adjacent to player
                instance_id = await gsm.spawn_entity_instance(
                    map_id="samplemap",
                    entity_name="GOBLIN",
                    spawn_x=26,
                    spawn_y=25,
                    wander_radius=0,
                    spawn_point_id=1
                )
                
                await asyncio.sleep(0.2)
                
                # Attack multiple times until entity dies
                for attempt in range(20):  # Max 20 attacks
                    response = await ws_client.send_command(
                        MessageType.CMD_ATTACK,
                        {
                            "target_type": "entity",
                            "target_id": instance_id
                        }
                    )
                    
                    if response["type"] == MessageType.RESP_SUCCESS:
                        payload = response["payload"]
                        
                        # Check if entity died
                        if payload.get("defender_died"):
                            assert payload["defender_hp"] == 0
                            assert "died" in payload["message"].lower()
                            
                            # Wait for dying state to appear in game update
                            await asyncio.sleep(0.2)
                            
                            # Verify entity enters dying state
                            entity_data = await gsm.get_entity_instance(instance_id)
                            assert entity_data is not None
                            assert entity_data["state"] == "dying"
                            assert entity_data["current_hp"] == 0
                            
                            break
                    else:
                        # Check if entity is already dead
                        error = response["payload"].get("message", "")
                        if "already dead" in error.lower():
                            break
                    
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("Entity did not die after 20 attacks")
    
    async def test_attack_out_of_range_fails(self, test_client):
        """Test attack fails when target is out of range."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        player_data = await create_test_player(
            test_client,
            username="ranged_test_player",
            password="testpass123"
        )
        
        async with test_client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {player_data['access_token']}"}
        ) as websocket:
            async with WebSocketTestClient(websocket, default_timeout=5.0) as ws_client:
                await ws_client.wait_for_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=3.0
                )
                
                # Spawn entity far away (player at 25,25, entity at 30,30 = too far)
                gsm = get_game_state_manager()
                instance_id = await gsm.spawn_entity_instance(
                    map_id="samplemap",
                    entity_name="GOBLIN",
                    spawn_x=30,
                    spawn_y=30,
                    wander_radius=0,
                    spawn_point_id=1
                )
                
                await asyncio.sleep(0.2)
                
                # Try to attack
                response = await ws_client.send_command(
                    MessageType.CMD_ATTACK,
                    {
                        "target_type": "entity",
                        "target_id": instance_id
                    }
                )
                
                # Should fail with range error
                assert response["type"] == MessageType.RESP_ERROR
                payload = response["payload"]
                assert "too far" in payload["message"].lower()
    
    async def test_attack_dead_entity_fails(self, test_client):
        """Test attack on dead entity fails."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        player_data = await create_test_player(
            test_client,
            username="necro_test_player",
            password="testpass123"
        )
        
        async with test_client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {player_data['access_token']}"}
        ) as websocket:
            async with WebSocketTestClient(websocket, default_timeout=5.0) as ws_client:
                await ws_client.wait_for_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=3.0
                )
                
                # Spawn entity adjacent to player
                gsm = get_game_state_manager()
                instance_id = await gsm.spawn_entity_instance(
                    map_id="samplemap",
                    entity_name="GOBLIN",
                    spawn_x=26,
                    spawn_y=25,
                    wander_radius=0,
                    spawn_point_id=1
                )
                
                await asyncio.sleep(0.2)
                
                # Kill the entity by setting HP to 0
                await gsm.update_entity_hp(instance_id, 0)
                await gsm.despawn_entity(instance_id, death_tick=0, respawn_delay_seconds=60)
                
                await asyncio.sleep(0.2)
                
                # Try to attack dead entity
                response = await ws_client.send_command(
                    MessageType.CMD_ATTACK,
                    {
                        "target_type": "entity",
                        "target_id": instance_id
                    }
                )
                
                # Should fail
                assert response["type"] == MessageType.RESP_ERROR
                payload = response["payload"]
                assert "dead" in payload["message"].lower() or "cannot be attacked" in payload["message"].lower()
    
    async def test_attack_awards_xp(self, test_client):
        """Test successful attack awards XP."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        player_data = await create_test_player(
            test_client,
            username="xp_test_player",
            password="testpass123"
        )
        
        async with test_client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {player_data['access_token']}"}
        ) as websocket:
            async with WebSocketTestClient(websocket, default_timeout=5.0) as ws_client:
                await ws_client.wait_for_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=3.0
                )
                
                # Get initial XP
                gsm = get_game_state_manager()
                initial_attack_xp = await gsm.get_skill_xp(player_data["player_id"], "attack")
                initial_strength_xp = await gsm.get_skill_xp(player_data["player_id"], "strength")
                initial_hp_xp = await gsm.get_skill_xp(player_data["player_id"], "hitpoints")
                
                # Spawn entity
                instance_id = await gsm.spawn_entity_instance(
                    map_id="samplemap",
                    entity_name="GOBLIN",
                    spawn_x=26,
                    spawn_y=25,
                    wander_radius=0,
                    spawn_point_id=1
                )
                
                await asyncio.sleep(0.2)
                
                # Attack entity - keep trying until we get a hit
                for attempt in range(50):
                    response = await ws_client.send_command(
                        MessageType.CMD_ATTACK,
                        {
                            "target_type": "entity",
                            "target_id": instance_id
                        }
                    )
                    
                    if response["type"] == MessageType.RESP_SUCCESS:
                        payload = response["payload"]
                        
                        # Check if we hit and dealt damage
                        if payload.get("hit") and payload.get("damage") > 0:
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
                            
                            # Verify XP was actually added in GSM
                            final_attack_xp = await gsm.get_skill_xp(player_data["player_id"], "attack")
                            assert final_attack_xp > initial_attack_xp
                            
                            break
                    elif response["type"] == MessageType.RESP_ERROR:
                        error = response["payload"].get("message", "")
                        if "dead" in error.lower():
                            pytest.fail("Entity died before we could verify XP gain")
                        break
                    
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("No successful hit after 50 attempts")
    
    async def test_attack_nonexistent_entity_fails(self, test_client):
        """Test attack on non-existent entity fails."""
        player_data = await create_test_player(
            test_client,
            username="phantom_test_player",
            password="testpass123"
        )
        
        async with test_client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {player_data['access_token']}"}
        ) as websocket:
            async with WebSocketTestClient(websocket, default_timeout=5.0) as ws_client:
                await ws_client.wait_for_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=3.0
                )
                
                # Try to attack non-existent entity
                response = await ws_client.send_command(
                    MessageType.CMD_ATTACK,
                    {
                        "target_type": "entity",
                        "target_id": 999999
                    }
                )
                
                # Should fail
                assert response["type"] == MessageType.RESP_ERROR
                payload = response["payload"]
                assert "not found" in payload["message"].lower()
    
    async def test_attack_player_not_implemented(self, test_client):
        """Test player vs player combat is not yet implemented."""
        player_data = await create_test_player(
            test_client,
            username="pvp_test_player",
            password="testpass123"
        )
        
        async with test_client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {player_data['access_token']}"}
        ) as websocket:
            async with WebSocketTestClient(websocket, default_timeout=5.0) as ws_client:
                await ws_client.wait_for_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=3.0
                )
                
                # Try to attack another player
                response = await ws_client.send_command(
                    MessageType.CMD_ATTACK,
                    {
                        "target_type": "player",
                        "target_id": "other_player"
                    }
                )
                
                # Should fail with not implemented
                assert response["type"] == MessageType.RESP_ERROR
                payload = response["payload"]
                assert "not yet implemented" in payload["message"].lower()
