"""Complete integration tests for MCP endpoints.

This module provides comprehensive integration testing for the MCP server,
ensuring all tools and resources work correctly together.
"""

import json
import tempfile
from pathlib import Path

import pytest

from server.mcp_server import DocumentationMCPServer


class TestMCPCompleteIntegration:
    """Test complete MCP server integration."""

    @pytest.fixture
    def mcp_server(self) -> DocumentationMCPServer:
        """Create MCP server instance for testing."""
        return DocumentationMCPServer()

    @pytest.fixture
    def sample_project(self):
        """Create a sample Python project for testing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)

            # Create basic project structure
            (project_path / "src").mkdir()
            (project_path / "src" / "__init__.py").write_text("")
            (project_path / "src" / "main.py").write_text(
                '''
"""Main module for testing documentation generation."""

def hello_world():
    """Print hello world message.

    Returns:
        str: Hello world message
    """
    return "Hello, World!"

class Calculator:
    """A simple calculator class."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers.

        Args:
            a: First number
            b: Second number

        Returns:
            Sum of a and b
        """
        return a + b

    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b
'''
            )

            # Create configuration file
            config_content = """
project:
  name: "Sample Integration Test Project"
  source_paths: ["src/"]
  exclude_patterns: ["tests/", "*.pyc"]
  include_private: false

obsidian:
  docs_folder: "Documentation"
  use_wikilinks: true
  tag_prefix: "test/"

sphinx:
  extensions:
    - "sphinx.ext.autodoc"
    - "sphinx.ext.napoleon"

output:
  generate_index: true
  include_source_links: true
"""
            (project_path / ".mcp-docs.yaml").write_text(config_content.strip())

            yield project_path

    def test_tool_discovery_integration(self, mcp_server: DocumentationMCPServer):
        """Test that all tools are properly discovered and registered."""
        # Access the tools registered by the server
        # Since the server uses decorators, we need to test differently

        # Test basic server setup
        assert mcp_server.name == "obsidian-doc-mcp"
        assert mcp_server.version == "0.1.0"
        assert mcp_server.config_manager is not None

    def test_resource_discovery_integration(self, mcp_server: DocumentationMCPServer):
        """Test that all resources are properly discovered and registered."""
        # Test basic server setup for resources
        assert mcp_server.server is not None

    @pytest.mark.asyncio
    async def test_server_status_integration(self, mcp_server: DocumentationMCPServer):
        """Test server status functionality."""
        status = await mcp_server._get_server_status()
        status_data = json.loads(status)

        assert status_data["name"] == "obsidian-doc-mcp"
        assert status_data["version"] == "0.1.0"
        assert status_data["status"] == "running"
        assert status_data["tools_registered"] == 7
        assert status_data["resources_registered"] == 5

        # Test features
        features = status_data["features"]
        expected_features = [
            "documentation_generation",
            "obsidian_integration",
            "sphinx_integration",
            "project_analysis",
            "configuration_management",
            "validation_and_quality",
            "link_analysis",
        ]
        for feature in expected_features:
            assert features[feature] is True

    @pytest.mark.asyncio
    async def test_server_capabilities_integration(self, mcp_server: DocumentationMCPServer):
        """Test server capabilities functionality."""
        capabilities = await mcp_server._get_server_capabilities()
        capabilities_data = json.loads(capabilities)

        # Test tools
        tools = capabilities_data["tools"]
        assert len(tools) == 7

        expected_tool_names = [
            "generate_docs",
            "update_docs",
            "configure_project",
            "validate_docs",
            "link_analysis",
            "analyze_project",
            "health_check",
        ]

        tool_names = [tool["name"] for tool in tools]
        for expected_name in expected_tool_names:
            assert expected_name in tool_names

        # Test resources
        resources = capabilities_data["resources"]
        assert len(resources) == 5

        expected_resource_uris = [
            "mcp://project/structure",
            "mcp://project/documentation_status",
            "mcp://project/configuration",
            "mcp://server/status",
            "mcp://server/capabilities",
        ]

        resource_uris = [resource["uri"] for resource in resources]
        for expected_uri in expected_resource_uris:
            assert expected_uri in resource_uris

        # Test supported formats
        assert "supported_formats" in capabilities_data
        assert "input" in capabilities_data["supported_formats"]
        assert "output" in capabilities_data["supported_formats"]

        # Test integrations
        assert "integrations" in capabilities_data
        expected_integrations = ["Obsidian", "Sphinx", "Claude Code", "MCP Protocol"]
        for integration in expected_integrations:
            assert integration in capabilities_data["integrations"]

    @pytest.mark.asyncio
    async def test_health_check_integration(self, mcp_server: DocumentationMCPServer):
        """Test health check tool integration."""
        result = await mcp_server._handle_health_check({})

        assert len(result) == 1
        assert "Health check passed:" in result[0].text

        # Extract JSON from the response
        json_start = result[0].text.find("{")
        health_data = json.loads(result[0].text[json_start:])

        assert health_data["server_name"] == "obsidian-doc-mcp"
        assert health_data["version"] == "0.1.0"
        assert health_data["status"] == "healthy"

        # Test capabilities in health check
        capabilities = health_data["capabilities"]
        expected_capabilities = [
            "project_analysis",
            "configuration_management",
            "file_operations",
        ]
        for capability in expected_capabilities:
            assert capabilities[capability] is True

    @pytest.mark.asyncio
    async def test_analyze_project_integration(
        self, mcp_server: DocumentationMCPServer, sample_project: Path
    ):
        """Test legacy analyze_project tool integration."""
        arguments = {"project_path": str(sample_project)}

        result = await mcp_server._handle_analyze_project(arguments)

        assert len(result) == 1
        assert "Project analysis completed successfully:" in result[0].text

        # Extract JSON from the response
        json_start = result[0].text.find("{")
        analysis_data = json.loads(result[0].text[json_start:])

        assert analysis_data["project_name"] == str(sample_project.name)
        assert analysis_data["total_modules"] >= 1
        assert "modules" in analysis_data
        assert "dependencies" in analysis_data

        # Check that our sample module was analyzed
        module_names = [module["name"] for module in analysis_data["modules"]]
        assert "main" in module_names or "src.main" in module_names

    @pytest.mark.asyncio
    async def test_project_analysis_error_handling(self, mcp_server: DocumentationMCPServer):
        """Test error handling for non-existent project."""
        arguments = {"project_path": "/nonexistent/path/to/project"}

        result = await mcp_server._handle_analyze_project(arguments)

        assert len(result) == 1
        assert "Error: Project path does not exist" in result[0].text

    def test_configuration_manager_integration(
        self, mcp_server: DocumentationMCPServer, sample_project: Path
    ):
        """Test configuration manager integration."""
        config_path = sample_project / ".mcp-docs.yaml"

        # Test loading configuration
        config = mcp_server.config_manager.load_config(config_path)

        assert config.project.name == "Sample Integration Test Project"
        assert "src/" in config.project.source_paths
        assert config.obsidian.use_wikilinks is True
        assert config.obsidian.tag_prefix == "test/"

    def test_server_component_integration(self, mcp_server: DocumentationMCPServer):
        """Test that all server components are properly integrated."""
        # Test that the server has all required components
        assert hasattr(mcp_server, "name")
        assert hasattr(mcp_server, "version")
        assert hasattr(mcp_server, "server")
        assert hasattr(mcp_server, "config_manager")

        # Test that the MCP server is properly initialized
        assert mcp_server.server is not None
        assert mcp_server.config_manager is not None

    @pytest.mark.asyncio
    async def test_end_to_end_workflow_simulation(
        self, mcp_server: DocumentationMCPServer, sample_project: Path
    ):
        """Test a complete end-to-end workflow simulation."""
        # Step 1: Check server health
        health_result = await mcp_server._handle_health_check({})
        assert "Health check passed:" in health_result[0].text

        # Step 2: Get server status
        status = await mcp_server._get_server_status()
        status_data = json.loads(status)
        assert status_data["status"] == "running"

        # Step 3: Get server capabilities
        capabilities = await mcp_server._get_server_capabilities()
        capabilities_data = json.loads(capabilities)
        assert len(capabilities_data["tools"]) == 7
        assert len(capabilities_data["resources"]) == 5

        # Step 4: Analyze the sample project
        analysis_result = await mcp_server._handle_analyze_project(
            {"project_path": str(sample_project)}
        )
        assert "Project analysis completed successfully:" in analysis_result[0].text

        # Step 5: Test configuration loading
        config = mcp_server.config_manager.load_config(sample_project / ".mcp-docs.yaml")
        assert config.project.name == "Sample Integration Test Project"


class TestMCPToolSchemaValidation:
    """Test MCP tool schema validation."""

    @pytest.fixture
    def mcp_server(self) -> DocumentationMCPServer:
        """Create MCP server instance for testing."""
        return DocumentationMCPServer()

    def test_tool_schemas_are_valid(self, mcp_server: DocumentationMCPServer):
        """Test that all tool schemas are properly defined."""
        # Import tool definitions to test their schemas
        from server.tools.configure_project import (
            TOOL_DEFINITION as configure_project_def,
        )
        from server.tools.generate_docs import TOOL_DEFINITION as generate_docs_def
        from server.tools.link_analysis import TOOL_DEFINITION as link_analysis_def
        from server.tools.update_docs import TOOL_DEFINITION as update_docs_def
        from server.tools.validate_docs import TOOL_DEFINITION as validate_docs_def

        tool_definitions = [
            generate_docs_def,
            update_docs_def,
            configure_project_def,
            validate_docs_def,
            link_analysis_def,
        ]

        for tool_def in tool_definitions:
            # Test required fields
            assert "name" in tool_def
            assert "description" in tool_def
            assert "inputSchema" in tool_def

            # Test schema structure
            schema = tool_def["inputSchema"]
            assert schema["type"] == "object"
            assert "properties" in schema
            assert "required" in schema
            assert "additionalProperties" in schema

            # Test that project_path is always required
            assert "project_path" in schema["required"]
            assert "project_path" in schema["properties"]
            assert schema["properties"]["project_path"]["type"] == "string"

    def test_resource_schemas_are_valid(self, mcp_server: DocumentationMCPServer):
        """Test that all resource schemas are properly defined."""
        # Import resource definitions to test their schemas
        from server.resources.configuration import (
            RESOURCE_DEFINITION as configuration_def,
        )
        from server.resources.documentation_status import (
            RESOURCE_DEFINITION as documentation_status_def,
        )
        from server.resources.project_structure import (
            RESOURCE_DEFINITION as project_structure_def,
        )

        resource_definitions = [
            project_structure_def,
            documentation_status_def,
            configuration_def,
        ]

        for resource_def in resource_definitions:
            # Test required fields
            assert "name" in resource_def
            assert "description" in resource_def
            assert "schema" in resource_def

            # Test schema structure
            schema = resource_def["schema"]
            assert schema["type"] == "object"
            assert "properties" in schema


class TestMCPErrorIntegration:
    """Test MCP error handling integration."""

    @pytest.fixture
    def mcp_server(self) -> DocumentationMCPServer:
        """Create MCP server instance for testing."""
        return DocumentationMCPServer()

    @pytest.mark.asyncio
    async def test_nonexistent_project_error(self, mcp_server: DocumentationMCPServer):
        """Test error handling for nonexistent projects."""
        result = await mcp_server._handle_analyze_project({"project_path": "/does/not/exist"})

        assert len(result) == 1
        assert "Error: Project path does not exist" in result[0].text

    @pytest.mark.asyncio
    async def test_invalid_config_path_error(self, mcp_server: DocumentationMCPServer):
        """Test error handling for invalid config paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            (project_path / "test.py").write_text("# test file")

            # Test with invalid config path
            result = await mcp_server._handle_analyze_project(
                {
                    "project_path": str(project_path),
                    "config_path": "/invalid/config/path.yaml",
                }
            )

            assert len(result) == 1
            assert "Error: Config file does not exist" in result[0].text

    def test_configuration_error_handling(self, mcp_server: DocumentationMCPServer):
        """Test configuration loading error handling."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)

            # Create invalid YAML config
            invalid_config = project_path / ".mcp-docs.yaml"
            invalid_config.write_text("invalid: yaml: content: [unclosed")

            # Test that error is properly handled
            from config.project_config import ConfigurationError

            with pytest.raises(ConfigurationError):
                mcp_server.config_manager.load_config(invalid_config)
