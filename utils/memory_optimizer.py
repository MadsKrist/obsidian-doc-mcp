"""Memory optimization utilities for documentation generation.

This module provides tools and strategies to minimize memory usage during
large-scale documentation generation processes.
"""

import gc
import logging
import sys
import tracemalloc
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    psutil = None

logger = logging.getLogger(__name__)


@dataclass
class MemorySnapshot:
    """Represents a memory usage snapshot."""

    timestamp: float
    rss_mb: float  # Resident Set Size in MB
    vms_mb: float  # Virtual Memory Size in MB
    percent: float  # Memory percentage
    available_mb: float  # Available system memory in MB
    python_objects: int = 0  # Number of Python objects
    tracemalloc_mb: float = 0.0  # Tracemalloc current memory in MB


@dataclass
class MemoryProfile:
    """Memory profiling results for an operation."""

    operation_name: str
    start_snapshot: MemorySnapshot
    end_snapshot: MemorySnapshot
    peak_snapshot: Optional[MemorySnapshot] = None
    snapshots: list[MemorySnapshot] = field(default_factory=list)

    @property
    def memory_delta_mb(self) -> float:
        """Memory difference between start and end."""
        return self.end_snapshot.rss_mb - self.start_snapshot.rss_mb

    @property
    def peak_memory_mb(self) -> float:
        """Peak memory usage during operation."""
        if self.peak_snapshot:
            return self.peak_snapshot.rss_mb
        return max(self.start_snapshot.rss_mb, self.end_snapshot.rss_mb)


class MemoryMonitor:
    """Monitors and profiles memory usage during operations."""

    def __init__(self, enable_tracemalloc: bool = True, enable_profiling: bool = True):
        """Initialize memory monitor.

        Args:
            enable_tracemalloc: Enable detailed Python memory tracking
            enable_profiling: Enable memory profiling
        """
        self.enable_tracemalloc = enable_tracemalloc
        self.enable_profiling = enable_profiling
        self.current_profile: Optional[MemoryProfile] = None

        if self.enable_tracemalloc and not tracemalloc.is_tracing():
            tracemalloc.start()

        logger.info(f"Memory monitor initialized (tracemalloc: {enable_tracemalloc})")

    def get_memory_snapshot(self) -> MemorySnapshot:
        """Get current memory usage snapshot."""
        import time

        if HAS_PSUTIL and psutil:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            system_memory = psutil.virtual_memory()

            snapshot = MemorySnapshot(
                timestamp=time.time(),
                rss_mb=memory_info.rss / 1024 / 1024,
                vms_mb=memory_info.vms / 1024 / 1024,
                percent=memory_percent,
                available_mb=system_memory.available / 1024 / 1024,
                python_objects=len(gc.get_objects()),
            )
        else:
            # Fallback when psutil is not available
            import resource

            rusage = resource.getrusage(resource.RUSAGE_SELF)
            # Note: rusage.ru_maxrss is in KB on Linux, bytes on macOS
            rss_mb = (
                rusage.ru_maxrss / 1024
                if sys.platform != "darwin"
                else rusage.ru_maxrss / 1024 / 1024
            )

            snapshot = MemorySnapshot(
                timestamp=time.time(),
                rss_mb=rss_mb,
                vms_mb=0.0,  # Not available without psutil
                percent=0.0,  # Not available without psutil
                available_mb=0.0,  # Not available without psutil
                python_objects=len(gc.get_objects()),
            )

        if self.enable_tracemalloc and tracemalloc.is_tracing():
            current, peak = tracemalloc.get_traced_memory()
            snapshot.tracemalloc_mb = current / 1024 / 1024

        return snapshot

    @contextmanager
    def profile_operation(
        self, operation_name: str
    ) -> Generator[MemoryProfile, None, None]:
        """Context manager for profiling memory usage of an operation.

        Args:
            operation_name: Name of the operation being profiled

        Yields:
            MemoryProfile object that gets populated during execution
        """
        if not self.enable_profiling:
            # Create dummy profile if profiling disabled
            dummy_snapshot = self.get_memory_snapshot()
            profile = MemoryProfile(operation_name, dummy_snapshot, dummy_snapshot)
            yield profile
            return

        logger.debug(f"Starting memory profiling for: {operation_name}")

        # Force garbage collection before starting
        gc.collect()

        start_snapshot = self.get_memory_snapshot()
        profile = MemoryProfile(operation_name, start_snapshot, start_snapshot)
        self.current_profile = profile

        try:
            yield profile
        finally:
            gc.collect()  # Force GC before final measurement
            end_snapshot = self.get_memory_snapshot()
            profile.end_snapshot = end_snapshot

            # Find peak memory usage from snapshots
            if profile.snapshots:
                profile.peak_snapshot = max(profile.snapshots, key=lambda s: s.rss_mb)

            delta = profile.memory_delta_mb

            if delta > 1.0:  # Only log significant memory changes
                logger.info(
                    f"Memory profile for '{operation_name}': "
                    f"Delta: {delta:+.1f}MB, Peak: {profile.peak_memory_mb:.1f}MB, "
                    f"Final: {end_snapshot.rss_mb:.1f}MB"
                )

            self.current_profile = None

    def take_snapshot(self) -> None:
        """Take a memory snapshot during profiling."""
        if self.current_profile:
            snapshot = self.get_memory_snapshot()
            self.current_profile.snapshots.append(snapshot)

    def get_memory_recommendations(self) -> list[str]:
        """Get memory optimization recommendations based on current state."""
        recommendations = []
        snapshot = self.get_memory_snapshot()

        # Memory pressure recommendations
        if snapshot.percent > 80:
            recommendations.append(
                "High memory usage detected - consider processing in smaller batches"
            )

        if snapshot.available_mb < 500:
            recommendations.append(
                "Low available memory - enable aggressive garbage collection"
            )

        if snapshot.python_objects > 1000000:
            recommendations.append(
                "High object count - consider using generators and context managers"
            )

        # System-specific recommendations
        if sys.platform == "darwin" and snapshot.rss_mb > 8000:  # macOS
            recommendations.append(
                "macOS detected with high memory usage - consider memory mapping for large files"
            )

        return recommendations


class MemoryOptimizer:
    """Provides memory optimization strategies and utilities."""

    def __init__(self, aggressive_gc: bool = False, object_limit: int = 1000000):
        """Initialize memory optimizer.

        Args:
            aggressive_gc: Enable aggressive garbage collection
            object_limit: Trigger GC when object count exceeds this limit
        """
        self.aggressive_gc = aggressive_gc
        self.object_limit = object_limit
        self._gc_threshold_original = gc.get_threshold()

        if aggressive_gc:
            # Set more aggressive GC thresholds
            gc.set_threshold(100, 5, 5)

        logger.info(f"Memory optimizer initialized (aggressive_gc: {aggressive_gc})")

    def __del__(self):
        """Restore original GC settings on cleanup."""
        if hasattr(self, "_gc_threshold_original"):
            gc.set_threshold(*self._gc_threshold_original)

    @contextmanager
    def batch_processor(
        self, items: list[Any], batch_size: int = 100
    ) -> Generator[Iterator[list[Any]], None, None]:
        """Process items in memory-efficient batches.

        Args:
            items: Items to process
            batch_size: Size of each batch

        Yields:
            Iterator that yields batches of items for processing
        """
        total_batches = (len(items) + batch_size - 1) // batch_size

        def batch_iterator():
            for i in range(0, len(items), batch_size):
                batch_num = (i // batch_size) + 1
                batch = items[i : i + batch_size]

                logger.debug(
                    f"Processing batch {batch_num}/{total_batches} ({len(batch)} items)"
                )

                # Force garbage collection after each batch if aggressive
                if self.aggressive_gc:
                    gc.collect()

                # Check object count
                if len(gc.get_objects()) > self.object_limit:
                    logger.warning(
                        f"Object count exceeded {self.object_limit}, forcing GC"
                    )
                    gc.collect()

                yield batch

        try:
            yield batch_iterator()
        finally:
            # Final cleanup
            if self.aggressive_gc:
                gc.collect()

    def optimize_string_operations(self, strings: list[str]) -> list[str]:
        """Optimize memory usage for string operations.

        Args:
            strings: List of strings to optimize

        Returns:
            Memory-optimized list of strings
        """
        # Use sys.intern for frequently used strings
        optimized = []
        seen = set()

        for s in strings:
            if len(s) < 100 and s in seen:
                # Intern short, repeated strings
                optimized.append(sys.intern(s))
            else:
                optimized.append(s)
                if len(s) < 100:
                    seen.add(s)

        return optimized

    @contextmanager
    def memory_limit(self, max_memory_mb: float) -> Generator[None, None, None]:
        """Context manager that monitors and enforces memory limits.

        Args:
            max_memory_mb: Maximum memory usage in MB

        Raises:
            MemoryError: If memory limit is exceeded
        """
        monitor = MemoryMonitor(enable_profiling=False)

        try:
            yield
        finally:
            current_memory = monitor.get_memory_snapshot().rss_mb
            if current_memory > max_memory_mb:
                # Try aggressive cleanup first
                gc.collect()
                final_memory = monitor.get_memory_snapshot().rss_mb

                if final_memory > max_memory_mb:
                    raise MemoryError(
                        f"Memory limit exceeded: {final_memory:.1f}MB > {max_memory_mb:.1f}MB"
                    )

    def get_large_objects(self, min_size_mb: float = 1.0) -> list[dict[str, Any]]:
        """Get information about large objects in memory.

        Args:
            min_size_mb: Minimum size in MB to consider "large"

        Returns:
            List of large object information
        """
        if not tracemalloc.is_tracing():
            return []

        large_objects = []
        snapshot = tracemalloc.take_snapshot()

        for stat in snapshot.statistics("traceback"):
            size_mb = stat.size / 1024 / 1024
            if size_mb >= min_size_mb:
                large_objects.append(
                    {
                        "size_mb": size_mb,
                        "count": stat.count,
                        "traceback": stat.traceback.format(),
                    }
                )

        return sorted(large_objects, key=lambda x: x["size_mb"], reverse=True)

    def memory_efficient_file_reader(
        self, file_path: Path, chunk_size: int = 8192
    ) -> Iterator[str]:
        """Memory-efficient file reader that yields chunks.

        Args:
            file_path: Path to file to read
            chunk_size: Size of each chunk in bytes

        Yields:
            File content chunks
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")

    def clear_caches(self) -> dict[str, int]:
        """Clear various Python caches to free memory.

        Returns:
            Dictionary with cleared cache counts
        """
        cleared = {}

        # Clear import caches
        if hasattr(sys, "_clear_type_cache"):
            sys._clear_type_cache()
            cleared["type_cache"] = 1

        # Clear regex cache (if available)
        import re

        if hasattr(re, "_cache"):
            cache = re._cache
            cache_size = len(cache) if hasattr(cache, "__len__") else 0
            if hasattr(cache, "clear"):
                cache.clear()
            cleared["regex_cache"] = cache_size
        else:
            cleared["regex_cache"] = 0

        # Clear linecache
        import linecache

        linecache.clearcache()
        cleared["linecache"] = 1

        # Force garbage collection
        collected = gc.collect()
        cleared["gc_collected"] = collected

        logger.info(f"Cleared caches: {cleared}")
        return cleared


@contextmanager
def memory_efficient_context(
    max_memory_mb: Optional[float] = None,
    aggressive_gc: bool = False,
    monitor_operations: bool = True,
) -> Generator[tuple[MemoryMonitor, MemoryOptimizer], None, None]:
    """Context manager providing memory monitoring and optimization.

    Args:
        max_memory_mb: Optional memory limit
        aggressive_gc: Enable aggressive garbage collection
        monitor_operations: Enable operation monitoring

    Yields:
        Tuple of (MemoryMonitor, MemoryOptimizer)
    """
    monitor = MemoryMonitor(enable_profiling=monitor_operations)
    optimizer = MemoryOptimizer(aggressive_gc=aggressive_gc)

    try:
        if max_memory_mb:
            with optimizer.memory_limit(max_memory_mb):
                yield monitor, optimizer
        else:
            yield monitor, optimizer
    finally:
        # Cleanup
        if monitor_operations:
            recommendations = monitor.get_memory_recommendations()
            if recommendations:
                logger.info("Memory recommendations: " + "; ".join(recommendations))

        optimizer.clear_caches()
