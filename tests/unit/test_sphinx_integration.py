"""Tests for Sphinx integration functionality."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.project_config import Config, SphinxConfig
from docs_generator.analyzer import ModuleInfo, ProjectStructure
from docs_generator.sphinx_integration import (
    SphinxDocumentationGenerator,
    SphinxGenerationError,
    SphinxProject,
    generate_sphinx_documentation,
)


class TestSphinxProject:
    """Test SphinxProject class functionality."""

    @pytest.fixture
    def sample_project_structure(self) -> ProjectStructure:
        """Create a sample project structure for testing."""
        structure = ProjectStructure(
            project_name="test_project",
            root_path=Path("/test"),
            modules=[
                ModuleInfo(
                    name="test_module",
                    file_path=Path("/test/test_module.py"),
                    docstring="Test module docstring",
                    is_package=False,
                    package_path="",
                ),
                ModuleInfo(
                    name="test_package",
                    file_path=Path("/test/test_package/__init__.py"),
                    docstring="Test package docstring",
                    is_package=True,
                    package_path="test_package",
                ),
            ],
        )
        structure.packages = {"test_package": ["test_package.submodule"]}
        return structure

    @pytest.fixture
    def config(self) -> Config:
        """Create test configuration."""
        config = Config()
        config.sphinx = SphinxConfig(
            extensions=[
                "sphinx.ext.autodoc",
                "sphinx.ext.napoleon",
                "sphinx.ext.viewcode",
            ],
            theme="sphinx_rtd_theme",
        )
        return config

    @pytest.fixture
    def sphinx_project(
        self, sample_project_structure: ProjectStructure, config: Config
    ) -> SphinxProject:
        """Create SphinxProject instance for testing."""
        return SphinxProject(sample_project_structure, config)

    def test_sphinx_project_initialization(
        self,
        sphinx_project: SphinxProject,
        sample_project_structure: ProjectStructure,
        config: Config,
    ) -> None:
        """Test SphinxProject initialization."""
        assert sphinx_project.project_structure == sample_project_structure
        assert sphinx_project.config == config
        assert sphinx_project.project_path is None
        assert sphinx_project.build_path is None
        assert sphinx_project.source_path is None

    def test_generate_conf_py(self, sphinx_project: SphinxProject) -> None:
        """Test conf.py generation."""
        conf_content = sphinx_project.generate_conf_py()

        assert 'project = "test_project"' in conf_content
        assert "sphinx.ext.autodoc" in conf_content
        assert "sphinx.ext.napoleon" in conf_content
        assert "sphinx.ext.viewcode" in conf_content
        assert 'html_theme = "sphinx_rtd_theme"' in conf_content
        assert "napoleon_google_docstring = True" in conf_content

    def test_generate_index_rst(self, sphinx_project: SphinxProject) -> None:
        """Test index.rst generation."""
        index_content = sphinx_project.generate_index_rst()

        assert "test_project Documentation" in index_content
        assert "Welcome to the test_project documentation" in index_content
        assert ".. toctree::" in index_content
        assert ":ref:`genindex`" in index_content

    def test_generate_modules_rst(self, sphinx_project: SphinxProject) -> None:
        """Test modules.rst generation."""
        modules_content = sphinx_project.generate_modules_rst()

        assert "API Reference" in modules_content
        assert "test_project" in modules_content
        assert ".. toctree::" in modules_content
        assert "test_module" in modules_content

    def test_generate_package_rst(self, sphinx_project: SphinxProject) -> None:
        """Test package RST generation."""
        package_rst = sphinx_project._generate_package_rst("test_package")

        assert "test_package package" in package_rst
        assert ".. automodule:: test_package" in package_rst
        assert ":members:" in package_rst
        assert ":show-inheritance:" in package_rst

    def test_generate_module_rst(self, sphinx_project: SphinxProject) -> None:
        """Test module RST generation."""
        module_rst = sphinx_project._generate_module_rst("test_module")

        assert "test_module module" in module_rst
        assert ".. automodule:: test_module" in module_rst
        assert ":members:" in module_rst

    def test_create_project_structure(self, sphinx_project: SphinxProject, tmp_path: Path) -> None:
        """Test Sphinx project structure creation."""
        sphinx_project.create_project_structure(tmp_path)

        # Check that paths are set
        assert sphinx_project.project_path is not None
        assert sphinx_project.source_path is not None
        assert sphinx_project.build_path is not None

        # Check directory creation
        assert sphinx_project.project_path.exists()
        assert sphinx_project.source_path.exists()
        assert (sphinx_project.source_path / "_static").exists()
        assert (sphinx_project.source_path / "_templates").exists()

        # Check file creation
        assert (sphinx_project.source_path / "conf.py").exists()
        assert (sphinx_project.source_path / "index.rst").exists()
        assert (sphinx_project.source_path / "modules.rst").exists()
        assert (sphinx_project.source_path / "_static" / "custom.css").exists()

        # Check API directory and files
        api_dir = sphinx_project.source_path / "api"
        assert api_dir.exists()
        assert (api_dir / "test_module.rst").exists()

    def test_generate_module_rst_files(self, sphinx_project: SphinxProject, tmp_path: Path) -> None:
        """Test individual module RST file generation."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        sphinx_project.generate_module_rst_files(output_dir)

        api_dir = output_dir / "api"
        assert api_dir.exists()
        assert (api_dir / "test_module.rst").exists()
        assert (api_dir / "test_package.rst").exists()

        # Check content
        module_content = (api_dir / "test_module.rst").read_text()
        assert "test_module module" in module_content


class TestSphinxBuild:
    """Test Sphinx build functionality."""

    @pytest.fixture
    def mock_project_structure(self) -> ProjectStructure:
        """Create mock project structure."""
        return ProjectStructure(
            project_name="mock_project",
            root_path=Path("/mock"),
            modules=[
                ModuleInfo(
                    name="mock_module",
                    file_path=Path("/mock/mock_module.py"),
                    docstring="Mock module",
                    is_package=False,
                    package_path="",
                )
            ],
        )

    @pytest.fixture
    def sphinx_project_with_structure(
        self, mock_project_structure: ProjectStructure, tmp_path: Path
    ) -> SphinxProject:
        """Create SphinxProject with project structure."""
        config = Config()
        project = SphinxProject(mock_project_structure, config)
        project.create_project_structure(tmp_path)
        return project

    @patch("subprocess.run")
    def test_build_documentation_success(
        self, mock_subprocess: MagicMock, sphinx_project_with_structure: SphinxProject
    ) -> None:
        """Test successful documentation build."""
        # Mock successful subprocess call
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Build finished successfully"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        result = sphinx_project_with_structure.build_documentation()

        assert result["success"] is True
        assert "output_dir" in result
        assert "source_dir" in result
        assert "build_dir" in result
        assert result["stdout"] == "Build finished successfully"

        # Check that subprocess was called with correct arguments
        mock_subprocess.assert_called_once()
        args = mock_subprocess.call_args[0][0]
        assert args[0] == "sphinx-build"
        assert "-b" in args and "html" in args
        assert "-W" in args  # Warnings as errors
        assert "-q" in args  # Quiet mode

    @patch("subprocess.run")
    def test_build_documentation_failure(
        self, mock_subprocess: MagicMock, sphinx_project_with_structure: SphinxProject
    ) -> None:
        """Test documentation build failure."""
        # Mock failed subprocess call
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "Build output"
        mock_result.stderr = "Build error"
        mock_subprocess.return_value = mock_result

        with pytest.raises(SphinxGenerationError, match="Sphinx build failed"):
            sphinx_project_with_structure.build_documentation()

    @patch("subprocess.run")
    def test_build_documentation_timeout(
        self, mock_subprocess: MagicMock, sphinx_project_with_structure: SphinxProject
    ) -> None:
        """Test documentation build timeout."""
        mock_subprocess.side_effect = subprocess.TimeoutExpired("sphinx-build", 300)

        with pytest.raises(SphinxGenerationError, match="timed out"):
            sphinx_project_with_structure.build_documentation()

    @patch("subprocess.run")
    def test_build_documentation_command_not_found(
        self, mock_subprocess: MagicMock, sphinx_project_with_structure: SphinxProject
    ) -> None:
        """Test handling of missing sphinx-build command."""
        mock_subprocess.side_effect = FileNotFoundError("sphinx-build not found")

        with pytest.raises(SphinxGenerationError, match="sphinx-build command not found"):
            sphinx_project_with_structure.build_documentation()

    def test_build_documentation_no_structure(self) -> None:
        """Test build failure when project structure not created."""
        config = Config()
        structure = ProjectStructure(project_name="test", root_path=Path("/test"), modules=[])
        project = SphinxProject(structure, config)

        with pytest.raises(SphinxGenerationError, match="Project structure not created"):
            project.build_documentation()


class TestSphinxDocumentationGenerator:
    """Test SphinxDocumentationGenerator class."""

    @pytest.fixture
    def generator(self) -> SphinxDocumentationGenerator:
        """Create generator instance."""
        config = Config()
        return SphinxDocumentationGenerator(config)

    @pytest.fixture
    def sample_structure(self) -> ProjectStructure:
        """Create sample project structure."""
        return ProjectStructure(
            project_name="sample_project",
            root_path=Path("/sample"),
            modules=[
                ModuleInfo(
                    name="sample_module",
                    file_path=Path("/sample/sample_module.py"),
                    docstring="Sample module",
                    is_package=False,
                    package_path="",
                )
            ],
        )

    @patch("docs_generator.sphinx_integration.temporary_directory")
    @patch("docs_generator.sphinx_integration.SphinxProject")
    def test_generate_documentation_success(
        self,
        mock_sphinx_project_class: MagicMock,
        mock_temp_dir: MagicMock,
        generator: SphinxDocumentationGenerator,
        sample_structure: ProjectStructure,
        tmp_path: Path,
    ) -> None:
        """Test successful documentation generation."""
        # Mock temporary directory
        mock_temp_dir.return_value.__enter__.return_value = tmp_path

        # Mock SphinxProject
        mock_project = MagicMock()
        mock_project.build_documentation.return_value = {
            "success": True,
            "output_dir": str(tmp_path / "output"),
        }
        mock_sphinx_project_class.return_value = mock_project

        result = generator.generate_documentation(sample_structure)

        assert result["project_name"] == "sample_project"
        assert "temp_dir" in result
        assert "build_result" in result
        assert result["modules_processed"] == 1

        # Verify SphinxProject was created and used correctly
        mock_sphinx_project_class.assert_called_once()
        mock_project.create_project_structure.assert_called_once()
        mock_project.build_documentation.assert_called_once()

    @patch("docs_generator.sphinx_integration.temporary_directory")
    def test_generate_documentation_failure(
        self,
        mock_temp_dir: MagicMock,
        generator: SphinxDocumentationGenerator,
        sample_structure: ProjectStructure,
    ) -> None:
        """Test documentation generation failure."""
        # Mock temporary directory to raise exception
        mock_temp_dir.side_effect = Exception("Temporary directory creation failed")

        with pytest.raises(SphinxGenerationError, match="Documentation generation failed"):
            generator.generate_documentation(sample_structure)

    @patch("subprocess.run")
    def test_validate_sphinx_installation_success(
        self, mock_subprocess: MagicMock, generator: SphinxDocumentationGenerator
    ) -> None:
        """Test successful Sphinx installation validation."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Sphinx (sphinx-build) 4.0.0"
        mock_subprocess.return_value = mock_result

        assert generator.validate_sphinx_installation() is True
        mock_subprocess.assert_called_once_with(
            ["sphinx-build", "--version"], capture_output=True, text=True, timeout=10
        )

    @patch("subprocess.run")
    def test_validate_sphinx_installation_failure(
        self, mock_subprocess: MagicMock, generator: SphinxDocumentationGenerator
    ) -> None:
        """Test Sphinx installation validation failure."""
        mock_subprocess.side_effect = FileNotFoundError("Command not found")

        assert generator.validate_sphinx_installation() is False

    @patch("subprocess.run")
    def test_validate_sphinx_installation_error(
        self, mock_subprocess: MagicMock, generator: SphinxDocumentationGenerator
    ) -> None:
        """Test Sphinx validation with command error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Command failed"
        mock_subprocess.return_value = mock_result

        assert generator.validate_sphinx_installation() is False


class TestConvenienceFunction:
    """Test the convenience function."""

    @patch("docs_generator.sphinx_integration.SphinxDocumentationGenerator")
    def test_generate_sphinx_documentation(self, mock_generator_class: MagicMock) -> None:
        """Test the convenience function."""
        # Mock generator
        mock_generator = MagicMock()
        mock_generator.generate_documentation.return_value = {"success": True}
        mock_generator_class.return_value = mock_generator

        # Create test data
        config = Config()
        structure = ProjectStructure(project_name="test", root_path=Path("/test"), modules=[])

        result = generate_sphinx_documentation(structure, config)

        assert result["success"] is True
        mock_generator_class.assert_called_once_with(config)
        mock_generator.generate_documentation.assert_called_once_with(structure)
