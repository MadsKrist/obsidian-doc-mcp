"""Project configuration management.

This module handles loading, validating, and managing configuration
for Python project documentation generation.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:
    import tomllib
except ImportError:
    import tomli as tomllib

logger = logging.getLogger(__name__)


@dataclass
class ProjectConfig:
    """Project-specific configuration."""

    name: str = "Untitled Project"
    version: str = "1.0.0"
    source_paths: list[str] = field(default_factory=lambda: ["src/", "lib/"])
    exclude_patterns: list[str] = field(default_factory=lambda: ["tests/", "*.pyc"])
    include_private: bool = False


@dataclass
class ObsidianConfig:
    """Obsidian-specific configuration."""

    vault_path: str = ""
    docs_folder: str = "Projects"
    use_wikilinks: bool = True
    tag_prefix: str = "code/"
    template_folder: str = "Templates/Code"


@dataclass
class SphinxConfig:
    """Sphinx-specific configuration."""

    extensions: list[str] = field(
        default_factory=lambda: [
            "sphinx.ext.autodoc",
            "sphinx.ext.napoleon",
            "sphinx.ext.viewcode",
        ]
    )
    theme: str = "sphinx_rtd_theme"
    custom_config: str | None = None


@dataclass
class OutputConfig:
    """Output formatting configuration."""

    generate_index: bool = True
    cross_reference_external: bool = True
    include_source_links: bool = True
    group_by_module: bool = True


@dataclass
class Config:
    """Complete configuration for documentation generation."""

    project: ProjectConfig = field(default_factory=ProjectConfig)
    obsidian: ObsidianConfig = field(default_factory=ObsidianConfig)
    sphinx: SphinxConfig = field(default_factory=SphinxConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


class ConfigurationError(Exception):
    """Exception raised when configuration is invalid."""

    pass


class ConfigManager:
    """Manages loading and validation of project configuration."""

    DEFAULT_CONFIG_NAMES = [".mcp-docs.yaml", ".mcp-docs.yml", ".mcp-docs.toml"]

    def __init__(self) -> None:
        """Initialize the configuration manager."""
        self.config: Config | None = None
        logger.info("Configuration manager initialized")

    def load_config(
        self, config_path: Path | None = None, project_path: Path | None = None
    ) -> Config:
        """Load configuration from file or create default.

        Args:
            config_path: Explicit path to configuration file
            project_path: Project root path to search for config files

        Returns:
            Loaded or default configuration

        Raises:
            ConfigurationError: If configuration is invalid
        """
        logger.info("Loading configuration")

        if config_path:
            if not config_path.exists():
                raise ConfigurationError(f"Configuration file not found: {config_path}")

            self.config = self._load_config_file(config_path)
        else:
            # Search for config files in project directory
            config_file = self._find_config_file(project_path or Path.cwd())

            if config_file:
                logger.info(f"Found configuration file: {config_file}")
                self.config = self._load_config_file(config_file)
            else:
                logger.info("No configuration file found, using defaults")
                self.config = Config()

        self._validate_config(self.config)
        return self.config

    def _find_config_file(self, project_path: Path) -> Path | None:
        """Find configuration file in project directory.

        Args:
            project_path: Project root path

        Returns:
            Path to configuration file or None if not found
        """
        for config_name in self.DEFAULT_CONFIG_NAMES:
            config_path = project_path / config_name
            if config_path.exists():
                return config_path

        return None

    def _load_config_file(self, config_path: Path) -> Config:
        """Load configuration from a specific file.

        Args:
            config_path: Path to configuration file

        Returns:
            Loaded configuration

        Raises:
            ConfigurationError: If file cannot be loaded or parsed
        """
        try:
            if config_path.suffix.lower() in [".yaml", ".yml"]:
                return self._load_yaml_config(config_path)
            elif config_path.suffix.lower() == ".toml":
                return self._load_toml_config(config_path)
            else:
                raise ConfigurationError(
                    f"Unsupported configuration format: {config_path.suffix}"
                )

        except Exception as e:
            raise ConfigurationError(
                f"Failed to load configuration from {config_path}: {e}"
            ) from e

    def _load_yaml_config(self, config_path: Path) -> Config:
        """Load YAML configuration file.

        Args:
            config_path: Path to YAML file

        Returns:
            Loaded configuration

        Raises:
            ConfigurationError: If YAML cannot be parsed or is invalid
        """
        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                logger.warning(f"Empty configuration file: {config_path}")
                return Config()

            return self._create_config_from_dict(data)

        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in {config_path}: {e}") from e
        except FileNotFoundError as e:
            raise ConfigurationError(
                f"Configuration file not found: {config_path}"
            ) from e

    def _load_toml_config(self, config_path: Path) -> Config:
        """Load TOML configuration file.

        Args:
            config_path: Path to TOML file

        Returns:
            Loaded configuration

        Raises:
            ConfigurationError: If TOML cannot be parsed or is invalid
        """
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

            return self._create_config_from_dict(data)

        except tomllib.TOMLDecodeError as e:
            raise ConfigurationError(f"Invalid TOML in {config_path}: {e}") from e
        except FileNotFoundError as e:
            raise ConfigurationError(
                f"Configuration file not found: {config_path}"
            ) from e

    def _validate_config(self, config: Config) -> None:
        """Validate configuration values.

        Args:
            config: Configuration to validate

        Raises:
            ConfigurationError: If configuration is invalid
        """
        logger.debug("Validating configuration")

        # Validate project settings
        if not config.project.name:
            raise ConfigurationError("Project name cannot be empty")

        if not config.project.source_paths:
            raise ConfigurationError("At least one source path must be specified")

        # Validate Obsidian settings
        if config.obsidian.vault_path and not Path(config.obsidian.vault_path).exists():
            logger.warning(
                f"Obsidian vault path does not exist: {config.obsidian.vault_path}"
            )

        # Validate Sphinx settings
        if not config.sphinx.extensions:
            logger.warning("No Sphinx extensions specified")

        logger.info("Configuration validation complete")

    def create_default_config_file(
        self, project_path: Path, config_format: str = "yaml"
    ) -> Path:
        """Create a default configuration file.

        Args:
            project_path: Project root path
            config_format: Format for config file ("yaml" or "toml")

        Returns:
            Path to created configuration file

        Raises:
            ConfigurationError: If file creation fails
        """
        if config_format not in ["yaml", "toml"]:
            raise ConfigurationError(f"Unsupported config format: {config_format}")

        config_filename = f".mcp-docs.{config_format}"
        config_path = project_path / config_filename

        if config_path.exists():
            raise ConfigurationError(
                f"Configuration file already exists: {config_path}"
            )

        try:
            if config_format == "yaml":
                self._write_yaml_config(config_path)
            else:
                self._write_toml_config(config_path)

            logger.info(f"Created default configuration file: {config_path}")
            return config_path

        except Exception as e:
            raise ConfigurationError(f"Failed to create configuration file: {e}") from e

    def _write_yaml_config(self, config_path: Path) -> None:
        """Write default YAML configuration file."""
        default_config = """project:
  name: "My Python Project"
  version: "1.0.0"
  source_paths: ["src/", "lib/"]
  exclude_patterns: ["tests/", "*.pyc", "__pycache__/"]
  include_private: false

obsidian:
  vault_path: "/path/to/obsidian/vault"
  docs_folder: "Projects/MyProject"
  use_wikilinks: true
  tag_prefix: "code/"
  template_folder: "Templates/Code"

sphinx:
  extensions:
    - "sphinx.ext.autodoc"
    - "sphinx.ext.napoleon"
    - "sphinx.ext.viewcode"
  theme: "sphinx_rtd_theme"
  # custom_config: "docs/conf.py"

output:
  generate_index: true
  cross_reference_external: true
  include_source_links: true
  group_by_module: true
"""

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(default_config)

    def _write_toml_config(self, config_path: Path) -> None:
        """Write default TOML configuration file."""
        default_config = """[project]
name = "My Python Project"
version = "1.0.0"
source_paths = ["src/", "lib/"]
exclude_patterns = ["tests/", "*.pyc", "__pycache__/"]
include_private = false

[obsidian]
vault_path = "/path/to/obsidian/vault"
docs_folder = "Projects/MyProject"
use_wikilinks = true
tag_prefix = "code/"
template_folder = "Templates/Code"

[sphinx]
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode"
]
theme = "sphinx_rtd_theme"
# custom_config = "docs/conf.py"

[output]
generate_index = true
cross_reference_external = true
include_source_links = true
group_by_module = true
"""

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(default_config)

    def _create_config_from_dict(self, data: dict[str, Any]) -> Config:
        """Create Config object from dictionary data.

        Args:
            data: Configuration data from YAML/TOML

        Returns:
            Config object with data populated

        Raises:
            ConfigurationError: If data structure is invalid
        """
        try:
            # Extract project config
            project_data = data.get("project", {})
            project_config = ProjectConfig(
                name=self._get_env_override(
                    "MCP_DOCS_PROJECT_NAME",
                    project_data.get("name", "Untitled Project"),
                ),
                version=self._get_env_override(
                    "MCP_DOCS_PROJECT_VERSION", project_data.get("version", "1.0.0")
                ),
                source_paths=self._get_env_override_list(
                    "MCP_DOCS_SOURCE_PATHS",
                    project_data.get("source_paths", ["src/", "lib/"]),
                ),
                exclude_patterns=self._get_env_override_list(
                    "MCP_DOCS_EXCLUDE_PATTERNS",
                    project_data.get("exclude_patterns", ["tests/", "*.pyc"]),
                ),
                include_private=self._get_env_override_bool(
                    "MCP_DOCS_INCLUDE_PRIVATE",
                    project_data.get("include_private", False),
                ),
            )

            # Extract Obsidian config
            obsidian_data = data.get("obsidian", {})
            obsidian_config = ObsidianConfig(
                vault_path=self._get_env_override(
                    "MCP_DOCS_VAULT_PATH", obsidian_data.get("vault_path", "")
                ),
                docs_folder=self._get_env_override(
                    "MCP_DOCS_DOCS_FOLDER", obsidian_data.get("docs_folder", "Projects")
                ),
                use_wikilinks=self._get_env_override_bool(
                    "MCP_DOCS_USE_WIKILINKS", obsidian_data.get("use_wikilinks", True)
                ),
                tag_prefix=self._get_env_override(
                    "MCP_DOCS_TAG_PREFIX", obsidian_data.get("tag_prefix", "code/")
                ),
                template_folder=self._get_env_override(
                    "MCP_DOCS_TEMPLATE_FOLDER",
                    obsidian_data.get("template_folder", "Templates/Code"),
                ),
            )

            # Extract Sphinx config
            sphinx_data = data.get("sphinx", {})
            sphinx_config = SphinxConfig(
                extensions=self._get_env_override_list(
                    "MCP_DOCS_SPHINX_EXTENSIONS",
                    sphinx_data.get(
                        "extensions",
                        [
                            "sphinx.ext.autodoc",
                            "sphinx.ext.napoleon",
                            "sphinx.ext.viewcode",
                        ],
                    ),
                ),
                theme=self._get_env_override(
                    "MCP_DOCS_SPHINX_THEME",
                    sphinx_data.get("theme", "sphinx_rtd_theme"),
                ),
                custom_config=sphinx_data.get("custom_config"),
            )

            # Extract output config
            output_data = data.get("output", {})
            output_config = OutputConfig(
                generate_index=self._get_env_override_bool(
                    "MCP_DOCS_GENERATE_INDEX", output_data.get("generate_index", True)
                ),
                cross_reference_external=self._get_env_override_bool(
                    "MCP_DOCS_CROSS_REFERENCE_EXTERNAL",
                    output_data.get("cross_reference_external", True),
                ),
                include_source_links=self._get_env_override_bool(
                    "MCP_DOCS_INCLUDE_SOURCE_LINKS",
                    output_data.get("include_source_links", True),
                ),
                group_by_module=self._get_env_override_bool(
                    "MCP_DOCS_GROUP_BY_MODULE", output_data.get("group_by_module", True)
                ),
            )

            return Config(
                project=project_config,
                obsidian=obsidian_config,
                sphinx=sphinx_config,
                output=output_config,
            )

        except Exception as e:
            raise ConfigurationError(f"Invalid configuration structure: {e}") from e

    def _get_env_override(self, env_var: str, default_value: str) -> str:
        """Get configuration value with environment variable override.

        Args:
            env_var: Environment variable name
            default_value: Default value if env var not set

        Returns:
            Environment variable value or default
        """
        return os.environ.get(env_var, default_value)

    def _get_env_override_bool(self, env_var: str, default_value: bool) -> bool:
        """Get boolean configuration value with environment variable override.

        Args:
            env_var: Environment variable name
            default_value: Default value if env var not set

        Returns:
            Environment variable value as boolean or default
        """
        env_value = os.environ.get(env_var)
        if env_value is None:
            return default_value
        return env_value.lower() in ("true", "1", "yes", "on")

    def _get_env_override_list(
        self, env_var: str, default_value: list[str]
    ) -> list[str]:
        """Get list configuration value with environment variable override.

        Args:
            env_var: Environment variable name
            default_value: Default value if env var not set

        Returns:
            Environment variable value as list (comma-separated) or default
        """
        env_value = os.environ.get(env_var)
        if env_value is None:
            return default_value
        return [item.strip() for item in env_value.split(",") if item.strip()]
