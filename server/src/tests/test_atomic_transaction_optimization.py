"""
Tests for atomic transaction optimization features including retry logic and monitoring.
"""

import pytest
import pytest_asyncio
import time
import asyncio
from unittest.mock import patch, AsyncMock

from server.src.core.concurrency import ValkeyAtomicOperations
from server.src.tests.conftest import FakeValkey


class TestAtomicTransactionOptimization:
    """Test atomic transaction retry logic and monitoring features."""
    
    @pytest_asyncio.fixture
    async def valkey_ops(self, fake_valkey: FakeValkey):
        """Create ValkeyAtomicOperations instance with test configuration."""
        return ValkeyAtomicOperations(fake_valkey, max_retries=2, base_retry_delay=0.001)
    
    async def test_successful_transaction_no_retries(self, valkey_ops: ValkeyAtomicOperations):
        """Test that successful transactions complete without retries."""
        start_time = time.time()
        operation_called = False
        
        async with valkey_ops.transaction("test_success") as tx:
            await tx.set("test_key", "test_value") 
            operation_called = True
        
        duration = time.time() - start_time
        assert operation_called
        assert duration < 0.1  # Should be very fast without retries
    
    async def test_transaction_retry_on_failure(self, valkey_ops: ValkeyAtomicOperations):
        """Test that transactions retry on failure with exponential backoff."""
        call_count = 0
        
        # Mock the multi() method to fail the first two times, succeed on third
        original_multi = valkey_ops.valkey.multi
        
        def mock_multi():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Simulated transaction failure")
            return original_multi()
        
        valkey_ops.valkey.multi = mock_multi
        
        try:
            start_time = time.time()
            
            async with valkey_ops.transaction("test_retry") as tx:
                await tx.set("test_key", "test_value")
            
            duration = time.time() - start_time
            
            # Should have retried twice (3 total attempts)
            assert call_count == 3
            # Should take longer due to retry delays
            assert duration > 0.001  # At least the retry delays
            
        finally:
            # Restore original method
            valkey_ops.valkey.multi = original_multi
    
    async def test_transaction_failure_after_max_retries(self, valkey_ops: ValkeyAtomicOperations):
        """Test that transactions fail after exhausting max retries."""
        call_count = 0
        
        # Mock the multi() method to always fail
        def mock_multi():
            nonlocal call_count
            call_count += 1
            raise Exception("Persistent failure")
        
        original_multi = valkey_ops.valkey.multi
        valkey_ops.valkey.multi = mock_multi
        
        try:
            with pytest.raises(Exception, match="Persistent failure"):
                async with valkey_ops.transaction("test_max_retries") as tx:
                    await tx.set("test_key", "test_value")
            
            # Should have tried max_retries + 1 times (initial + 2 retries = 3 total)
            assert call_count == 3
            
        finally:
            # Restore original method
            valkey_ops.valkey.multi = original_multi
    
    async def test_retry_delay_increases_exponentially(self, valkey_ops: ValkeyAtomicOperations):
        """Test that retry delays increase exponentially."""
        call_count = 0
        retry_times = []
        
        original_multi = valkey_ops.valkey.multi
        
        def mock_multi():
            nonlocal call_count
            call_count += 1
            retry_times.append(time.time())
            if call_count <= 2:
                raise Exception("Simulated failure")
            # Call the original multi function, not the replaced one
            return original_multi()
        
        sleep_durations = []
        
        # Store the original sleep to avoid recursion
        original_sleep = asyncio.sleep
        
        async def mock_sleep(duration):
            sleep_durations.append(duration)
            # Use the original sleep function to avoid recursion
            await original_sleep(0.001)
        
        valkey_ops.valkey.multi = mock_multi
        
        # Patch the module-level asyncio.sleep directly
        with patch('server.src.core.concurrency.asyncio.sleep', side_effect=mock_sleep):
            try:
                async with valkey_ops.transaction("test_backoff") as tx:
                    await tx.set("test_key", "test_value")
                
                # Should have two retry delays: 0.001 * 1, 0.001 * 2
                assert len(sleep_durations) == 2
                assert sleep_durations[0] == 0.001  # First retry
                assert sleep_durations[1] == 0.002  # Second retry (exponential backoff)
                
            finally:
                valkey_ops.valkey.multi = original_multi
    
    async def test_concurrent_transactions_with_different_descriptions(self, valkey_ops: ValkeyAtomicOperations):
        """Test that multiple concurrent transactions work correctly."""
        results = []
        
        async def transaction_operation(description: str, key: str, value: str):
            async with valkey_ops.transaction(description) as tx:
                await tx.set(key, value)
                results.append(f"{description}:{key}:{value}")
        
        # Run multiple transactions concurrently
        await asyncio.gather(
            transaction_operation("txn1", "key1", "value1"),
            transaction_operation("txn2", "key2", "value2"), 
            transaction_operation("txn3", "key3", "value3"),
        )
        
        # All transactions should complete
        assert len(results) == 3
        assert "txn1:key1:value1" in results
        assert "txn2:key2:value2" in results  
        assert "txn3:key3:value3" in results
    
    @pytest.mark.integration
    async def test_transaction_metrics_tracking(self, valkey_ops: ValkeyAtomicOperations):
        """Test that transaction metrics are properly tracked."""
        # This test would verify Prometheus metrics if available
        # For now, just ensure transactions complete without errors
        
        async with valkey_ops.transaction("metrics_test") as tx:
            await tx.set("metrics_key", "metrics_value")
            await tx.hset("metrics_hash", {"field": "value"})
            await tx.sadd("metrics_set", ["member1", "member2"])
        
        # Verify operations completed
        assert await valkey_ops.valkey.get("metrics_key") == b"metrics_value"
        hash_data = await valkey_ops.valkey.hgetall("metrics_hash")
        assert hash_data == {b"field": b"value"}
        set_data = await valkey_ops.valkey.smembers("metrics_set")
        assert set_data == {b"member1", b"member2"}