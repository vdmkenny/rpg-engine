"""
Performance benchmark for Pydantic model overhead.

Tests the tick budget impact of using Pydantic models vs raw dicts.
Measures validation and serialization overhead without database calls.
"""

import asyncio
import time
from typing import Dict, Any, List

# Import Pydantic schemas to benchmark
from server.src.schemas.player import PlayerPosition, PlayerData, NearbyPlayer, Direction, AnimationState
from server.src.schemas.item import InventoryData, EquipmentData, EquipmentSlot, InventorySlot, ItemInfo, ItemStats, ItemCategory, ItemRarity
from server.src.schemas.skill import SkillData, SkillType


# Mock raw dict data similar to what GSM returns
MOCK_POSITION_DICT = {
    "player_id": 1,
    "x": 100,
    "y": 200,
    "direction": "south",
    "animation_state": "idle",
    "map_id": "test_map",
    "chunk_x": 12,
    "chunk_y": 25,
}

MOCK_PLAYER_DICT = {
    "id": 1,
    "username": "test_player",
    "x": 100,
    "y": 200,
    "map_id": "test_map",
    "current_hp": 100,
    "max_hp": 100,
    "role": "player",
    "is_banned": False,
    "is_online": True,
    "facing_direction": "south",
    "animation_state": "idle",
    "total_level": 50,
}

MOCK_NEARBY_PLAYERS = [
    {"player_id": i, "username": f"player_{i}", "x": 100 + i, "y": 200 + i, "direction": "south", "animation_state": "idle", "appearance_hash": None}
    for i in range(10)
]

MOCK_ITEM_STATS = {
    "attack_bonus": 10,
    "strength_bonus": 5,
    "ranged_attack_bonus": 0,
    "ranged_strength_bonus": 0,
    "magic_attack_bonus": 0,
    "magic_damage_bonus": 0,
    "physical_defence_bonus": 0,
    "magic_defence_bonus": 0,
    "health_bonus": 0,
    "speed_bonus": 0,
    "mining_bonus": 0,
    "woodcutting_bonus": 0,
    "fishing_bonus": 0,
}

MOCK_ITEM_DICT = {
    "id": 1,
    "name": "bronze_sword",
    "display_name": "Bronze Sword",
    "description": "A basic bronze sword",
    "category": "weapon",
    "rarity": "common",
    "rarity_color": "#ffffff",
    "equipment_slot": "weapon",
    "max_stack_size": 1,
    "is_two_handed": False,
    "max_durability": None,
    "is_indestructible": False,
    "required_skill": None,
    "required_level": 1,
    "is_tradeable": True,
    "value": 100,
    "stats": MOCK_ITEM_STATS,
    "icon_sprite_id": "bronze_sword_icon",
    "equipped_sprite_id": "bronze_sword_equipped",
}

MOCK_INVENTORY_SLOTS = [
    {"slot": i, "item": MOCK_ITEM_DICT, "quantity": 1}
    for i in range(5)
]

MOCK_INVENTORY_DICT = {
    "slots": MOCK_INVENTORY_SLOTS,
    "max_slots": 28,
    "used_slots": 5,
}

MOCK_EQUIPMENT_SLOT_DATA = {
    "slot": "weapon",
    "item": MOCK_ITEM_DICT,
    "quantity": 1,
    "current_durability": None,
}

MOCK_EQUIPMENT_DICT = {
    "slots": [MOCK_EQUIPMENT_SLOT_DATA],
    "total_stats": MOCK_ITEM_STATS,
}

MOCK_SKILL_DICT = {
    "name": "Attack",
    "category": "combat",
    "description": "Increases accuracy in melee combat",
    "current_level": 75,
    "experience": 500000,
    "xp_for_current_level": 484275,
    "xp_for_next_level": 1000000,
    "xp_to_next_level": 500000,
    "xp_multiplier": 1.0,
    "progress_percent": 50.0,
    "max_level": 99,
}


def benchmark_player_position(iterations: int = 10000) -> dict:
    """Benchmark PlayerPosition model creation vs raw dict."""
    
    # Benchmark Pydantic model creation
    start = time.perf_counter()
    for _ in range(iterations):
        pos = PlayerPosition(**MOCK_POSITION_DICT)
    pydantic_time = time.perf_counter() - start
    
    # Benchmark raw dict creation (baseline)
    start = time.perf_counter()
    for _ in range(iterations):
        pos = dict(MOCK_POSITION_DICT)
    dict_time = time.perf_counter() - start
    
    return {
        "pydantic_ms": pydantic_time * 1000,
        "dict_ms": dict_time * 1000,
        "overhead_ms": (pydantic_time - dict_time) * 1000,
        "overhead_percent": ((pydantic_time / dict_time) - 1) * 100 if dict_time > 0 else 0,
        "per_call_pydantic_ms": (pydantic_time / iterations) * 1000,
        "per_call_dict_ms": (dict_time / iterations) * 1000,
    }


def benchmark_player_data(iterations: int = 5000) -> dict:
    """Benchmark PlayerData model creation vs raw dict."""
    
    # Benchmark Pydantic model creation
    start = time.perf_counter()
    for _ in range(iterations):
        player = PlayerData(**MOCK_PLAYER_DICT)
    pydantic_time = time.perf_counter() - start
    
    # Benchmark raw dict creation
    start = time.perf_counter()
    for _ in range(iterations):
        player = dict(MOCK_PLAYER_DICT)
        player["position"] = dict(MOCK_POSITION_DICT)
    dict_time = time.perf_counter() - start
    
    return {
        "pydantic_ms": pydantic_time * 1000,
        "dict_ms": dict_time * 1000,
        "overhead_ms": (pydantic_time - dict_time) * 1000,
        "overhead_percent": ((pydantic_time / dict_time) - 1) * 100 if dict_time > 0 else 0,
        "per_call_pydantic_ms": (pydantic_time / iterations) * 1000,
        "per_call_dict_ms": (dict_time / iterations) * 1000,
    }


def benchmark_nearby_players(iterations: int = 2000) -> dict:
    """Benchmark creating list of NearbyPlayer models."""
    
    # Benchmark Pydantic model creation
    start = time.perf_counter()
    for _ in range(iterations):
        players = [NearbyPlayer(**p) for p in MOCK_NEARBY_PLAYERS]
    pydantic_time = time.perf_counter() - start
    
    # Benchmark raw dict creation
    start = time.perf_counter()
    for _ in range(iterations):
        players = [dict(p) for p in MOCK_NEARBY_PLAYERS]
    dict_time = time.perf_counter() - start
    
    return {
        "pydantic_ms": pydantic_time * 1000,
        "dict_ms": dict_time * 1000,
        "overhead_ms": (pydantic_time - dict_time) * 1000,
        "overhead_percent": ((pydantic_time / dict_time) - 1) * 100 if dict_time > 0 else 0,
        "per_call_pydantic_ms": (pydantic_time / iterations) * 1000,
        "per_call_dict_ms": (dict_time / iterations) * 1000,
    }


def benchmark_inventory_data(iterations: int = 3000) -> dict:
    """Benchmark InventoryData model creation vs raw dict."""
    
    # Benchmark Pydantic model creation
    start = time.perf_counter()
    for _ in range(iterations):
        inv = InventoryData(**MOCK_INVENTORY_DICT)
    pydantic_time = time.perf_counter() - start
    
    # Benchmark raw dict creation
    start = time.perf_counter()
    for _ in range(iterations):
        inv = {
            "max_slots": 28,
            "used_slots": 5,
            "items": [dict(slot) for slot in MOCK_INVENTORY_SLOTS],
        }
    dict_time = time.perf_counter() - start
    
    return {
        "pydantic_ms": pydantic_time * 1000,
        "dict_ms": dict_time * 1000,
        "overhead_ms": (pydantic_time - dict_time) * 1000,
        "overhead_percent": ((pydantic_time / dict_time) - 1) * 100 if dict_time > 0 else 0,
        "per_call_pydantic_ms": (pydantic_time / iterations) * 1000,
        "per_call_dict_ms": (dict_time / iterations) * 1000,
    }


def benchmark_equipment_data(iterations: int = 3000) -> dict:
    """Benchmark EquipmentData model creation vs raw dict."""
    
    # Benchmark Pydantic model creation
    start = time.perf_counter()
    for _ in range(iterations):
        eq = EquipmentData(**MOCK_EQUIPMENT_DICT)
    pydantic_time = time.perf_counter() - start
    
    # Benchmark raw dict creation
    start = time.perf_counter()
    for _ in range(iterations):
        eq = dict(MOCK_EQUIPMENT_DICT)
    dict_time = time.perf_counter() - start
    
    return {
        "pydantic_ms": pydantic_time * 1000,
        "dict_ms": dict_time * 1000,
        "overhead_ms": (pydantic_time - dict_time) * 1000,
        "overhead_percent": ((pydantic_time / dict_time) - 1) * 100 if dict_time > 0 else 0,
        "per_call_pydantic_ms": (pydantic_time / iterations) * 1000,
        "per_call_dict_ms": (dict_time / iterations) * 1000,
    }


def benchmark_skill_data(iterations: int = 5000) -> dict:
    """Benchmark SkillData model creation vs raw dict."""
    
    # Benchmark Pydantic model creation
    start = time.perf_counter()
    for _ in range(iterations):
        skill = SkillData(**MOCK_SKILL_DICT)
    pydantic_time = time.perf_counter() - start
    
    # Benchmark raw dict creation
    start = time.perf_counter()
    for _ in range(iterations):
        skill = dict(MOCK_SKILL_DICT)
    dict_time = time.perf_counter() - start
    
    return {
        "pydantic_ms": pydantic_time * 1000,
        "dict_ms": dict_time * 1000,
        "overhead_ms": (pydantic_time - dict_time) * 1000,
        "overhead_percent": ((pydantic_time / dict_time) - 1) * 100 if dict_time > 0 else 0,
        "per_call_pydantic_ms": (pydantic_time / iterations) * 1000,
        "per_call_dict_ms": (dict_time / iterations) * 1000,
    }


def run_benchmark():
    """Run all benchmarks and report results."""
    
    print("=" * 70)
    print("PYDANTIC MODEL PERFORMANCE BENCHMARK")
    print("=" * 70)
    print()
    print("Testing model validation overhead vs raw dict creation")
    print("Target: 20 TPS game loop = 50ms per tick budget")
    print()
    
    results = {}
    
    # PlayerPosition benchmark
    print("PlayerPosition (10000 iterations):")
    print("-" * 50)
    results["PlayerPosition"] = benchmark_player_position(10000)
    r = results["PlayerPosition"]
    print(f"  Pydantic: {r['pydantic_ms']:.2f}ms total, {r['per_call_pydantic_ms']:.4f}ms per call")
    print(f"  Dict:     {r['dict_ms']:.2f}ms total, {r['per_call_dict_ms']:.4f}ms per call")
    print(f"  Overhead: {r['overhead_ms']:.2f}ms ({r['overhead_percent']:.1f}%)")
    print()
    
    # PlayerData benchmark
    print("PlayerData (5000 iterations):")
    print("-" * 50)
    results["PlayerData"] = benchmark_player_data(5000)
    r = results["PlayerData"]
    print(f"  Pydantic: {r['pydantic_ms']:.2f}ms total, {r['per_call_pydantic_ms']:.4f}ms per call")
    print(f"  Dict:     {r['dict_ms']:.2f}ms total, {r['per_call_dict_ms']:.4f}ms per call")
    print(f"  Overhead: {r['overhead_ms']:.2f}ms ({r['overhead_percent']:.1f}%)")
    print()
    
    # NearbyPlayers benchmark
    print("NearbyPlayer List (10 players x 2000 iterations):")
    print("-" * 50)
    results["NearbyPlayers"] = benchmark_nearby_players(2000)
    r = results["NearbyPlayers"]
    print(f"  Pydantic: {r['pydantic_ms']:.2f}ms total, {r['per_call_pydantic_ms']:.4f}ms per call")
    print(f"  Dict:     {r['dict_ms']:.2f}ms total, {r['per_call_dict_ms']:.4f}ms per call")
    print(f"  Overhead: {r['overhead_ms']:.2f}ms ({r['overhead_percent']:.1f}%)")
    print()
    
    # InventoryData benchmark
    print("InventoryData (5 items x 3000 iterations):")
    print("-" * 50)
    results["InventoryData"] = benchmark_inventory_data(3000)
    r = results["InventoryData"]
    print(f"  Pydantic: {r['pydantic_ms']:.2f}ms total, {r['per_call_pydantic_ms']:.4f}ms per call")
    print(f"  Dict:     {r['dict_ms']:.2f}ms total, {r['per_call_dict_ms']:.4f}ms per call")
    print(f"  Overhead: {r['overhead_ms']:.2f}ms ({r['overhead_percent']:.1f}%)")
    print()
    
    # EquipmentData benchmark
    print("EquipmentData (3000 iterations):")
    print("-" * 50)
    results["EquipmentData"] = benchmark_equipment_data(3000)
    r = results["EquipmentData"]
    print(f"  Pydantic: {r['pydantic_ms']:.2f}ms total, {r['per_call_pydantic_ms']:.4f}ms per call")
    print(f"  Dict:     {r['dict_ms']:.2f}ms total, {r['per_call_dict_ms']:.4f}ms per call")
    print(f"  Overhead: {r['overhead_ms']:.2f}ms ({r['overhead_percent']:.1f}%)")
    print()
    
    # SkillData benchmark
    print("SkillData (5000 iterations):")
    print("-" * 50)
    results["SkillData"] = benchmark_skill_data(5000)
    r = results["SkillData"]
    print(f"  Pydantic: {r['pydantic_ms']:.2f}ms total, {r['per_call_pydantic_ms']:.4f}ms per call")
    print(f"  Dict:     {r['dict_ms']:.2f}ms total, {r['per_call_dict_ms']:.4f}ms per call")
    print(f"  Overhead: {r['overhead_ms']:.2f}ms ({r['overhead_percent']:.1f}%)")
    print()
    
    # Summary - Tick Budget Analysis
    print("=" * 70)
    print("SUMMARY - Tick Budget Analysis (20 TPS = 50ms budget)")
    print("=" * 70)
    print()
    
    # Estimate game loop impact
    # Assuming typical game loop calls:
    # - 1 PlayerData per player per tick
    # - 10 NearbyPlayer per player per tick
    # - 1 InventoryData check per 10 ticks
    # - 1 EquipmentData check per 10 ticks
    # - 20 SkillData updates per tick (various skills)
    
    per_tick_estimate = (
        results["PlayerData"]["per_call_pydantic_ms"] * 1 +
        results["NearbyPlayers"]["per_call_pydantic_ms"] * 1 +
        results["InventoryData"]["per_call_pydantic_ms"] * 0.1 +
        results["EquipmentData"]["per_call_pydantic_ms"] * 0.1 +
        results["SkillData"]["per_call_pydantic_ms"] * 20
    )
    
    print("Estimated per-tick impact (typical game loop usage):")
    print(f"  1x PlayerData:    {results['PlayerData']['per_call_pydantic_ms']:.4f}ms")
    print(f"  1x NearbyPlayers: {results['NearbyPlayers']['per_call_pydantic_ms']:.4f}ms")
    print(f"  0.1x Inventory:   {results['InventoryData']['per_call_pydantic_ms'] * 0.1:.4f}ms")
    print(f"  0.1x Equipment:   {results['EquipmentData']['per_call_pydantic_ms'] * 0.1:.4f}ms")
    print(f"  20x SkillData:    {results['SkillData']['per_call_pydantic_ms'] * 20:.4f}ms")
    print(f"  " + "-" * 35)
    print(f"  Total Pydantic:   {per_tick_estimate:.4f}ms")
    print(f"  Budget remaining: {50 - per_tick_estimate:.1f}ms ({(per_tick_estimate/50)*100:.2f}% used)")
    print()
    
    if per_tick_estimate < 5:
        print("✅ PASS: Pydantic overhead is minimal (< 10% of tick budget)")
    elif per_tick_estimate < 25:
        print("✅ PASS: Pydantic overhead is acceptable (< 50% of tick budget)")
    else:
        print("⚠️  WARNING: Pydantic overhead is high (> 50% of tick budget)")
    
    print()
    
    # Per-player scaling
    players_10 = per_tick_estimate * 10
    players_50 = per_tick_estimate * 50
    players_100 = per_tick_estimate * 100
    
    print("Scaling estimates:")
    print(f"  10 players:  {players_10:.2f}ms ({(players_10/50)*100:.1f}% of 50ms tick)")
    print(f"  50 players:    {players_50:.2f}ms ({(players_50/50)*100:.1f}% of 50ms tick)")
    print(f"  100 players:   {players_100:.2f}ms ({(players_100/50)*100:.1f}% of 50ms tick)")
    print()
    
    print("Note: These estimates are for model validation only.")
    print("      Actual game loop includes database/Valkey access,")
    print("      which dominates performance.")
    print()
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
