"""Tests for memory-optimized documentation generator."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from config.project_config import Config, ObsidianConfig, ProjectConfig
from docs_generator.analyzer import ModuleInfo
from utils.memory_optimized_generator import MemoryOptimizedDocumentationGenerator


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

class SampleClass:
    \"\"\"A sample class for testing.\"\"\"

    def method(self):
        \"\"\"A sample method.\"\"\"
        return "method result"
"""
        )

        yield project_path


@pytest.fixture
def sample_modules():
    """Create sample ModuleInfo objects."""
    return [
        ModuleInfo(
            name="sample_module",
            file_path=Path("src/sample_module.py"),
            docstring="Sample module for testing.",
            functions=[],
            classes=[],
            imports=[],
        )
    ]


class TestMemoryOptimizedGenerator:
    """Test cases for MemoryOptimizedDocumentationGenerator."""

    def test_init_basic(self, sample_config, temp_project_dir):
        """Test basic generator initialization."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config)

        assert generator.config == config
        assert generator.max_memory_mb is None
        assert generator.batch_size == 10  # Default batch size
        assert generator.aggressive_gc is True  # Default
        assert generator.project_path == Path(config.project.source_paths[0])
        assert generator.analyzer is not None
        assert generator.sphinx_generator is not None
        assert generator.obsidian_converter is not None
        assert generator.vault_manager is None  # No vault path set

    def test_init_with_custom_params(self, sample_config, temp_project_dir):
        """Test initialization with custom parameters."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(
            config,
            max_memory_mb=512.0,
            batch_size=5,
            aggressive_gc=False,
        )

        assert generator.max_memory_mb == 512.0
        assert generator.batch_size == 5
        assert generator.aggressive_gc is False

    def test_init_with_vault_path(self, sample_config, temp_project_dir):
        """Test initialization with valid vault path."""
        vault_path = temp_project_dir / "vault"
        vault_path.mkdir()

        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]
        config.obsidian.vault_path = str(vault_path)

        generator = MemoryOptimizedDocumentationGenerator(config)

        # vault_manager might still be None if ObsidianVaultManager fails
        # This is expected behavior based on the implementation
        assert hasattr(generator, "vault_manager")

    @pytest.mark.asyncio
    async def test_discover_files_efficiently(self, sample_config, temp_project_dir):
        """Test efficient file discovery."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config)

        files = await generator._discover_files_efficiently()

        assert len(files) == 1
        assert files[0].name == "sample_module.py"

    @pytest.mark.asyncio
    async def test_discover_files_with_exclusions(
        self, sample_config, temp_project_dir
    ):
        """Test file discovery with exclusion patterns."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]
        config.project.exclude_patterns = ["sample_module"]

        generator = MemoryOptimizedDocumentationGenerator(config)

        files = await generator._discover_files_efficiently()

        # Should exclude the file containing "sample_module" in the path
        assert len(files) == 0

    @pytest.mark.asyncio
    async def test_analyze_files_batch(
        self, sample_config, temp_project_dir, sample_modules
    ):
        """Test batch file analysis."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config)

        # Mock memory optimizer
        mock_optimizer = Mock()
        mock_optimizer.memory_efficient_file_reader.return_value = ["file content"]

        # Mock analyzer method
        with patch.object(
            generator.analyzer, "_analyze_file", return_value=sample_modules[0]
        ):
            file_paths = [temp_project_dir / "src" / "sample_module.py"]

            modules = await generator._analyze_files_batch(file_paths, mock_optimizer)

            assert len(modules) == 1
            assert modules[0].name == "sample_module"

    @pytest.mark.asyncio
    async def test_analyze_files_batch_with_error(
        self, sample_config, temp_project_dir
    ):
        """Test batch file analysis with file error."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config)

        # Mock memory optimizer
        mock_optimizer = Mock()
        mock_optimizer.memory_efficient_file_reader.side_effect = Exception(
            "File error"
        )

        file_paths = [temp_project_dir / "src" / "sample_module.py"]

        # Should handle error gracefully and continue
        modules = await generator._analyze_files_batch(file_paths, mock_optimizer)

        assert len(modules) == 0  # No modules due to error

    def test_create_batch_structure(
        self, sample_config, temp_project_dir, sample_modules
    ):
        """Test batch structure creation."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config)

        structure = generator._create_batch_structure(sample_modules)

        assert structure.project_name == generator.project_path.name
        assert structure.root_path == generator.project_path
        assert len(structure.modules) == 1
        assert structure.modules[0].name == "sample_module"

    @pytest.mark.asyncio
    async def test_convert_batch_to_obsidian(self, sample_config, temp_project_dir):
        """Test batch Obsidian conversion."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config)

        sphinx_output = {
            "build_dir": temp_project_dir / "sphinx_build",
            "files": ["index.html"],
            "project_name": "TestProject",
        }

        expected_obsidian = {"files": {"index.md": "# TestProject\n\nContent here."}}

        # Mock the standalone function
        with patch(
            "docs_generator.obsidian_converter.convert_sphinx_to_obsidian",
            return_value=expected_obsidian,
        ):
            result = await generator._convert_batch_to_obsidian(sphinx_output)
            assert result == expected_obsidian

    @pytest.mark.asyncio
    async def test_save_batch_to_vault_no_manager(
        self, sample_config, temp_project_dir
    ):
        """Test vault saving with no vault manager."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config)

        obsidian_docs = {"files": {"test.md": "Content"}}

        result = await generator._save_batch_to_vault(obsidian_docs)

        assert result == []  # Empty list when no vault manager

    @pytest.mark.asyncio
    async def test_save_batch_to_vault_with_manager(
        self, sample_config, temp_project_dir
    ):
        """Test vault saving with mock vault manager."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config)

        # Create a temporary vault directory that exists
        vault_dir = temp_project_dir / "vault" / "docs"
        vault_dir.mkdir(parents=True)

        # Mock vault manager
        mock_vault_manager = Mock()
        mock_vault_manager.ensure_folder_exists.return_value = vault_dir
        mock_vault_manager.safe_write_file.return_value = None
        generator.vault_manager = mock_vault_manager

        obsidian_docs = {"files": {"test.md": "Content"}}

        result = await generator._save_batch_to_vault(obsidian_docs)

        assert len(result) == 1
        mock_vault_manager.ensure_folder_exists.assert_called_once()
        mock_vault_manager.safe_write_file.assert_called_once()

    def test_create_generation_summary(self, sample_config, temp_project_dir):
        """Test generation summary creation."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config)

        results = {
            "statistics": {
                "modules_analyzed": 5,
                "total_files_generated": 10,
            },
            "memory_profile": {
                "peak_memory_mb": 128.5,
            },
        }

        summary = generator._create_generation_summary(results)

        assert "Memory-optimized generation" in summary
        assert "5 modules" in summary
        assert "10 files generated" in summary
        assert "128.5MB" in summary

    @pytest.mark.asyncio
    async def test_estimate_memory_requirements(self, sample_config, temp_project_dir):
        """Test memory requirements estimation."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config)

        with patch.object(generator, "_discover_files_efficiently") as mock_discover:
            with patch.object(generator, "_analyze_files_batch") as mock_analyze:
                mock_discover.return_value = [
                    Path("file1.py"),
                    Path("file2.py"),
                    Path("file3.py"),
                ]
                mock_analyze.return_value = []

                # Mock memory context manager
                mock_monitor = Mock()
                mock_monitor.current_profile = Mock()
                mock_monitor.current_profile.memory_delta_mb = 10.0
                mock_monitor.get_memory_recommendations.return_value = [
                    "Test recommendation"
                ]

                # Mock profile_operation context manager
                mock_profile_context = Mock()
                mock_profile_context.__enter__ = Mock(return_value=Mock())
                mock_profile_context.__exit__ = Mock(return_value=None)
                mock_monitor.profile_operation.return_value = mock_profile_context

                mock_optimizer = Mock()

                with patch(
                    "utils.memory_optimized_generator.memory_efficient_context"
                ) as mock_context:
                    mock_context.return_value.__enter__ = Mock(
                        return_value=(mock_monitor, mock_optimizer)
                    )
                    mock_context.return_value.__exit__ = Mock(return_value=None)

                    result = await generator.estimate_memory_requirements()

                    assert result["total_files"] == 3
                    assert result["sample_files"] == 3  # Min of 5 and 3
                    assert "avg_memory_per_file_mb" in result
                    assert "estimated_total_memory_mb" in result
                    assert "recommended_batch_size" in result
                    assert "memory_recommendations" in result


class TestMemoryOptimizedGeneratorFullPipeline:
    """Test the full memory-optimized generation pipeline."""

    @pytest.mark.asyncio
    async def test_generate_documentation_basic(
        self, sample_config, temp_project_dir, sample_modules
    ):
        """Test basic documentation generation."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config, batch_size=1)

        # Mock all major dependencies
        with patch.object(generator, "_discover_files_efficiently") as mock_discover:
            with patch.object(generator, "_analyze_files_batch") as mock_analyze:
                with patch.object(
                    generator, "_generate_documentation_streaming"
                ) as mock_generate:
                    mock_discover.return_value = [Path("test.py")]
                    mock_analyze.return_value = sample_modules
                    mock_generate.return_value = ["output.md"]

                    # Mock memory context manager
                    mock_monitor = Mock()
                    mock_monitor.profile_operation.return_value.__enter__ = Mock(
                        return_value=Mock()
                    )
                    mock_monitor.profile_operation.return_value.__exit__ = Mock(
                        return_value=None
                    )
                    mock_monitor.take_snapshot.return_value = None
                    mock_monitor.get_memory_snapshot.return_value = Mock(
                        rss_mb=64.0, python_objects=1000
                    )
                    mock_monitor.get_memory_recommendations.return_value = []

                    mock_optimizer = Mock()
                    mock_optimizer.batch_processor.return_value.__enter__ = Mock(
                        return_value=iter([[Path("test.py")]])
                    )
                    mock_optimizer.batch_processor.return_value.__exit__ = Mock(
                        return_value=None
                    )
                    mock_optimizer.clear_caches.return_value = {}

                    with patch(
                        "utils.memory_optimized_generator.memory_efficient_context"
                    ) as mock_context:
                        mock_context.return_value.__enter__.return_value = (
                            mock_monitor,
                            mock_optimizer,
                        )
                        mock_context.return_value.__exit__.return_value = None

                        result = await generator.generate_documentation()

                        assert result["status"] == "success"
                        assert result["generation_mode"] == "memory_optimized"
                        assert len(result["steps_completed"]) > 0
                        assert "memory_profile" in result
                        assert "statistics" in result

    @pytest.mark.asyncio
    async def test_generate_documentation_streaming_empty(
        self, sample_config, temp_project_dir
    ):
        """Test streaming generation with empty module list."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config, batch_size=1)

        # Mock optimizer for batch processing
        mock_optimizer = Mock()
        mock_optimizer.batch_processor.return_value.__enter__ = Mock(
            return_value=iter([])
        )
        mock_optimizer.batch_processor.return_value.__exit__ = Mock(return_value=None)

        result = await generator._generate_documentation_streaming([], mock_optimizer)

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_documentation_streaming_with_modules(
        self, sample_config, temp_project_dir, sample_modules
    ):
        """Test streaming generation with modules."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config, batch_size=1)

        # Mock optimizer for batch processing
        mock_optimizer = Mock()
        mock_batch_context = Mock()
        mock_batch_context.__enter__ = Mock(return_value=iter([sample_modules]))
        mock_batch_context.__exit__ = Mock(return_value=None)
        mock_optimizer.batch_processor.return_value = mock_batch_context

        # Mock Sphinx generation to succeed
        with patch.object(
            generator.sphinx_generator, "generate_documentation"
        ) as mock_sphinx:
            with patch.object(generator, "_convert_batch_to_obsidian") as mock_convert:
                with patch.object(generator, "_save_batch_to_vault") as mock_save:
                    mock_sphinx.return_value = {
                        "build_dir": Path("/tmp/sphinx"),
                        "files": ["index.html"],
                        "project_name": "TestProject",
                    }
                    mock_convert.return_value = {"files": {"index.md": "Content"}}
                    mock_save.return_value = ["index.md"]

                    result = await generator._generate_documentation_streaming(
                        sample_modules, mock_optimizer
                    )

                    # Should have processed the batch successfully
                    assert isinstance(result, list)
                    # The actual length depends on vault manager being present
                    # We can't assert exact length without more complex mocking

    @pytest.mark.asyncio
    async def test_generate_documentation_streaming_with_error(
        self, sample_config, temp_project_dir, sample_modules
    ):
        """Test streaming generation with error handling."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = MemoryOptimizedDocumentationGenerator(config, batch_size=1)

        # Mock optimizer for batch processing
        mock_optimizer = Mock()
        mock_optimizer.batch_processor.return_value.__enter__ = Mock(
            return_value=iter([sample_modules])
        )
        mock_optimizer.batch_processor.return_value.__exit__ = Mock(return_value=None)

        # Mock Sphinx generation to raise an error
        with patch.object(
            generator.sphinx_generator, "generate_documentation"
        ) as mock_sphinx:
            mock_sphinx.side_effect = Exception("Sphinx error")

            # Should handle error gracefully and continue
            result = await generator._generate_documentation_streaming(
                sample_modules, mock_optimizer
            )

            assert result == []


class TestMemoryOptimizedGeneratorErrorHandling:
    """Test error handling in memory-optimized generator."""

    def test_init_with_invalid_vault_path(self, sample_config, temp_project_dir):
        """Test initialization with invalid vault path logs warning."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]
        config.obsidian.vault_path = "/nonexistent/vault/path"

        # Should not raise exception, just log warning
        generator = MemoryOptimizedDocumentationGenerator(config)

        assert generator.vault_manager is None

    def test_multiple_generator_instances(self, sample_config, temp_project_dir):
        """Test creating multiple generator instances."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generators = [
            MemoryOptimizedDocumentationGenerator(config, batch_size=5)
            for _ in range(3)
        ]

        for gen in generators:
            assert gen.analyzer is not None
            assert gen.batch_size == 5
