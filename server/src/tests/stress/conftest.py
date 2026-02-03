"""
Test fixtures for stress/load tests.

Fixtures for concurrency and performance testing.
"""

import pytest
import pytest_asyncio
import asyncio


@pytest.fixture
def concurrent_player_factory(create_test_player):
    """Factory for creating multiple players concurrently."""
    async def _create(num_players, prefix="concurrent"):
        tasks = []
        for i in range(num_players):
            task = create_test_player(f"{prefix}_{i}", "password123")
            tasks.append(task)
        return await asyncio.gather(*tasks)
    return _create


@pytest.fixture
def stress_test_monitor():
    """Monitor for stress test metrics."""
    class StressMonitor:
        def __init__(self):
            self.errors = []
            self.latencies = []
            self.success_count = 0
            self.failure_count = 0
        
        def record_success(self, latency_ms):
            self.success_count += 1
            self.latencies.append(latency_ms)
        
        def record_failure(self, error):
            self.failure_count += 1
            self.errors.append(error)
        
        def get_stats(self):
            if not self.latencies:
                return {"success": 0, "failure": 0, "avg_latency": 0}
            return {
                "success": self.success_count,
                "failure": self.failure_count,
                "avg_latency": sum(self.latencies) / len(self.latencies),
                "max_latency": max(self.latencies) if self.latencies else 0,
                "min_latency": min(self.latencies) if self.latencies else 0,
            }
    
    return StressMonitor()
