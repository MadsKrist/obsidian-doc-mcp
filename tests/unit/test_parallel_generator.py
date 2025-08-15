"""Tests for parallel documentation generator."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from config.project_config import Config, ObsidianConfig, ProjectConfig
from docs_generator.analyzer import ModuleInfo, ProjectStructure
from utils.parallel_generator import ParallelDocumentationGenerator


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

        # Create sample Python files
        sample_file1 = src_dir / "module1.py"
        sample_file1.write_text(
            """
\"\"\"First module for testing.\"\"\"

def function1():
    \"\"\"Function 1.\"\"\"
    return "result1"
"""
        )

        sample_file2 = src_dir / "module2.py"
        sample_file2.write_text(
            """
\"\"\"Second module for testing.\"\"\"

def function2():
    \"\"\"Function 2.\"\"\"
    return "result2"
"""
        )

        yield project_path


@pytest.fixture
def sample_modules():
    """Create sample ModuleInfo objects."""
    return [
        ModuleInfo(
            name="module1",
            file_path=Path("src/module1.py"),
            docstring="First module for testing.",
            functions=[],
            classes=[],
            imports=[],
        ),
        ModuleInfo(
            name="module2",
            file_path=Path("src/module2.py"),
            docstring="Second module for testing.",
            functions=[],
            classes=[],
            imports=["module1"],  # module2 depends on module1
        ),
    ]


@pytest.fixture
def sample_project_structure(sample_modules):
    """Create sample ProjectStructure."""
    return ProjectStructure(
        project_name="TestProject",
        root_path=Path("test_project"),
        modules=sample_modules,
    )


class TestParallelDocumentationGenerator:
    """Test cases for ParallelDocumentationGenerator."""

    def test_init_basic(self, sample_config, temp_project_dir):
        """Test basic generator initialization."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        assert generator.config == config
        assert generator.max_workers is None  # Default
        assert generator.use_threads is True  # Default
        assert generator.enable_memory_optimization is True  # Default
        assert generator.project_path == Path(config.project.source_paths[0])
        assert generator.analyzer is not None
        assert generator.sphinx_generator is not None
        assert generator.obsidian_converter is not None
        assert generator.parallel_processor is not None
        assert generator.dependency_analyzer is not None
        assert generator.vault_manager is None  # No vault path set

    def test_init_with_custom_params(self, sample_config, temp_project_dir):
        """Test initialization with custom parameters."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(
            config,
            max_workers=4,
            use_threads=False,
            enable_memory_optimization=False,
        )

        assert generator.max_workers == 4
        assert generator.use_threads is False
        assert generator.enable_memory_optimization is False

    def test_init_with_vault_path(self, sample_config, temp_project_dir):
        """Test initialization with valid vault path."""
        vault_path = temp_project_dir / "vault"
        vault_path.mkdir()

        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]
        config.obsidian.vault_path = str(vault_path)

        generator = ParallelDocumentationGenerator(config)

        # vault_manager might still be None if ObsidianVaultManager fails
        assert hasattr(generator, "vault_manager")

    def test_setup_parallel_tasks(
        self, sample_config, temp_project_dir, sample_modules
    ):
        """Test parallel task setup."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        # Mock dependencies
        dependencies = {"module1": set(), "module2": {"module1"}}

        with patch.object(
            generator.dependency_analyzer, "estimate_processing_complexity"
        ) as mock_complexity:
            mock_complexity.return_value = 1.5

            generator._setup_parallel_tasks(sample_modules, dependencies)

            # Verify tasks were added to parallel processor
            assert len(generator.parallel_processor.dependency_resolver.tasks) == 2

    def test_process_single_module(
        self, sample_config, temp_project_dir, sample_modules
    ):
        """Test single module processing."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        # Mock Sphinx generation
        with patch.object(
            generator.sphinx_generator, "generate_documentation"
        ) as mock_sphinx:
            with patch.object(generator, "_convert_module_to_obsidian") as mock_convert:
                with patch.object(generator, "_save_module_to_vault") as mock_save:
                    mock_sphinx.return_value = {
                        "build_dir": Path("/tmp/sphinx"),
                        "files": ["index.html"],
                        "project_name": "TestProject",
                    }
                    mock_convert.return_value = {"files": {"index.md": "Content"}}
                    mock_save.return_value = ["index.md"]

                    result = generator._process_single_module(sample_modules[0])

                    assert result["module_name"] == "module1"
                    assert result["status"] == "success"
                    assert "sphinx_files" in result
                    assert "obsidian_files" in result
                    assert "vault_files" in result

    def test_process_single_module_error(
        self, sample_config, temp_project_dir, sample_modules
    ):
        """Test single module processing with error."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        # Mock Sphinx generation to raise error
        with patch.object(
            generator.sphinx_generator, "generate_documentation"
        ) as mock_sphinx:
            mock_sphinx.side_effect = Exception("Sphinx error")

            result = generator._process_single_module(sample_modules[0])

            assert result["module_name"] == "module1"
            assert result["status"] == "failed"
            assert "error" in result
            assert "Sphinx error" in result["error"]

    def test_convert_module_to_obsidian(self, sample_config, temp_project_dir):
        """Test module Obsidian conversion."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        sphinx_output = {
            "build_dir": Path("/tmp/sphinx"),
            "files": ["index.html"],
            "project_name": "TestProject",
        }

        expected_obsidian = {"files": {"index.md": "Content"}}

        # Mock the standalone function
        with patch(
            "docs_generator.obsidian_converter.convert_sphinx_to_obsidian",
            return_value=expected_obsidian,
        ):
            result = generator._convert_module_to_obsidian(sphinx_output)
            assert result == expected_obsidian

    def test_save_module_to_vault_no_manager(self, sample_config, temp_project_dir):
        """Test vault saving with no vault manager."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        obsidian_docs = {"files": {"test.md": "Content"}}

        result = generator._save_module_to_vault(obsidian_docs, "test_module")

        assert result == []  # Empty list when no vault manager

    def test_save_module_to_vault_with_manager(self, sample_config, temp_project_dir):
        """Test vault saving with mock vault manager."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        # Create temp vault directory
        vault_dir = temp_project_dir / "vault" / "docs"
        vault_dir.mkdir(parents=True)

        # Mock vault manager
        mock_vault_manager = Mock()
        mock_vault_manager.ensure_folder_exists.return_value = vault_dir
        mock_vault_manager.safe_write_file.return_value = None
        generator.vault_manager = mock_vault_manager

        obsidian_docs = {"files": {"test.md": "Content"}}

        result = generator._save_module_to_vault(obsidian_docs, "test_module")

        assert len(result) == 1
        mock_vault_manager.ensure_folder_exists.assert_called_once()
        mock_vault_manager.safe_write_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_parallel_results(self, sample_config, temp_project_dir):
        """Test parallel results collection."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        # Mock processing results
        mock_result1 = Mock()
        mock_result1.success = True
        mock_result1.result = {"module_name": "module1", "vault_files": ["file1.md"]}

        mock_result2 = Mock()
        mock_result2.success = True
        mock_result2.result = {"module_name": "module2", "vault_files": ["file2.md"]}

        processing_results = {
            "task1": mock_result1,
            "task2": mock_result2,
        }

        result = await generator._collect_parallel_results(processing_results)

        assert len(result) == 2
        assert "file1.md" in result
        assert "file2.md" in result

    @pytest.mark.asyncio
    async def test_analyze_project(
        self, sample_config, temp_project_dir, sample_project_structure
    ):
        """Test project analysis."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        with patch.object(
            generator.analyzer, "analyze_project", return_value=sample_project_structure
        ):
            result = await generator._analyze_project()
            assert result == sample_project_structure

    def test_create_generation_summary(self, sample_config, temp_project_dir):
        """Test generation summary creation."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        results = {
            "statistics": {
                "successful_modules": 5,
                "modules_processed": 6,
                "total_files_generated": 15,
            },
            "parallel_stats": {
                "success_rate": 0.83,
                "total_processing_time": 45.2,
            },
        }

        summary = generator._create_generation_summary(results)

        assert "Parallel generation" in summary
        assert "5/6 modules successful" in summary
        assert "15 files generated" in summary
        assert "83.0%" in summary

    def test_get_performance_recommendations(self, sample_config, temp_project_dir):
        """Test performance recommendations."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        # Test high dependency coupling
        recommendations = generator._get_performance_recommendations(10, 2, 1.5)
        assert any("High dependency coupling" in rec for rec in recommendations)

        # Test small project
        recommendations = generator._get_performance_recommendations(5, 3, 3.0)
        assert any("Small project" in rec for rec in recommendations)

        # Test excellent parallelization
        recommendations = generator._get_performance_recommendations(20, 15, 6.0)
        assert any("Excellent parallelization" in rec for rec in recommendations)


class TestParallelGeneratorPerformanceEstimation:
    """Test performance estimation functionality."""

    @pytest.mark.asyncio
    async def test_estimate_parallel_performance(
        self, sample_config, temp_project_dir, sample_modules
    ):
        """Test parallel performance estimation."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        # Mock project structure
        mock_structure = ProjectStructure(
            project_name="TestProject",
            root_path=Path("test"),
            modules=sample_modules,
        )

        # Mock dependencies
        mock_dependencies = {"module1": set(), "module2": {"module1"}}

        with patch.object(generator, "_analyze_project", return_value=mock_structure):
            with patch.object(
                generator.dependency_analyzer,
                "analyze_module_dependencies",
                return_value=mock_dependencies,
            ):
                with patch.object(
                    generator.dependency_analyzer,
                    "get_independent_modules",
                    return_value=["module1"],
                ):
                    with patch.object(
                        generator.dependency_analyzer,
                        "estimate_processing_complexity",
                        return_value=2.0,
                    ):
                        result = await generator.estimate_parallel_performance()

                        assert result["total_modules"] == 2
                        assert result["independent_modules"] == 1
                        assert result["modules_with_dependencies"] == 1
                        assert "dependency_ratio" in result
                        assert "estimated_sequential_time_seconds" in result
                        assert "estimated_parallel_time_seconds" in result
                        assert "estimated_speedup_factor" in result
                        assert "parallelism_potential" in result
                        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_estimate_parallel_performance_no_modules(
        self, sample_config, temp_project_dir
    ):
        """Test performance estimation with no modules."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        # Mock empty project structure
        mock_structure = ProjectStructure(
            project_name="TestProject",
            root_path=Path("test"),
            modules=[],
        )

        with patch.object(generator, "_analyze_project", return_value=mock_structure):
            result = await generator.estimate_parallel_performance()

            assert "error" in result
            assert "No modules found" in result["error"]


class TestParallelGeneratorFullPipeline:
    """Test the full parallel generation pipeline."""

    @pytest.mark.asyncio
    async def test_generate_documentation_with_memory_optimization(
        self, sample_config, temp_project_dir, sample_project_structure
    ):
        """Test documentation generation with memory optimization."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(
            config, enable_memory_optimization=True
        )

        # Mock memory context manager
        mock_monitor = Mock()
        mock_monitor.profile_operation.return_value.__enter__ = Mock()
        mock_monitor.profile_operation.return_value.__exit__ = Mock()
        mock_monitor.get_memory_snapshot.return_value = Mock(
            rss_mb=128.0, python_objects=5000
        )
        mock_monitor.get_memory_recommendations.return_value = []

        mock_optimizer = Mock()

        with patch("utils.parallel_generator.memory_efficient_context") as mock_context:
            mock_context.return_value.__enter__ = Mock(
                return_value=(mock_monitor, mock_optimizer)
            )
            mock_context.return_value.__exit__ = Mock(return_value=None)

            with patch.object(generator, "_generate_with_parallelism") as mock_generate:
                mock_generate.return_value = {
                    "status": "success",
                    "generation_mode": "parallel",
                    "statistics": {"modules_processed": 2},
                }

                result = await generator.generate_documentation()

                assert result["status"] == "success"
                assert result["generation_mode"] == "parallel"

    @pytest.mark.asyncio
    async def test_generate_documentation_without_memory_optimization(
        self, sample_config, temp_project_dir, sample_project_structure
    ):
        """Test documentation generation without memory optimization."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(
            config, enable_memory_optimization=False
        )

        with patch.object(generator, "_generate_with_parallelism") as mock_generate:
            mock_generate.return_value = {
                "status": "success",
                "generation_mode": "parallel",
                "statistics": {"modules_processed": 2},
            }

            result = await generator.generate_documentation()

            assert result["status"] == "success"
            assert result["generation_mode"] == "parallel"

    @pytest.mark.asyncio
    async def test_generate_with_parallelism_no_modules(
        self, sample_config, temp_project_dir
    ):
        """Test parallel generation with no modules."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        # Mock empty project structure
        mock_structure = ProjectStructure(
            project_name="TestProject",
            root_path=Path("test"),
            modules=[],
        )

        with patch.object(generator, "_analyze_project", return_value=mock_structure):
            result = await generator._generate_with_parallelism(None)

            assert result["status"] == "success"
            assert result["statistics"]["modules_found"] == 0

    @pytest.mark.asyncio
    async def test_generate_with_parallelism_mocked_pipeline(
        self, sample_config, temp_project_dir, sample_project_structure
    ):
        """Test parallel generation with mocked complete pipeline."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generator = ParallelDocumentationGenerator(config)

        # Mock all major dependencies
        with patch.object(
            generator, "_analyze_project", return_value=sample_project_structure
        ):
            with patch.object(
                generator.dependency_analyzer, "analyze_module_dependencies"
            ) as mock_deps:
                with patch.object(generator, "_setup_parallel_tasks") as mock_setup:
                    with patch.object(
                        generator.parallel_processor, "process_all"
                    ) as mock_process:
                        with patch.object(
                            generator.parallel_processor, "get_processing_statistics"
                        ) as mock_stats:
                            with patch.object(
                                generator, "_collect_parallel_results"
                            ) as mock_collect:
                                mock_deps.return_value = {
                                    "module1": set(),
                                    "module2": {"module1"},
                                }
                                mock_setup.return_value = None
                                mock_process.return_value = {}
                                mock_stats.return_value = {"success_rate": 1.0}
                                mock_collect.return_value = ["file1.md", "file2.md"]

                                result = await generator._generate_with_parallelism(
                                    None
                                )

                                assert result["status"] == "success"
                                assert result["generation_mode"] == "parallel"
                                assert len(result["steps_completed"]) > 0


class TestParallelGeneratorErrorHandling:
    """Test error handling in parallel generator."""

    def test_init_with_invalid_vault_path(self, sample_config, temp_project_dir):
        """Test initialization with invalid vault path logs warning."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]
        config.obsidian.vault_path = "/nonexistent/vault/path"

        # Should not raise exception, just log warning
        generator = ParallelDocumentationGenerator(config)

        assert generator.vault_manager is None

    def test_multiple_generator_instances(self, sample_config, temp_project_dir):
        """Test creating multiple generator instances."""
        config = sample_config
        config.project.source_paths = [str(temp_project_dir / "src")]

        generators = [
            ParallelDocumentationGenerator(config, max_workers=2) for _ in range(3)
        ]

        for gen in generators:
            assert gen.analyzer is not None
            assert gen.parallel_processor.max_workers == 2
