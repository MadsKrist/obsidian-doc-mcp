"""Tests for performance profiler functionality."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from utils.performance_profiler import (
    PerformanceMetrics,
    PerformanceProfiler,
    PerformanceReport,
    analyze_project_performance,
    get_global_profiler,
    profile_context,
    profile_critical_path,
    profile_performance,
)


class TestPerformanceMetrics:
    """Test cases for PerformanceMetrics."""

    def test_initialization(self):
        """Test metrics initialization."""
        metrics = PerformanceMetrics(
            name="test_operation", duration=1.5, memory_peak=1024, cpu_percent=50.0
        )

        assert metrics.name == "test_operation"
        assert metrics.duration == 1.5
        assert metrics.memory_peak == 1024
        assert metrics.cpu_percent == 50.0
        assert metrics.calls_count == 0
        assert metrics.cumulative_time == 0.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = PerformanceMetrics(
            name="test_operation",
            duration=2.0,
            memory_peak=2048,
            cpu_percent=75.0,
            calls_count=100,
        )

        result = metrics.to_dict()

        assert result["name"] == "test_operation"
        assert result["duration"] == 2.0
        assert result["memory_peak"] == 2048
        assert result["cpu_percent"] == 75.0
        assert result["calls_count"] == 100
        assert result["has_profile_stats"] is False
        assert result["has_memory_trace"] is False


class TestPerformanceReport:
    """Test cases for PerformanceReport."""

    def test_initialization(self):
        """Test report initialization."""
        report = PerformanceReport(total_duration=5.0, peak_memory=4096)

        assert report.total_duration == 5.0
        assert report.peak_memory == 4096
        assert report.metrics == []
        assert report.bottlenecks == []
        assert report.recommendations == []

    def test_add_metric(self):
        """Test adding metrics to report."""
        report = PerformanceReport(total_duration=5.0, peak_memory=4096)
        metric = PerformanceMetrics(name="test", duration=1.0)

        report.add_metric(metric)

        assert len(report.metrics) == 1
        assert report.metrics[0] is metric

    def test_identify_bottlenecks(self):
        """Test bottleneck identification."""
        report = PerformanceReport(total_duration=10.0, peak_memory=4096)

        # Add metrics with different durations
        report.add_metric(PerformanceMetrics(name="fast_op", duration=0.5))
        report.add_metric(
            PerformanceMetrics(name="slow_op", duration=3.0)
        )  # 30% of total
        report.add_metric(PerformanceMetrics(name="medium_op", duration=1.5))

        report.identify_bottlenecks(threshold_ratio=0.2)  # 20% threshold

        assert len(report.bottlenecks) == 1
        assert "slow_op" in report.bottlenecks[0]
        assert "30.0%" in report.bottlenecks[0]

    def test_identify_bottlenecks_empty_metrics(self):
        """Test bottleneck identification with no metrics."""
        report = PerformanceReport(total_duration=10.0, peak_memory=4096)

        report.identify_bottlenecks()

        assert report.bottlenecks == []

    def test_generate_recommendations_high_memory(self):
        """Test recommendations for high memory usage."""
        report = PerformanceReport(
            total_duration=5.0, peak_memory=600 * 1024 * 1024  # 600MB
        )

        report.generate_recommendations()

        assert len(report.recommendations) >= 1
        assert any("memory usage" in rec.lower() for rec in report.recommendations)

    def test_generate_recommendations_long_duration(self):
        """Test recommendations for long execution time."""
        report = PerformanceReport(total_duration=35.0, peak_memory=1024)

        report.generate_recommendations()

        assert len(report.recommendations) >= 1
        assert any("execution time" in rec.lower() for rec in report.recommendations)

    def test_generate_recommendations_high_cpu(self):
        """Test recommendations for high CPU usage."""
        report = PerformanceReport(total_duration=5.0, peak_memory=1024)
        report.add_metric(
            PerformanceMetrics(name="cpu_intensive", duration=1.0, cpu_percent=85.0)
        )

        report.generate_recommendations()

        assert len(report.recommendations) >= 1
        assert any("cpu-intensive" in rec.lower() for rec in report.recommendations)

    def test_generate_recommendations_high_calls(self):
        """Test recommendations for high function call counts."""
        report = PerformanceReport(total_duration=5.0, peak_memory=1024)
        report.add_metric(
            PerformanceMetrics(name="call_heavy", duration=1.0, calls_count=15000)
        )

        report.generate_recommendations()

        assert len(report.recommendations) >= 1
        assert any("call counts" in rec.lower() for rec in report.recommendations)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        report = PerformanceReport(total_duration=5.0, peak_memory=4096)
        metric = PerformanceMetrics(name="test", duration=1.0)
        report.add_metric(metric)
        report.bottlenecks = ["test bottleneck"]
        report.recommendations = ["test recommendation"]

        result = report.to_dict()

        assert result["total_duration"] == 5.0
        assert result["peak_memory"] == 4096
        assert len(result["metrics"]) == 1
        assert result["bottlenecks"] == ["test bottleneck"]
        assert result["recommendations"] == ["test recommendation"]


class TestPerformanceProfiler:
    """Test cases for PerformanceProfiler."""

    def test_initialization(self):
        """Test profiler initialization."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)

        assert profiler.enable_memory_tracing is False
        assert profiler.metrics == []
        assert profiler._profiler_stack == []
        assert profiler._start_times == {}
        assert profiler._memory_start == {}

    def test_initialization_with_memory_tracing(self):
        """Test profiler initialization with memory tracing."""
        with patch("utils.performance_profiler.tracemalloc") as mock_tracemalloc:
            mock_tracemalloc.is_tracing.return_value = False

            profiler = PerformanceProfiler(enable_memory_tracing=True)

            assert profiler.enable_memory_tracing is True
            mock_tracemalloc.start.assert_called_once()

    def test_start_profiling(self):
        """Test starting profiling."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)

        with patch("time.time", return_value=1000.0):
            profiler.start_profiling("test_operation")

        assert "test_operation" in profiler._profiler_stack
        assert profiler._start_times["test_operation"] == 1000.0

    def test_start_profiling_with_memory(self):
        """Test starting profiling with memory tracing."""
        with patch("utils.performance_profiler.tracemalloc") as mock_tracemalloc:
            mock_tracemalloc.is_tracing.return_value = True
            mock_tracemalloc.get_traced_memory.return_value = (1024, 2048)

            profiler = PerformanceProfiler(enable_memory_tracing=True)
            profiler.start_profiling("test_operation")

            assert profiler._memory_start["test_operation"] == 1024

    def test_stop_profiling(self):
        """Test stopping profiling."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)

        # Mock CPU monitoring methods
        profiler._start_cpu_monitoring = Mock()
        profiler._stop_cpu_monitoring = Mock(return_value=50.0)

        with patch("time.time", side_effect=[1000.0, 1002.5]):
            profiler.start_profiling("test_operation")
            metrics = profiler.stop_profiling("test_operation")

        assert metrics.name == "test_operation"
        assert metrics.duration == 2.5
        assert metrics.cpu_percent == 50.0
        assert len(profiler.metrics) == 1
        assert "test_operation" not in profiler._profiler_stack
        assert "test_operation" not in profiler._start_times

    def test_stop_profiling_not_started(self):
        """Test stopping profiling that wasn't started."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)

        metrics = profiler.stop_profiling("nonexistent")

        assert metrics.name == "nonexistent"
        assert metrics.duration == 0.0

    def test_stop_profiling_with_memory(self):
        """Test stopping profiling with memory tracing."""
        with patch("utils.performance_profiler.tracemalloc") as mock_tracemalloc:
            mock_tracemalloc.is_tracing.return_value = True
            mock_tracemalloc.get_traced_memory.side_effect = [
                (1024, 2048),
                (2048, 4096),
            ]

            profiler = PerformanceProfiler(enable_memory_tracing=True)
            profiler._start_cpu_monitoring = Mock()
            profiler._stop_cpu_monitoring = Mock(return_value=25.0)

            with patch("time.time", side_effect=[1000.0, 1001.0]):
                profiler.start_profiling("test_operation")
                metrics = profiler.stop_profiling("test_operation")

            assert metrics.memory_current == 2048
            assert metrics.memory_peak == 1024  # 2048 - 1024 from start

    def test_profile_section_context_manager(self):
        """Test profile_section context manager."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)
        profiler._start_cpu_monitoring = Mock()
        profiler._stop_cpu_monitoring = Mock(return_value=30.0)

        with patch("time.time", side_effect=[1000.0, 1001.5]):
            with profiler.profile_section("test_context"):
                # Simulate some work
                pass

        assert len(profiler.metrics) == 1
        assert profiler.metrics[0].name == "test_context"
        assert profiler.metrics[0].duration == 1.5

    def test_profile_section_with_exception(self):
        """Test profile_section context manager with exception."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)
        profiler._start_cpu_monitoring = Mock()
        profiler._stop_cpu_monitoring = Mock(return_value=30.0)

        with patch("time.time", side_effect=[1000.0, 1001.0]):
            with pytest.raises(ValueError):
                with profiler.profile_section("test_exception"):
                    raise ValueError("Test exception")

        # Profiling should still complete
        assert len(profiler.metrics) == 1
        assert profiler.metrics[0].name == "test_exception"

    def test_get_memory_trace_disabled(self):
        """Test getting memory trace when disabled."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)

        result = profiler.get_memory_trace()

        assert result is None

    def test_get_memory_trace_enabled(self):
        """Test getting memory trace when enabled."""
        with patch("utils.performance_profiler.tracemalloc") as mock_tracemalloc:
            mock_tracemalloc.is_tracing.return_value = True

            # Mock snapshot and statistics
            mock_stat = Mock()
            mock_stat.size = 1024 * 1024  # 1MB
            mock_stat.traceback.format.return_value = ["file.py:10: function()"]

            mock_snapshot = Mock()
            mock_snapshot.statistics.return_value = [mock_stat]
            mock_tracemalloc.take_snapshot.return_value = mock_snapshot

            profiler = PerformanceProfiler(enable_memory_tracing=True)
            result = profiler.get_memory_trace(limit=5)

            assert result is not None
            assert len(result) == 1
            assert "1.0 MB" in result[0]

    def test_generate_report(self):
        """Test generating performance report."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)

        # Add some test metrics
        metric1 = PerformanceMetrics(name="op1", duration=1.0, memory_peak=1024)
        metric2 = PerformanceMetrics(name="op2", duration=2.0, memory_peak=2048)
        profiler.metrics = [metric1, metric2]

        report = profiler.generate_report()

        assert report.total_duration == 3.0
        assert report.peak_memory == 2048
        assert len(report.metrics) == 2

    def test_generate_report_empty_metrics(self):
        """Test generating report with no metrics."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)

        report = profiler.generate_report()

        assert report.total_duration == 0.0
        assert report.peak_memory == 0
        assert len(report.metrics) == 0

    def test_clear_metrics(self):
        """Test clearing metrics."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)

        # Add some test data
        profiler.metrics = [PerformanceMetrics(name="test", duration=1.0)]
        profiler._profiler_stack = ["test"]
        profiler._start_times = {"test": 1000.0}
        profiler._memory_start = {"test": 1024}
        profiler._cpu_usage = {"test": [50.0]}

        profiler.clear_metrics()

        assert profiler.metrics == []
        assert profiler._profiler_stack == []
        assert profiler._start_times == {}
        assert profiler._memory_start == {}
        assert profiler._cpu_usage == {}

    def test_save_report(self):
        """Test saving performance report."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)

        # Create test report
        report = PerformanceReport(total_duration=5.0, peak_memory=4096)
        report.add_metric(PerformanceMetrics(name="test", duration=1.0))
        report.bottlenecks = ["test bottleneck"]
        report.recommendations = ["test recommendation"]

        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            with patch("time.time", return_value=1234567890.0):
                profiler.save_report(report, temp_path)

            # Verify file contents
            with open(temp_path) as f:
                saved_data = json.load(f)

            assert saved_data["total_duration"] == 5.0
            assert saved_data["peak_memory"] == 4096
            assert saved_data["timestamp"] == 1234567890.0
            assert "profiler_config" in saved_data

        finally:
            temp_path.unlink(missing_ok=True)


class TestDecoratorsAndHelpers:
    """Test cases for decorators and helper functions."""

    def test_profile_performance_decorator(self):
        """Test profile_performance decorator."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)
        profiler._start_cpu_monitoring = Mock()
        profiler._stop_cpu_monitoring = Mock(return_value=40.0)

        @profile_performance("test_func", profiler)
        def test_function(x, y):
            return x + y

        with patch("time.time", side_effect=[1000.0, 1001.0]):
            result = test_function(2, 3)

        assert result == 5
        assert len(profiler.metrics) == 1
        assert profiler.metrics[0].name == "test_func:test_function"

    def test_profile_performance_decorator_without_profiler(self):
        """Test profile_performance decorator without providing profiler."""

        @profile_performance("test_func")
        def test_function(x):
            return x * 2

        with patch(
            "utils.performance_profiler.PerformanceProfiler"
        ) as mock_profiler_class:
            mock_profiler = Mock()
            mock_profiler.profile_section.return_value.__enter__ = Mock()
            mock_profiler.profile_section.return_value.__exit__ = Mock()
            mock_profiler_class.return_value = mock_profiler

            result = test_function(5)

        assert result == 10
        mock_profiler_class.assert_called_once()

    def test_get_global_profiler(self):
        """Test getting global profiler instance."""
        # Clear global profiler first
        import utils.performance_profiler

        utils.performance_profiler._global_profiler = None

        profiler1 = get_global_profiler()
        profiler2 = get_global_profiler()

        assert profiler1 is profiler2
        assert isinstance(profiler1, PerformanceProfiler)

    def test_profile_critical_path_decorator(self):
        """Test profile_critical_path decorator."""
        with patch("utils.performance_profiler.get_global_profiler") as mock_get_global:
            mock_profiler = Mock()
            mock_profiler.profile_section.return_value.__enter__ = Mock()
            mock_profiler.profile_section.return_value.__exit__ = Mock()
            mock_get_global.return_value = mock_profiler

            @profile_critical_path("critical_section")
            def critical_function():
                return "critical_result"

            result = critical_function()

        assert result == "critical_result"
        mock_get_global.assert_called_once()

    def test_profile_context_manager(self):
        """Test profile_context context manager."""
        with patch(
            "utils.performance_profiler.PerformanceProfiler"
        ) as mock_profiler_class:
            mock_profiler = Mock()
            mock_profiler.profile_section.return_value.__enter__ = Mock(
                return_value=None
            )
            mock_profiler.profile_section.return_value.__exit__ = Mock(
                return_value=None
            )
            mock_profiler_class.return_value = mock_profiler

            with profile_context("test_context") as profiler:
                assert profiler is mock_profiler

            mock_profiler.profile_section.assert_called_once_with("test_context")

    def test_analyze_project_performance(self):
        """Test project performance analysis."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create some test Python files
            (project_path / "module1.py").write_text("# Module 1")
            (project_path / "module2.py").write_text("# Module 2")

            with patch(
                "utils.performance_profiler.PerformanceProfiler"
            ) as mock_profiler_class:
                mock_profiler = Mock()
                mock_profiler.profile_section.return_value.__enter__ = Mock()
                mock_profiler.profile_section.return_value.__exit__ = Mock()
                mock_report = Mock()
                mock_profiler.generate_report.return_value = mock_report
                mock_profiler_class.return_value = mock_profiler

                result = analyze_project_performance(project_path)

            assert result is mock_report
            mock_profiler.profile_section.assert_called_once_with("project_analysis")
            mock_profiler.generate_report.assert_called_once()


class TestCPUMonitoring:
    """Test cases for CPU monitoring functionality."""

    def test_start_stop_cpu_monitoring(self):
        """Test CPU monitoring start and stop."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)

        with patch(
            "utils.performance_profiler.psutil.Process"
        ) as mock_process_class, patch("threading.Thread") as mock_thread_class:
            mock_process = Mock()
            mock_process.cpu_percent.return_value = 75.0
            mock_process_class.return_value = mock_process

            mock_thread = Mock()
            mock_thread_class.return_value = mock_thread

            # Start monitoring
            profiler._start_cpu_monitoring("test_op")

            assert "test_op" in profiler._cpu_usage
            mock_thread_class.assert_called_once()
            mock_thread.start.assert_called_once()

            # Simulate some CPU readings
            profiler._cpu_usage["test_op"] = [70.0, 75.0, 80.0]

            # Stop monitoring
            avg_cpu = profiler._stop_cpu_monitoring("test_op")

            assert avg_cpu == 75.0  # (70 + 75 + 80) / 3
            assert "test_op" not in profiler._cpu_usage

    def test_stop_cpu_monitoring_no_readings(self):
        """Test stopping CPU monitoring with no readings."""
        profiler = PerformanceProfiler(enable_memory_tracing=False)

        avg_cpu = profiler._stop_cpu_monitoring("nonexistent")

        assert avg_cpu == 0.0
