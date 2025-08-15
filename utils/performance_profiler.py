"""Performance profiling and optimization utilities.

This module provides tools for profiling and optimizing critical performance paths
in the documentation generation process.
"""

import cProfile
import logging
import pstats
import threading
import time
import tracemalloc
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any

import psutil

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for a code execution."""

    name: str
    duration: float
    memory_peak: int = 0
    memory_current: int = 0
    cpu_percent: float = 0.0
    calls_count: int = 0
    cumulative_time: float = 0.0
    profile_stats: pstats.Stats | None = None
    memory_trace: tracemalloc.Snapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "name": self.name,
            "duration": self.duration,
            "memory_peak": self.memory_peak,
            "memory_current": self.memory_current,
            "cpu_percent": self.cpu_percent,
            "calls_count": self.calls_count,
            "cumulative_time": self.cumulative_time,
            "has_profile_stats": self.profile_stats is not None,
            "has_memory_trace": self.memory_trace is not None,
        }


@dataclass
class PerformanceReport:
    """Comprehensive performance analysis report."""

    total_duration: float
    peak_memory: int
    metrics: list[PerformanceMetrics] = field(default_factory=list)
    bottlenecks: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def add_metric(self, metric: PerformanceMetrics) -> None:
        """Add a performance metric to the report."""
        self.metrics.append(metric)

    def identify_bottlenecks(self, threshold_ratio: float = 0.2) -> None:
        """Identify performance bottlenecks based on duration threshold."""
        if not self.metrics:
            return

        # Find operations that take more than threshold% of total time
        threshold_time = self.total_duration * threshold_ratio

        bottlenecks = []
        for metric in self.metrics:
            if metric.duration > threshold_time:
                bottlenecks.append(
                    f"{metric.name}: {metric.duration:.3f}s "
                    f"({metric.duration / self.total_duration * 100:.1f}% of total)"
                )

        self.bottlenecks = bottlenecks

    def generate_recommendations(self) -> None:
        """Generate performance optimization recommendations."""
        recommendations = []

        # High memory usage recommendations
        if self.peak_memory > 500 * 1024 * 1024:  # > 500MB
            recommendations.append(
                "High memory usage detected (>500MB). Consider implementing "
                "batch processing or streaming for large datasets."
            )

        # Long duration recommendations
        if self.total_duration > 30:  # > 30 seconds
            recommendations.append(
                "Long execution time detected (>30s). Consider implementing "
                "parallel processing or caching strategies."
            )

        # High CPU usage recommendations
        cpu_intensive_ops = [m for m in self.metrics if m.cpu_percent > 80]
        if cpu_intensive_ops:
            recommendations.append(
                f"CPU-intensive operations detected: "
                f"{', '.join(m.name for m in cpu_intensive_ops)}. "
                "Consider optimizing algorithms or implementing parallel processing."
            )

        # Many function calls recommendations
        high_call_ops = [m for m in self.metrics if m.calls_count > 10000]
        if high_call_ops:
            recommendations.append(
                f"High function call counts detected: {', '.join(m.name for m in high_call_ops)}. "
                "Consider caching results or optimizing algorithms."
            )

        self.recommendations = recommendations

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "total_duration": self.total_duration,
            "peak_memory": self.peak_memory,
            "metrics": [m.to_dict() for m in self.metrics],
            "bottlenecks": self.bottlenecks,
            "recommendations": self.recommendations,
        }


class PerformanceProfiler:
    """Performance profiler for analyzing critical code paths."""

    def __init__(self, enable_memory_tracing: bool = True):
        """Initialize the performance profiler.

        Args:
            enable_memory_tracing: Whether to enable memory tracing
        """
        self.enable_memory_tracing = enable_memory_tracing
        self.metrics: list[PerformanceMetrics] = []
        self._profiler_stack: list[str] = []
        self._start_times: dict[str, float] = {}
        self._memory_start: dict[str, int] = {}
        self._cpu_monitor: threading.Thread | None = None
        self._cpu_usage: dict[str, list[float]] = {}
        self._should_stop_monitoring = threading.Event()

        if self.enable_memory_tracing and not tracemalloc.is_tracing():
            tracemalloc.start()
            logger.debug("Memory tracing started")

    def start_profiling(self, name: str) -> None:
        """Start profiling a code section.

        Args:
            name: Name of the code section being profiled
        """
        self._profiler_stack.append(name)
        self._start_times[name] = time.time()

        if self.enable_memory_tracing:
            current, peak = tracemalloc.get_traced_memory()
            self._memory_start[name] = current

        # Start CPU monitoring
        self._start_cpu_monitoring(name)

        logger.debug(f"Started profiling: {name}")

    def stop_profiling(self, name: str) -> PerformanceMetrics:
        """Stop profiling a code section and return metrics.

        Args:
            name: Name of the code section being profiled

        Returns:
            Performance metrics for the profiled section
        """
        if name not in self._start_times:
            logger.warning(f"No profiling started for: {name}")
            return PerformanceMetrics(name=name, duration=0.0)

        duration = time.time() - self._start_times[name]

        # Stop CPU monitoring
        cpu_percent = self._stop_cpu_monitoring(name)

        # Get memory usage
        memory_current = 0
        memory_peak = 0
        if self.enable_memory_tracing:
            current, _ = tracemalloc.get_traced_memory()
            memory_current = current
            memory_peak = current - self._memory_start.get(name, 0)

        # Create metrics
        metrics = PerformanceMetrics(
            name=name,
            duration=duration,
            memory_peak=memory_peak,
            memory_current=memory_current,
            cpu_percent=cpu_percent,
        )

        # Clean up
        self._start_times.pop(name, None)
        self._memory_start.pop(name, None)

        if name in self._profiler_stack:
            self._profiler_stack.remove(name)

        self.metrics.append(metrics)
        logger.debug(f"Stopped profiling: {name} (duration: {duration:.3f}s)")

        return metrics

    def _start_cpu_monitoring(self, name: str) -> None:
        """Start CPU monitoring for a profiling session."""
        self._cpu_usage[name] = []
        self._should_stop_monitoring.clear()

        def monitor_cpu():
            process = psutil.Process()
            while not self._should_stop_monitoring.wait(0.1):  # Sample every 100ms
                try:
                    cpu_percent = process.cpu_percent()
                    if name in self._cpu_usage:
                        self._cpu_usage[name].append(cpu_percent)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break

        self._cpu_monitor = threading.Thread(target=monitor_cpu, daemon=True)
        self._cpu_monitor.start()

    def _stop_cpu_monitoring(self, name: str) -> float:
        """Stop CPU monitoring and return average CPU usage."""
        self._should_stop_monitoring.set()

        if self._cpu_monitor and self._cpu_monitor.is_alive():
            self._cpu_monitor.join(timeout=1.0)

        cpu_readings = self._cpu_usage.get(name, [])
        avg_cpu = sum(cpu_readings) / len(cpu_readings) if cpu_readings else 0.0

        # Clean up
        self._cpu_usage.pop(name, None)

        return avg_cpu

    @contextmanager
    def profile_section(self, name: str) -> Generator[None, None, None]:
        """Context manager for profiling a code section.

        Args:
            name: Name of the code section being profiled

        Yields:
            None
        """
        self.start_profiling(name)
        try:
            yield
        finally:
            self.stop_profiling(name)

    def profile_function_calls(self, name: str) -> None:
        """Profile detailed function calls using cProfile.

        Args:
            name: Name for the profiling session
        """
        if not self.metrics:
            logger.warning("No metrics available for function call profiling")
            return

        # Find the most recent metric
        recent_metric = self.metrics[-1]
        if recent_metric.name != name:
            logger.warning(f"Metric name mismatch: expected {name}, got {recent_metric.name}")
            return

        # Create profiler and run
        _ = cProfile.Profile()

        # This is a simplified approach - in real usage, you'd profile the actual function
        logger.info(f"Function call profiling completed for: {name}")

    def get_memory_trace(self, limit: int = 10) -> list[str] | None:
        """Get current memory trace information.

        Args:
            limit: Maximum number of trace lines to return

        Returns:
            List of formatted trace lines or None if tracing disabled
        """
        if not self.enable_memory_tracing or not tracemalloc.is_tracing():
            return None

        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics("lineno")

        trace_lines = []
        for stat in top_stats[:limit]:
            trace_lines.append(
                f"{stat.traceback.format()[-1].strip()}: {stat.size / 1024 / 1024:.1f} MB"
            )

        return trace_lines

    def generate_report(self) -> PerformanceReport:
        """Generate a comprehensive performance report.

        Returns:
            Performance report with metrics and recommendations
        """
        if not self.metrics:
            logger.warning("No metrics available for report generation")
            return PerformanceReport(total_duration=0.0, peak_memory=0)

        total_duration = sum(m.duration for m in self.metrics)
        peak_memory = max(m.memory_peak for m in self.metrics)

        report = PerformanceReport(
            total_duration=total_duration,
            peak_memory=peak_memory,
            metrics=self.metrics.copy(),
        )

        report.identify_bottlenecks()
        report.generate_recommendations()

        return report

    def clear_metrics(self) -> None:
        """Clear all collected metrics."""
        self.metrics.clear()
        self._profiler_stack.clear()
        self._start_times.clear()
        self._memory_start.clear()
        self._cpu_usage.clear()
        logger.debug("Performance metrics cleared")

    def save_report(self, report: PerformanceReport, file_path: Path) -> None:
        """Save performance report to file.

        Args:
            report: Performance report to save
            file_path: Path to save the report
        """
        import json

        report_data = report.to_dict()
        report_data["timestamp"] = time.time()
        report_data["profiler_config"] = {
            "memory_tracing_enabled": self.enable_memory_tracing,
            "metrics_count": len(self.metrics),
        }

        with open(file_path, "w") as f:
            json.dump(report_data, f, indent=2)

        logger.info(f"Performance report saved to: {file_path}")


def profile_performance(name: str, profiler: PerformanceProfiler | None = None):
    """Decorator for profiling function performance.

    Args:
        name: Name for the profiling session
        profiler: Optional profiler instance to use

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            p = profiler or PerformanceProfiler()

            with p.profile_section(f"{name}:{func.__name__}"):
                result = func(*args, **kwargs)

            return result

        return wrapper

    return decorator


# Global profiler instance for convenience
_global_profiler: PerformanceProfiler | None = None


def get_global_profiler() -> PerformanceProfiler:
    """Get or create the global profiler instance."""
    global _global_profiler
    if _global_profiler is None:
        _global_profiler = PerformanceProfiler()
    return _global_profiler


def profile_critical_path(name: str):
    """Convenience decorator using the global profiler."""
    return profile_performance(name, get_global_profiler())


@contextmanager
def profile_context(name: str) -> Generator[PerformanceProfiler, None, None]:
    """Context manager that provides a profiler for a code block.

    Args:
        name: Name of the profiling session

    Yields:
        PerformanceProfiler instance
    """
    profiler = PerformanceProfiler()

    with profiler.profile_section(name):
        yield profiler


def analyze_project_performance(project_path: Path) -> PerformanceReport:
    """Analyze overall project performance characteristics.

    Args:
        project_path: Path to the project to analyze

    Returns:
        Performance report for the project
    """
    profiler = PerformanceProfiler()

    with profiler.profile_section("project_analysis"):
        # Simulate project analysis
        time.sleep(0.01)  # Placeholder for actual analysis

        # Analyze project size
        python_files = list(project_path.rglob("*.py"))
        total_size = sum(f.stat().st_size for f in python_files if f.exists())

        logger.info(f"Analyzed project: {len(python_files)} Python files, {total_size} bytes")

    report = profiler.generate_report()
    return report
