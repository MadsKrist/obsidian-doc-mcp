"""Tests for memory optimization functionality."""

import gc
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from utils.memory_optimizer import (
    MemoryMonitor,
    MemoryOptimizer,
    MemoryProfile,
    MemorySnapshot,
    memory_efficient_context,
)


class TestMemorySnapshot:
    """Test MemorySnapshot dataclass."""

    def test_memory_snapshot_creation(self):
        """Test MemorySnapshot creation."""
        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=100.5,
            vms_mb=200.0,
            percent=15.5,
            available_mb=500.0,
            python_objects=1000,
            tracemalloc_mb=50.0,
        )

        assert snapshot.rss_mb == 100.5
        assert snapshot.vms_mb == 200.0
        assert snapshot.percent == 15.5
        assert snapshot.available_mb == 500.0
        assert snapshot.python_objects == 1000
        assert snapshot.tracemalloc_mb == 50.0


class TestMemoryProfile:
    """Test MemoryProfile dataclass."""

    def test_memory_profile_creation(self):
        """Test MemoryProfile creation and properties."""
        start_snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=100.0,
            vms_mb=150.0,
            percent=10.0,
            available_mb=500.0,
        )

        end_snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=120.0,
            vms_mb=170.0,
            percent=12.0,
            available_mb=480.0,
        )

        profile = MemoryProfile("test_operation", start_snapshot, end_snapshot)

        assert profile.operation_name == "test_operation"
        assert profile.memory_delta_mb == 20.0  # 120 - 100
        assert profile.peak_memory_mb == 120.0  # max of start/end since no peak set


class TestMemoryMonitor:
    """Test MemoryMonitor functionality."""

    def test_monitor_initialization(self):
        """Test memory monitor initialization."""
        monitor = MemoryMonitor(enable_tracemalloc=False, enable_profiling=True)

        assert monitor.enable_tracemalloc is False
        assert monitor.enable_profiling is True
        assert monitor.current_profile is None

    def test_get_memory_snapshot(self):
        """Test memory snapshot capture."""
        monitor = MemoryMonitor()
        snapshot = monitor.get_memory_snapshot()

        assert isinstance(snapshot, MemorySnapshot)
        assert snapshot.timestamp > 0
        assert snapshot.rss_mb > 0  # Should have some memory usage
        assert snapshot.python_objects > 0

    def test_profile_operation_context(self):
        """Test operation profiling context manager."""
        monitor = MemoryMonitor(enable_profiling=True)

        with monitor.profile_operation("test_operation") as profile:
            assert isinstance(profile, MemoryProfile)
            assert profile.operation_name == "test_operation"
            assert monitor.current_profile is profile

            # Do some work that uses memory
            test_data = list(range(1000))
            monitor.take_snapshot()
            del test_data

        # After context, should be cleaned up
        assert monitor.current_profile is None
        assert len(profile.snapshots) > 0

    def test_profile_operation_disabled(self):
        """Test operation profiling when disabled."""
        monitor = MemoryMonitor(enable_profiling=False)

        with monitor.profile_operation("test_operation") as profile:
            assert isinstance(profile, MemoryProfile)
            # Should still work but minimal tracking

    def test_memory_recommendations(self):
        """Test memory recommendations generation."""
        monitor = MemoryMonitor()
        recommendations = monitor.get_memory_recommendations()

        assert isinstance(recommendations, list)
        # Recommendations depend on current system state, so we can't be too specific

    @patch("utils.memory_optimizer.psutil")
    def test_memory_snapshot_without_psutil(self, mock_psutil):
        """Test memory snapshot when psutil is not available."""
        # Simulate psutil not being available
        with patch("utils.memory_optimizer.HAS_PSUTIL", False):
            monitor = MemoryMonitor()
            snapshot = monitor.get_memory_snapshot()

            assert isinstance(snapshot, MemorySnapshot)
            # Without psutil, some fields will be 0 or minimal


class TestMemoryOptimizer:
    """Test MemoryOptimizer functionality."""

    def test_optimizer_initialization(self):
        """Test memory optimizer initialization."""
        optimizer = MemoryOptimizer(aggressive_gc=True, object_limit=500000)

        assert optimizer.aggressive_gc is True
        assert optimizer.object_limit == 500000

    def test_batch_processor(self):
        """Test batch processing functionality."""
        optimizer = MemoryOptimizer()
        items = list(range(25))  # 25 items
        batch_size = 10

        processed_batches = []
        with optimizer.batch_processor(items, batch_size) as batch_iter:
            for batch in batch_iter:
                processed_batches.append(len(batch))

        # Should have 3 batches: 10, 10, 5
        assert len(processed_batches) == 3
        assert processed_batches == [10, 10, 5]

    def test_optimize_string_operations(self):
        """Test string optimization."""
        optimizer = MemoryOptimizer()

        # Test with repeated strings
        strings = ["hello", "world", "hello", "foo", "world"]
        optimized = optimizer.optimize_string_operations(strings)

        assert len(optimized) == len(strings)
        # Can't easily test sys.intern behavior, but should not crash

    def test_memory_limit_context(self):
        """Test memory limit enforcement."""
        optimizer = MemoryOptimizer()

        # Test with reasonable limit that shouldn't be exceeded
        with optimizer.memory_limit(1000.0):  # 1GB limit
            test_data = list(range(100))
            del test_data

        # Should complete without raising MemoryError

    def test_memory_efficient_file_reader(self):
        """Test memory-efficient file reading."""
        optimizer = MemoryOptimizer()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            test_content = "This is a test file with some content.\n" * 100
            f.write(test_content)
            temp_path = Path(f.name)

        try:
            # Read file in chunks
            read_content = ""
            for chunk in optimizer.memory_efficient_file_reader(
                temp_path, chunk_size=50
            ):
                read_content += chunk

            assert read_content == test_content
        finally:
            temp_path.unlink()

    def test_clear_caches(self):
        """Test cache clearing functionality."""
        optimizer = MemoryOptimizer()

        # This should not crash and should return some statistics
        cleared = optimizer.clear_caches()

        assert isinstance(cleared, dict)
        assert "gc_collected" in cleared
        assert cleared["gc_collected"] >= 0

    def test_get_large_objects_no_tracemalloc(self):
        """Test large object detection when tracemalloc is disabled."""
        optimizer = MemoryOptimizer()

        # Should return empty list if tracemalloc is not tracing
        large_objects = optimizer.get_large_objects()
        assert isinstance(large_objects, list)


class TestMemoryEfficientContext:
    """Test memory-efficient context manager."""

    def test_memory_efficient_context_basic(self):
        """Test basic memory-efficient context usage."""
        with memory_efficient_context() as (monitor, optimizer):
            assert isinstance(monitor, MemoryMonitor)
            assert isinstance(optimizer, MemoryOptimizer)

    def test_memory_efficient_context_with_limit(self):
        """Test memory-efficient context with memory limit."""
        # Use a very high limit that shouldn't be exceeded
        with memory_efficient_context(max_memory_mb=10000.0) as (monitor, optimizer):
            test_data = list(range(1000))
            del test_data

    def test_memory_efficient_context_aggressive_gc(self):
        """Test memory-efficient context with aggressive GC."""
        with memory_efficient_context(aggressive_gc=True) as (monitor, optimizer):
            assert optimizer.aggressive_gc is True

    def test_memory_efficient_context_no_monitoring(self):
        """Test memory-efficient context without operation monitoring."""
        with memory_efficient_context(monitor_operations=False) as (monitor, optimizer):
            assert monitor.enable_profiling is False


class TestMemoryOptimizationIntegration:
    """Integration tests for memory optimization."""

    def test_memory_optimization_with_gc(self):
        """Test that memory optimization properly triggers garbage collection."""
        with memory_efficient_context(aggressive_gc=True) as (monitor, optimizer):
            # Create some objects
            with monitor.profile_operation("memory_test") as profile:
                test_objects = []
                for i in range(1000):
                    test_objects.append({"id": i, "data": f"test_data_{i}"})

                monitor.take_snapshot()

                # Clear objects
                del test_objects
                gc.collect()

                monitor.take_snapshot()

            # Should have captured memory usage
            assert len(profile.snapshots) >= 2

    def test_batch_processing_memory_efficiency(self):
        """Test that batch processing helps with memory efficiency."""
        optimizer = MemoryOptimizer(aggressive_gc=True)

        # Create a large dataset
        large_dataset = [{"id": i, "data": f"item_{i}" * 100} for i in range(1000)]

        processed_count = 0
        with optimizer.batch_processor(large_dataset, batch_size=50) as batch_iter:
            for batch in batch_iter:
                # Simulate processing
                processed_batch = [item["id"] for item in batch]
                processed_count += len(processed_batch)
                del processed_batch

        assert processed_count == len(large_dataset)

    def test_memory_monitoring_recommendations(self):
        """Test that memory monitoring provides useful recommendations."""
        monitor = MemoryMonitor()

        # Create conditions that might trigger recommendations
        monitor.get_memory_snapshot()
        recommendations = monitor.get_memory_recommendations()

        # Should return a list (may be empty depending on system state)
        assert isinstance(recommendations, list)

        # Each recommendation should be a string
        for rec in recommendations:
            assert isinstance(rec, str)
            assert len(rec) > 0
