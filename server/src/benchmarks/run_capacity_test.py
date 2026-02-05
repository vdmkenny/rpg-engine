#!/usr/bin/env python3
"""
Simple test runner for capacity benchmarks.
Run this script to test server performance under load.
"""

import sys
import os
import asyncio

# Add the project root to Python path
sys.path.insert(0, '/app')

async def main():
    """Run capacity benchmark tests."""
    try:
        from server.src.benchmarks.capacity_benchmark import CapacityBenchmark
        
        print("Starting RPG Server Capacity Benchmark")
        print("Testing performance up to 1000 concurrent players")
        print("-" * 50)
        
        benchmark = CapacityBenchmark(target_tick_time_ms=50.0)
        await benchmark.setup()
        
        # Run focused tests for our target capacities
        test_cases = [100, 250, 500, 1000]
        
        for player_count in test_cases:
            print(f"\nTesting {player_count} players...")
            result = await benchmark.run_benchmark(player_count, duration_seconds=30)
            
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"{status} | {result.avg_tick_time_ms:.1f}ms avg | {result.p95_tick_time_ms:.1f}ms P95 | {result.memory_usage_mb:.0f}MB")
        
        print("\n" + "="*50)
        print("CAPACITY BENCHMARK COMPLETE")
        print("="*50)
        
        benchmark.print_results()
        
    except Exception as e:
        print(f"❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)