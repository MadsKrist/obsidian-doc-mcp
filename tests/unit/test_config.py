"""Unit tests for configuration management.

Tests the functionality of loading, validating, and managing
project configuration for documentation generation.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from config.project_config import (
    Config,
    ConfigManager,
    ConfigurationError,
    ObsidianConfig,
    OutputConfig,
    ProjectConfig,
    SphinxConfig,
)


class TestConfigDataClasses:
    """Tests for configuration data classes."""

    def test_project_config_defaults(self) -> None:
        """Test ProjectConfig default values."""
        config = ProjectConfig()

        assert config.name == "Untitled Project"
        assert config.version == "1.0.0"
        assert "src/" in config.source_paths
        assert "tests/" in config.exclude_patterns
        assert not config.include_private

    def test_obsidian_config_defaults(self) -> None:
        """Test ObsidianConfig default values."""
        config = ObsidianConfig()

        assert config.vault_path == ""
        assert config.docs_folder == "Projects"
        assert config.use_wikilinks is True
        assert config.tag_prefix == "code/"
        assert config.template_folder == "Templates/Code"

    def test_sphinx_config_defaults(self) -> None:
        """Test SphinxConfig default values."""
        config = SphinxConfig()

        assert "sphinx.ext.autodoc" in config.extensions
        assert "sphinx.ext.napoleon" in config.extensions
        assert config.theme == "sphinx_rtd_theme"
        assert config.custom_config is None

    def test_output_config_defaults(self) -> None:
        """Test OutputConfig default values."""
        config = OutputConfig()

        assert config.generate_index is True
        assert config.cross_reference_external is True
        assert config.include_source_links is True
        assert config.group_by_module is True

    def test_complete_config_defaults(self) -> None:
        """Test complete Config with all defaults."""
        config = Config()

        assert isinstance(config.project, ProjectConfig)
        assert isinstance(config.obsidian, ObsidianConfig)
        assert isinstance(config.sphinx, SphinxConfig)
        assert isinstance(config.output, OutputConfig)


class TestConfigManager:
    """Tests for ConfigManager class."""

    def test_init(self) -> None:
        """Test ConfigManager initialization."""
        manager = ConfigManager()
        assert manager.config is None

    def test_find_config_file_exists(self, temp_dir: Path) -> None:
        """Test finding existing configuration file."""
        config_file = temp_dir / ".mcp-docs.yaml"
        config_file.write_text("project:\n  name: Test")

        manager = ConfigManager()
        found_file = manager._find_config_file(temp_dir)

        assert found_file == config_file

    def test_find_config_file_not_exists(self, temp_dir: Path) -> None:
        """Test finding configuration file when none exists."""
        manager = ConfigManager()
        found_file = manager._find_config_file(temp_dir)

        assert found_file is None

    def test_find_config_file_multiple_formats(self, temp_dir: Path) -> None:
        """Test finding configuration file with multiple formats present."""
        # Create both YAML and TOML files
        yaml_file = temp_dir / ".mcp-docs.yaml"
        toml_file = temp_dir / ".mcp-docs.toml"

        yaml_file.write_text("project:\n  name: Test YAML")
        toml_file.write_text("[project]\nname = 'Test TOML'")

        manager = ConfigManager()
        found_file = manager._find_config_file(temp_dir)

        # Should prefer YAML (first in DEFAULT_CONFIG_NAMES)
        assert found_file == yaml_file

    def test_load_config_with_explicit_path(self, temp_dir: Path) -> None:
        """Test loading configuration with explicit file path."""
        config_file = temp_dir / "custom-config.yaml"
        config_file.write_text("project:\n  name: Custom Config")

        manager = ConfigManager()

        # Mock the _load_config_file method since we don't have YAML parsing yet
        with patch.object(
            manager, "_load_config_file", return_value=Config()
        ) as mock_load:
            config = manager.load_config(config_path=config_file)
            mock_load.assert_called_once_with(config_file)
            assert isinstance(config, Config)

    def test_load_config_file_not_found(self, temp_dir: Path) -> None:
        """Test loading configuration with nonexistent file."""
        nonexistent_file = temp_dir / "nonexistent.yaml"

        manager = ConfigManager()

        with pytest.raises(ConfigurationError, match="Configuration file not found"):
            manager.load_config(config_path=nonexistent_file)

    def test_load_config_auto_discover(self, temp_dir: Path) -> None:
        """Test automatic configuration file discovery."""
        config_file = temp_dir / ".mcp-docs.yaml"
        config_file.write_text("project:\n  name: Auto Discovered")

        manager = ConfigManager()

        with patch.object(
            manager, "_load_config_file", return_value=Config()
        ) as mock_load:
            config = manager.load_config(project_path=temp_dir)
            mock_load.assert_called_once_with(config_file)
            assert isinstance(config, Config)

    def test_load_config_defaults_when_no_file(self, temp_dir: Path) -> None:
        """Test loading default configuration when no file is found."""
        manager = ConfigManager()
        config = manager.load_config(project_path=temp_dir)

        assert isinstance(config, Config)
        assert config.project.name == "Untitled Project"  # Default value

    def test_validate_config_valid(self) -> None:
        """Test validation of valid configuration."""
        config = Config()
        config.project.name = "Valid Project"
        config.project.source_paths = ["src/"]

        manager = ConfigManager()
        # Should not raise any exception
        manager._validate_config(config)

    def test_validate_config_empty_name(self) -> None:
        """Test validation with empty project name."""
        config = Config()
        config.project.name = ""

        manager = ConfigManager()

        with pytest.raises(ConfigurationError, match="Project name cannot be empty"):
            manager._validate_config(config)

    def test_validate_config_no_source_paths(self) -> None:
        """Test validation with no source paths."""
        config = Config()
        config.project.source_paths = []

        manager = ConfigManager()

        with pytest.raises(
            ConfigurationError, match="At least one source path must be specified"
        ):
            manager._validate_config(config)

    def test_validate_config_invalid_vault_path(self, temp_dir: Path) -> None:
        """Test validation with invalid Obsidian vault path."""
        config = Config()
        config.obsidian.vault_path = str(temp_dir / "nonexistent")

        manager = ConfigManager()

        # Should log warning but not raise exception
        with patch("config.project_config.logger") as mock_logger:
            manager._validate_config(config)
            mock_logger.warning.assert_called()

    def test_create_default_config_file_yaml(self, temp_dir: Path) -> None:
        """Test creating default YAML configuration file."""
        manager = ConfigManager()
        config_path = manager.create_default_config_file(temp_dir, "yaml")

        assert config_path.exists()
        assert config_path.name == ".mcp-docs.yaml"

        content = config_path.read_text()
        assert "project:" in content
        assert "obsidian:" in content
        assert "sphinx:" in content

    def test_create_default_config_file_toml(self, temp_dir: Path) -> None:
        """Test creating default TOML configuration file."""
        manager = ConfigManager()
        config_path = manager.create_default_config_file(temp_dir, "toml")

        assert config_path.exists()
        assert config_path.name == ".mcp-docs.toml"

        content = config_path.read_text()
        assert "[project]" in content
        assert "[obsidian]" in content
        assert "[sphinx]" in content

    def test_create_default_config_file_exists(self, temp_dir: Path) -> None:
        """Test creating default configuration file when one already exists."""
        existing_file = temp_dir / ".mcp-docs.yaml"
        existing_file.write_text("existing content")

        manager = ConfigManager()

        with pytest.raises(
            ConfigurationError, match="Configuration file already exists"
        ):
            manager.create_default_config_file(temp_dir, "yaml")

    def test_create_default_config_invalid_format(self, temp_dir: Path) -> None:
        """Test creating default configuration file with invalid format."""
        manager = ConfigManager()

        with pytest.raises(ConfigurationError, match="Unsupported config format"):
            manager.create_default_config_file(temp_dir, "json")

    def test_load_config_unsupported_format(self, temp_dir: Path) -> None:
        """Test loading configuration file with unsupported format."""
        config_file = temp_dir / ".mcp-docs.json"
        config_file.write_text('{"project": {"name": "JSON Config"}}')

        manager = ConfigManager()

        with pytest.raises(
            ConfigurationError, match="Unsupported configuration format"
        ):
            manager.load_config(config_path=config_file)
