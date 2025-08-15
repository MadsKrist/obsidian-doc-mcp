"""
MCP tool for generating complete project documentation.

This module implements the generate_docs MCP tool that provides full
project documentation generation functionality.
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from config.project_config import Config, ConfigManager
from docs_generator.analyzer import PythonProjectAnalyzer
from docs_generator.obsidian_converter import ObsidianConverter
from docs_generator.sphinx_integration import SphinxDocumentationGenerator
from utils.obsidian_utils import ObsidianVaultManager

logger = logging.getLogger(__name__)


class DocumentationGenerationError(Exception):
    """Exception raised during documentation generation."""

    pass


class DocumentationGenerator:
    """Main documentation generator orchestrating the full pipeline."""

    def __init__(self, config: Config):
        """Initialize the documentation generator.

        Args:
            config: Project configuration
        """
        self.config = config
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

    async def generate_documentation(
        self, progress_callback: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        """Generate complete project documentation.

        Args:
            progress_callback: Optional callback for progress updates

        Returns:
            Generation results and statistics

        Raises:
            DocumentationGenerationError: If generation fails
        """
        try:
            results = {
                "status": "success",
                "steps_completed": [],
                "files_generated": [],
                "warnings": [],
                "statistics": {},
            }

            # Step 1: Analyze Python project
            if progress_callback:
                progress_callback("Analyzing Python project structure...")

            logger.info("Starting Python project analysis")
            project_structure = await self._analyze_project()
            results["steps_completed"].append("project_analysis")
            results["statistics"]["modules_found"] = len(project_structure.modules)
            results["statistics"]["classes_found"] = sum(
                len(mod.classes) for mod in project_structure.modules
            )
            results["statistics"]["functions_found"] = sum(
                len(mod.functions) for mod in project_structure.modules
            )

            # Step 2: Generate Sphinx documentation
            if progress_callback:
                progress_callback("Generating Sphinx documentation...")

            logger.info("Generating Sphinx documentation")
            sphinx_output = await self._generate_sphinx_docs(project_structure)
            results["steps_completed"].append("sphinx_generation")
            results["statistics"]["sphinx_files"] = len(sphinx_output.get("files", []))

            # Step 3: Convert to Obsidian format
            if progress_callback:
                progress_callback("Converting to Obsidian format...")

            logger.info("Converting to Obsidian format")
            obsidian_docs = await self._convert_to_obsidian(sphinx_output)
            results["steps_completed"].append("obsidian_conversion")
            results["statistics"]["obsidian_files"] = len(obsidian_docs.get("files", {}))

            # Step 4: Save to vault (if configured)
            if self.vault_manager:
                if progress_callback:
                    progress_callback("Saving documentation to Obsidian vault...")

                logger.info("Saving to Obsidian vault")
                vault_results = await self._save_to_vault(obsidian_docs)
                results["steps_completed"].append("vault_integration")
                results["files_generated"].extend(vault_results["files_created"])
                results["warnings"].extend(vault_results.get("warnings", []))
            else:
                results["warnings"].append(
                    "Obsidian vault not configured - documentation not saved to vault"
                )

            # Step 5: Generate summary
            if progress_callback:
                progress_callback("Finalizing documentation generation...")

            results["statistics"]["total_files_generated"] = len(results["files_generated"])
            results["generation_summary"] = self._create_generation_summary(results)

            logger.info(f"Documentation generation completed successfully: {results['statistics']}")
            return results

        except Exception as e:
            logger.error(f"Documentation generation failed: {e}")
            raise DocumentationGenerationError(f"Failed to generate documentation: {e}") from e

    async def _analyze_project(self):
        """Analyze the Python project structure."""
        try:
            # Run analysis in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.analyzer.analyze_project,
                self.config.project.exclude_patterns,
            )
        except Exception as e:
            raise DocumentationGenerationError(f"Project analysis failed: {e}") from e

    async def _generate_sphinx_docs(self, project_structure):
        """Generate Sphinx documentation."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self.sphinx_generator.generate_documentation, project_structure
            )
        except Exception as e:
            raise DocumentationGenerationError(f"Sphinx generation failed: {e}") from e

    async def _convert_to_obsidian(self, sphinx_output):
        """Convert Sphinx output to Obsidian format."""
        try:
            loop = asyncio.get_event_loop()
            html_dir = Path(sphinx_output.get("output_dir", ""))
            output_dir = Path("temp_obsidian_output")
            return await loop.run_in_executor(
                None,
                self.obsidian_converter.convert_html_directory,
                html_dir,
                output_dir,
            )
        except Exception as e:
            raise DocumentationGenerationError(f"Obsidian conversion failed: {e}") from e

    async def _save_to_vault(self, obsidian_docs) -> dict[str, Any]:
        """Save documentation to Obsidian vault."""
        if not self.vault_manager:
            raise DocumentationGenerationError("Vault manager not initialized")

        try:
            results = {"files_created": [], "warnings": []}

            # Ensure documentation folder exists
            docs_folder = self.vault_manager.ensure_folder_exists(self.config.obsidian.docs_folder)

            # Save each documentation file
            for file_path, content in obsidian_docs.get("files", {}).items():
                target_path = docs_folder / file_path

                # Create backup if file exists
                created_path, backup_path = self.vault_manager.safe_write_file(
                    target_path, content, create_backup=True
                )

                results["files_created"].append(str(created_path))
                if backup_path:
                    results["warnings"].append(f"Created backup: {backup_path}")

            # Generate and save index file
            if self.config.output.generate_index:
                index_content = self._create_index_content(obsidian_docs)
                index_path = docs_folder / "index.md"

                file_path, backup_path = self.vault_manager.safe_write_file(
                    index_path, index_content, create_backup=True
                )

                results["files_created"].append(str(file_path))
                if backup_path:
                    results["warnings"].append(f"Created backup: {backup_path}")

            return results

        except Exception as e:
            raise DocumentationGenerationError(f"Failed to save to vault: {e}") from e

    def _create_index_content(self, obsidian_docs) -> str:
        """Create content for the main index file."""
        content_lines = [
            f"# {self.config.project.name} Documentation",
            "",
            f"Generated on {obsidian_docs.get('metadata', {}).get('generated_at', 'unknown')}",
            "",
            "## Project Overview",
            "",
            f"- **Version**: {self.config.project.version}",
            f"- **Source Paths**: {', '.join(self.config.project.source_paths)}",
            "",
            "## Documentation Files",
            "",
        ]

        # List all documentation files
        files = list(obsidian_docs.get("files", {}).keys())

        if files:
            content_lines.extend(["### Documentation Files", ""])
            for file_path in sorted(files):
                from pathlib import Path

                name = Path(file_path).stem.replace("_", " ").title()
                content_lines.append(f"- [[{file_path}|{name}]]")
            content_lines.append("")

        return "\n".join(content_lines)

    def _create_generation_summary(self, results: dict[str, Any]) -> str:
        """Create a summary of the generation process."""
        summary_lines = [
            "Documentation Generation Summary",
            "=" * 35,
            "",
            f"Status: {results['status'].title()}",
            f"Steps Completed: {len(results['steps_completed'])}/4",
            f"Files Generated: {results['statistics'].get('total_files_generated', 0)}",
            f"Warnings: {len(results['warnings'])}",
            "",
            "Project Statistics:",
            f"- Modules: {results['statistics'].get('modules_found', 0)}",
            f"- Classes: {results['statistics'].get('classes_found', 0)}",
            f"- Functions: {results['statistics'].get('functions_found', 0)}",
        ]

        if results["warnings"]:
            summary_lines.extend(
                ["", "Warnings:", *[f"- {warning}" for warning in results["warnings"]]]
            )

        return "\n".join(summary_lines)


async def generate_docs_tool(
    project_path: str, config_override: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    MCP tool implementation for generating complete project documentation.

    Args:
        project_path: Path to the Python project root
        config_override: Optional configuration overrides

    Returns:
        Documentation generation results

    Raises:
        DocumentationGenerationError: If generation fails
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
            # Simple override application - could be enhanced with deep merging
            for key, value in config_override.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Initialize generator
        generator = DocumentationGenerator(config)

        # Progress tracking
        progress_messages = []

        def progress_callback(message: str):
            progress_messages.append(message)
            logger.info(f"Progress: {message}")

        # Generate documentation
        results = await generator.generate_documentation(progress_callback)
        results["progress_messages"] = progress_messages

        return results

    except Exception as e:
        logger.error(f"generate_docs_tool failed: {e}")
        return {"status": "error", "error": str(e), "error_type": type(e).__name__}


# Tool metadata for MCP registration
TOOL_DEFINITION = {
    "name": "generate_docs",
    "description": "Generate complete Python project documentation in Obsidian format",
    "inputSchema": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Path to the Python project root directory",
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
