"""
MCP tool for incremental documentation updates.

This module implements the update_docs MCP tool that provides incremental
documentation updates for changed files, with conflict resolution for manual edits.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from config.project_config import Config, ConfigManager
from docs_generator.analyzer import PythonProjectAnalyzer
from docs_generator.obsidian_converter import ObsidianConverter
from docs_generator.sphinx_integration import SphinxDocumentationGenerator
from utils.obsidian_utils import ObsidianVaultManager

logger = logging.getLogger(__name__)


class DocumentationUpdateError(Exception):
    """Exception raised during documentation updates."""

    pass


class ChangeDetector:
    """Detects changes in Python source files and existing documentation."""

    def __init__(self, config: Config):
        """Initialize change detector.

        Args:
            config: Project configuration
        """
        self.config = config
        self.project_path = Path(config.project.source_paths[0])

    def detect_changed_files(self, changed_files: list[str] | None = None) -> dict[str, Any]:
        """Detect files that need documentation updates.

        Args:
            changed_files: Optional list of specific files to check

        Returns:
            Dictionary with changed files categorized by type
        """
        changes = {
            "python_files": [],
            "config_files": [],
            "documentation_files": [],
            "metadata": {
                "detection_method": "explicit" if changed_files else "full_scan",
                "timestamp": datetime.now().isoformat(),
            },
        }

        if changed_files:
            # Process explicitly provided file list
            changes.update(self._analyze_explicit_changes(changed_files))
        else:
            # Full project scan for changes
            changes.update(self._scan_for_changes())

        return changes

    def _analyze_explicit_changes(self, changed_files: list[str]) -> dict[str, Any]:
        """Analyze explicitly provided list of changed files.

        Args:
            changed_files: List of file paths that changed

        Returns:
            Categorized changes dictionary
        """
        changes = {"python_files": [], "config_files": [], "documentation_files": []}

        for file_path in changed_files:
            path = Path(file_path)

            # Make path relative to project if it's absolute
            if path.is_absolute():
                try:
                    path = path.relative_to(self.project_path.resolve())
                except ValueError:
                    # File is outside project, skip
                    logger.warning(f"File outside project scope: {file_path}")
                    continue

            # Categorize file type
            if path.suffix == ".py":
                if path.exists() and self._should_include_python_file(path):
                    changes["python_files"].append(str(path))
            elif path.name in [".mcp-docs.yaml", ".mcp-docs.yml", "pyproject.toml"]:
                changes["config_files"].append(str(path))
            elif path.suffix in [".md", ".rst"]:
                changes["documentation_files"].append(str(path))

        return changes

    def _scan_for_changes(self) -> dict[str, Any]:
        """Perform full project scan for changes.

        This is a simplified implementation that could be enhanced with
        file modification time tracking in the future.

        Returns:
            Categorized changes dictionary
        """
        changes = {"python_files": [], "config_files": [], "documentation_files": []}

        # For now, treat all Python files as potentially changed
        # In a future enhancement, this could check modification times
        # against last documentation generation time
        for py_file in self.project_path.rglob("*.py"):
            rel_path = py_file.relative_to(self.project_path)
            if self._should_include_python_file(rel_path):
                changes["python_files"].append(str(rel_path))

        # Check for config file changes
        for config_file in [".mcp-docs.yaml", ".mcp-docs.yml", "pyproject.toml"]:
            config_path = self.project_path / config_file
            if config_path.exists():
                changes["config_files"].append(config_file)

        return changes

    def _should_include_python_file(self, path: Path) -> bool:
        """Check if Python file should be included in documentation.

        Args:
            path: Path to Python file (relative to project root)

        Returns:
            True if file should be included
        """
        path_str = str(path)

        # Check against exclusion patterns
        for pattern in self.config.project.exclude_patterns:
            if pattern in path_str or path.match(pattern):
                return False

        # Exclude test files by default (could be made configurable)
        if "test" in path_str.lower():
            return False

        return True


class IncrementalDocumentationUpdater:
    """Handles incremental documentation updates with conflict resolution."""

    def __init__(self, config: Config):
        """Initialize the incremental updater.

        Args:
            config: Project configuration
        """
        self.config = config
        self.change_detector = ChangeDetector(config)
        self.analyzer = PythonProjectAnalyzer(Path(config.project.source_paths[0]))
        self.sphinx_generator = SphinxDocumentationGenerator(config)
        self.obsidian_converter = ObsidianConverter(config)
        self.vault_manager: ObsidianVaultManager | None = None

        # Initialize vault manager if vault path is configured
        if config.obsidian.vault_path:
            try:
                self.vault_manager = ObsidianVaultManager(Path(config.obsidian.vault_path))
            except Exception as e:
                logger.warning(f"Failed to initialize vault manager: {e}")

    async def update_documentation(
        self,
        changed_files: list[str] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Update documentation for changed files.

        Args:
            changed_files: Optional list of specific files that changed
            progress_callback: Optional callback for progress updates

        Returns:
            Update results and statistics

        Raises:
            DocumentationUpdateError: If update fails
        """
        try:
            results = {
                "status": "success",
                "update_type": "incremental",
                "steps_completed": [],
                "files_updated": [],
                "files_skipped": [],
                "warnings": [],
                "conflicts_resolved": [],
                "statistics": {},
            }

            # Step 1: Detect changes
            if progress_callback:
                progress_callback("Detecting changes...")

            logger.info("Detecting file changes for incremental update")
            changes = self.change_detector.detect_changed_files(changed_files)
            results["steps_completed"].append("change_detection")
            results["statistics"]["changes_detected"] = changes

            # If no changes, return early
            if not any(
                [
                    changes["python_files"],
                    changes["config_files"],
                    changes["documentation_files"],
                ]
            ):
                results["status"] = "no_changes"
                results["message"] = "No changes detected that require documentation updates"
                return results

            # Step 2: Handle configuration changes
            if changes["config_files"]:
                if progress_callback:
                    progress_callback("Processing configuration changes...")

                config_results = await self._handle_config_changes(changes["config_files"])
                results["steps_completed"].append("config_processing")
                results["warnings"].extend(config_results.get("warnings", []))

            # Step 3: Update Python documentation
            if changes["python_files"]:
                if progress_callback:
                    progress_callback("Updating Python documentation...")

                python_results = await self._update_python_documentation(changes["python_files"])
                results["steps_completed"].append("python_documentation_update")
                results["files_updated"].extend(python_results["files_updated"])
                results["conflicts_resolved"].extend(python_results.get("conflicts_resolved", []))
                results["warnings"].extend(python_results.get("warnings", []))

            # Step 4: Update cross-references and index
            if progress_callback:
                progress_callback("Updating cross-references...")

            reference_results = await self._update_cross_references()
            results["steps_completed"].append("cross_reference_update")
            results["files_updated"].extend(reference_results.get("files_updated", []))

            # Step 5: Generate summary
            results["statistics"]["total_files_updated"] = len(results["files_updated"])
            results["update_summary"] = self._create_update_summary(results)

            logger.info(f"Incremental documentation update completed: {results['statistics']}")
            return results

        except Exception as e:
            logger.error(f"Documentation update failed: {e}")
            raise DocumentationUpdateError(f"Failed to update documentation: {e}") from e

    async def _handle_config_changes(self, config_files: list[str]) -> dict[str, Any]:
        """Handle configuration file changes.

        Args:
            config_files: List of changed configuration files

        Returns:
            Results of configuration processing
        """
        results = {"warnings": []}

        if ".mcp-docs.yaml" in config_files or ".mcp-docs.yml" in config_files:
            results["warnings"].append(
                "Configuration changed - full regeneration recommended for complete consistency"
            )

        if "pyproject.toml" in config_files:
            results["warnings"].append(
                "Project metadata changed - consider updating documentation metadata"
            )

        return results

    async def _update_python_documentation(self, python_files: list[str]) -> dict[str, Any]:
        """Update documentation for specific Python files.

        Args:
            python_files: List of Python files to update

        Returns:
            Results of Python documentation updates
        """
        results = {
            "files_updated": [],
            "conflicts_resolved": [],
            "warnings": [],
        }

        try:
            # Analyze only the changed files
            loop = asyncio.get_event_loop()

            for py_file in python_files:
                file_path = Path(self.config.project.source_paths[0]) / py_file

                if not file_path.exists():
                    results["warnings"].append(f"File not found: {py_file}")
                    continue

                # Analyze individual file
                module_info = await loop.run_in_executor(
                    None, self.analyzer._analyze_file, file_path
                )

                if module_info is None:
                    results["warnings"].append(f"Failed to analyze: {py_file}")
                    continue

                # Generate documentation for this module
                sphinx_output = await self._generate_module_docs(module_info)

                if sphinx_output:
                    # Convert to Obsidian format
                    obsidian_docs = await self._convert_module_to_obsidian(sphinx_output, py_file)

                    # Save to vault with conflict resolution
                    if self.vault_manager:
                        save_results = await self._save_module_docs(obsidian_docs, py_file)
                        results["files_updated"].extend(save_results["files_updated"])
                        results["conflicts_resolved"].extend(
                            save_results.get("conflicts_resolved", [])
                        )
                        results["warnings"].extend(save_results.get("warnings", []))

        except Exception as e:
            raise DocumentationUpdateError(f"Failed to update Python documentation: {e}") from e

        return results

    async def _generate_module_docs(self, module_info) -> dict[str, Any] | None:
        """Generate Sphinx documentation for a single module.

        Args:
            module_info: Module analysis results

        Returns:
            Sphinx output for the module
        """
        try:
            loop = asyncio.get_event_loop()
            # For now, use the full documentation generation and extract relevant parts
            # In future, could optimize with single-module generation
            from docs_generator.analyzer import ModuleInfo, ProjectStructure

            # Create a minimal project structure with just this module
            temp_structure = ProjectStructure(
                project_name=self.config.project.name,
                root_path=Path(self.config.project.source_paths[0]),
                modules=[module_info] if isinstance(module_info, ModuleInfo) else [],
                dependencies=set(),
            )

            return await loop.run_in_executor(
                None, self.sphinx_generator.generate_documentation, temp_structure
            )
        except Exception as e:
            logger.warning(f"Failed to generate Sphinx docs for module: {e}")
            return None

    async def _convert_module_to_obsidian(
        self, sphinx_output: dict[str, Any], source_file: str
    ) -> dict[str, Any]:
        """Convert module Sphinx output to Obsidian format.

        Args:
            sphinx_output: Sphinx generation results for module
            source_file: Original Python source file path

        Returns:
            Obsidian conversion results
        """
        try:
            loop = asyncio.get_event_loop()
            html_dir = Path(sphinx_output.get("output_dir", ""))
            output_dir = Path("temp_obsidian_update")

            return await loop.run_in_executor(
                None,
                self.obsidian_converter.convert_html_directory,
                html_dir,
                output_dir,
            )
        except Exception as e:
            logger.warning(f"Failed to convert module to Obsidian format: {e}")
            return {}

    async def _save_module_docs(
        self, obsidian_docs: dict[str, Any], source_file: str
    ) -> dict[str, Any]:
        """Save module documentation to vault with conflict resolution.

        Args:
            obsidian_docs: Obsidian format documentation
            source_file: Original Python source file path

        Returns:
            Results of saving operation
        """
        if not self.vault_manager:
            return {"files_updated": [], "warnings": ["Vault manager not available"]}

        results = {
            "files_updated": [],
            "conflicts_resolved": [],
            "warnings": [],
        }

        try:
            docs_folder = self.vault_manager.ensure_folder_exists(self.config.obsidian.docs_folder)

            for file_path, content in obsidian_docs.get("files", {}).items():
                target_path = docs_folder / file_path

                # Check for manual edits and handle conflicts
                conflict_resolution = await self._resolve_conflicts(target_path, content)

                if conflict_resolution["action"] == "skip":
                    results["warnings"].append(
                        f"Skipped {file_path}: {conflict_resolution['reason']}"
                    )
                    continue

                # Save with appropriate backup strategy
                created_path, backup_path = self.vault_manager.safe_write_file(
                    target_path, conflict_resolution["content"], create_backup=True
                )

                results["files_updated"].append(str(created_path))

                if backup_path:
                    results["warnings"].append(f"Created backup: {backup_path}")

                if conflict_resolution.get("conflict_resolved"):
                    results["conflicts_resolved"].append(
                        {
                            "file": str(target_path),
                            "resolution": conflict_resolution["resolution_method"],
                        }
                    )

        except Exception as e:
            logger.error(f"Failed to save module documentation: {e}")
            results["warnings"].append(f"Save error: {e}")

        return results

    async def _resolve_conflicts(self, target_path: Path, new_content: str) -> dict[str, Any]:
        """Resolve conflicts between existing documentation and new content.

        Args:
            target_path: Path to documentation file
            new_content: New generated content

        Returns:
            Conflict resolution results
        """
        if not target_path.exists():
            return {
                "action": "write",
                "content": new_content,
                "conflict_resolved": False,
            }

        try:
            existing_content = target_path.read_text(encoding="utf-8")

            # Simple conflict detection - check if file has been manually modified
            # This could be enhanced with more sophisticated diff analysis
            if self._has_manual_modifications(existing_content):
                # For now, preserve manual edits by creating backup and warning
                return {
                    "action": "write",
                    "content": new_content,
                    "conflict_resolved": True,
                    "resolution_method": "backup_and_overwrite",
                    "reason": "Manual modifications detected, preserved via backup",
                }
            else:
                # Safe to overwrite
                return {
                    "action": "write",
                    "content": new_content,
                    "conflict_resolved": False,
                }

        except Exception as e:
            logger.warning(f"Error reading existing file {target_path}: {e}")
            return {
                "action": "write",
                "content": new_content,
                "conflict_resolved": False,
            }

    def _has_manual_modifications(self, content: str) -> bool:
        """Detect if documentation has manual modifications.

        Args:
            content: File content to analyze

        Returns:
            True if manual modifications detected
        """
        # Simple heuristic - check for common manual addition markers
        manual_indicators = [
            "<!-- manual edit -->",
            "<!-- added by user -->",
            "**Note:**",
            "**Important:**",
        ]

        for indicator in manual_indicators:
            if indicator in content:
                return True

        # Could be enhanced with more sophisticated detection
        return False

    async def _update_cross_references(self) -> dict[str, Any]:
        """Update cross-references and navigation files.

        Returns:
            Results of cross-reference updates
        """
        results = {"files_updated": []}

        if not self.vault_manager or not self.config.output.generate_index:
            return results

        try:
            # Update index file with current state
            docs_folder = self.vault_manager.ensure_folder_exists(self.config.obsidian.docs_folder)

            index_path = docs_folder / "index.md"
            index_content = await self._generate_updated_index()

            created_path, _ = self.vault_manager.safe_write_file(
                index_path, index_content, create_backup=True
            )

            results["files_updated"].append(str(created_path))

        except Exception as e:
            logger.warning(f"Failed to update cross-references: {e}")

        return results

    async def _generate_updated_index(self) -> str:
        """Generate updated index content.

        Returns:
            Updated index file content
        """
        # This is a simplified version - could be enhanced with more
        # sophisticated index generation
        lines = [
            f"# {self.config.project.name} Documentation",
            "",
            f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Quick Navigation",
            "",
            "This documentation was incrementally updated.",
            "Use the file explorer to navigate to specific modules.",
            "",
        ]

        return "\n".join(lines)

    def _create_update_summary(self, results: dict[str, Any]) -> str:
        """Create a summary of the update process.

        Args:
            results: Update results dictionary

        Returns:
            Formatted update summary
        """
        summary_lines = [
            "Documentation Update Summary",
            "=" * 32,
            "",
            f"Update Type: {results['update_type'].title()}",
            f"Status: {results['status'].title()}",
            f"Files Updated: {results['statistics'].get('total_files_updated', 0)}",
            f"Conflicts Resolved: {len(results.get('conflicts_resolved', []))}",
            f"Warnings: {len(results['warnings'])}",
            "",
        ]

        changes = results["statistics"].get("changes_detected", {})
        if changes:
            summary_lines.extend(
                [
                    "Changes Processed:",
                    f"- Python files: {len(changes.get('python_files', []))}",
                    f"- Config files: {len(changes.get('config_files', []))}",
                    f"- Documentation files: {len(changes.get('documentation_files', []))}",
                    "",
                ]
            )

        if results.get("conflicts_resolved"):
            summary_lines.extend(
                [
                    "Conflicts Resolved:",
                    *[
                        f"- {conflict['file']}: {conflict['resolution']}"
                        for conflict in results["conflicts_resolved"]
                    ],
                    "",
                ]
            )

        if results["warnings"]:
            summary_lines.extend(
                [
                    "Warnings:",
                    *[f"- {warning}" for warning in results["warnings"]],
                ]
            )

        return "\n".join(summary_lines)


async def update_docs_tool(
    project_path: str,
    changed_files: list[str] | None = None,
    config_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    MCP tool implementation for incremental documentation updates.

    Args:
        project_path: Path to the Python project root
        changed_files: Optional list of files that changed
        config_override: Optional configuration overrides

    Returns:
        Documentation update results

    Raises:
        DocumentationUpdateError: If update fails
    """
    try:
        # Load configuration
        config_manager = ConfigManager()
        config_path = Path(project_path) / ".mcp-docs.yaml"
        if config_path.exists():
            config = config_manager.load_config(config_path)
        else:
            # Use default configuration
            config = Config()

        # Apply overrides if provided
        if config_override:
            for key, value in config_override.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Initialize updater
        updater = IncrementalDocumentationUpdater(config)

        # Progress tracking
        progress_messages = []

        def progress_callback(message: str):
            progress_messages.append(message)
            logger.info(f"Progress: {message}")

        # Update documentation
        results = await updater.update_documentation(changed_files, progress_callback)
        results["progress_messages"] = progress_messages

        return results

    except Exception as e:
        logger.error(f"update_docs_tool failed: {e}")
        return {"status": "error", "error": str(e), "error_type": type(e).__name__}


# Tool metadata for MCP registration
TOOL_DEFINITION = {
    "name": "update_docs",
    "description": "Incrementally update Python project documentation for changed files",
    "inputSchema": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Path to the Python project root directory",
            },
            "changed_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of specific files that changed",
                "default": None,
            },
            "config_override": {
                "type": "object",
                "description": "Optional configuration overrides",
                "additionalProperties": True,
                "default": None,
            },
        },
        "required": ["project_path"],
        "additionalProperties": False,
    },
}
