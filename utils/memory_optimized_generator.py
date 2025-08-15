"""Memory-optimized documentation generator.

This module provides documentation generation with aggressive memory optimization
for large projects and resource-constrained environments.
"""

import asyncio
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Optional

from config.project_config import Config
from docs_generator.analyzer import ModuleInfo, PythonProjectAnalyzer
from docs_generator.obsidian_converter import ObsidianConverter
from docs_generator.sphinx_integration import SphinxDocumentationGenerator
from utils.memory_optimizer import (
    MemoryMonitor,
    MemoryOptimizer,
    memory_efficient_context,
)
from utils.obsidian_utils import ObsidianVaultManager

logger = logging.getLogger(__name__)


class MemoryOptimizedDocumentationGenerator:
    """Documentation generator optimized for minimal memory usage."""

    def __init__(
        self,
        config: Config,
        max_memory_mb: Optional[float] = None,
        batch_size: int = 10,
        aggressive_gc: bool = True,
    ):
        """Initialize the memory-optimized documentation generator.

        Args:
            config: Project configuration
            max_memory_mb: Maximum memory limit in MB (None for no limit)
            batch_size: Number of modules to process in each batch
            aggressive_gc: Enable aggressive garbage collection
        """
        self.config = config
        self.max_memory_mb = max_memory_mb
        self.batch_size = batch_size
        self.aggressive_gc = aggressive_gc

        # Initialize core components with memory optimization
        self.project_path = Path(config.project.source_paths[0])
        self.analyzer = PythonProjectAnalyzer(self.project_path, enable_cache=True)
        self.sphinx_generator = SphinxDocumentationGenerator(config)
        self.obsidian_converter = ObsidianConverter(config)
        self.vault_manager: ObsidianVaultManager | None = None

        # Initialize vault manager if configured
        if config.obsidian.vault_path:
            try:
                self.vault_manager = ObsidianVaultManager(
                    Path(config.obsidian.vault_path)
                )
            except Exception as e:
                logger.warning(f"Failed to initialize vault manager: {e}")

        logger.info(
            f"Memory-optimized generator initialized "
            f"(max_memory: {max_memory_mb}MB, batch_size: {batch_size})"
        )

    async def generate_documentation(
        self, progress_callback: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        """Generate documentation with memory optimization.

        Args:
            progress_callback: Optional callback for progress updates

        Returns:
            Generation results and statistics
        """
        with memory_efficient_context(
            max_memory_mb=self.max_memory_mb,
            aggressive_gc=self.aggressive_gc,
            monitor_operations=True,
        ) as (monitor, optimizer):
            with monitor.profile_operation("memory_optimized_documentation_generation"):
                return await self._generate_with_optimization(
                    monitor, optimizer, progress_callback
                )

    async def _generate_with_optimization(
        self,
        monitor: MemoryMonitor,
        optimizer: MemoryOptimizer,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Perform memory-optimized documentation generation."""
        results = {
            "status": "success",
            "generation_mode": "memory_optimized",
            "steps_completed": [],
            "files_generated": [],
            "warnings": [],
            "statistics": {},
            "memory_profile": {},
        }

        # Step 1: Discover files with memory-efficient scanning
        if progress_callback:
            progress_callback("Discovering Python files...")

        with monitor.profile_operation("file_discovery"):
            python_files = await self._discover_files_efficiently()
            results["statistics"]["total_files"] = len(python_files)
            monitor.take_snapshot()

        # Step 2: Process files in memory-efficient batches
        if progress_callback:
            progress_callback(
                f"Processing {len(python_files)} files in batches of {self.batch_size}..."
            )

        all_modules = []
        with optimizer.batch_processor(python_files, self.batch_size) as batches:
            for batch_idx, batch_files in enumerate(batches):
                batch_name = f"file_analysis_batch_{batch_idx + 1}"

                with monitor.profile_operation(batch_name):
                    if progress_callback:
                        progress_callback(
                            f"Analyzing batch {batch_idx + 1} ({len(batch_files)} files)..."
                        )

                    batch_modules = await self._analyze_files_batch(
                        batch_files, optimizer
                    )
                    all_modules.extend(batch_modules)

                    # Take snapshot after each batch
                    monitor.take_snapshot()

                    # Force cleanup between batches
                    optimizer.clear_caches()

        results["steps_completed"].append("batch_analysis")
        results["statistics"]["modules_analyzed"] = len(all_modules)

        # Step 3: Generate documentation in streaming fashion
        if progress_callback:
            progress_callback("Generating documentation in memory-efficient mode...")

        with monitor.profile_operation("streaming_documentation_generation"):
            generated_files = await self._generate_documentation_streaming(
                all_modules, optimizer, progress_callback
            )
            results["files_generated"].extend(generated_files)
            monitor.take_snapshot()

        results["steps_completed"].append("streaming_generation")

        # Step 4: Memory profile summary
        final_snapshot = monitor.get_memory_snapshot()
        results["memory_profile"] = {
            "peak_memory_mb": final_snapshot.rss_mb,
            "python_objects": final_snapshot.python_objects,
            "memory_recommendations": monitor.get_memory_recommendations(),
        }

        results["statistics"]["total_files_generated"] = len(results["files_generated"])
        results["generation_summary"] = self._create_generation_summary(results)

        logger.info(f"Memory-optimized generation completed: {results['statistics']}")
        return results

    async def _discover_files_efficiently(self) -> list[Path]:
        """Discover Python files with minimal memory footprint."""
        exclude_patterns = self.config.project.exclude_patterns

        # Use generator to minimize memory usage during discovery
        def file_generator() -> Iterator[Path]:
            for file_path in self.project_path.rglob("*.py"):
                # Quick exclusion check to avoid loading everything into memory
                relative_path = file_path.relative_to(self.project_path)

                # Simple exclusion check
                excluded = False
                for pattern in exclude_patterns:
                    if pattern in str(relative_path):
                        excluded = True
                        break

                if not excluded:
                    yield file_path

        # Convert generator to list in one go to minimize allocations
        return list(file_generator())

    async def _analyze_files_batch(
        self, file_paths: list[Path], optimizer: MemoryOptimizer
    ) -> list[ModuleInfo]:
        """Analyze a batch of files with memory optimization."""
        modules = []

        for file_path in file_paths:
            try:
                # Use memory-efficient file reading
                file_content = ""
                for chunk in optimizer.memory_efficient_file_reader(file_path):
                    file_content += chunk

                # Analyze file (this already uses caching from PythonProjectAnalyzer)
                module_info = await asyncio.get_event_loop().run_in_executor(
                    None, self.analyzer._analyze_file, file_path
                )
                modules.append(module_info)

                # Clear file content from memory immediately
                del file_content

            except Exception as e:
                logger.warning(f"Failed to analyze {file_path}: {e}")
                continue

        return modules

    async def _generate_documentation_streaming(
        self,
        modules: list[ModuleInfo],
        optimizer: MemoryOptimizer,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[str]:
        """Generate documentation using streaming/batch processing."""
        generated_files = []

        # Process modules in batches to control memory usage
        with optimizer.batch_processor(modules, self.batch_size) as batches:
            for batch_idx, module_batch in enumerate(batches):
                if progress_callback:
                    progress_callback(f"Generating docs for batch {batch_idx + 1}...")

                # Create partial project structure for this batch
                batch_structure = self._create_batch_structure(module_batch)

                try:
                    # Generate Sphinx docs for this batch
                    sphinx_output = await asyncio.get_event_loop().run_in_executor(
                        None,
                        self.sphinx_generator.generate_documentation,
                        batch_structure,
                    )

                    # Convert to Obsidian format
                    obsidian_docs = await self._convert_batch_to_obsidian(sphinx_output)

                    # Save to vault immediately to free memory
                    if self.vault_manager:
                        batch_files = await self._save_batch_to_vault(obsidian_docs)
                        generated_files.extend(batch_files)

                    # Clear batch data from memory
                    del sphinx_output, obsidian_docs

                except Exception as e:
                    logger.error(
                        f"Failed to generate docs for batch {batch_idx + 1}: {e}"
                    )
                    continue

        return generated_files

    def _create_batch_structure(self, modules: list[ModuleInfo]) -> Any:
        """Create a partial project structure for a batch of modules."""
        from docs_generator.analyzer import ProjectStructure

        structure = ProjectStructure(
            project_name=self.project_path.name,
            root_path=self.project_path,
            modules=modules,
        )

        # Build minimal dependency information
        for module in modules:
            structure.dependencies.update(module.imports)

        return structure

    async def _convert_batch_to_obsidian(
        self, sphinx_output: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert a batch of Sphinx output to Obsidian format."""
        from docs_generator.obsidian_converter import convert_sphinx_to_obsidian

        # Extract paths and convert
        sphinx_html_dir = sphinx_output.get("build_dir", Path("."))
        output_dir = Path("./obsidian_output_batch")

        return await asyncio.get_event_loop().run_in_executor(
            None, convert_sphinx_to_obsidian, sphinx_html_dir, output_dir, self.config
        )

    async def _save_batch_to_vault(self, obsidian_docs: dict[str, Any]) -> list[str]:
        """Save a batch of documentation to the Obsidian vault."""
        if not self.vault_manager:
            return []

        saved_files = []

        try:
            docs_folder_path = self.vault_manager.ensure_folder_exists(
                self.config.obsidian.docs_folder
            )

            for file_path, content in obsidian_docs.get("files", {}).items():
                output_path = docs_folder_path / file_path
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Use vault manager's safe write method
                self.vault_manager.safe_write_file(
                    output_path, content, create_backup=True
                )
                saved_files.append(str(output_path))

        except Exception as e:
            logger.error(f"Failed to save batch to vault: {e}")

        return saved_files

    def _create_generation_summary(self, results: dict[str, Any]) -> str:
        """Create a human-readable generation summary."""
        stats = results.get("statistics", {})
        memory = results.get("memory_profile", {})

        return (
            f"Memory-optimized generation completed: {stats.get('modules_analyzed', 0)} modules, "
            f"{stats.get('total_files_generated', 0)} files generated, "
            f"peak memory: {memory.get('peak_memory_mb', 0):.1f}MB"
        )

    async def estimate_memory_requirements(self) -> dict[str, Any]:
        """Estimate memory requirements for the project."""
        with memory_efficient_context(monitor_operations=True) as (monitor, optimizer):
            # Sample a few files to estimate memory usage
            python_files = await self._discover_files_efficiently()
            sample_size = min(5, len(python_files))
            sample_files = python_files[:sample_size]

            with monitor.profile_operation("memory_estimation"):
                sample_modules = await self._analyze_files_batch(
                    sample_files, optimizer
                )

            # Estimate based on sample
            if monitor.current_profile and sample_size > 0:
                avg_memory_per_file = (
                    monitor.current_profile.memory_delta_mb / sample_size
                )
            else:
                avg_memory_per_file = 0
            estimated_total_memory = avg_memory_per_file * len(python_files)

            return {
                "total_files": len(python_files),
                "sample_files": sample_size,
                "avg_memory_per_file_mb": avg_memory_per_file,
                "estimated_total_memory_mb": estimated_total_memory,
                "recommended_batch_size": max(
                    1, int(100 / max(avg_memory_per_file, 0.1))
                ),
                "memory_recommendations": monitor.get_memory_recommendations(),
            }
