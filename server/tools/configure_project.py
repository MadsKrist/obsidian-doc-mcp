"""
MCP tool for interactive project configuration setup.

This module implements the configure_project MCP tool that provides
interactive configuration setup, validation, and customization.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml

from config.project_config import Config, ConfigManager

logger = logging.getLogger(__name__)


class ProjectConfigurationError(Exception):
    """Exception raised during project configuration."""

    pass


class ProjectConfigurator:
    """Handles interactive project configuration setup and management."""

    def __init__(self, project_path: Path):
        """Initialize the project configurator.

        Args:
            project_path: Path to the project root directory
        """
        self.project_path = project_path
        self.config_manager = ConfigManager()

    async def configure_project(
        self,
        config_data: dict[str, Any] | None = None,
        template_name: str | None = None,
        interactive: bool = False,
    ) -> dict[str, Any]:
        """Configure project documentation settings.

        Args:
            config_data: Optional configuration data to apply
            template_name: Optional configuration template to use
            interactive: Whether to use interactive configuration mode

        Returns:
            Configuration results and validation information

        Raises:
            ProjectConfigurationError: If configuration fails
        """
        try:
            results = {
                "status": "success",
                "steps_completed": [],
                "config_created": False,
                "config_updated": False,
                "warnings": [],
                "suggestions": [],
                "config_path": "",
                "validation_results": {},
            }

            # Step 1: Analyze current project structure
            logger.info("Analyzing project structure for configuration")
            project_analysis = await self._analyze_project_structure()
            results["steps_completed"].append("project_analysis")
            results["project_analysis"] = project_analysis

            # Step 2: Load or create base configuration
            logger.info("Loading or creating base configuration")
            config, config_path = await self._load_or_create_config(template_name)
            results["steps_completed"].append("config_initialization")
            results["config_path"] = str(config_path)

            # Step 3: Apply user-provided configuration
            if config_data:
                logger.info("Applying user configuration data")
                config = await self._apply_config_data(config, config_data)
                results["steps_completed"].append("config_application")
                results["config_updated"] = True

            # Step 4: Auto-configure based on project structure
            logger.info("Auto-configuring based on project structure")
            config = await self._auto_configure(config, project_analysis)
            results["steps_completed"].append("auto_configuration")

            # Step 5: Interactive configuration (if requested)
            if interactive:
                logger.info("Running interactive configuration")
                config, interaction_results = await self._interactive_configure(config)
                results["steps_completed"].append("interactive_configuration")
                results["interactive_results"] = interaction_results

            # Step 6: Validate final configuration
            logger.info("Validating final configuration")
            validation_results = await self._validate_configuration(config)
            results["steps_completed"].append("configuration_validation")
            results["validation_results"] = validation_results
            results["warnings"].extend(validation_results.get("warnings", []))

            # Step 7: Save configuration
            logger.info("Saving configuration to file")
            save_results = await self._save_configuration(config, config_path)
            results["steps_completed"].append("configuration_save")
            results["config_created"] = save_results["created"]
            results["warnings"].extend(save_results.get("warnings", []))

            # Step 8: Generate suggestions
            logger.info("Generating configuration suggestions")
            suggestions = await self._generate_suggestions(
                config, project_analysis, validation_results
            )
            results["suggestions"] = suggestions

            logger.info(f"Project configuration completed successfully: {config_path}")
            return results

        except Exception as e:
            logger.error(f"Project configuration failed: {e}")
            raise ProjectConfigurationError(f"Failed to configure project: {e}") from e

    async def _analyze_project_structure(self) -> dict[str, Any]:
        """Analyze the project structure to inform configuration choices.

        Returns:
            Project structure analysis results
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._sync_analyze_project)

        except Exception as e:
            logger.warning(f"Project structure analysis failed: {e}")
            return {
                "python_files": [],
                "source_paths": [],
                "has_tests": False,
                "has_docs": False,
                "package_structure": "single",
                "warnings": [f"Analysis failed: {e}"],
            }

    def _sync_analyze_project(self) -> dict[str, Any]:
        """Synchronous project structure analysis.

        Returns:
            Analysis results dictionary
        """
        analysis = {
            "python_files": [],
            "source_paths": [],
            "has_tests": False,
            "has_docs": False,
            "package_structure": "single",
            "potential_source_dirs": [],
            "estimated_project_size": "small",
        }

        # Find Python files
        python_files = list(self.project_path.rglob("*.py"))
        analysis["python_files"] = [
            str(f.relative_to(self.project_path)) for f in python_files
        ]

        # Identify potential source directories
        common_source_dirs = ["src", "lib", "app", self.project_path.name]
        potential_dirs = []

        for dir_name in common_source_dirs:
            potential_dir = self.project_path / dir_name
            if potential_dir.exists() and potential_dir.is_dir():
                py_files_in_dir = list(potential_dir.rglob("*.py"))
                if py_files_in_dir:
                    potential_dirs.append(
                        {
                            "path": dir_name,
                            "python_files": len(py_files_in_dir),
                            "has_init": (potential_dir / "__init__.py").exists(),
                        }
                    )

        # If no obvious source dirs, use project root
        if not potential_dirs:
            root_py_files = [f for f in python_files if len(f.parts) == 1]
            if root_py_files:
                potential_dirs.append(
                    {
                        "path": ".",
                        "python_files": len(root_py_files),
                        "has_init": (self.project_path / "__init__.py").exists(),
                    }
                )

        analysis["potential_source_dirs"] = potential_dirs
        analysis["source_paths"] = [d["path"] for d in potential_dirs[:2]]  # Top 2

        # Check for tests
        test_patterns = ["test_*.py", "*_test.py", "tests/"]
        analysis["has_tests"] = any(
            self.project_path.glob(pattern) or self.project_path.rglob(pattern)
            for pattern in test_patterns
        )

        # Check for existing documentation
        doc_patterns = ["docs/", "doc/", "README.md", "*.rst"]
        analysis["has_docs"] = any(
            self.project_path.glob(pattern) for pattern in doc_patterns
        )

        # Estimate project size
        if len(python_files) > 100:
            analysis["estimated_project_size"] = "large"
        elif len(python_files) > 20:
            analysis["estimated_project_size"] = "medium"
        else:
            analysis["estimated_project_size"] = "small"

        # Determine package structure
        if len(potential_dirs) > 1:
            analysis["package_structure"] = "multi"
        elif potential_dirs and potential_dirs[0].get("has_init"):
            analysis["package_structure"] = "package"
        else:
            analysis["package_structure"] = "single"

        return analysis

    async def _load_or_create_config(
        self, template_name: str | None = None
    ) -> tuple[Config, Path]:
        """Load existing configuration or create new one.

        Args:
            template_name: Optional template to use for new configuration

        Returns:
            Tuple of (config object, config file path)
        """
        # Check for existing configuration
        for config_name in self.config_manager.DEFAULT_CONFIG_NAMES:
            config_path = self.project_path / config_name
            if config_path.exists():
                try:
                    config = self.config_manager.load_config(config_path)
                    logger.info(f"Loaded existing configuration from {config_path}")
                    return config, config_path
                except Exception as e:
                    logger.warning(f"Failed to load existing config {config_path}: {e}")

        # Create new configuration
        config_path = self.project_path / ".mcp-docs.yaml"

        if template_name:
            config = self._load_template_config(template_name)
        else:
            config = Config()  # Default configuration

        logger.info(f"Created new configuration at {config_path}")
        return config, config_path

    def _load_template_config(self, template_name: str) -> Config:
        """Load configuration from template.

        Args:
            template_name: Name of the configuration template

        Returns:
            Configuration object based on template
        """
        templates = {
            "minimal": {
                "project": {"name": "Minimal Project"},
                "obsidian": {"vault_path": "", "docs_folder": "Docs"},
                "sphinx": {"extensions": ["sphinx.ext.autodoc"]},
                "output": {"generate_index": True},
            },
            "standard": {
                "project": {"name": "Standard Project"},
                "obsidian": {"vault_path": "", "use_wikilinks": True},
                "sphinx": {
                    "extensions": [
                        "sphinx.ext.autodoc",
                        "sphinx.ext.napoleon",
                        "sphinx.ext.viewcode",
                    ]
                },
                "output": {
                    "generate_index": True,
                    "cross_reference_external": True,
                },
            },
            "comprehensive": {
                "project": {
                    "name": "Comprehensive Project",
                    "exclude_patterns": ["tests/", "*.pyc", "__pycache__/"],
                },
                "obsidian": {
                    "vault_path": "",
                    "use_wikilinks": True,
                    "tag_prefix": "code/",
                },
                "sphinx": {
                    "extensions": [
                        "sphinx.ext.autodoc",
                        "sphinx.ext.napoleon",
                        "sphinx.ext.viewcode",
                        "sphinx.ext.intersphinx",
                        "sphinx.ext.todo",
                    ],
                    "theme": "sphinx_rtd_theme",
                },
                "output": {
                    "generate_index": True,
                    "cross_reference_external": True,
                    "include_source_links": True,
                    "group_by_module": True,
                },
            },
        }

        template_data = templates.get(template_name, templates["standard"])

        # Create config from template data
        # This is a simplified implementation - could be enhanced
        # with proper deep merging and validation
        config = Config()

        if "project" in template_data:
            for key, value in template_data["project"].items():
                if hasattr(config.project, key):
                    setattr(config.project, key, value)

        if "obsidian" in template_data:
            for key, value in template_data["obsidian"].items():
                if hasattr(config.obsidian, key):
                    setattr(config.obsidian, key, value)

        if "sphinx" in template_data:
            for key, value in template_data["sphinx"].items():
                if hasattr(config.sphinx, key):
                    setattr(config.sphinx, key, value)

        if "output" in template_data:
            for key, value in template_data["output"].items():
                if hasattr(config.output, key):
                    setattr(config.output, key, value)

        return config

    async def _apply_config_data(
        self, config: Config, config_data: dict[str, Any]
    ) -> Config:
        """Apply user-provided configuration data.

        Args:
            config: Base configuration object
            config_data: Configuration data to apply

        Returns:
            Updated configuration object
        """
        try:
            # Simple deep merge implementation
            # Could be enhanced with more sophisticated merging logic

            if "project" in config_data:
                for key, value in config_data["project"].items():
                    if hasattr(config.project, key):
                        setattr(config.project, key, value)

            if "obsidian" in config_data:
                for key, value in config_data["obsidian"].items():
                    if hasattr(config.obsidian, key):
                        setattr(config.obsidian, key, value)

            if "sphinx" in config_data:
                for key, value in config_data["sphinx"].items():
                    if hasattr(config.sphinx, key):
                        setattr(config.sphinx, key, value)

            if "output" in config_data:
                for key, value in config_data["output"].items():
                    if hasattr(config.output, key):
                        setattr(config.output, key, value)

            return config

        except Exception as e:
            raise ProjectConfigurationError(
                f"Failed to apply configuration data: {e}"
            ) from e

    async def _auto_configure(
        self, config: Config, project_analysis: dict[str, Any]
    ) -> Config:
        """Auto-configure settings based on project structure analysis.

        Args:
            config: Configuration object to update
            project_analysis: Project structure analysis results

        Returns:
            Auto-configured configuration object
        """
        # Update source paths based on analysis
        if project_analysis.get("source_paths"):
            config.project.source_paths = project_analysis["source_paths"]

        # Set project name based on directory name if not set
        if config.project.name == "Untitled Project":
            config.project.name = self.project_path.name.replace("_", " ").title()

        # Adjust exclusion patterns based on project structure
        if (
            project_analysis.get("has_tests")
            and "tests/" not in config.project.exclude_patterns
        ):
            config.project.exclude_patterns.append("tests/")

        # Set documentation folder based on project name
        if not config.obsidian.docs_folder or config.obsidian.docs_folder == "Projects":
            safe_name = "".join(
                c for c in config.project.name if c.isalnum() or c in " -_"
            )
            config.obsidian.docs_folder = f"Projects/{safe_name}"

        return config

    async def _interactive_configure(
        self, config: Config
    ) -> tuple[Config, dict[str, Any]]:
        """Run interactive configuration (placeholder implementation).

        Args:
            config: Configuration object to update

        Returns:
            Tuple of (updated config, interaction results)
        """
        # This is a placeholder for interactive configuration
        # In a real implementation, this would prompt for user input
        # For MCP context, we return the config as-is with minimal interaction data

        interaction_results = {
            "mode": "automatic",
            "questions_asked": 0,
            "responses_received": 0,
            "note": "Interactive mode not fully implemented - using automatic configuration",
        }

        return config, interaction_results

    async def _validate_configuration(self, config: Config) -> dict[str, Any]:
        """Validate the final configuration.

        Args:
            config: Configuration object to validate

        Returns:
            Validation results with warnings and errors
        """
        validation = {
            "is_valid": True,
            "warnings": [],
            "errors": [],
            "suggestions": [],
        }

        # Validate source paths exist
        for source_path in config.project.source_paths:
            path = self.project_path / source_path
            if not path.exists():
                validation["warnings"].append(
                    f"Source path does not exist: {source_path}"
                )

        # Validate Obsidian vault path if provided
        if config.obsidian.vault_path:
            vault_path = Path(config.obsidian.vault_path)
            if not vault_path.exists():
                validation["warnings"].append(
                    f"Obsidian vault path does not exist: {config.obsidian.vault_path}"
                )
            elif not vault_path.is_dir():
                validation["errors"].append(
                    f"Obsidian vault path is not a directory: {config.obsidian.vault_path}"
                )

        # Validate Sphinx extensions
        for extension in config.sphinx.extensions:
            if not extension.startswith("sphinx.ext."):
                validation["suggestions"].append(
                    f"Consider using official Sphinx extension: {extension}"
                )

        # Check if any critical errors
        if validation["errors"]:
            validation["is_valid"] = False

        return validation

    async def _save_configuration(
        self, config: Config, config_path: Path
    ) -> dict[str, Any]:
        """Save configuration to file.

        Args:
            config: Configuration object to save
            config_path: Path where to save the configuration

        Returns:
            Save operation results
        """
        results = {"created": False, "warnings": []}

        try:
            # Convert config to dictionary for YAML serialization
            config_dict = {
                "project": {
                    "name": config.project.name,
                    "version": config.project.version,
                    "source_paths": config.project.source_paths,
                    "exclude_patterns": config.project.exclude_patterns,
                    "include_private": config.project.include_private,
                },
                "obsidian": {
                    "vault_path": config.obsidian.vault_path,
                    "docs_folder": config.obsidian.docs_folder,
                    "use_wikilinks": config.obsidian.use_wikilinks,
                    "tag_prefix": config.obsidian.tag_prefix,
                    "template_folder": config.obsidian.template_folder,
                },
                "sphinx": {
                    "extensions": config.sphinx.extensions,
                    "theme": config.sphinx.theme,
                },
                "output": {
                    "generate_index": config.output.generate_index,
                    "cross_reference_external": config.output.cross_reference_external,
                    "include_source_links": config.output.include_source_links,
                    "group_by_module": config.output.group_by_module,
                },
            }

            # Remove empty custom_config field
            if config.sphinx.custom_config:
                config_dict["sphinx"]["custom_config"] = config.sphinx.custom_config

            # Create backup if file exists
            if config_path.exists():
                backup_path = config_path.with_suffix(config_path.suffix + ".backup")
                config_path.rename(backup_path)
                results["warnings"].append(f"Created backup: {backup_path}")
            else:
                results["created"] = True

            # Write configuration
            with config_path.open("w", encoding="utf-8") as f:
                yaml.dump(
                    config_dict,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    indent=2,
                    width=80,
                )

            logger.info(f"Configuration saved to {config_path}")

        except Exception as e:
            raise ProjectConfigurationError(f"Failed to save configuration: {e}") from e

        return results

    async def _generate_suggestions(
        self,
        config: Config,
        project_analysis: dict[str, Any],
        validation_results: dict[str, Any],
    ) -> list[str]:
        """Generate helpful suggestions for the user.

        Args:
            config: Final configuration
            project_analysis: Project structure analysis
            validation_results: Configuration validation results

        Returns:
            List of suggestion strings
        """
        suggestions = []

        # Obsidian-specific suggestions
        if not config.obsidian.vault_path:
            suggestions.append(
                "Consider setting obsidian.vault_path to integrate with your Obsidian vault"
            )

        # Project structure suggestions
        if project_analysis.get("estimated_project_size") == "large":
            suggestions.append(
                "Large project detected - consider using exclude_patterns to focus documentation"
            )

        # Sphinx extension suggestions
        if (
            project_analysis.get("has_tests")
            and "sphinx.ext.doctest" not in config.sphinx.extensions
        ):
            suggestions.append(
                "Tests detected - consider adding 'sphinx.ext.doctest' extension"
            )

        # Documentation suggestions
        if not project_analysis.get("has_docs"):
            suggestions.append(
                "No existing documentation found - generated docs will be your primary documentation"
            )

        return suggestions


async def configure_project_tool(
    project_path: str,
    config_data: dict[str, Any] | None = None,
    template_name: str | None = None,
    interactive: bool = False,
) -> dict[str, Any]:
    """
    MCP tool implementation for interactive project configuration setup.

    Args:
        project_path: Path to the Python project root
        config_data: Optional configuration data to apply
        template_name: Optional configuration template ('minimal', 'standard', 'comprehensive')
        interactive: Whether to use interactive configuration mode

    Returns:
        Configuration results and validation information

    Raises:
        ProjectConfigurationError: If configuration fails
    """
    try:
        configurator = ProjectConfigurator(Path(project_path))

        results = await configurator.configure_project(
            config_data=config_data,
            template_name=template_name,
            interactive=interactive,
        )

        return results

    except Exception as e:
        logger.error(f"configure_project_tool failed: {e}")
        return {"status": "error", "error": str(e), "error_type": type(e).__name__}


# Tool metadata for MCP registration
TOOL_DEFINITION = {
    "name": "configure_project",
    "description": "Set up and configure Python project documentation settings interactively",
    "inputSchema": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Path to the Python project root directory",
            },
            "config_data": {
                "type": "object",
                "description": "Optional configuration data to apply",
                "additionalProperties": True,
                "default": None,
            },
            "template_name": {
                "type": "string",
                "description": "Configuration template to use",
                "enum": ["minimal", "standard", "comprehensive"],
                "default": None,
            },
            "interactive": {
                "type": "boolean",
                "description": "Enable interactive configuration mode",
                "default": False,
            },
        },
        "required": ["project_path"],
        "additionalProperties": False,
    },
}
