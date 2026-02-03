"""
Test fixtures for unit tests.

Fast fixtures that don't require database access.
"""

import pytest
import pytest_asyncio


@pytest.fixture
def sample_skill_data():
    """Sample skill data for unit tests."""
    return {
        "attack": {"level": 50, "experience": 101333},
        "strength": {"level": 50, "experience": 101333},
        "defence": {"level": 50, "experience": 101333},
        "hitpoints": {"level": 60, "experience": 200000},
    }


@pytest.fixture
def sample_inventory_data():
    """Sample inventory data for unit tests."""
    return {
        0: {"item_id": 1, "quantity": 50, "current_durability": 1.0},  # 50 arrows
        1: {"item_id": 2, "quantity": 1, "current_durability": 1.0},   # 1 sword
        2: {"item_id": 3, "quantity": 10, "current_durability": 1.0},  # 10 potions
    }


@pytest.fixture
def sample_equipment_data():
    """Sample equipment data for unit tests."""
    return {
        "HEAD": {"item_id": 101, "quantity": 1, "current_durability": 1.0},
        "BODY": {"item_id": 102, "quantity": 1, "current_durability": 1.0},
        "WEAPON": {"item_id": 2, "quantity": 1, "current_durability": 1.0},
    }


@pytest.fixture
def sample_combat_stats():
    """Sample combat stats for unit tests."""
    return {
        "attack_level": 50,
        "strength_level": 50,
        "defence_level": 50,
        "attack_bonus": 20,
        "strength_bonus": 20,
        "defence_bonus": 20,
        "current_hp": 600,
        "max_hp": 600,
    }
