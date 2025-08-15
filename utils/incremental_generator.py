"""Incremental documentation generator.

This module provides enhanced documentation generation with incremental build
support for improved performance on large projects.
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from config.project_config import Config
from docs_generator.analyzer import PythonProjectAnalyzer
from docs_generator.obsidian_converter import ObsidianConverter
from docs_generator.sphinx_integration import SphinxDocumentationGenerator
from utils.incremental_build import IncrementalBuildManager
from utils.obsidian_utils import ObsidianVaultManager

logger = logging.getLogger(__name__)


class IncrementalDocumentationGenerationError(Exception):
    """Exception raised during incremental documentation generation."""

    pass


class IncrementalDocumentationGenerator:
    """Enhanced documentation generator with incremental build support."""

    def __init__(self, config: Config, enable_incremental: bool = True):
        """Initialize the incremental documentation generator.

        Args:
            config: Project configuration
            enable_incremental: Whether to enable incremental builds
        """
        self.config = config
        self.enable_incremental = enable_incremental

        # Initialize core components
        self.project_path = Path(config.project.source_paths[0])
        self.analyzer = PythonProjectAnalyzer(self.project_path, enable_cache=True)
        self.sphinx_generator = SphinxDocumentationGenerator(config)
        self.obsidian_converter = ObsidianConverter(config)
        self.vault_manager: ObsidianVaultManager | None = None

        # Initialize incremental build manager
        self.build_manager: IncrementalBuildManager | None = None
        if self.enable_incremental:
            self.build_manager = IncrementalBuildManager(self.project_path)

        # Initialize vault manager if configured
        if config.obsidian.vault_path:
            try:
                self.vault_manager = ObsidianVaultManager(Path(config.obsidian.vault_path))
            except Exception as e:
                logger.warning(f"Failed to initialize vault manager: {e}")

        logger.info(
            f"Initialized incremental documentation generator (incremental: {enable_incremental})"
        )

    async def generate_documentation(
        self,
        force_full: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Generate documentation with incremental build support.

        Args:
            force_full: Force a complete rebuild regardless of changes
            progress_callback: Optional callback for progress updates

        Returns:
            Generation results and statistics

        Raises:
            IncrementalDocumentationGenerationError: If generation fails
        """
        try:
            # start_time = asyncio.get_event_loop().time()  # Not used

            results = {
                "status": "success",
                "build_type": "full" if force_full else "incremental",
                "steps_completed": [],
                "files_generated": [],
                "files_skipped": [],
                "warnings": [],
                "statistics": {},
                "performance": {},
            }

            # Determine build strategy
            should_full_build = await self._should_perform_full_build(force_full)
            if should_full_build:
                results["build_type"] = "full"
                return await self._perform_full_build(progress_callback)

            # Incremental build path
            results["build_type"] = "incremental"
            return await self._perform_incremental_build(progress_callback)

        except Exception as e:
            logger.error(f"Documentation generation failed: {e}")
            raise IncrementalDocumentationGenerationError(
                f"Failed to generate documentation: {e}"
            ) from e

    async def _should_perform_full_build(self, force_full: bool) -> bool:
        """Determine if a full build should be performed.

        Args:
            force_full: User requested full build

        Returns:
            True if full build should be performed
        """
        if not self.enable_incremental or not self.build_manager:
            return True

        if force_full:
            logger.info("Full build requested by user")
            return True

        if self.build_manager.should_force_full_build():
            logger.info("Full build required due to age or missing previous build")
            return True

        return False

    async def _perform_full_build(
        self, progress_callback: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        """Perform a complete documentation build.

        Args:
            progress_callback: Progress update callback

        Returns:
            Build results
        """
        logger.info("Starting full documentation build")

        results = {
            "status": "success",
            "build_type": "full",
            "steps_completed": [],
            "files_generated": [],
            "files_skipped": [],
            "warnings": [],
            "statistics": {},
            "performance": {},
        }

        start_time = asyncio.get_event_loop().time()

        # Step 1: Analyze entire project
        if progress_callback:
            progress_callback("Analyzing complete project structure...")

        logger.info("Analyzing complete project structure")
        project_structure = await self._analyze_project()
        results["steps_completed"].append("project_analysis")
        results["statistics"]["modules_analyzed"] = len(project_structure.modules)

        # Step 2: Generate Sphinx documentation for all modules
        if progress_callback:
            progress_callback("Generating complete Sphinx documentation...")

        logger.info("Generating complete Sphinx documentation")
        sphinx_output = await self._generate_sphinx_docs(project_structure)
        results["steps_completed"].append("sphinx_generation")
        results["statistics"]["sphinx_files"] = len(sphinx_output.get("files", []))

        # Step 3: Convert all to Obsidian format
        if progress_callback:
            progress_callback("Converting all documentation to Obsidian format...")

        logger.info("Converting all documentation to Obsidian format")
        obsidian_docs = await self._convert_to_obsidian(sphinx_output)
        results["steps_completed"].append("obsidian_conversion")
        results["statistics"]["obsidian_files"] = len(obsidian_docs.get("files", {}))

        # Step 4: Save to vault
        if self.vault_manager:
            if progress_callback:
                progress_callback("Saving all documentation to Obsidian vault...")

            logger.info("Saving complete documentation to Obsidian vault")
            vault_results = await self._save_to_vault(obsidian_docs)
            results["steps_completed"].append("vault_integration")
            results["files_generated"].extend(vault_results["files_created"])
            results["warnings"].extend(vault_results.get("warnings", []))

        # Step 5: Update build state
        if self.build_manager:
            python_files = [mod.file_path for mod in project_structure.modules]
            generated_files = {str(f): results["files_generated"] for f in python_files}
            self.build_manager.mark_files_built(python_files, generated_files)
            self.build_manager.mark_full_build()

        # Performance metrics
        end_time = asyncio.get_event_loop().time()
        results["performance"] = {
            "total_time_seconds": round(end_time - start_time, 2),
            "modules_per_second": round(len(project_structure.modules) / (end_time - start_time), 2)
            if end_time > start_time
            else 0,
        }

        results["statistics"]["total_files_generated"] = len(results["files_generated"])
        results["generation_summary"] = self._create_generation_summary(results)

        logger.info(f"Full build completed in {results['performance']['total_time_seconds']}s")
        return results

    async def _perform_incremental_build(
        self, progress_callback: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        """Perform an incremental documentation build.

        Args:
            progress_callback: Progress update callback

        Returns:
            Build results
        """
        logger.info("Starting incremental documentation build")

        results = {
            "status": "success",
            "build_type": "incremental",
            "steps_completed": [],
            "files_generated": [],
            "files_skipped": [],
            "warnings": [],
            "statistics": {},
            "performance": {},
        }

        start_time = asyncio.get_event_loop().time()

        # Step 1: Discover all Python files
        if progress_callback:
            progress_callback("Discovering project files...")

        exclude_patterns = self.config.project.exclude_patterns
        all_python_files = self.analyzer._discover_python_files(exclude_patterns)

        # Step 2: Determine changed files
        if progress_callback:
            progress_callback("Detecting changed files...")

        if not self.build_manager:
            # Fallback to full build if no build manager
            return await self._perform_full_build(progress_callback)

        changed_files = self.build_manager.get_changed_files(all_python_files)
        if not changed_files:
            logger.info("No changes detected, skipping build")
            results["statistics"]["files_checked"] = len(all_python_files)
            results["statistics"]["files_changed"] = 0
            results["files_skipped"] = [str(f) for f in all_python_files]
            return results

        logger.info(f"Found {len(changed_files)} changed files")
        results["statistics"]["files_checked"] = len(all_python_files)
        results["statistics"]["files_changed"] = len(changed_files)

        # Step 3: Get dependent files that need rebuilding
        dependent_files = set()
        for changed_file in changed_files:
            if self.build_manager:
                dependent_files.update(self.build_manager.get_dependent_files(changed_file))

        files_to_rebuild = changed_files | dependent_files
        logger.info(
            f"Total files to rebuild: {len(files_to_rebuild)} "
            f"(including {len(dependent_files)} dependents)"
        )
        results["statistics"]["files_to_rebuild"] = len(files_to_rebuild)

        # Step 4: Analyze only changed files
        if progress_callback:
            progress_callback(f"Analyzing {len(files_to_rebuild)} changed files...")

        modules_to_rebuild = []
        for file_path in files_to_rebuild:
            if file_path.exists():
                try:
                    module_info = await asyncio.get_event_loop().run_in_executor(
                        None, self.analyzer._analyze_file, file_path
                    )
                    modules_to_rebuild.append(module_info)
                except Exception as e:
                    logger.warning(f"Failed to analyze {file_path}: {e}")
                    results["warnings"].append(f"Failed to analyze {file_path}: {e}")

        results["steps_completed"].append("incremental_analysis")
        results["statistics"]["modules_analyzed"] = len(modules_to_rebuild)

        if not modules_to_rebuild:
            logger.info("No valid modules to rebuild")
            return results

        # Step 5: Generate Sphinx documentation for changed modules only
        if progress_callback:
            progress_callback(f"Generating Sphinx docs for {len(modules_to_rebuild)} modules...")

        # Create a partial project structure for changed modules
        partial_structure = self._create_partial_project_structure(modules_to_rebuild)
        sphinx_output = await self._generate_sphinx_docs(partial_structure)
        results["steps_completed"].append("incremental_sphinx_generation")
        results["statistics"]["sphinx_files"] = len(sphinx_output.get("files", []))

        # Step 6: Convert to Obsidian format
        if progress_callback:
            progress_callback("Converting changed documentation to Obsidian format...")

        obsidian_docs = await self._convert_to_obsidian(sphinx_output)
        results["steps_completed"].append("incremental_obsidian_conversion")
        results["statistics"]["obsidian_files"] = len(obsidian_docs.get("files", {}))

        # Step 7: Clean up outdated outputs
        if self.build_manager:
            cleaned_files = self.build_manager.clean_orphaned_outputs()
            if cleaned_files:
                results["statistics"]["cleaned_files"] = len(cleaned_files)

        # Step 8: Save to vault (only changed files)
        if self.vault_manager:
            if progress_callback:
                progress_callback("Saving changed documentation to Obsidian vault...")

            vault_results = await self._save_to_vault(obsidian_docs, incremental=True)
            results["steps_completed"].append("incremental_vault_integration")
            results["files_generated"].extend(vault_results["files_created"])
            results["warnings"].extend(vault_results.get("warnings", []))

        # Step 9: Update build state
        if self.build_manager:
            generated_files = {str(f): results["files_generated"] for f in files_to_rebuild}
            self.build_manager.mark_files_built(list(files_to_rebuild), generated_files)

        # Performance metrics
        end_time = asyncio.get_event_loop().time()
        results["performance"] = {
            "total_time_seconds": round(end_time - start_time, 2),
            "modules_per_second": round(len(modules_to_rebuild) / (end_time - start_time), 2)
            if end_time > start_time
            else 0,
            "time_saved_vs_full": "estimated 60-80% time saving",
        }

        results["statistics"]["total_files_generated"] = len(results["files_generated"])
        results["files_skipped"] = [str(f) for f in all_python_files if f not in files_to_rebuild]
        results["generation_summary"] = self._create_generation_summary(results)

        logger.info(
            f"Incremental build completed in {results['performance']['total_time_seconds']}s"
        )
        return results

    def _create_partial_project_structure(self, modules: list[Any]) -> Any:
        """Create a partial project structure for incremental builds.

        Args:
            modules: List of module info objects

        Returns:
            ProjectStructure with only the specified modules
        """
        from docs_generator.analyzer import ProjectStructure

        structure = ProjectStructure(
            project_name=self.project_path.name,
            root_path=self.project_path,
            modules=modules,
        )

        # Build dependency information for the modules
        for module in modules:
            structure.dependencies.update(module.imports)

        return structure

    async def _analyze_project(self):
        """Analyze the complete Python project structure."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.analyzer.analyze_project, self.config.project.exclude_patterns
        )

    async def _generate_sphinx_docs(self, project_structure):
        """Generate Sphinx documentation."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.sphinx_generator.generate_documentation, project_structure
        )

    async def _convert_to_obsidian(self, sphinx_output):
        """Convert Sphinx output to Obsidian format."""
        from docs_generator.obsidian_converter import convert_sphinx_to_obsidian

        # Extract paths from sphinx_output
        sphinx_html_dir = sphinx_output.get("build_dir", Path("."))
        output_dir = Path("./obsidian_output")

        return await asyncio.get_event_loop().run_in_executor(
            None, convert_sphinx_to_obsidian, sphinx_html_dir, output_dir, self.config
        )

    async def _save_to_vault(self, obsidian_docs, incremental: bool = False):
        """Save documentation to Obsidian vault."""
        if not self.vault_manager:
            return {"files_created": [], "warnings": ["No vault manager configured"]}

        # Implement vault saving logic using existing vault manager methods
        files_created = []
        warnings = []

        try:
            docs_folder_path = self.vault_manager.ensure_folder_exists(
                self.config.obsidian.docs_folder
            )

            for file_path, content in obsidian_docs.get("files", {}).items():
                output_path = docs_folder_path / file_path
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Use vault manager's safe write method
                written_path, backup_path = self.vault_manager.safe_write_file(
                    output_path, content, create_backup=True
                )
                files_created.append(str(output_path))

            return {"files_created": files_created, "warnings": warnings}

        except Exception as e:
            warnings.append(f"Failed to save to vault: {e}")
            return {"files_created": files_created, "warnings": warnings}

    def _create_generation_summary(self, results: dict[str, Any]) -> str:
        """Create a human-readable generation summary."""
        build_type = results.get("build_type", "unknown")
        stats = results.get("statistics", {})
        perf = results.get("performance", {})

        if build_type == "incremental":
            return (
                f"Incremental build completed: {stats.get('files_changed', 0)} "
                f"changed files, {stats.get('modules_analyzed', 0)} modules rebuilt, "
                f"{stats.get('total_files_generated', 0)} files generated in "
                f"{perf.get('total_time_seconds', 0)}s"
            )
        else:
            return (
                f"Full build completed: {stats.get('modules_analyzed', 0)} "
                f"modules analyzed, {stats.get('total_files_generated', 0)} "
                f"files generated in {perf.get('total_time_seconds', 0)}s"
            )

    def get_build_status(self) -> dict[str, Any]:
        """Get current build status and statistics."""
        base_status = {
            "incremental_enabled": self.enable_incremental,
            "project_path": str(self.project_path),
            "has_vault_manager": self.vault_manager is not None,
        }

        if self.build_manager:
            base_status.update(self.build_manager.get_build_stats())

        return base_status

    def clear_build_cache(self) -> None:
        """Clear incremental build cache."""
        if self.build_manager:
            self.build_manager.clear_build_cache()

        # Also clear analyzer cache
        self.analyzer.clear_cache()

        logger.info("All build caches cleared")
