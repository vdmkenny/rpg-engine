"""
Performance benchmark suite for testing server capacity at scale.

Tests server performance under various load conditions up to 1000 concurrent players,
measuring tick times, memory usage, and system resource utilization.
"""

import asyncio
import time
import statistics
import logging
import os
import resource
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from contextlib import asynccontextmanager

from server.src.core.config import settings
from server.src.core.logging_config import get_logger
from server.src.services.game_state_manager import get_game_state_manager, init_game_state_manager
from server.src.services.visibility_service import get_visibility_service, init_visibility_service
from server.src.core.database import get_valkey, AsyncSessionLocal

logger = get_logger(__name__)

@dataclass
class BenchmarkResult:
    """Results from a performance benchmark test."""
    player_count: int
    avg_tick_time_ms: float
    max_tick_time_ms: float
    min_tick_time_ms: float
    p95_tick_time_ms: float
    memory_usage_mb: float
    cpu_usage_percent: float
    tick_rate_achieved: float
    target_tick_rate: float
    passed: bool
    error: Optional[str] = None


class CapacityBenchmark:
    """
    Performance benchmarking for server capacity testing.
    
    Simulates multiple concurrent players and measures system performance
    under various load conditions to validate scaling targets.
    """
    
    def __init__(self, target_tick_time_ms: float = 50.0):
        """
        Initialize benchmark suite.
        
        Args:
            target_tick_time_ms: Maximum acceptable tick time in milliseconds
        """
        self.target_tick_time_ms = target_tick_time_ms
        self.target_tick_rate = settings.GAME_TICK_RATE
        self.results: List[BenchmarkResult] = []
        
    async def setup(self):
        """Initialize benchmark environment."""
        logger.info("Setting up benchmark environment")
        
        # Initialize services
        valkey = await get_valkey()
        gsm = init_game_state_manager(valkey, AsyncSessionLocal)
        visibility_service = init_visibility_service(max_cache_size=1000)
        
        # Load reference data is handled by GSM initialization
        logger.info("GSM reference data loaded automatically")
        
        logger.info("Benchmark environment ready")
    
    async def simulate_players(self, player_count: int) -> Dict[str, Any]:
        """
        Simulate concurrent players for load testing.
        
        Args:
            player_count: Number of players to simulate
            
        Returns:
            Dictionary with simulated player data
        """
        gsm = get_game_state_manager()
        players = {}
        
        # Create simulated players
        for i in range(player_count):
            username = f"testuser_{i:04d}"
            player_id = 1000 + i
            
            # Register player as online
            gsm.register_online_player(player_id, username)
            
            # Set basic player state using full state method
            await gsm.set_player_full_state(
                player_id=player_id,
                x=10 + (i % 100),  # Spread players across map
                y=10 + (i // 100),
                map_id="testmap",
                current_hp=100,
                max_hp=100
            )
            
            players[username] = {
                "player_id": player_id,
                "x": 10 + (i % 100),
                "y": 10 + (i // 100),
                "map_id": "testmap"
            }
        
        logger.info(f"Simulated {player_count} players")
        return players
    
    async def measure_tick_performance(self, players: Dict[str, Any], duration_seconds: int = 30) -> List[float]:
        """
        Measure game loop tick performance with simulated load.
        
        Args:
            players: Simulated player data
            duration_seconds: How long to run the test
            
        Returns:
            List of tick times in milliseconds
        """
        gsm = get_game_state_manager()
        visibility_service = get_visibility_service()
        tick_times = []
        
        start_time = time.time()
        tick_count = 0
        
        while time.time() - start_time < duration_seconds:
            tick_start = time.time()
            
            # Simulate game loop operations
            usernames = list(players.keys())
            
            # Batch fetch player data (tests our optimization)
            player_data = await gsm.state_access.get_multiple_players_by_usernames(usernames)
            
            # Simulate visibility updates for each player
            for username, data in player_data.items():
                if data:
                    # Create mock visible entities
                    visible_entities = {
                        f"player_{username}": {
                            "id": username,
                            "type": "player",
                            "x": data.get("x", 0),
                            "y": data.get("y", 0)
                        }
                    }
                    
                    # Update visibility (tests VisibilityService performance)
                    await visibility_service.update_player_visible_entities(username, visible_entities)
            
            tick_end = time.time()
            tick_time_ms = (tick_end - tick_start) * 1000
            tick_times.append(tick_time_ms)
            tick_count += 1
            
            # Sleep to maintain target tick rate
            target_interval = 1.0 / self.target_tick_rate
            sleep_time = max(0, target_interval - (tick_end - tick_start))
            await asyncio.sleep(sleep_time)
        
        logger.info(f"Completed {tick_count} ticks in {duration_seconds} seconds")
        return tick_times
    
    def get_system_metrics(self) -> Dict[str, float]:
        """Get current system resource usage using resource module."""
        # Use resource module for memory info (RSS not available, use peak)
        memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
        
        return {
            "memory_usage_mb": memory_mb,
            "cpu_usage_percent": 0.0  # CPU usage not available without psutil
        }
    
    async def run_benchmark(self, player_count: int, duration_seconds: int = 30) -> BenchmarkResult:
        """
        Run performance benchmark for specified player count.
        
        Args:
            player_count: Number of concurrent players to simulate
            duration_seconds: Duration of the benchmark test
            
        Returns:
            BenchmarkResult with performance metrics
        """
        logger.info(f"Running benchmark: {player_count} players for {duration_seconds}s")
        
        try:
            # Setup simulated players
            players = await self.simulate_players(player_count)
            
            # Warm up system
            await asyncio.sleep(2)
            
            # Get baseline metrics
            baseline_metrics = self.get_system_metrics()
            
            # Run performance test
            tick_times = await self.measure_tick_performance(players, duration_seconds)
            
            # Get final metrics
            final_metrics = self.get_system_metrics()
            
            # Calculate performance statistics
            avg_tick_time = statistics.mean(tick_times)
            max_tick_time = max(tick_times)
            min_tick_time = min(tick_times)
            p95_tick_time = statistics.quantiles(tick_times, n=20)[18]  # 95th percentile
            
            actual_tick_rate = len(tick_times) / duration_seconds
            
            # Determine if benchmark passed
            passed = (
                avg_tick_time <= self.target_tick_time_ms and
                p95_tick_time <= self.target_tick_time_ms * 1.5  # Allow 50% variance for P95
            )
            
            result = BenchmarkResult(
                player_count=player_count,
                avg_tick_time_ms=round(avg_tick_time, 2),
                max_tick_time_ms=round(max_tick_time, 2),
                min_tick_time_ms=round(min_tick_time, 2),
                p95_tick_time_ms=round(p95_tick_time, 2),
                memory_usage_mb=round(final_metrics["memory_usage_mb"], 2),
                cpu_usage_percent=round(final_metrics["cpu_usage_percent"], 2),
                tick_rate_achieved=round(actual_tick_rate, 2),
                target_tick_rate=self.target_tick_rate,
                passed=passed
            )
            
            # Cleanup
            await self.cleanup_players(players)
            
            logger.info(f"Benchmark completed: {result}")
            return result
            
        except Exception as e:
            error_msg = f"Benchmark failed: {str(e)}"
            logger.error(error_msg)
            
            return BenchmarkResult(
                player_count=player_count,
                avg_tick_time_ms=0,
                max_tick_time_ms=0,
                min_tick_time_ms=0,
                p95_tick_time_ms=0,
                memory_usage_mb=0,
                cpu_usage_percent=0,
                tick_rate_achieved=0,
                target_tick_rate=self.target_tick_rate,
                passed=False,
                error=error_msg
            )
    
    async def cleanup_players(self, players: Dict[str, Any]):
        """Clean up simulated players."""
        gsm = get_game_state_manager()
        visibility_service = get_visibility_service()
        
        for username in players.keys():
            player_id = players[username]["player_id"]
            await gsm.unregister_online_player(player_id)
            await visibility_service.remove_player(username)
    
    async def run_capacity_test_suite(self) -> List[BenchmarkResult]:
        """
        Run complete capacity test suite with multiple player counts.
        
        Returns:
            List of benchmark results for analysis
        """
        test_cases = [50, 100, 250, 500, 750, 1000]
        results = []
        
        logger.info("Starting capacity test suite")
        
        for player_count in test_cases:
            result = await self.run_benchmark(player_count, duration_seconds=60)
            results.append(result)
            self.results.append(result)
            
            # Short break between tests
            await asyncio.sleep(5)
        
        logger.info("Capacity test suite completed")
        return results
    
    def print_results(self):
        """Print formatted benchmark results."""
        print("\n" + "="*80)
        print("CAPACITY BENCHMARK RESULTS")
        print("="*80)
        print(f"Target: <{self.target_tick_time_ms}ms avg tick time at {self.target_tick_rate} TPS")
        print("-"*80)
        
        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            print(f"Players: {result.player_count:4d} | "
                  f"Avg: {result.avg_tick_time_ms:6.2f}ms | "
                  f"P95: {result.p95_tick_time_ms:6.2f}ms | "
                  f"Memory: {result.memory_usage_mb:6.1f}MB | "
                  f"CPU: {result.cpu_usage_percent:5.1f}% | "
                  f"TPS: {result.tick_rate_achieved:5.1f} | "
                  f"{status}")
        
        print("-"*80)
        
        # Summary
        passed_tests = sum(1 for r in self.results if r.passed)
        total_tests = len(self.results)
        
        if passed_tests == total_tests:
            print(f"✅ ALL TESTS PASSED ({passed_tests}/{total_tests})")
            print("Server meets 1000 player capacity target!")
        else:
            print(f"❌ SOME TESTS FAILED ({passed_tests}/{total_tests})")
            max_passing = max((r.player_count for r in self.results if r.passed), default=0)
            print(f"Maximum supported capacity: {max_passing} players")
        
        print("="*80)


async def main():
    """Run the capacity benchmark suite."""
    # Configure logging for benchmark
    logging.basicConfig(level=logging.INFO)
    
    benchmark = CapacityBenchmark(target_tick_time_ms=50.0)
    
    try:
        await benchmark.setup()
        await benchmark.run_capacity_test_suite()
        benchmark.print_results()
        
    except Exception as e:
        logger.error(f"Benchmark suite failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())