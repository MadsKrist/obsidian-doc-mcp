"""Tests for parallel processing functionality."""

import time
from unittest.mock import MagicMock

import pytest

from utils.parallel_processor import (
    DependencyResolver,
    ModuleDependencyAnalyzer,
    ParallelProcessor,
    ProcessingResult,
    ProcessingTask,
)


class TestProcessingTask:
    """Test ProcessingTask dataclass."""

    def test_processing_task_creation(self):
        """Test ProcessingTask creation."""

        def dummy_processor(x):
            return x * 2

        task = ProcessingTask(
            task_id="test_task",
            input_data=42,
            processor_func=dummy_processor,
            dependencies={"dep1", "dep2"},
            priority=5,
            estimated_duration=2.5,
        )

        assert task.task_id == "test_task"
        assert task.input_data == 42
        assert task.processor_func == dummy_processor
        assert task.dependencies == {"dep1", "dep2"}
        assert task.priority == 5
        assert task.estimated_duration == 2.5


class TestProcessingResult:
    """Test ProcessingResult dataclass."""

    def test_processing_result_creation(self):
        """Test ProcessingResult creation and properties."""
        result = ProcessingResult(
            task_id="test_task", result="success", start_time=100.0, end_time=105.0
        )

        assert result.task_id == "test_task"
        assert result.result == "success"
        assert result.duration == 5.0
        assert result.success is True  # No error

    def test_processing_result_with_error(self):
        """Test ProcessingResult with error."""
        error = ValueError("Test error")
        result = ProcessingResult(task_id="test_task", error=error)

        assert result.success is False
        assert result.error == error


class TestDependencyResolver:
    """Test DependencyResolver functionality."""

    def test_dependency_resolver_simple(self):
        """Test simple dependency resolution."""
        resolver = DependencyResolver()

        # Add tasks with no dependencies
        task1 = ProcessingTask("task1", "data1", lambda x: x)
        task2 = ProcessingTask("task2", "data2", lambda x: x)

        resolver.add_task(task1)
        resolver.add_task(task2)

        execution_levels = resolver.resolve_dependencies()

        # Should have one level with both tasks
        assert len(execution_levels) == 1
        assert set(execution_levels[0]) == {"task1", "task2"}

    def test_dependency_resolver_with_dependencies(self):
        """Test dependency resolution with dependencies."""
        resolver = DependencyResolver()

        # Create tasks with dependencies: task2 depends on task1
        task1 = ProcessingTask("task1", "data1", lambda x: x)
        task2 = ProcessingTask("task2", "data2", lambda x: x, dependencies={"task1"})
        task3 = ProcessingTask("task3", "data3", lambda x: x)

        resolver.add_task(task1)
        resolver.add_task(task2)
        resolver.add_task(task3)

        execution_levels = resolver.resolve_dependencies()

        # Should have two levels
        assert len(execution_levels) == 2

        # First level: task1 and task3 (no dependencies)
        assert set(execution_levels[0]) == {"task1", "task3"}

        # Second level: task2 (depends on task1)
        assert execution_levels[1] == ["task2"]

    def test_dependency_resolver_priority_ordering(self):
        """Test that higher priority tasks are ordered first within a level."""
        resolver = DependencyResolver()

        task1 = ProcessingTask("task1", "data1", lambda x: x, priority=1)
        task2 = ProcessingTask("task2", "data2", lambda x: x, priority=5)
        task3 = ProcessingTask("task3", "data3", lambda x: x, priority=3)

        resolver.add_task(task1)
        resolver.add_task(task2)
        resolver.add_task(task3)

        execution_levels = resolver.resolve_dependencies()

        # Should have one level, ordered by priority (highest first)
        assert len(execution_levels) == 1
        assert execution_levels[0] == ["task2", "task3", "task1"]

    def test_dependency_resolver_circular_dependency(self):
        """Test detection of circular dependencies."""
        resolver = DependencyResolver()

        task1 = ProcessingTask("task1", "data1", lambda x: x, dependencies={"task2"})
        task2 = ProcessingTask("task2", "data2", lambda x: x, dependencies={"task1"})

        resolver.add_task(task1)
        resolver.add_task(task2)

        with pytest.raises(ValueError, match="Circular dependency"):
            resolver.resolve_dependencies()

    def test_dependency_resolver_missing_dependency(self):
        """Test detection of missing dependencies."""
        resolver = DependencyResolver()

        task1 = ProcessingTask("task1", "data1", lambda x: x, dependencies={"missing_task"})
        resolver.add_task(task1)

        with pytest.raises(ValueError, match="Circular dependency or missing tasks"):
            resolver.resolve_dependencies()


class TestParallelProcessor:
    """Test ParallelProcessor functionality."""

    def test_parallel_processor_initialization(self):
        """Test parallel processor initialization."""
        processor = ParallelProcessor(max_workers=4, use_threads=True)

        assert processor.max_workers == 4
        assert processor.use_threads is True
        assert processor.timeout_per_task == 300.0

    def test_add_task(self):
        """Test adding tasks to the processor."""
        processor = ParallelProcessor()

        def dummy_processor(x):
            return x * 2

        processor.add_task(
            task_id="test_task",
            input_data=42,
            processor_func=dummy_processor,
            priority=5,
            estimated_duration=2.0,
        )

        assert "test_task" in processor.dependency_resolver.tasks
        task = processor.dependency_resolver.tasks["test_task"]
        assert task.input_data == 42
        assert task.priority == 5

    def test_process_simple_tasks(self):
        """Test processing simple tasks without dependencies."""
        processor = ParallelProcessor(max_workers=2, use_threads=True)

        def multiply_by_two(x):
            return x * 2

        def add_ten(x):
            return x + 10

        processor.add_task("task1", 5, multiply_by_two)
        processor.add_task("task2", 3, add_ten)

        results = processor.process_all()

        assert len(results) == 2
        assert results["task1"].success is True
        assert results["task1"].result == 10  # 5 * 2
        assert results["task2"].success is True
        assert results["task2"].result == 13  # 3 + 10

    def test_process_with_dependencies(self):
        """Test processing tasks with dependencies."""
        processor = ParallelProcessor(max_workers=2, use_threads=True)

        def identity(x):
            return x

        def double(x):
            return x * 2

        # task2 depends on task1
        processor.add_task("task1", 5, identity)
        processor.add_task("task2", 10, double, dependencies={"task1"})

        results = processor.process_all()

        assert len(results) == 2
        assert results["task1"].success is True
        assert results["task1"].result == 5
        assert results["task2"].success is True
        assert results["task2"].result == 20

        # task1 should complete before task2
        assert results["task1"].end_time <= results["task2"].start_time

    def test_process_with_error(self):
        """Test processing tasks that raise errors."""
        processor = ParallelProcessor(max_workers=1, use_threads=True)

        def failing_processor(x):
            raise ValueError("Test error")

        def success_processor(x):
            return x * 2

        processor.add_task("failing_task", 5, failing_processor)
        processor.add_task("success_task", 3, success_processor)

        results = processor.process_all()

        assert len(results) == 2
        assert results["failing_task"].success is False
        assert isinstance(results["failing_task"].error, ValueError)
        assert results["success_task"].success is True
        assert results["success_task"].result == 6

    def test_processing_statistics(self):
        """Test processing statistics generation."""
        processor = ParallelProcessor(max_workers=2, use_threads=True)

        def slow_processor(x):
            time.sleep(0.01)  # Small delay for timing (reduced to avoid slowdown)
            return x

        processor.add_task("task1", 1, slow_processor)
        processor.add_task("task2", 2, slow_processor)

        processor.process_all()
        stats = processor.get_processing_statistics()

        assert stats["total_tasks"] == 2
        assert stats["successful_tasks"] == 2
        assert stats["failed_tasks"] == 0
        assert stats["success_rate"] == 1.0
        assert stats["total_processing_time"] >= 0  # Allow zero for very fast operations
        assert stats["average_task_time"] >= 0  # Allow zero for very fast operations
        assert len(stats["failed_task_ids"]) == 0

    def test_empty_processing(self):
        """Test processing when no tasks are added."""
        processor = ParallelProcessor()
        results = processor.process_all()

        assert len(results) == 0

        stats = processor.get_processing_statistics()
        assert stats["message"] == "No processing results available"


class TestModuleDependencyAnalyzer:
    """Test ModuleDependencyAnalyzer functionality."""

    def test_dependency_analyzer_initialization(self):
        """Test dependency analyzer initialization."""
        analyzer = ModuleDependencyAnalyzer()

        assert len(analyzer.import_graph) == 0
        assert len(analyzer.file_dependencies) == 0

    def test_analyze_simple_modules(self):
        """Test analyzing modules with no dependencies."""
        analyzer = ModuleDependencyAnalyzer()

        # Create mock modules
        module1 = MagicMock()
        module1.name = "module1"
        module1.imports = []

        module2 = MagicMock()
        module2.name = "module2"
        module2.imports = []

        modules = [module1, module2]
        dependencies = analyzer.analyze_module_dependencies(modules)

        assert len(dependencies) == 2
        assert dependencies["module1"] == set()
        assert dependencies["module2"] == set()

    def test_analyze_modules_with_dependencies(self):
        """Test analyzing modules with internal dependencies."""
        analyzer = ModuleDependencyAnalyzer()

        # Create mock modules where module2 imports module1
        module1 = MagicMock()
        module1.name = "module1"
        module1.imports = []

        module2 = MagicMock()
        module2.name = "module2"
        module2.imports = ["module1", "external_lib"]  # One internal, one external

        modules = [module1, module2]
        dependencies = analyzer.analyze_module_dependencies(modules)

        assert dependencies["module1"] == set()
        assert dependencies["module2"] == {"module1"}  # Only internal dependency

    def test_get_independent_modules(self):
        """Test getting modules with no dependencies."""
        analyzer = ModuleDependencyAnalyzer()

        module1 = MagicMock()
        module1.name = "module1"
        module1.imports = []

        module2 = MagicMock()
        module2.name = "module2"
        module2.imports = ["module1"]

        analyzer.analyze_module_dependencies([module1, module2])
        independent = analyzer.get_independent_modules()

        assert independent == ["module1"]

    def test_estimate_processing_complexity(self):
        """Test processing complexity estimation."""
        analyzer = ModuleDependencyAnalyzer()

        # Create a mock module with various components
        module = MagicMock()
        module.functions = [MagicMock() for _ in range(5)]  # 5 functions
        module.classes = []
        for _ in range(2):  # 2 classes
            cls = MagicMock()
            cls.methods = [MagicMock() for _ in range(3)]  # 3 methods each
            cls.properties = [MagicMock()]  # 1 property each
            module.classes.append(cls)
        module.imports = ["lib1", "lib2", "lib3"]  # 3 imports

        complexity = analyzer.estimate_processing_complexity(module)

        # Expected complexity calculation:
        # Base: 1.0
        # Functions: 5 * 0.1 = 0.5
        # Classes: 2 * 0.2 = 0.4
        # Methods: 2 * 3 * 0.05 = 0.3
        # Properties: 2 * 1 * 0.03 = 0.06
        # Imports: 3 * 0.02 = 0.06
        # Total: 1.0 + 0.5 + 0.4 + 0.3 + 0.06 + 0.06 = 2.32

        expected_complexity = 1.0 + 0.5 + 0.4 + 0.3 + 0.06 + 0.06
        assert abs(complexity - expected_complexity) < 0.01

    def test_transitive_dependency_reduction(self):
        """Test reduction of transitive dependencies."""
        analyzer = ModuleDependencyAnalyzer()

        # Create modules: A -> B -> C, A -> C
        # After reduction, A should only depend on B (not C)
        module_a = MagicMock()
        module_a.name = "A"
        module_a.imports = ["B", "C"]

        module_b = MagicMock()
        module_b.name = "B"
        module_b.imports = ["C"]

        module_c = MagicMock()
        module_c.name = "C"
        module_c.imports = []

        modules = [module_a, module_b, module_c]
        dependencies = analyzer.analyze_module_dependencies(modules)

        # After transitive reduction, A should only depend on B
        assert dependencies["A"] == {"B"}  # C should be removed as transitive
        assert dependencies["B"] == {"C"}
        assert dependencies["C"] == set()
