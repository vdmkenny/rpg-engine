"""
Unit tests for Entity database model.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from server.src.models.entity import Entity

@pytest.mark.asyncio
async def test_create_entity(session: AsyncSession):
    """Test creating an entity in the database."""
    entity = Entity(
        name="TEST_GOBLIN",
        display_name="Test Goblin",
        description="A test creature",
        behavior="aggressive",
        is_attackable=True,
        level=1,
        xp_reward=10,
        skills={"ATTACK": 5, "HITPOINTS": 10},
        dialogue=["Graaah!", "Die!"],
        attack_bonus=2
    )
    
    session.add(entity)
    await session.commit()
    
    # Retrieve
    result = await session.execute(select(Entity).where(Entity.name == "TEST_GOBLIN"))
    stored_entity = result.scalar_one()
    
    assert stored_entity.display_name == "Test Goblin"
    assert stored_entity.behavior == "aggressive"
    assert stored_entity.skills == {"ATTACK": 5, "HITPOINTS": 10}
    assert len(stored_entity.dialogue) == 2
    assert stored_entity.attack_bonus == 2

@pytest.mark.asyncio
async def test_entity_json_fields(session: AsyncSession):
    """Test that JSON fields (skills, dialogue) are stored and retrieved correctly."""
    entity = Entity(
        name="TEST_SHOPKEEPER",
        display_name="Bob",
        behavior="merchant",
        skills={"HITPOINTS": 100},
        dialogue=["Welcome!", "Buy something!"]
    )
    
    session.add(entity)
    await session.commit()
    
    result = await session.execute(select(Entity).where(Entity.name == "TEST_SHOPKEEPER"))
    stored = result.scalar_one()
    
    assert isinstance(stored.skills, dict)
    assert stored.skills["HITPOINTS"] == 100
    
    assert isinstance(stored.dialogue, list)
    assert "Welcome!" in stored.dialogue

@pytest.mark.asyncio
async def test_entity_defaults(session: AsyncSession):
    """Test default values for entity fields."""
    entity = Entity(
        name="DEFAULT_TEST",
        display_name="Default One",
        behavior="passive"
    )
    
    session.add(entity)
    await session.commit()
    
    result = await session.execute(select(Entity).where(Entity.name == "DEFAULT_TEST"))
    stored = result.scalar_one()
    
    assert stored.is_attackable is True
    assert stored.level == 1
    assert stored.skills == {}
    assert stored.attack_bonus == 0
