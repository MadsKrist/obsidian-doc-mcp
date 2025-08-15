"""Parallel documentation generator.

This module provides parallel documentation generation capabilities,
processing multiple modules simultaneously for improved performance.
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from config.project_config import Config
from docs_generator.analyzer import ModuleInfo, ProjectStructure, PythonProjectAnalyzer
from docs_generator.obsidian_converter import ObsidianConverter
from docs_generator.sphinx_integration import SphinxDocumentationGenerator
from utils.memory_optimizer import MemoryMonitor, memory_efficient_context
from utils.obsidian_utils import ObsidianVaultManager
from utils.parallel_processor import ModuleDependencyAnalyzer, ParallelProcessor

logger = logging.getLogger(__name__)


class ParallelDocumentationGenerationError(Exception):
    """Exception raised during parallel documentation generation."""

    pass


class ParallelDocumentationGenerator:
    """Documentation generator with parallel processing capabilities."""

    def __init__(
        self,
        config: Config,
        max_workers: int | None = None,
        use_threads: bool = True,
        enable_memory_optimization: bool = True,
    ):
        """Initialize the parallel documentation generator.

        Args:
            config: Project configuration
            max_workers: Maximum number of worker processes/threads
            use_threads: Use threads instead of processes for parallelism
            enable_memory_optimization: Enable memory optimization features
        """
        self.config = config
        self.max_workers = max_workers
        self.use_threads = use_threads
        self.enable_memory_optimization = enable_memory_optimization

        # Initialize core components
        self.project_path = Path(config.project.source_paths[0])
        self.analyzer = PythonProjectAnalyzer(self.project_path, enable_cache=True)
        self.sphinx_generator = SphinxDocumentationGenerator(config)
        self.obsidian_converter = ObsidianConverter(config)
        self.vault_manager: ObsidianVaultManager | None = None

        # Initialize parallel processing components
        self.parallel_processor = ParallelProcessor(
            max_workers=max_workers,
            use_threads=use_threads,
            timeout_per_task=600.0,  # 10 minutes per task
        )
        self.dependency_analyzer = ModuleDependencyAnalyzer()

        # Initialize vault manager if configured
        if config.obsidian.vault_path:
            try:
                self.vault_manager = ObsidianVaultManager(
                    Path(config.obsidian.vault_path)
                )
            except Exception as e:
                logger.warning(f"Failed to initialize vault manager: {e}")

        logger.info(
            f"Parallel documentation generator initialized "
            f"(workers: {self.parallel_processor.max_workers}, "
            f"threads: {use_threads}, memory_opt: {enable_memory_optimization})"
        )

    async def generate_documentation(
        self, progress_callback: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        """Generate documentation using parallel processing.

        Args:
            progress_callback: Optional callback for progress updates

        Returns:
            Generation results and statistics
        """
        if self.enable_memory_optimization:
            with memory_efficient_context(monitor_operations=True) as (
                monitor,
                optimizer,
            ):
                with monitor.profile_operation("parallel_documentation_generation"):
                    return await self._generate_with_parallelism(
                        monitor, progress_callback
                    )
        else:
            return await self._generate_with_parallelism(None, progress_callback)

    async def _generate_with_parallelism(
        self,
        monitor: MemoryMonitor | None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Perform parallel documentation generation."""
        results = {
            "status": "success",
            "generation_mode": "parallel",
            "steps_completed": [],
            "files_generated": [],
            "warnings": [],
            "statistics": {},
            "parallel_stats": {},
            "memory_profile": {},
        }

        # Step 1: Analyze project structure
        if progress_callback:
            progress_callback("Analyzing project structure...")

        logger.info("Analyzing complete project structure")
        project_structure = await self._analyze_project()
        results["steps_completed"].append("project_analysis")
        results["statistics"]["modules_found"] = len(project_structure.modules)

        if not project_structure.modules:
            logger.warning("No modules found to process")
            return results

        # Step 2: Analyze module dependencies for optimal processing order
        if progress_callback:
            progress_callback("Analyzing module dependencies...")

        logger.info("Analyzing module dependencies for parallel processing")
        module_dependencies = self.dependency_analyzer.analyze_module_dependencies(
            project_structure.modules
        )
        results["statistics"]["dependency_relationships"] = sum(
            len(deps) for deps in module_dependencies.values()
        )

        # Step 3: Set up parallel processing tasks
        if progress_callback:
            progress_callback("Setting up parallel processing tasks...")

        self._setup_parallel_tasks(project_structure.modules, module_dependencies)
        results["steps_completed"].append("task_setup")

        # Step 4: Execute parallel processing
        if progress_callback:
            progress_callback("Executing parallel documentation generation...")

        logger.info(
            f"Starting parallel processing of {len(project_structure.modules)} modules"
        )

        def parallel_progress(message: str, progress: float):
            if progress_callback:
                progress_callback(f"Parallel processing: {message} ({progress:.0%})")

        processing_results = await asyncio.get_event_loop().run_in_executor(
            None, self.parallel_processor.process_all, parallel_progress
        )

        results["steps_completed"].append("parallel_processing")
        results["parallel_stats"] = self.parallel_processor.get_processing_statistics()

        # Step 5: Collect and organize results
        if progress_callback:
            progress_callback("Collecting and organizing results...")

        generated_files = await self._collect_parallel_results(processing_results)
        results["files_generated"].extend(generated_files)
        results["steps_completed"].append("result_collection")

        # Step 6: Generate summary and statistics
        successful_modules = len([r for r in processing_results.values() if r.success])
        results["statistics"]["modules_processed"] = len(processing_results)
        results["statistics"]["successful_modules"] = successful_modules
        results["statistics"]["failed_modules"] = (
            len(processing_results) - successful_modules
        )
        results["statistics"]["total_files_generated"] = len(results["files_generated"])

        # Memory profile if enabled
        if monitor and self.enable_memory_optimization:
            final_snapshot = monitor.get_memory_snapshot()
            results["memory_profile"] = {
                "peak_memory_mb": final_snapshot.rss_mb,
                "python_objects": final_snapshot.python_objects,
                "memory_recommendations": monitor.get_memory_recommendations(),
            }

        results["generation_summary"] = self._create_generation_summary(results)

        logger.info(f"Parallel generation completed: {results['statistics']}")
        return results

    def _setup_parallel_tasks(
        self, modules: list[ModuleInfo], dependencies: dict[str, set]
    ) -> None:
        """Set up parallel processing tasks for modules."""
        for module in modules:
            # Estimate processing complexity for prioritization
            complexity = self.dependency_analyzer.estimate_processing_complexity(module)

            # Higher complexity gets lower priority number (processed later)
            # This helps balance the workload
            priority = max(0, 100 - int(complexity * 10))

            # Task will process this module through the entire pipeline
            self.parallel_processor.add_task(
                task_id=module.name,
                input_data=module,
                processor_func=self._process_single_module,
                dependencies=dependencies.get(module.name, set()),
                priority=priority,
                estimated_duration=complexity,
            )

    def _process_single_module(self, module: ModuleInfo) -> dict[str, Any]:
        """Process a single module through the documentation pipeline.

        This function will be executed in parallel for each module.
        """
        logger.debug(f"Processing module: {module.name}")

        try:
            # Create a minimal project structure for this module
            module_structure = ProjectStructure(
                project_name=self.project_path.name,
                root_path=self.project_path,
                modules=[module],
            )

            # Add dependencies for this module
            module_structure.dependencies.update(module.imports)

            # Step 1: Generate Sphinx documentation for this module
            sphinx_output = self.sphinx_generator.generate_documentation(
                module_structure
            )

            # Step 2: Convert to Obsidian format
            obsidian_docs = self._convert_module_to_obsidian(sphinx_output)

            # Step 3: Save to vault if configured
            vault_files = []
            if self.vault_manager:
                vault_files = self._save_module_to_vault(obsidian_docs, module.name)

            return {
                "module_name": module.name,
                "sphinx_files": len(sphinx_output.get("files", [])),
                "obsidian_files": len(obsidian_docs.get("files", {})),
                "vault_files": vault_files,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"Failed to process module {module.name}: {e}")
            return {"module_name": module.name, "status": "failed", "error": str(e)}

    def _convert_module_to_obsidian(
        self, sphinx_output: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert Sphinx output to Obsidian format for a single module."""
        from docs_generator.obsidian_converter import convert_sphinx_to_obsidian

        sphinx_html_dir = sphinx_output.get("build_dir", Path("."))
        output_dir = Path(
            f"./obsidian_output_{sphinx_output.get('project_name', 'module')}"
        )

        return convert_sphinx_to_obsidian(sphinx_html_dir, output_dir, self.config)

    def _save_module_to_vault(
        self, obsidian_docs: dict[str, Any], module_name: str
    ) -> list[str]:
        """Save module documentation to Obsidian vault."""
        if not self.vault_manager:
            return []

        saved_files = []

        try:
            docs_folder_path = self.vault_manager.ensure_folder_exists(
                self.config.obsidian.docs_folder
            )

            # Create module-specific subdirectory
            module_folder = docs_folder_path / module_name.replace(".", "/")
            module_folder.mkdir(parents=True, exist_ok=True)

            for file_path, content in obsidian_docs.get("files", {}).items():
                output_path = module_folder / file_path
                output_path.parent.mkdir(parents=True, exist_ok=True)

                self.vault_manager.safe_write_file(
                    output_path, content, create_backup=True
                )
                saved_files.append(str(output_path))

        except Exception as e:
            logger.error(f"Failed to save module {module_name} to vault: {e}")

        return saved_files

    async def _collect_parallel_results(
        self, processing_results: dict[str, Any]
    ) -> list[str]:
        """Collect and organize results from parallel processing."""
        all_generated_files = []

        for _task_id, result in processing_results.items():
            if result.success and result.result:
                module_result = result.result
                if isinstance(module_result, dict) and "vault_files" in module_result:
                    all_generated_files.extend(module_result["vault_files"])

        return all_generated_files

    async def _analyze_project(self):
        """Analyze the complete Python project structure."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.analyzer.analyze_project, self.config.project.exclude_patterns
        )

    def _create_generation_summary(self, results: dict[str, Any]) -> str:
        """Create a human-readable generation summary."""
        stats = results.get("statistics", {})
        parallel_stats = results.get("parallel_stats", {})

        return (
            f"Parallel generation completed: {stats.get('successful_modules', 0)}/"
            f"{stats.get('modules_processed', 0)} modules successful, "
            f"{stats.get('total_files_generated', 0)} files generated, "
            f"success rate: {parallel_stats.get('success_rate', 0):.1%}, "
            f"total time: {parallel_stats.get('total_processing_time', 0):.1f}s"
        )

    async def estimate_parallel_performance(self) -> dict[str, Any]:
        """Estimate performance benefits of parallel processing."""
        # Analyze project to get baseline metrics
        project_structure = await self._analyze_project()

        if not project_structure.modules:
            return {"error": "No modules found to analyze"}

        # Analyze dependencies
        dependencies = self.dependency_analyzer.analyze_module_dependencies(
            project_structure.modules
        )

        # Calculate metrics
        total_modules = len(project_structure.modules)
        independent_modules = len(self.dependency_analyzer.get_independent_modules())
        dependency_chains = len([m for m, deps in dependencies.items() if deps])

        # Estimate processing time
        total_complexity = sum(
            self.dependency_analyzer.estimate_processing_complexity(module)
            for module in project_structure.modules
        )

        # Rough estimates
        sequential_time = total_complexity * 2  # 2 seconds per complexity unit
        parallel_time = (total_complexity / self.parallel_processor.max_workers) * 2
        speedup_factor = sequential_time / parallel_time if parallel_time > 0 else 1

        return {
            "total_modules": total_modules,
            "independent_modules": independent_modules,
            "modules_with_dependencies": dependency_chains,
            "dependency_ratio": dependency_chains / total_modules
            if total_modules > 0
            else 0,
            "estimated_sequential_time_seconds": sequential_time,
            "estimated_parallel_time_seconds": parallel_time,
            "estimated_speedup_factor": speedup_factor,
            "max_workers": self.parallel_processor.max_workers,
            "parallelism_potential": "high"
            if independent_modules / total_modules > 0.7
            else "moderate"
            if independent_modules / total_modules > 0.4
            else "low",
            "recommendations": self._get_performance_recommendations(
                total_modules, independent_modules, speedup_factor
            ),
        }

    def _get_performance_recommendations(
        self, total_modules: int, independent_modules: int, speedup_factor: float
    ) -> list[str]:
        """Get performance optimization recommendations."""
        recommendations = []

        if independent_modules / total_modules < 0.3:
            recommendations.append(
                "High dependency coupling detected - consider refactoring to "
                "reduce inter-module dependencies"
            )

        if speedup_factor < 2.0:
            recommendations.append(
                "Limited parallel speedup expected - consider using "
                "incremental builds instead"
            )

        if total_modules < 10:
            recommendations.append(
                "Small project - parallel processing overhead may exceed benefits"
            )

        if speedup_factor > 5.0:
            recommendations.append(
                "Excellent parallelization potential - parallel processing "
                "highly recommended"
            )

        return recommendations
