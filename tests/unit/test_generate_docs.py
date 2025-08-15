"""Tests for generate_docs tool."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from server.tools.generate_docs import (
    DocumentationGenerationError,
    DocumentationGenerator,
    generate_docs_tool,
)


class TestDocumentationGenerator:
    """Test cases for DocumentationGenerator."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration."""
        config = Mock()
        # Configure nested attributes
        config.project = Mock()
        config.project.source_paths = ["src/"]
        config.project.exclude_patterns = ["tests/", "*.pyc"]
        config.project.name = "Test Project"
        config.project.version = "1.0.0"

        config.obsidian = Mock()
        config.obsidian.vault_path = ""
        config.obsidian.docs_folder = "Projects/Test"

        config.output = Mock()
        config.output.generate_index = True

        return config

    @pytest.fixture
    def mock_vault_config(self, tmp_path):
        """Create a mock configuration with vault path."""
        config = Mock()
        # Configure nested attributes
        config.project = Mock()
        config.project.source_paths = ["src/"]
        config.project.exclude_patterns = ["tests/", "*.pyc"]
        config.project.name = "Test Project"
        config.project.version = "1.0.0"

        config.obsidian = Mock()
        config.obsidian.vault_path = str(tmp_path)
        config.obsidian.docs_folder = "Projects/Test"

        config.output = Mock()
        config.output.generate_index = True

        return config

    def test_init_without_vault(self, mock_config):
        """Test initializing generator without vault."""
        with (
            patch("server.tools.generate_docs.PythonProjectAnalyzer"),
            patch("server.tools.generate_docs.SphinxDocumentationGenerator"),
            patch("server.tools.generate_docs.ObsidianConverter"),
        ):
            generator = DocumentationGenerator(mock_config)
            assert generator.config == mock_config
            assert generator.vault_manager is None

    def test_init_with_vault(self, mock_vault_config, tmp_path):
        """Test initializing generator with vault."""
        # Create .obsidian directory
        obsidian_dir = tmp_path / ".obsidian"
        obsidian_dir.mkdir()

        with (
            patch("server.tools.generate_docs.PythonProjectAnalyzer"),
            patch("server.tools.generate_docs.SphinxDocumentationGenerator"),
            patch("server.tools.generate_docs.ObsidianConverter"),
        ):
            generator = DocumentationGenerator(mock_vault_config)
            assert generator.config == mock_vault_config
            assert generator.vault_manager is not None

    def test_init_with_invalid_vault(self, mock_config):
        """Test initializing generator with invalid vault path."""
        mock_config.obsidian.vault_path = "/invalid/path"

        with (
            patch("server.tools.generate_docs.PythonProjectAnalyzer"),
            patch("server.tools.generate_docs.SphinxDocumentationGenerator"),
            patch("server.tools.generate_docs.ObsidianConverter"),
        ):
            generator = DocumentationGenerator(mock_config)
            assert generator.vault_manager is None

    @pytest.mark.asyncio
    async def test_generate_documentation_success(self, mock_config):
        """Test successful documentation generation."""
        mock_project_structure = Mock()
        mock_project_structure.modules = [Mock()]
        mock_project_structure.modules[0].classes = [Mock()]
        mock_project_structure.modules[0].functions = [Mock()]

        mock_sphinx_output = {
            "files": ["doc1.html", "doc2.html"],
            "output_dir": "/tmp/sphinx_out",
        }

        mock_obsidian_docs = {
            "files": {"doc1.md": "content1", "doc2.md": "content2"},
            "metadata": {"generated_at": "2024-01-01"},
        }

        with (
            patch("server.tools.generate_docs.PythonProjectAnalyzer") as mock_analyzer_class,
            patch("server.tools.generate_docs.SphinxDocumentationGenerator") as mock_sphinx_class,
            patch("server.tools.generate_docs.ObsidianConverter") as mock_obsidian_class,
        ):
            mock_analyzer = Mock()
            mock_analyzer.analyze_project.return_value = mock_project_structure
            mock_analyzer_class.return_value = mock_analyzer

            mock_sphinx = Mock()
            mock_sphinx.generate_documentation.return_value = mock_sphinx_output
            mock_sphinx_class.return_value = mock_sphinx

            mock_obsidian = Mock()
            mock_obsidian.convert_html_directory.return_value = mock_obsidian_docs
            mock_obsidian_class.return_value = mock_obsidian

            generator = DocumentationGenerator(mock_config)

            # Mock progress callback
            progress_messages = []

            def progress_callback(message):
                progress_messages.append(message)

            results = await generator.generate_documentation(progress_callback)

            # Verify results structure
            assert results["status"] == "success"
            assert "project_analysis" in results["steps_completed"]
            assert "sphinx_generation" in results["steps_completed"]
            assert "obsidian_conversion" in results["steps_completed"]
            assert results["statistics"]["modules_found"] == 1
            assert results["statistics"]["classes_found"] == 1
            assert results["statistics"]["functions_found"] == 1
            assert results["statistics"]["sphinx_files"] == 2
            assert results["statistics"]["obsidian_files"] == 2
            assert len(progress_messages) > 0

    @pytest.mark.asyncio
    async def test_generate_documentation_with_vault(self, mock_vault_config, tmp_path):
        """Test documentation generation with vault integration."""
        # Create .obsidian directory
        obsidian_dir = tmp_path / ".obsidian"
        obsidian_dir.mkdir()

        mock_project_structure = Mock()
        mock_project_structure.modules = [Mock()]
        mock_project_structure.modules[0].classes = []
        mock_project_structure.modules[0].functions = []

        mock_sphinx_output = {"files": ["doc1.html"], "output_dir": "/tmp/sphinx_out"}

        mock_obsidian_docs = {
            "files": {"doc1.md": "content1"},
            "metadata": {"generated_at": "2024-01-01"},
        }

        with (
            patch("server.tools.generate_docs.PythonProjectAnalyzer") as mock_analyzer_class,
            patch("server.tools.generate_docs.SphinxDocumentationGenerator") as mock_sphinx_class,
            patch("server.tools.generate_docs.ObsidianConverter") as mock_obsidian_class,
        ):
            mock_analyzer = Mock()
            mock_analyzer.analyze_project.return_value = mock_project_structure
            mock_analyzer_class.return_value = mock_analyzer

            mock_sphinx = Mock()
            mock_sphinx.generate_documentation.return_value = mock_sphinx_output
            mock_sphinx_class.return_value = mock_sphinx

            mock_obsidian = Mock()
            mock_obsidian.convert_html_directory.return_value = mock_obsidian_docs
            mock_obsidian_class.return_value = mock_obsidian

            generator = DocumentationGenerator(mock_vault_config)

            results = await generator.generate_documentation()

            # Verify vault integration
            assert results["status"] == "success"
            assert "vault_integration" in results["steps_completed"]
            assert len(results["files_generated"]) > 0

    @pytest.mark.asyncio
    async def test_generate_documentation_analysis_failure(self, mock_config):
        """Test documentation generation with analysis failure."""
        with patch("server.tools.generate_docs.PythonProjectAnalyzer") as mock_analyzer_class:
            mock_analyzer = Mock()
            mock_analyzer.analyze_project.side_effect = Exception("Analysis failed")
            mock_analyzer_class.return_value = mock_analyzer

            generator = DocumentationGenerator(mock_config)

            with pytest.raises(DocumentationGenerationError, match="Project analysis failed"):
                await generator.generate_documentation()

    @pytest.mark.asyncio
    async def test_generate_documentation_sphinx_failure(self, mock_config):
        """Test documentation generation with Sphinx failure."""
        mock_project_structure = Mock()
        mock_project_structure.modules = []

        with (
            patch("server.tools.generate_docs.PythonProjectAnalyzer") as mock_analyzer_class,
            patch("server.tools.generate_docs.SphinxDocumentationGenerator") as mock_sphinx_class,
        ):
            mock_analyzer = Mock()
            mock_analyzer.analyze_project.return_value = mock_project_structure
            mock_analyzer_class.return_value = mock_analyzer

            mock_sphinx = Mock()
            mock_sphinx.generate_documentation.side_effect = Exception("Sphinx failed")
            mock_sphinx_class.return_value = mock_sphinx

            generator = DocumentationGenerator(mock_config)

            with pytest.raises(DocumentationGenerationError, match="Sphinx generation failed"):
                await generator.generate_documentation()

    @pytest.mark.asyncio
    async def test_generate_documentation_obsidian_failure(self, mock_config):
        """Test documentation generation with Obsidian conversion failure."""
        mock_project_structure = Mock()
        mock_project_structure.modules = []

        mock_sphinx_output = {"files": [], "output_dir": "/tmp/sphinx_out"}

        with (
            patch("server.tools.generate_docs.PythonProjectAnalyzer") as mock_analyzer_class,
            patch("server.tools.generate_docs.SphinxDocumentationGenerator") as mock_sphinx_class,
            patch("server.tools.generate_docs.ObsidianConverter") as mock_obsidian_class,
        ):
            mock_analyzer = Mock()
            mock_analyzer.analyze_project.return_value = mock_project_structure
            mock_analyzer_class.return_value = mock_analyzer

            mock_sphinx = Mock()
            mock_sphinx.generate_documentation.return_value = mock_sphinx_output
            mock_sphinx_class.return_value = mock_sphinx

            mock_obsidian = Mock()
            mock_obsidian.convert_html_directory.side_effect = Exception("Obsidian failed")
            mock_obsidian_class.return_value = mock_obsidian

            generator = DocumentationGenerator(mock_config)

            with pytest.raises(DocumentationGenerationError, match="Obsidian conversion failed"):
                await generator.generate_documentation()

    def test_create_index_content(self, mock_config):
        """Test creating index file content."""
        with (
            patch("server.tools.generate_docs.PythonProjectAnalyzer"),
            patch("server.tools.generate_docs.SphinxDocumentationGenerator"),
            patch("server.tools.generate_docs.ObsidianConverter"),
        ):
            generator = DocumentationGenerator(mock_config)

            mock_obsidian_docs = {
                "files": {"module1.md": "content1", "class1.md": "content2"},
                "metadata": {"generated_at": "2024-01-01T12:00:00"},
            }

            content = generator._create_index_content(mock_obsidian_docs)

            assert "Test Project Documentation" in content
            assert "Generated on 2024-01-01T12:00:00" in content
            assert "Version**: 1.0.0" in content
            assert "[[module1.md|Module1]]" in content
            assert "[[class1.md|Class1]]" in content

    def test_create_generation_summary(self, mock_config):
        """Test creating generation summary."""
        with (
            patch("server.tools.generate_docs.PythonProjectAnalyzer"),
            patch("server.tools.generate_docs.SphinxDocumentationGenerator"),
            patch("server.tools.generate_docs.ObsidianConverter"),
        ):
            generator = DocumentationGenerator(mock_config)

            results = {
                "status": "success",
                "steps_completed": ["analysis", "sphinx", "obsidian"],
                "warnings": ["Warning 1", "Warning 2"],
                "statistics": {
                    "total_files_generated": 5,
                    "modules_found": 3,
                    "classes_found": 7,
                    "functions_found": 15,
                },
            }

            summary = generator._create_generation_summary(results)

            assert "Documentation Generation Summary" in summary
            assert "Status: Success" in summary
            assert "Steps Completed: 3/4" in summary
            assert "Files Generated: 5" in summary
            assert "Warnings: 2" in summary
            assert "Modules: 3" in summary
            assert "Classes: 7" in summary
            assert "Functions: 15" in summary
            assert "Warning 1" in summary
            assert "Warning 2" in summary


class TestGenerateDocsTool:
    """Test cases for generate_docs_tool function."""

    @pytest.mark.asyncio
    async def test_generate_docs_tool_success(self, tmp_path):
        """Test successful generate_docs_tool execution."""
        # Create test project structure
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        # Create mock config file
        config_file = project_path / ".mcp-docs.yaml"
        config_file.write_text(
            """
project:
  name: "Test Project"
  version: "1.0.0"
  source_paths: ["src/"]

obsidian:
  vault_path: ""
  docs_folder: "Projects/Test"
"""
        )

        mock_results = {
            "status": "success",
            "steps_completed": ["analysis", "sphinx", "obsidian"],
            "files_generated": ["/vault/doc1.md", "/vault/doc2.md"],
            "warnings": [],
            "statistics": {"modules_found": 2},
        }

        with (
            patch("server.tools.generate_docs.ConfigManager") as mock_config_manager_class,
            patch("server.tools.generate_docs.DocumentationGenerator") as mock_generator_class,
        ):
            mock_config_manager = Mock()
            mock_config = Mock()
            mock_config_manager.load_config.return_value = mock_config
            mock_config_manager_class.return_value = mock_config_manager

            # Create a mock generator that calls the progress callback
            async def mock_generate_docs(progress_callback=None):
                if progress_callback:
                    progress_callback("Test progress message")
                return mock_results

            mock_generator = Mock()
            mock_generator.generate_documentation = AsyncMock(side_effect=mock_generate_docs)
            mock_generator_class.return_value = mock_generator

            result = await generate_docs_tool(str(project_path))

            assert result["status"] == "success"
            assert "progress_messages" in result
            assert len(result["progress_messages"]) > 0
            mock_config_manager.load_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_docs_tool_no_config(self, tmp_path):
        """Test generate_docs_tool with no config file."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        mock_results = {
            "status": "success",
            "steps_completed": ["analysis"],
            "files_generated": [],
            "warnings": [],
            "statistics": {"modules_found": 0},
        }

        with (
            patch("server.tools.generate_docs.Config") as mock_config_class,
            patch("server.tools.generate_docs.DocumentationGenerator") as mock_generator_class,
        ):
            mock_config = Mock()
            mock_config_class.return_value = mock_config

            mock_generator = Mock()
            mock_generator.generate_documentation = AsyncMock(return_value=mock_results)
            mock_generator_class.return_value = mock_generator

            result = await generate_docs_tool(str(project_path))

            assert result["status"] == "success"
            mock_config_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_docs_tool_with_overrides(self, tmp_path):
        """Test generate_docs_tool with configuration overrides."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        config_overrides = {"project": {"name": "Override Project"}}

        mock_results = {
            "status": "success",
            "steps_completed": [],
            "files_generated": [],
            "warnings": [],
            "statistics": {},
        }

        with (
            patch("server.tools.generate_docs.Config") as mock_config_class,
            patch("server.tools.generate_docs.DocumentationGenerator") as mock_generator_class,
        ):
            mock_config = Mock()
            mock_config_class.return_value = mock_config

            mock_generator = Mock()
            mock_generator.generate_documentation = AsyncMock(return_value=mock_results)
            mock_generator_class.return_value = mock_generator

            result = await generate_docs_tool(str(project_path), config_overrides)

            assert result["status"] == "success"
            # Verify config overrides were applied
            assert hasattr(mock_config, "project")

    @pytest.mark.asyncio
    async def test_generate_docs_tool_error(self, tmp_path):
        """Test generate_docs_tool with generation error."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        with (
            patch("server.tools.generate_docs.Config") as mock_config_class,
            patch("server.tools.generate_docs.DocumentationGenerator") as mock_generator_class,
        ):
            mock_config = Mock()
            mock_config_class.return_value = mock_config

            mock_generator = Mock()
            mock_generator.generate_documentation = AsyncMock(
                side_effect=DocumentationGenerationError("Test error")
            )
            mock_generator_class.return_value = mock_generator

            result = await generate_docs_tool(str(project_path))

            assert result["status"] == "error"
            assert result["error"] == "Test error"
            assert result["error_type"] == "DocumentationGenerationError"

    @pytest.mark.asyncio
    async def test_generate_docs_tool_unexpected_error(self, tmp_path):
        """Test generate_docs_tool with unexpected error."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        with patch("server.tools.generate_docs.Config") as mock_config_class:
            mock_config_class.side_effect = Exception("Unexpected error")

            result = await generate_docs_tool(str(project_path))

            assert result["status"] == "error"
            assert "Unexpected error" in result["error"]
            assert result["error_type"] == "Exception"


class TestToolDefinition:
    """Test cases for MCP tool definition."""

    def test_tool_definition_structure(self):
        """Test that TOOL_DEFINITION has correct structure."""
        from server.tools.generate_docs import TOOL_DEFINITION

        assert TOOL_DEFINITION["name"] == "generate_docs"
        assert "description" in TOOL_DEFINITION
        assert "inputSchema" in TOOL_DEFINITION

        schema = TOOL_DEFINITION["inputSchema"]
        assert schema["type"] == "object"
        assert "project_path" in schema["properties"]
        assert "config_override" in schema["properties"]
        assert "project_path" in schema["required"]
        assert schema["additionalProperties"] is False

        # Check project_path property
        project_path_prop = schema["properties"]["project_path"]
        assert project_path_prop["type"] == "string"
        assert "description" in project_path_prop

        # Check config_override property
        config_override_prop = schema["properties"]["config_override"]
        assert config_override_prop["type"] == "object"
        assert config_override_prop["additionalProperties"] is True
        assert config_override_prop["default"] is None
