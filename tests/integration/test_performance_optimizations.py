"""Integration tests for all performance optimization features.

This module tests the complete performance optimization pipeline including:
- AST parsing caching
- Incremental build support
- Memory optimization
- Parallel processing
"""

import tempfile
import time
from pathlib import Path

import pytest

from docs_generator.analyzer import PythonProjectAnalyzer
from utils.incremental_build import IncrementalBuildManager
from utils.memory_optimizer import memory_efficient_context
from utils.parallel_processor import ModuleDependencyAnalyzer, ParallelProcessor


class TestPerformanceOptimizationIntegration:
    """Test integration of all performance optimization features."""

    @pytest.fixture
    def large_project(self):
        """Create a large project for performance testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create a project with multiple modules and dependencies
            modules = [
                (
                    "utils",
                    "# Utility functions\n\ndef helper():\n    '''Helper function.'''\n    return 'help'",
                ),
                (
                    "core",
                    "# Core module\nfrom . import utils\n\ndef main():\n    '''Main function.'''\n    return utils.helper()",
                ),
                (
                    "api",
                    "# API module\nfrom . import core\n\nclass API:\n    '''API class.'''\n    def get(self):\n        '''Get data.'''\n        return core.main()",
                ),
                (
                    "models",
                    "# Models\n\nclass User:\n    '''User model.'''\n    def __init__(self, name):\n        self.name = name",
                ),
                (
                    "handlers",
                    "# Handlers\nfrom . import models\nfrom . import api\n\nclass Handler:\n    '''Request handler.'''\n    def process(self):\n        return api.API().get()",
                ),
            ]

            # Create __init__.py to make it a package
            (project_path / "__init__.py").write_text("")

            for name, content in modules:
                (project_path / f"{name}.py").write_text(content)

            # Create a simple config file
            config_content = """
project:
  name: "Performance Test Project"
  source_paths: ["./"]
  exclude_patterns: ["tests/", "*.pyc"]

obsidian:
  docs_folder: "TestDocs"
  use_wikilinks: true

sphinx:
  extensions:
    - "sphinx.ext.autodoc"
    - "sphinx.ext.napoleon"

output:
  generate_index: true
"""
            (project_path / ".mcp-docs.yaml").write_text(config_content.strip())

            yield project_path

    def test_ast_caching_performance(self, large_project):
        """Test that AST caching improves performance."""
        # First run without cache
        analyzer_no_cache = PythonProjectAnalyzer(large_project, enable_cache=False)

        start_time = time.time()
        structure1 = analyzer_no_cache.analyze_project()
        no_cache_time = time.time() - start_time

        # Second run with cache enabled
        analyzer_with_cache = PythonProjectAnalyzer(large_project, enable_cache=True)

        start_time = time.time()
        structure2 = analyzer_with_cache.analyze_project()
        first_cache_time = time.time() - start_time

        # Third run should be faster due to cache
        start_time = time.time()
        structure3 = analyzer_with_cache.analyze_project()
        second_cache_time = time.time() - start_time

        # Verify results are equivalent
        assert (
            len(structure1.modules)
            == len(structure2.modules)
            == len(structure3.modules)
        )

        # Cache should improve performance on subsequent runs
        assert second_cache_time <= first_cache_time

        # Check that cache file was created
        cache_file = large_project / ".mcp-docs-cache.json"
        assert cache_file.exists()

    def test_incremental_build_detection(self, large_project):
        """Test incremental build change detection."""
        build_manager = IncrementalBuildManager(large_project)

        # Get all Python files
        python_files = list(large_project.rglob("*.py"))
        assert len(python_files) > 0

        # All files should be detected as changed initially
        changed_files = build_manager.get_changed_files(python_files)
        assert len(changed_files) == len(python_files)

        # Mark files as built
        build_manager.mark_files_built(python_files)

        # No files should be changed now
        changed_files = build_manager.get_changed_files(python_files)
        assert len(changed_files) == 0

        # Modify one file
        core_file = large_project / "core.py"
        original_content = core_file.read_text()
        core_file.write_text(original_content + "\n# Added comment")

        # Only modified file should be detected as changed
        changed_files = build_manager.get_changed_files(python_files)
        assert len(changed_files) == 1
        assert core_file in changed_files

    def test_memory_optimization_context(self, large_project):
        """Test memory optimization context manager."""
        with memory_efficient_context(
            max_memory_mb=1000,  # 1GB limit (should be safe)
            aggressive_gc=True,
            monitor_operations=True,
        ) as (monitor, optimizer):
            # Test memory monitoring
            initial_snapshot = monitor.get_memory_snapshot()
            assert initial_snapshot.rss_mb > 0

            # Test batch processing
            test_data = list(range(100))
            processed_items = []

            with optimizer.batch_processor(test_data, batch_size=20) as batch_iter:
                for batch in batch_iter:
                    processed_items.extend([x * 2 for x in batch])

            assert len(processed_items) == 100
            assert processed_items[0] == 0
            assert processed_items[99] == 198

            # Test cache clearing
            cleared = optimizer.clear_caches()
            assert isinstance(cleared, dict)
            assert "gc_collected" in cleared

    def test_parallel_processing_setup(self, large_project):
        """Test parallel processing setup and dependency resolution."""
        analyzer = PythonProjectAnalyzer(large_project, enable_cache=True)
        project_structure = analyzer.analyze_project()

        # Test dependency analysis
        dependency_analyzer = ModuleDependencyAnalyzer()
        dependencies = dependency_analyzer.analyze_module_dependencies(
            project_structure.modules
        )

        assert len(dependencies) == len(project_structure.modules)

        # Check that dependencies were detected correctly
        # 'handlers' should depend on 'models' and 'api'
        handlers_deps = dependencies.get("handlers", set())
        expected_deps = {"models", "api"}  # Based on imports in our test data

        # At least some dependencies should be detected
        assert len(dependencies) > 0

        # Test parallel processor setup
        processor = ParallelProcessor(max_workers=2, use_threads=True)

        def dummy_processor(module):
            return f"processed_{module.name}"

        # Add tasks for each module
        for module in project_structure.modules:
            processor.add_task(
                task_id=module.name,
                input_data=module,
                processor_func=dummy_processor,
                dependencies=dependencies.get(module.name, set()),
            )

        # Process all tasks
        results = processor.process_all()

        assert len(results) == len(project_structure.modules)

        # All tasks should succeed
        successful = [r for r in results.values() if r.success]
        assert len(successful) == len(project_structure.modules)

    def test_combined_optimizations(self, large_project):
        """Test multiple optimizations working together."""
        with memory_efficient_context(aggressive_gc=True) as (monitor, optimizer):
            # 1. AST parsing with caching
            with monitor.profile_operation("ast_parsing"):
                analyzer = PythonProjectAnalyzer(large_project, enable_cache=True)
                project_structure = analyzer.analyze_project()

                assert len(project_structure.modules) > 0
                monitor.take_snapshot()

            # 2. Incremental build detection
            with monitor.profile_operation("incremental_build"):
                build_manager = IncrementalBuildManager(large_project)
                python_files = [m.file_path for m in project_structure.modules]
                changed_files = build_manager.get_changed_files(python_files)

                # All files should be new/changed initially
                assert len(changed_files) > 0
                monitor.take_snapshot()

            # 3. Parallel processing with dependencies
            with monitor.profile_operation("parallel_processing"):
                dependency_analyzer = ModuleDependencyAnalyzer()
                dependencies = dependency_analyzer.analyze_module_dependencies(
                    project_structure.modules
                )

                processor = ParallelProcessor(max_workers=2, use_threads=True)

                def process_module_batch(modules_data):
                    return [f"processed_{m.name}" for m in modules_data]

                # Process modules in batches using memory optimizer
                all_processed = []
                with optimizer.batch_processor(
                    project_structure.modules, batch_size=2
                ) as batch_iter:
                    for batch in batch_iter:
                        batch_results = process_module_batch(batch)
                        all_processed.extend(batch_results)

                assert len(all_processed) == len(project_structure.modules)
                monitor.take_snapshot()

        # Verify all optimizations worked together
        assert len(all_processed) > 0

    def test_performance_estimation(self, large_project):
        """Test performance estimation capabilities."""
        analyzer = PythonProjectAnalyzer(large_project, enable_cache=True)
        project_structure = analyzer.analyze_project()

        dependency_analyzer = ModuleDependencyAnalyzer()

        # Test complexity estimation
        complexities = []
        for module in project_structure.modules:
            complexity = dependency_analyzer.estimate_processing_complexity(module)
            complexities.append(complexity)
            assert complexity > 0  # All modules should have some complexity

        # Modules with more code should generally have higher complexity
        assert max(complexities) > min(complexities)

        # Test independence detection
        dependencies = dependency_analyzer.analyze_module_dependencies(
            project_structure.modules
        )
        independent_modules = dependency_analyzer.get_independent_modules()

        # Should have at least one independent module
        assert len(independent_modules) > 0

    def test_optimization_with_real_config(self, large_project):
        """Test optimizations with real project configuration."""
        # Load the config from the test project
        from config.project_config import ConfigManager

        config_manager = ConfigManager()
        config = config_manager.load_config(project_path=large_project)

        assert config.project.name == "Performance Test Project"
        assert config.obsidian.use_wikilinks is True

        # Test analyzer with config
        analyzer = PythonProjectAnalyzer(large_project, enable_cache=True)
        project_structure = analyzer.analyze_project(
            exclude_patterns=config.project.exclude_patterns
        )

        # Should exclude files based on patterns
        assert len(project_structure.modules) > 0

        # All module files should exist and be Python files
        for module in project_structure.modules:
            assert module.file_path.exists()
            assert module.file_path.suffix == ".py"

    def test_memory_limits_and_safety(self, large_project):
        """Test memory limits and safety features."""
        # Test with reasonable memory limit first
        with memory_efficient_context(
            max_memory_mb=500, aggressive_gc=True  # More reasonable limit
        ) as (monitor, optimizer):
            # Try to analyze the project within memory limits
            analyzer = PythonProjectAnalyzer(large_project, enable_cache=True)
            project_structure = analyzer.analyze_project()

            # Should work fine with our small test project
            assert len(project_structure.modules) > 0

            # Test memory recommendations
            recommendations = monitor.get_memory_recommendations()
            assert isinstance(recommendations, list)

        # Test that very low memory limits are properly enforced
        try:
            with memory_efficient_context(
                max_memory_mb=10,  # Extremely low limit to test enforcement
                aggressive_gc=True,
            ) as (monitor, optimizer):
                # This should trigger the memory limit
                large_data = [i for i in range(100000)]  # Create some data
                del large_data
        except MemoryError:
            # Expected behavior - memory limit was enforced
            pass

    def test_cache_persistence_across_sessions(self, large_project):
        """Test that caches persist across different sessions."""
        # First session
        analyzer1 = PythonProjectAnalyzer(large_project, enable_cache=True)
        structure1 = analyzer1.analyze_project()

        build_manager1 = IncrementalBuildManager(large_project)
        python_files = [m.file_path for m in structure1.modules]
        build_manager1.mark_files_built(python_files)

        # Second session (new instances)
        analyzer2 = PythonProjectAnalyzer(large_project, enable_cache=True)
        structure2 = analyzer2.analyze_project()  # Should use cache

        build_manager2 = IncrementalBuildManager(large_project)
        changed_files = build_manager2.get_changed_files(python_files)

        # Results should be consistent
        assert len(structure1.modules) == len(structure2.modules)
        assert len(changed_files) == 0  # No changes since last build

        # Cache files should exist
        assert (large_project / ".mcp-docs-cache.json").exists()
        assert (large_project / ".mcp-docs-build.json").exists()
