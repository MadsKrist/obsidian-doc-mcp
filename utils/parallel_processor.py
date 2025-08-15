"""Parallel processing utilities for documentation generation.

This module provides functionality to process multiple modules in parallel,
improving performance for large projects with many independent modules.
"""

import concurrent.futures
import logging
import multiprocessing
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class ProcessingTask(Generic[T, R]):
    """Represents a processing task with input and expected output types."""

    task_id: str
    input_data: T
    processor_func: Callable[[T], R]
    dependencies: set[str] = field(default_factory=set)
    priority: int = 0  # Higher numbers = higher priority
    estimated_duration: float = 1.0  # Estimated processing time in seconds


@dataclass
class ProcessingResult(Generic[R]):
    """Represents the result of a processing task."""

    task_id: str
    result: R | None = None
    error: Exception | None = None
    start_time: float = 0.0
    end_time: float = 0.0
    worker_id: str | None = None

    @property
    def duration(self) -> float:
        """Get the processing duration."""
        return self.end_time - self.start_time if self.end_time > self.start_time else 0.0

    @property
    def success(self) -> bool:
        """Check if the task was successful."""
        return self.error is None


class DependencyResolver:
    """Resolves task dependencies and determines execution order."""

    def __init__(self):
        self.tasks: dict[str, ProcessingTask] = {}
        self.resolved_order: list[str] = []

    def add_task(self, task: ProcessingTask) -> None:
        """Add a task to the dependency graph."""
        self.tasks[task.task_id] = task
        logger.debug(f"Added task {task.task_id} with dependencies: {task.dependencies}")

    def resolve_dependencies(self) -> list[list[str]]:
        """Resolve dependencies and return tasks grouped by execution level.

        Returns:
            List of lists, where each inner list contains task IDs that can
            be executed in parallel (no dependencies between them).
        """
        # Build dependency graph
        remaining_tasks = set(self.tasks.keys())
        completed_tasks: set[str] = set()
        execution_levels: list[list[str]] = []

        while remaining_tasks:
            # Find tasks that can be executed (all dependencies met)
            ready_tasks = []
            for task_id in remaining_tasks:
                task = self.tasks[task_id]
                if task.dependencies.issubset(completed_tasks):
                    ready_tasks.append(task_id)

            if not ready_tasks:
                # Circular dependency or missing dependency
                remaining_deps = []
                for task_id in remaining_tasks:
                    task = self.tasks[task_id]
                    missing = task.dependencies - completed_tasks
                    if missing:
                        remaining_deps.append(f"{task_id} -> {missing}")

                raise ValueError(f"Circular dependency or missing tasks detected: {remaining_deps}")

            # Sort by priority (higher priority first)
            ready_tasks.sort(key=lambda tid: self.tasks[tid].priority, reverse=True)
            execution_levels.append(ready_tasks)

            # Mark ready tasks as completed for next iteration
            for task_id in ready_tasks:
                remaining_tasks.remove(task_id)
                completed_tasks.add(task_id)

        logger.info(
            f"Resolved {len(self.tasks)} tasks into {len(execution_levels)} execution levels"
        )
        return execution_levels


class ParallelProcessor:
    """Manages parallel processing of tasks with dependency resolution."""

    def __init__(
        self,
        max_workers: int | None = None,
        use_threads: bool = True,
        timeout_per_task: float = 300.0,  # 5 minutes default
    ):
        """Initialize the parallel processor.

        Args:
            max_workers: Maximum number of worker processes/threads
            use_threads: Use threads instead of processes
            timeout_per_task: Timeout per task in seconds
        """
        self.max_workers = max_workers or min(32, (multiprocessing.cpu_count() or 1) + 4)
        self.use_threads = use_threads
        self.timeout_per_task = timeout_per_task
        self.dependency_resolver = DependencyResolver()
        self.results: dict[str, ProcessingResult] = {}

        logger.info(
            f"Parallel processor initialized: {self.max_workers} workers, "
            f"{'threads' if use_threads else 'processes'}"
        )

    def add_task(
        self,
        task_id: str,
        input_data: Any,
        processor_func: Callable[[Any], Any],
        dependencies: set[str] | None = None,
        priority: int = 0,
        estimated_duration: float = 1.0,
    ) -> None:
        """Add a task to be processed.

        Args:
            task_id: Unique identifier for the task
            input_data: Data to be processed
            processor_func: Function to process the data
            dependencies: Set of task IDs this task depends on
            priority: Task priority (higher = more important)
            estimated_duration: Estimated processing time in seconds
        """
        task = ProcessingTask(
            task_id=task_id,
            input_data=input_data,
            processor_func=processor_func,
            dependencies=dependencies or set(),
            priority=priority,
            estimated_duration=estimated_duration,
        )

        self.dependency_resolver.add_task(task)

    def process_all(
        self, progress_callback: Callable[[str, float], None] | None = None
    ) -> dict[str, ProcessingResult]:
        """Process all tasks in parallel, respecting dependencies.

        Args:
            progress_callback: Optional callback for progress updates
                               (message, progress)

        Returns:
            Dictionary of task results
        """
        if not self.dependency_resolver.tasks:
            logger.warning("No tasks to process")
            return {}

        execution_levels = self.dependency_resolver.resolve_dependencies()
        total_tasks = len(self.dependency_resolver.tasks)
        completed_tasks = 0

        logger.info(f"Starting parallel processing of {total_tasks} tasks")

        for level_idx, task_ids in enumerate(execution_levels):
            logger.info(
                f"Processing level {level_idx + 1}/{len(execution_levels)}: {len(task_ids)} tasks"
            )

            if progress_callback:
                progress_callback(
                    f"Processing level {level_idx + 1}/{len(execution_levels)}",
                    completed_tasks / total_tasks,
                )

            # Process tasks in this level in parallel
            level_results = self._process_task_level(task_ids)
            self.results.update(level_results)

            # Check for failures
            failed_tasks = [tid for tid, result in level_results.items() if not result.success]
            if failed_tasks:
                logger.error(f"Failed tasks in level {level_idx + 1}: {failed_tasks}")
                # Optionally continue or stop based on failure handling strategy

            completed_tasks += len(task_ids)

        if progress_callback:
            progress_callback("Processing complete", 1.0)

        # Log summary statistics
        successful = sum(1 for result in self.results.values() if result.success)
        total_time = sum(result.duration for result in self.results.values())

        logger.info(
            f"Parallel processing complete: {successful}/{total_tasks} successful, "
            f"total time: {total_time:.2f}s"
        )

        return self.results

    def _process_task_level(self, task_ids: list[str]) -> dict[str, ProcessingResult]:
        """Process a level of independent tasks in parallel."""
        if not task_ids:
            return {}

        tasks = [self.dependency_resolver.tasks[tid] for tid in task_ids]
        level_results = {}

        # Choose executor type based on configuration
        executor_class = (
            concurrent.futures.ThreadPoolExecutor
            if self.use_threads
            else concurrent.futures.ProcessPoolExecutor
        )

        with executor_class(max_workers=min(self.max_workers, len(tasks))) as executor:
            # Submit all tasks
            future_to_task = {executor.submit(self._execute_task, task): task for task in tasks}

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_task, timeout=None):
                task = future_to_task[future]

                try:
                    result = future.result(timeout=self.timeout_per_task)
                    level_results[task.task_id] = result

                    if result.success:
                        logger.debug(f"Task {task.task_id} completed in {result.duration:.2f}s")
                    else:
                        logger.error(f"Task {task.task_id} failed: {result.error}")

                except concurrent.futures.TimeoutError:
                    logger.error(f"Task {task.task_id} timed out after {self.timeout_per_task}s")
                    level_results[task.task_id] = ProcessingResult(
                        task_id=task.task_id,
                        error=TimeoutError(f"Task timed out after {self.timeout_per_task}s"),
                    )

                except Exception as e:
                    logger.error(f"Unexpected error processing task {task.task_id}: {e}")
                    level_results[task.task_id] = ProcessingResult(task_id=task.task_id, error=e)

        return level_results

    def _execute_task(self, task: ProcessingTask) -> ProcessingResult:
        """Execute a single task and return the result."""
        result = ProcessingResult(
            task_id=task.task_id,
            start_time=time.time(),
            worker_id=threading.current_thread().name if self.use_threads else None,
        )

        try:
            logger.debug(f"Starting task {task.task_id}")
            result.result = task.processor_func(task.input_data)
            logger.debug(f"Completed task {task.task_id}")

        except Exception as e:
            result.error = e
            logger.error(f"Task {task.task_id} failed with error: {e}")

        finally:
            result.end_time = time.time()

        return result

    def get_processing_statistics(self) -> dict[str, Any]:
        """Get detailed processing statistics."""
        if not self.results:
            return {"message": "No processing results available"}

        successful_results = [r for r in self.results.values() if r.success]
        failed_results = [r for r in self.results.values() if not r.success]

        total_time = sum(r.duration for r in self.results.values())
        successful_time = sum(r.duration for r in successful_results)

        return {
            "total_tasks": len(self.results),
            "successful_tasks": len(successful_results),
            "failed_tasks": len(failed_results),
            "success_rate": len(successful_results) / len(self.results) if self.results else 0,
            "total_processing_time": total_time,
            "successful_processing_time": successful_time,
            "average_task_time": successful_time / len(successful_results)
            if successful_results
            else 0,
            "max_task_time": max((r.duration for r in successful_results), default=0),
            "min_task_time": min((r.duration for r in successful_results), default=0),
            "failed_task_ids": [r.task_id for r in failed_results],
            "worker_configuration": {
                "max_workers": self.max_workers,
                "use_threads": self.use_threads,
                "timeout_per_task": self.timeout_per_task,
            },
        }


class ModuleDependencyAnalyzer:
    """Analyzes module dependencies to optimize parallel processing order."""

    def __init__(self):
        self.import_graph: dict[str, set[str]] = {}
        self.file_dependencies: dict[str, set[str]] = {}

    def analyze_module_dependencies(self, modules: list[Any]) -> dict[str, set[str]]:
        """Analyze dependencies between modules.

        Args:
            modules: List of ModuleInfo objects

        Returns:
            Dictionary mapping module names to their dependencies
        """
        # Build import graph
        for module in modules:
            module_name = module.name
            self.import_graph[module_name] = set()

            # Add internal imports as dependencies
            for import_name in module.imports:
                # Check if this import refers to another module in our set
                for other_module in modules:
                    if import_name == other_module.name or import_name.startswith(
                        other_module.name + "."
                    ):
                        self.import_graph[module_name].add(other_module.name)
                        break

        # Remove self-references
        for module_name in self.import_graph:
            self.import_graph[module_name].discard(module_name)

        # Transitive reduction to minimize dependencies
        self._reduce_transitive_dependencies()

        logger.info(f"Analyzed dependencies for {len(modules)} modules")
        return dict(self.import_graph)

    def _reduce_transitive_dependencies(self) -> None:
        """Remove transitive dependencies to minimize the dependency graph."""
        # For each module, remove dependencies that are implied by other dependencies
        for module_name in self.import_graph:
            deps = self.import_graph[module_name].copy()

            for dep in list(deps):
                # If any other dependency already depends on this one, remove it
                for other_dep in deps:
                    if other_dep != dep and dep in self.import_graph.get(other_dep, set()):
                        deps.discard(dep)
                        break

            self.import_graph[module_name] = deps

    def get_independent_modules(self) -> list[str]:
        """Get modules that have no dependencies and can be processed first."""
        return [module_name for module_name, deps in self.import_graph.items() if not deps]

    def estimate_processing_complexity(self, module) -> float:
        """Estimate processing complexity for a module (for priority/scheduling).

        Args:
            module: ModuleInfo object

        Returns:
            Estimated complexity score (higher = more complex)
        """
        complexity = 1.0

        # Base complexity on code size
        complexity += len(module.functions) * 0.1
        complexity += len(module.classes) * 0.2

        # Add complexity for each class method
        for cls in module.classes:
            complexity += len(cls.methods) * 0.05
            complexity += len(cls.properties) * 0.03

        # Add complexity for imports (external dependencies)
        complexity += len(module.imports) * 0.02

        return complexity
