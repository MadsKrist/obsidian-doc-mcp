"""Integration tests for MCP server functionality."""

import json
from pathlib import Path

import pytest

from server.mcp_server import DocumentationMCPServer


class TestMCPServerIntegration:
    """Test MCP server integration functionality."""

    @pytest.fixture
    def mcp_server(self) -> DocumentationMCPServer:
        """Create MCP server instance for testing."""
        return DocumentationMCPServer()

    def test_server_initialization(self, mcp_server: DocumentationMCPServer) -> None:
        """Test server initializes correctly."""
        assert mcp_server.name == "obsidian-doc-mcp"
        assert mcp_server.version == "0.1.0"
        assert mcp_server.server is not None
        assert mcp_server.config_manager is not None

    @pytest.mark.asyncio
    async def test_health_check_tool(self, mcp_server: DocumentationMCPServer) -> None:
        """Test health check tool functionality."""
        result = await mcp_server._handle_health_check({})

        assert len(result) == 1
        assert result[0].type == "text"

        # Parse the JSON response
        response_text = result[0].text
        assert "Health check passed:" in response_text

        # Extract JSON part
        json_start = response_text.find("{")
        json_data = json.loads(response_text[json_start:])

        assert json_data["server_name"] == "obsidian-doc-mcp"
        assert json_data["version"] == "0.1.0"
        assert json_data["status"] == "healthy"
        assert "capabilities" in json_data

    @pytest.mark.asyncio
    async def test_analyze_project_tool_nonexistent_path(
        self, mcp_server: DocumentationMCPServer
    ) -> None:
        """Test analyze_project tool with non-existent path."""
        arguments = {"project_path": "/nonexistent/path"}

        result = await mcp_server._handle_analyze_project(arguments)

        assert len(result) == 1
        assert result[0].type == "text"
        assert "Error: Project path does not exist" in result[0].text

    @pytest.mark.asyncio
    async def test_analyze_project_tool_with_sample_project(
        self, mcp_server: DocumentationMCPServer, sample_project_structure: Path
    ) -> None:
        """Test analyze_project tool with actual project."""
        arguments = {"project_path": str(sample_project_structure)}

        result = await mcp_server._handle_analyze_project(arguments)

        assert len(result) == 1
        assert result[0].type == "text"
        assert "Project analysis completed successfully" in result[0].text

        # Parse the JSON response
        response_text = result[0].text
        json_start = response_text.find("{")
        json_data = json.loads(response_text[json_start:])

        assert "project_name" in json_data
        assert "total_modules" in json_data
        assert "modules" in json_data
        assert "dependencies" in json_data
        assert json_data["total_modules"] >= 1

    @pytest.mark.asyncio
    async def test_analyze_project_with_config_file(
        self,
        mcp_server: DocumentationMCPServer,
        sample_project_structure: Path,
        temp_dir: Path,
    ) -> None:
        """Test analyze_project tool with configuration file."""
        # Create a test config file
        config_content = """
project:
  name: "Test Project"
  exclude_patterns: ["test_*.py"]

obsidian:
  vault_path: "/test/vault"
  docs_folder: "TestDocs"
"""
        config_file = temp_dir / "test_config.yaml"
        config_file.write_text(config_content)

        arguments = {
            "project_path": str(sample_project_structure),
            "config_path": str(config_file),
        }

        result = await mcp_server._handle_analyze_project(arguments)

        assert len(result) == 1
        assert result[0].type == "text"
        assert "Project analysis completed successfully" in result[0].text

    @pytest.mark.asyncio
    async def test_analyze_project_with_nonexistent_config(
        self, mcp_server: DocumentationMCPServer, sample_project_structure: Path
    ) -> None:
        """Test analyze_project tool with non-existent config file."""
        arguments = {
            "project_path": str(sample_project_structure),
            "config_path": "/nonexistent/config.yaml",
        }

        result = await mcp_server._handle_analyze_project(arguments)

        assert len(result) == 1
        assert result[0].type == "text"
        assert "Error: Config file does not exist" in result[0].text

    @pytest.mark.asyncio
    async def test_analyze_project_with_auto_config_discovery(
        self, mcp_server: DocumentationMCPServer, sample_project_structure: Path
    ) -> None:
        """Test analyze_project tool with automatic config file discovery."""
        # Create config file in project directory
        config_content = """
project:
  name: "Auto Config Project"
  exclude_patterns: ["__pycache__/"]
"""
        config_file = sample_project_structure / ".mcp-docs.yaml"
        config_file.write_text(config_content)

        arguments = {"project_path": str(sample_project_structure)}

        result = await mcp_server._handle_analyze_project(arguments)

        assert len(result) == 1
        assert result[0].type == "text"
        assert "Project analysis completed successfully" in result[0].text

    @pytest.mark.asyncio
    async def test_server_status_methods(self, mcp_server: DocumentationMCPServer) -> None:
        """Test server status and capabilities methods."""
        status = await mcp_server._get_server_status()
        capabilities = await mcp_server._get_server_capabilities()

        # Test status
        status_data = json.loads(status)
        assert status_data["name"] == "obsidian-doc-mcp"
        assert status_data["version"] == "0.1.0"
        assert status_data["status"] == "running"

        # Test capabilities
        capabilities_data = json.loads(capabilities)
        assert "tools" in capabilities_data
        assert "resources" in capabilities_data
        assert len(capabilities_data["tools"]) == 7  # 5 new tools + 2 legacy
        assert len(capabilities_data["resources"]) == 5  # 3 new resources + 2 legacy


class TestMCPServerErrorHandling:
    """Test MCP server error handling."""

    @pytest.fixture
    def mcp_server(self) -> DocumentationMCPServer:
        """Create MCP server instance for testing."""
        return DocumentationMCPServer()

    @pytest.mark.asyncio
    async def test_analyze_project_with_malformed_project(
        self, mcp_server: DocumentationMCPServer, temp_dir: Path, caplog
    ) -> None:
        """Test analyze_project with a project containing syntax errors."""
        # Create a project with syntax error
        bad_file = temp_dir / "bad_syntax.py"
        bad_file.write_text("def incomplete_function(\n    # Missing closing parenthesis")

        arguments = {"project_path": str(temp_dir)}

        result = await mcp_server._handle_analyze_project(arguments)

        assert len(result) == 1
        assert result[0].type == "text"
        # Should handle the error gracefully and still complete analysis
        assert "Project analysis completed successfully" in result[0].text
        # But should log a warning about the syntax error
        assert "Failed to analyze" in caplog.text and "Syntax error" in caplog.text

    @pytest.mark.asyncio
    async def test_analyze_project_with_invalid_arguments(
        self, mcp_server: DocumentationMCPServer
    ) -> None:
        """Test analyze_project with missing required arguments."""
        # Missing project_path argument
        arguments = {}

        try:
            result = await mcp_server._handle_analyze_project(arguments)
            # Should handle KeyError gracefully
            assert len(result) == 1
            assert result[0].type == "text"
            assert "Error analyzing project" in result[0].text
        except KeyError:
            # This is also acceptable - depends on implementation choice
            pass
