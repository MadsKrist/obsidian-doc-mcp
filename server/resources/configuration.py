"""
MCP resource for configuration file access and editing.

This module implements the configuration MCP resource that provides
access to project configuration with validation, editing, and default value management.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from config.project_config import Config, ConfigManager

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Exception raised during configuration operations."""

    pass


class ConfigurationResource:
    """Provides access to project configuration with editing capabilities."""

    def __init__(self, project_path: Path):
        """Initialize the configuration resource.

        Args:
            project_path: Path to the Python project root
        """
        self.project_path = project_path
        self.config_manager = ConfigManager()
        self.config_file_path = project_path / ".mcp-docs.yaml"

    async def get_configuration(self) -> dict[str, Any]:
        """Get the current project configuration.

        Returns:
            Configuration data with metadata

        Raises:
            ConfigurationError: If configuration access fails
        """
        try:
            config_data = {
                "config_file_path": str(self.config_file_path),
                "config_exists": self.config_file_path.exists(),
                "config_valid": False,
                "config_schema_version": "1.0",
                "last_modified": None,
                "configuration": {},
                "validation_errors": [],
                "missing_required_fields": [],
                "deprecated_fields": [],
                "recommendations": [],
                "access_timestamp": datetime.now().isoformat(),
            }

            if self.config_file_path.exists():
                # Get file metadata
                file_stat = self.config_file_path.stat()
                config_data["last_modified"] = datetime.fromtimestamp(
                    file_stat.st_mtime
                ).isoformat()

                # Load and validate configuration
                try:
                    config = self.config_manager.load_config(self.config_file_path)
                    config_data["config_valid"] = True
                    config_data["configuration"] = self._config_to_dict(config)

                    # Validate configuration completeness
                    validation_results = await self._validate_configuration(config)
                    config_data.update(validation_results)

                except Exception as e:
                    config_data["validation_errors"].append(
                        {
                            "type": "load_error",
                            "message": str(e),
                            "severity": "error",
                        }
                    )
                    logger.warning(f"Failed to load configuration: {e}")

            else:
                # Configuration file doesn't exist
                config_data["recommendations"].append(
                    "Create .mcp-docs.yaml configuration file for project-specific settings"
                )
                config_data["configuration"] = self._config_to_dict(Config())  # Default

            return config_data

        except Exception as e:
            logger.error(f"Failed to get configuration: {e}")
            raise ConfigurationError(f"Failed to access configuration: {e}") from e

    async def update_configuration(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Update project configuration with new values.

        Args:
            updates: Dictionary of configuration updates

        Returns:
            Update results and new configuration state

        Raises:
            ConfigurationError: If configuration update fails
        """
        try:
            # Create backup if file exists
            backup_path = None
            if self.config_file_path.exists():
                backup_path = self.config_file_path.with_suffix(
                    f".yaml.backup.{int(datetime.now().timestamp())}"
                )
                shutil.copy2(self.config_file_path, backup_path)

            # Load current configuration or create default
            if self.config_file_path.exists():
                current_config = self.config_manager.load_config(self.config_file_path)
            else:
                current_config = Config()

            # Apply updates
            updated_config = self._apply_updates(current_config, updates)

            # Validate updated configuration
            validation_results = await self._validate_configuration(updated_config)
            if validation_results["validation_errors"]:
                # Restore backup if validation fails
                if backup_path and backup_path.exists():
                    shutil.move(backup_path, self.config_file_path)
                raise ConfigurationError(
                    f"Configuration validation failed: {validation_results['validation_errors']}"
                )

            # Save updated configuration
            self.config_manager.save_config(updated_config, self.config_file_path)

            # Clean up backup on successful update
            if backup_path and backup_path.exists():
                backup_path.unlink()

            return {
                "success": True,
                "updated_fields": list(updates.keys()),
                "backup_created": backup_path is not None,
                "configuration": self._config_to_dict(updated_config),
                "update_timestamp": datetime.now().isoformat(),
                "validation_results": validation_results,
            }

        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            raise ConfigurationError(f"Failed to update configuration: {e}") from e

    async def reset_configuration(self, section: str | None = None) -> dict[str, Any]:
        """Reset configuration to defaults.

        Args:
            section: Optional section to reset (reset all if None)

        Returns:
            Reset results

        Raises:
            ConfigurationError: If configuration reset fails
        """
        try:
            # Create backup if file exists
            backup_path = None
            if self.config_file_path.exists():
                backup_path = self.config_file_path.with_suffix(
                    f".yaml.backup.{int(datetime.now().timestamp())}"
                )
                shutil.copy2(self.config_file_path, backup_path)

            if section is None:
                # Reset entire configuration
                default_config = Config()
                self.config_manager.save_config(default_config, self.config_file_path)

                return {
                    "success": True,
                    "reset_scope": "entire_configuration",
                    "backup_path": str(backup_path) if backup_path else None,
                    "configuration": self._config_to_dict(default_config),
                    "reset_timestamp": datetime.now().isoformat(),
                }

            else:
                # Reset specific section
                if self.config_file_path.exists():
                    current_config = self.config_manager.load_config(
                        self.config_file_path
                    )
                else:
                    current_config = Config()

                # Reset the specified section to defaults
                default_config = Config()
                if hasattr(current_config, section) and hasattr(
                    default_config, section
                ):
                    setattr(current_config, section, getattr(default_config, section))
                    self.config_manager.save_config(
                        current_config, self.config_file_path
                    )

                    return {
                        "success": True,
                        "reset_scope": f"section_{section}",
                        "backup_path": str(backup_path) if backup_path else None,
                        "configuration": self._config_to_dict(current_config),
                        "reset_timestamp": datetime.now().isoformat(),
                    }
                else:
                    raise ConfigurationError(
                        f"Unknown configuration section: {section}"
                    )

        except Exception as e:
            logger.error(f"Failed to reset configuration: {e}")
            raise ConfigurationError(f"Failed to reset configuration: {e}") from e

    async def get_schema(self) -> dict[str, Any]:
        """Get the configuration schema with field descriptions.

        Returns:
            Configuration schema information

        Raises:
            ConfigurationError: If schema access fails
        """
        try:
            schema = {
                "schema_version": "1.0",
                "sections": {
                    "project": {
                        "description": "Project-specific settings",
                        "fields": {
                            "name": {
                                "type": "string",
                                "required": True,
                                "default": "My Python Project",
                                "description": "Human-readable project name",
                            },
                            "version": {
                                "type": "string",
                                "required": False,
                                "default": "1.0.0",
                                "description": "Project version (semantic versioning)",
                            },
                            "source_paths": {
                                "type": "array",
                                "required": True,
                                "default": ["src/"],
                                "description": "List of paths to scan for Python files",
                            },
                            "exclude_patterns": {
                                "type": "array",
                                "required": False,
                                "default": ["tests/", "*.pyc", "__pycache__/"],
                                "description": "Patterns to exclude from analysis",
                            },
                            "include_private": {
                                "type": "boolean",
                                "required": False,
                                "default": False,
                                "description": "Include private methods and classes in documentation",
                            },
                        },
                    },
                    "obsidian": {
                        "description": "Obsidian vault integration settings",
                        "fields": {
                            "vault_path": {
                                "type": "string",
                                "required": False,
                                "default": None,
                                "description": "Path to Obsidian vault (optional)",
                            },
                            "docs_folder": {
                                "type": "string",
                                "required": False,
                                "default": "Documentation",
                                "description": "Folder within vault for generated docs",
                            },
                            "use_wikilinks": {
                                "type": "boolean",
                                "required": False,
                                "default": True,
                                "description": "Use [[wikilinks]] instead of [markdown](links)",
                            },
                            "tag_prefix": {
                                "type": "string",
                                "required": False,
                                "default": "code/",
                                "description": "Prefix for generated tags",
                            },
                        },
                    },
                    "sphinx": {
                        "description": "Sphinx documentation generation settings",
                        "fields": {
                            "extensions": {
                                "type": "array",
                                "required": False,
                                "default": [
                                    "sphinx.ext.autodoc",
                                    "sphinx.ext.napoleon",
                                    "sphinx.ext.viewcode",
                                ],
                                "description": "Sphinx extensions to use",
                            },
                            "theme": {
                                "type": "string",
                                "required": False,
                                "default": "sphinx_rtd_theme",
                                "description": "Sphinx theme for initial generation",
                            },
                        },
                    },
                    "output": {
                        "description": "Output formatting and generation options",
                        "fields": {
                            "generate_index": {
                                "type": "boolean",
                                "required": False,
                                "default": True,
                                "description": "Generate main index file",
                            },
                            "include_source_links": {
                                "type": "boolean",
                                "required": False,
                                "default": True,
                                "description": "Include links back to source code",
                            },
                            "group_by_module": {
                                "type": "boolean",
                                "required": False,
                                "default": True,
                                "description": "Organize docs by module structure",
                            },
                        },
                    },
                },
                "examples": {
                    "minimal": {
                        "project": {"name": "My Project", "source_paths": ["src/"]}
                    },
                    "complete": {
                        "project": {
                            "name": "Advanced Project",
                            "version": "2.1.0",
                            "source_paths": ["src/", "lib/"],
                            "exclude_patterns": ["tests/", "docs/", "*.pyc"],
                            "include_private": False,
                        },
                        "obsidian": {
                            "vault_path": "/path/to/vault",
                            "docs_folder": "Projects/MyProject",
                            "use_wikilinks": True,
                            "tag_prefix": "dev/python/",
                        },
                        "sphinx": {
                            "extensions": [
                                "sphinx.ext.autodoc",
                                "sphinx.ext.napoleon",
                                "sphinx.ext.viewcode",
                                "sphinx.ext.intersphinx",
                            ],
                            "theme": "furo",
                        },
                        "output": {
                            "generate_index": True,
                            "include_source_links": True,
                            "group_by_module": True,
                        },
                    },
                },
            }

            return schema

        except Exception as e:
            logger.error(f"Failed to get configuration schema: {e}")
            raise ConfigurationError(f"Failed to get schema: {e}") from e

    def _config_to_dict(self, config: Config) -> dict[str, Any]:
        """Convert Config object to dictionary.

        Args:
            config: Config object to convert

        Returns:
            Dictionary representation
        """
        return {
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
            },
            "sphinx": {
                "extensions": config.sphinx.extensions,
                "theme": config.sphinx.theme,
            },
            "output": {
                "generate_index": config.output.generate_index,
                "include_source_links": config.output.include_source_links,
                "group_by_module": config.output.group_by_module,
            },
        }

    def _apply_updates(self, config: Config, updates: dict[str, Any]) -> Config:
        """Apply updates to configuration object.

        Args:
            config: Current configuration
            updates: Updates to apply

        Returns:
            Updated configuration object
        """
        # Create a copy to avoid modifying the original
        updated_config = Config()

        # Copy current values
        updated_config.project = config.project
        updated_config.obsidian = config.obsidian
        updated_config.sphinx = config.sphinx
        updated_config.output = config.output

        # Apply updates section by section
        for section_name, section_updates in updates.items():
            if hasattr(updated_config, section_name):
                section_obj = getattr(updated_config, section_name)
                for field_name, field_value in section_updates.items():
                    if hasattr(section_obj, field_name):
                        setattr(section_obj, field_name, field_value)
                    else:
                        logger.warning(
                            f"Unknown field '{field_name}' in section '{section_name}'"
                        )
            else:
                logger.warning(f"Unknown configuration section: {section_name}")

        return updated_config

    async def _validate_configuration(self, config: Config) -> dict[str, Any]:
        """Validate configuration object.

        Args:
            config: Configuration to validate

        Returns:
            Validation results
        """
        validation_results = {
            "validation_errors": [],
            "missing_required_fields": [],
            "deprecated_fields": [],
            "recommendations": [],
        }

        # Validate project section
        if not config.project.name or not config.project.name.strip():
            validation_results["missing_required_fields"].append("project.name")

        if not config.project.source_paths:
            validation_results["missing_required_fields"].append("project.source_paths")

        # Check if source paths exist
        for source_path in config.project.source_paths:
            full_path = self.project_path / source_path
            if not full_path.exists():
                validation_results["validation_errors"].append(
                    {
                        "type": "path_not_found",
                        "message": f"Source path does not exist: {source_path}",
                        "severity": "warning",
                        "field": "project.source_paths",
                    }
                )

        # Validate Obsidian section
        if config.obsidian.vault_path:
            vault_path = Path(config.obsidian.vault_path)
            if not vault_path.exists():
                validation_results["validation_errors"].append(
                    {
                        "type": "vault_not_found",
                        "message": f"Obsidian vault path does not exist: {config.obsidian.vault_path}",
                        "severity": "warning",
                        "field": "obsidian.vault_path",
                    }
                )

        # Generate recommendations
        if not config.obsidian.vault_path:
            validation_results["recommendations"].append(
                "Consider configuring obsidian.vault_path for Obsidian integration"
            )

        if (
            len(config.project.source_paths) == 1
            and config.project.source_paths[0] == "src/"
        ):
            project_has_src = (self.project_path / "src").exists()
            if not project_has_src:
                validation_results["recommendations"].append(
                    "Update project.source_paths to match your project structure"
                )

        return validation_results


async def get_configuration_resource(
    project_path: str,
) -> dict[str, Any]:
    """
    MCP resource handler for configuration access.

    Args:
        project_path: Path to the Python project root

    Returns:
        Configuration resource data

    Raises:
        ConfigurationError: If resource access fails
    """
    try:
        # Initialize resource
        resource = ConfigurationResource(Path(project_path))

        # Get current configuration
        configuration = await resource.get_configuration()

        return {
            "resource_type": "configuration",
            "data": configuration,
            "capabilities": {
                "read": True,
                "write": True,
                "validate": True,
                "reset": True,
                "schema": True,
            },
        }

    except Exception as e:
        logger.error(f"get_configuration_resource failed: {e}")
        return {
            "resource_type": "configuration",
            "error": str(e),
            "error_type": type(e).__name__,
        }


# Resource metadata for MCP registration
RESOURCE_DEFINITION = {
    "name": "configuration",
    "description": "Project configuration access, editing, and validation",
    "schema": {
        "type": "object",
        "properties": {
            "config_file_path": {"type": "string"},
            "config_exists": {"type": "boolean"},
            "config_valid": {"type": "boolean"},
            "configuration": {
                "type": "object",
                "properties": {
                    "project": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "version": {"type": "string"},
                            "source_paths": {"type": "array"},
                            "exclude_patterns": {"type": "array"},
                            "include_private": {"type": "boolean"},
                        },
                    },
                    "obsidian": {
                        "type": "object",
                        "properties": {
                            "vault_path": {"type": ["string", "null"]},
                            "docs_folder": {"type": "string"},
                            "use_wikilinks": {"type": "boolean"},
                            "tag_prefix": {"type": "string"},
                        },
                    },
                    "sphinx": {
                        "type": "object",
                        "properties": {
                            "extensions": {"type": "array"},
                            "theme": {"type": "string"},
                        },
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "generate_index": {"type": "boolean"},
                            "include_source_links": {"type": "boolean"},
                            "group_by_module": {"type": "boolean"},
                        },
                    },
                },
            },
            "validation_errors": {"type": "array"},
            "recommendations": {"type": "array"},
        },
    },
}
