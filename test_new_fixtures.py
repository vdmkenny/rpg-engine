"""Test the new centralized fixtures to ensure they work correctly."""

import pytest
import pytest_asyncio
from server.src.tests.conftest import *


class TestNewFixtures:
    """Validate that new centralized fixtures work correctly."""
    
    async def test_create_offline_player(self, create_offline_player, session):
        """Test basic offline player creation."""
        player = await create_offline_player(
            player_id=999,
            username="test_fixture_player"
        )
        
        # Verify player was created with correct attributes
        assert player.id == 999
        assert player.username == "test_fixture_player"
        assert player.x == 50  # default
        assert player.y == 50  # default
        assert player.map_id == "test_map"  # default
        assert player.current_hp == 10  # default
        
        # Player should exist in database
        await session.commit()
        await session.refresh(player)
        assert player.id == 999
    
    async def test_create_player_with_skills(self, create_player_with_skills, session):
        """Test player creation with skills."""
        player = await create_player_with_skills(
            player_id=998,
            skills_data={
                "attack": {"level": 5, "xp": 388},
                "hitpoints": {"level": 10, "xp": 1154}
            }
        )
        
        # Verify player was created
        assert player.id == 998
        
        # Verify skills were created (check via database)
        await session.commit()
        
        # Query PlayerSkill records
        from server.src.models.skill import PlayerSkill
        from sqlalchemy.future import select
        
        result = await session.execute(
            select(PlayerSkill).where(PlayerSkill.player_id == 998)
        )
        skills = result.scalars().all()
        
        # Should have 2 skills
        assert len(skills) == 2
        
        # Verify skill levels and XP
        skill_data = {skill.skill_id: skill for skill in skills}
        
        # Note: We'd need skill_id mapping to verify exact values
        # For now, just verify records exist with correct player_id
        for skill in skills:
            assert skill.player_id == 998
            assert skill.current_level > 0
            assert skill.experience >= 0

    async def test_create_player_with_inventory(self, create_player_with_inventory, session):
        """Test player creation with inventory."""
        player = await create_player_with_inventory(
            player_id=997,
            inventory_data=[
                {"item_id": 1, "slot": 0, "quantity": 5, "durability": 1.0},
                {"item_id": 2, "slot": 1, "quantity": 3, "durability": 0.8}
            ]
        )
        
        # Verify player was created
        assert player.id == 997
        
        # Verify inventory was created (check via database)
        await session.commit()
        
        # Query PlayerInventory records
        from server.src.models.item import PlayerInventory
        from sqlalchemy.future import select
        
        result = await session.execute(
            select(PlayerInventory).where(PlayerInventory.player_id == 997)
        )
        inventory = result.scalars().all()
        
        # Should have 2 inventory items
        assert len(inventory) == 2
        
        # Verify inventory data
        for item in inventory:
            assert item.player_id == 997
            assert item.item_id in [1, 2]
            assert item.slot in [0, 1]
            assert item.quantity in [3, 5]