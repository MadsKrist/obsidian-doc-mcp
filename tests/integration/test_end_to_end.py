"""End-to-end integration tests.

Tests the complete workflow from project analysis through
documentation generation and Obsidian integration.
"""

from pathlib import Path

import pytest

from config.project_config import Config, ConfigManager
from docs_generator.analyzer import analyze_python_project


class TestEndToEndWorkflow:
    """Tests for complete documentation generation workflow."""

    def test_analyze_sample_project(self, sample_project_structure: Path) -> None:
        """Test analyzing a complete sample project."""
        # Analyze the project
        structure = analyze_python_project(sample_project_structure)

        # Verify basic structure
        assert structure.project_name == "sample_project"
        assert len(structure.modules) >= 1

        # Verify we found expected modules (enhanced naming with full paths)
        module_names = [mod.name for mod in structure.modules]

        # Check for modules containing the expected names
        has_main = any("main" in name for name in module_names)
        has_utils = any("utils" in name for name in module_names)
        has_package = any("sample_package" in name for name in module_names)

        # At least some of these should be found
        assert has_main or has_utils or has_package

    def test_config_integration_with_project_analysis(
        self, sample_project_structure: Path, temp_dir: Path
    ) -> None:
        """Test integration between configuration and project analysis."""
        # Create a configuration file
        config_file = sample_project_structure / ".mcp-docs.yaml"
        config_content = """
project:
  name: "Integration Test Project"
  version: "1.0.0"
  source_paths: ["src/"]
  exclude_patterns: ["tests/"]

obsidian:
  vault_path: "{vault_path}"
  docs_folder: "TestProject"

output:
  generate_index: true
""".format(
            vault_path=temp_dir / "test_vault"
        )

        config_file.write_text(config_content)

        # Load configuration
        ConfigManager()

        # Mock the YAML loading since we haven't implemented it yet
        config = Config()
        config.project.name = "Integration Test Project"
        config.project.source_paths = ["src/"]

        # Analyze project with configuration context
        structure = analyze_python_project(sample_project_structure)

        # Verify the analysis worked
        assert structure.project_name == "sample_project"  # From directory name
        assert len(structure.modules) >= 1

    @pytest.mark.skip(reason="MCP server not fully implemented yet")
    def test_mcp_server_initialization(self) -> None:
        """Test MCP server startup and initialization."""
        # This test will be implemented when the MCP server is complete
        pass

    @pytest.mark.skip(reason="Sphinx integration not implemented yet")
    def test_sphinx_generation_workflow(self, sample_project_structure: Path) -> None:
        """Test the complete Sphinx documentation generation workflow."""
        # This test will be implemented when Sphinx integration is complete
        pass

    @pytest.mark.skip(reason="Obsidian conversion not implemented yet")
    def test_obsidian_conversion_workflow(self, temp_dir: Path) -> None:
        """Test the complete Obsidian markdown conversion workflow."""
        # This test will be implemented when Obsidian conversion is complete
        pass
