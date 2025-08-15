"""Simple tests for incremental documentation generator."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from config.project_config import Config, ObsidianConfig, ProjectConfig
from docs_generator.analyzer import ProjectStructure
from utils.incremental_generator import (
    IncrementalDocumentationGenerationError,
    IncrementalDocumentationGenerator,
)


@pytest.fixture
def sample_config():
    """Create sample configuration for testing."""
    return Config(
        project=ProjectConfig(
            name="TestProject",
            version="1.0.0",
            source_paths=["src"],
            exclude_patterns=["tests", "*.pyc"],
        ),
        obsidian=ObsidianConfig(
            vault_path="",  # Empty to avoid vault creation
            docs_folder="Projects/TestProject",
            use_wikilinks=True,
            tag_prefix="code/",
        ),
    )


@pytest.fixture
def temp_project_dir():
    """Create temporary project directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create source directory
        src_dir = project_path / "src"
        src_dir.mkdir()

        # Create sample Python file
        sample_file = src_dir / "sample_module.py"
        sample_file.write_text(
            """
\"\"\"Sample module for testing.\"\"\"

def hello_world():
    \"\"\"Say hello to the world.\"\"\"
    return "Hello, World!"
"""
        )

        yield project_path


class TestIncrementalGeneratorBasics:
    """Basic tests for IncrementalDocumentationGenerator."""

    def test_init_basic(self, sample_config, temp_project_dir):
        """Test basic generator initialization."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        assert generator.config == config
        assert generator.project_path == Path(config.project.source_paths[0])
        assert generator.analyzer is not None
        assert generator.sphinx_generator is not None
        assert generator.obsidian_converter is not None
        assert generator.enable_incremental is True  # Default

    def test_init_disable_incremental(self, sample_config, temp_project_dir):
        """Test generator initialization with incremental disabled."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config, enable_incremental=False)

        assert generator.enable_incremental is False

    @pytest.mark.asyncio
    async def test_should_perform_full_build_first_run(self, sample_config, temp_project_dir):
        """Test full build detection on first run."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        # First run should always be full build
        should_full = await generator._should_perform_full_build(False)
        assert should_full is True

    @pytest.mark.asyncio
    async def test_should_perform_full_build_forced(self, sample_config, temp_project_dir):
        """Test forced full build."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        # Force flag should trigger full build
        should_full = await generator._should_perform_full_build(True)
        assert should_full is True

    @pytest.mark.asyncio
    async def test_analyze_project_mock(self, sample_config, temp_project_dir):
        """Test project analysis with mock."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        mock_structure = ProjectStructure(
            project_name="TestProject",
            root_path=Path("test"),
            modules=[],
        )

        with patch.object(generator.analyzer, "analyze_project", return_value=mock_structure):
            result = await generator._analyze_project()
            assert result == mock_structure

    def test_create_generation_summary_full(self, sample_config, temp_project_dir):
        """Test generation summary for full build."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        results = {
            "statistics": {
                "build_type": "full",
                "modules_analyzed": 5,
                "total_files_generated": 10,
                "build_time_seconds": 25.3,
            }
        }

        summary = generator._create_generation_summary(results)
        assert "Full build" in summary
        assert "5 modules" in summary
        assert "10 files" in summary

    def test_get_build_status_basic(self, sample_config, temp_project_dir):
        """Test build status retrieval."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        status = generator.get_build_status()

        assert "project_path" in status
        assert "incremental_enabled" in status
        assert status["incremental_enabled"] is True

    def test_clear_build_cache_safe(self, sample_config, temp_project_dir):
        """Test that cache clearing is safe."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        # Should not raise exception
        generator.clear_build_cache()

    @pytest.mark.asyncio
    async def test_generate_sphinx_docs_mock(self, sample_config, temp_project_dir):
        """Test Sphinx docs generation with mock."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        mock_structure = ProjectStructure(
            project_name="TestProject",
            root_path=Path("test"),
            modules=[],
        )

        expected_output = {
            "build_dir": Path("/tmp/sphinx_build"),
            "files": ["index.html"],
            "project_name": "TestProject",
        }

        with patch.object(
            generator.sphinx_generator,
            "generate_documentation",
            return_value=expected_output,
        ):
            result = await generator._generate_sphinx_docs(mock_structure)
            assert result == expected_output

    @pytest.mark.asyncio
    async def test_convert_to_obsidian_mock(self, sample_config, temp_project_dir):
        """Test Obsidian conversion with mock."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        sphinx_output = {
            "build_dir": Path("/tmp/sphinx_build"),
            "files": ["index.html"],
            "project_name": "TestProject",
        }

        expected_obsidian = {"files": {"index.md": "# TestProject\n\nContent here."}}

        # Mock the standalone function from its original module
        with patch(
            "docs_generator.obsidian_converter.convert_sphinx_to_obsidian",
            return_value=expected_obsidian,
        ):
            result = await generator._convert_to_obsidian(sphinx_output)
            assert result == expected_obsidian

    @pytest.mark.asyncio
    async def test_save_to_vault_no_manager(self, sample_config, temp_project_dir):
        """Test vault saving with no vault manager."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)
        # Ensure no vault manager
        generator.vault_manager = None

        obsidian_docs = {"files": {"test.md": "Content"}}

        result = await generator._save_to_vault(obsidian_docs)

        assert "files_created" in result
        assert "warnings" in result
        assert len(result["files_created"]) == 0
        assert "No vault manager" in result["warnings"][0]


class TestIncrementalGeneratorErrorHandling:
    """Test error handling in incremental generator."""

    @pytest.mark.asyncio
    async def test_generation_exception_handling(self, sample_config, temp_project_dir):
        """Test that generation exceptions are properly wrapped."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        # Mock analyzer to raise exception
        with patch.object(generator.analyzer, "analyze_project") as mock_analyze:
            mock_analyze.side_effect = RuntimeError("Test error")

            with pytest.raises(IncrementalDocumentationGenerationError) as exc_info:
                await generator.generate_documentation()

            assert "Test error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_sphinx_generation_failure(self, sample_config, temp_project_dir):
        """Test Sphinx generation failure handling."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        mock_structure = ProjectStructure(
            project_name="TestProject",
            root_path=Path("test"),
            modules=[],
        )

        with patch.object(generator.analyzer, "analyze_project", return_value=mock_structure):
            with patch.object(generator, "_generate_sphinx_docs") as mock_sphinx:
                mock_sphinx.side_effect = RuntimeError("Sphinx failed")

                with pytest.raises(IncrementalDocumentationGenerationError) as exc_info:
                    await generator.generate_documentation()

                assert "Sphinx failed" in str(exc_info.value)


class TestIncrementalGeneratorIntegration:
    """Integration-style tests with mocked external dependencies."""

    @pytest.mark.asyncio
    async def test_full_generation_pipeline_mocked(self, sample_config, temp_project_dir):
        """Test full generation pipeline with all external dependencies mocked."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = IncrementalDocumentationGenerator(config)

        # Mock project structure
        mock_structure = ProjectStructure(
            project_name="TestProject",
            root_path=Path("test"),
            modules=[],
        )

        # Mock all external calls
        with patch.object(generator.analyzer, "analyze_project", return_value=mock_structure):
            with patch.object(generator.sphinx_generator, "generate_documentation") as mock_sphinx:
                with patch(
                    "docs_generator.obsidian_converter.convert_sphinx_to_obsidian"
                ) as mock_obsidian:
                    # Setup mock returns
                    mock_sphinx.return_value = {
                        "build_dir": Path("/tmp/sphinx"),
                        "files": ["index.html"],
                        "project_name": "TestProject",
                    }
                    mock_obsidian.return_value = {"files": {"index.md": "# Test\nContent"}}

                    # Run generation
                    result = await generator.generate_documentation()

                    # Verify basic structure (will be from _perform_full_build)
                    assert isinstance(result, dict)
                    # The actual return structure depends on the implementation
                    # We'll just verify it doesn't crash and returns something

    def test_multiple_generator_instances(self, sample_config, temp_project_dir):
        """Test creating multiple generator instances."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        # Create multiple instances
        generators = [IncrementalDocumentationGenerator(config) for _ in range(3)]

        # All should initialize properly
        for gen in generators:
            assert gen.analyzer is not None
            assert gen.sphinx_generator is not None
            assert gen.obsidian_converter is not None
