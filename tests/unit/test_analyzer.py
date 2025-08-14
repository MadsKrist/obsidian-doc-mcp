"""Unit tests for the Python project analyzer.

Tests the functionality of analyzing Python projects and extracting
documentation information using AST parsing.
"""

from pathlib import Path

import pytest

from docs_generator.analyzer import (
    FunctionInfo,
    ProjectAnalysisError,
    ProjectStructure,
    PythonProjectAnalyzer,
    analyze_python_project,
)


class TestPythonProjectAnalyzer:
    """Tests for PythonProjectAnalyzer class."""

    def test_init_with_valid_path(self, sample_project_structure: Path) -> None:
        """Test analyzer initialization with valid project path."""
        analyzer = PythonProjectAnalyzer(sample_project_structure)
        assert analyzer.project_path == sample_project_structure

    def test_init_with_invalid_path(self, temp_dir: Path) -> None:
        """Test analyzer initialization with invalid project path."""
        invalid_path = temp_dir / "nonexistent"
        with pytest.raises(ProjectAnalysisError, match="Project path does not exist"):
            PythonProjectAnalyzer(invalid_path)

    def test_discover_python_files(
        self, analyzer_for_project: PythonProjectAnalyzer
    ) -> None:
        """Test discovery of Python files in project."""
        files = analyzer_for_project._discover_python_files([])

        # Should find __init__.py, main.py, and utils.py
        assert len(files) >= 3
        file_names = [f.name for f in files]
        assert "__init__.py" in file_names
        assert "main.py" in file_names
        assert "utils.py" in file_names

    def test_discover_python_files_with_exclusions(
        self, analyzer_for_project: PythonProjectAnalyzer
    ) -> None:
        """Test file discovery with exclusion patterns."""
        files = analyzer_for_project._discover_python_files(["main.py"])

        file_names = [f.name for f in files]
        assert "main.py" not in file_names
        assert "__init__.py" in file_names

    def test_analyze_file_valid(self, sample_python_file: Path) -> None:
        """Test analyzing a valid Python file."""
        analyzer = PythonProjectAnalyzer(sample_python_file.parent)
        module_info = analyzer._analyze_file(sample_python_file)

        assert module_info.name == "sample"
        assert module_info.file_path == sample_python_file
        assert module_info.docstring is not None
        assert "Sample module for testing" in module_info.docstring

        # Check that classes were found
        assert len(module_info.classes) >= 1
        sample_class = next(
            cls for cls in module_info.classes if cls.name == "SampleClass"
        )
        assert sample_class.docstring is not None
        assert "A sample class for testing" in sample_class.docstring

        # Check that functions were found
        assert len(module_info.functions) >= 2
        function_names = [func.name for func in module_info.functions]
        assert "sample_function" in function_names
        assert "async_sample_function" in function_names

    def test_analyze_file_syntax_error(self, temp_dir: Path) -> None:
        """Test analyzing file with syntax errors."""
        bad_file = temp_dir / "bad.py"
        bad_file.write_text("def invalid_syntax(\n")

        analyzer = PythonProjectAnalyzer(temp_dir)
        with pytest.raises(ProjectAnalysisError, match="Syntax error"):
            analyzer._analyze_file(bad_file)

    def test_analyze_project_success(
        self, analyzer_for_project: PythonProjectAnalyzer
    ) -> None:
        """Test successful project analysis."""
        structure = analyzer_for_project.analyze_project()

        assert isinstance(structure, ProjectStructure)
        assert structure.project_name == "sample_project"
        assert len(structure.modules) >= 3

        # Check that modules were analyzed (enhanced naming with full paths)
        module_names = [mod.name for mod in structure.modules]
        # Check for the expected module names in the enhanced format
        has_main = any("main" in name for name in module_names)
        has_package = any(
            "sample_package" in name and "main" not in name for name in module_names
        )
        assert has_main or has_package

    def test_analyze_project_with_exclusions(
        self, analyzer_for_project: PythonProjectAnalyzer
    ) -> None:
        """Test project analysis with exclusion patterns."""
        structure = analyzer_for_project.analyze_project(exclude_patterns=["utils.py"])

        module_names = [mod.name for mod in structure.modules]
        # Check that utils is not in any of the module names
        assert not any("utils" in name for name in module_names)


class TestModuleVisitor:
    """Tests for the AST visitor functionality."""

    def test_extract_function_info(self, sample_python_file: Path) -> None:
        """Test extraction of function information."""
        analyzer = PythonProjectAnalyzer(sample_python_file.parent)
        module_info = analyzer._analyze_file(sample_python_file)

        # Find the sample_function
        sample_func = next(
            func for func in module_info.functions if func.name == "sample_function"
        )

        assert isinstance(sample_func, FunctionInfo)
        assert not sample_func.is_async
        assert "items" in sample_func.parameters
        assert "default" in sample_func.parameters
        assert sample_func.docstring is not None
        assert "A sample function for testing" in sample_func.docstring

    def test_extract_async_function_info(self, sample_python_file: Path) -> None:
        """Test extraction of async function information."""
        analyzer = PythonProjectAnalyzer(sample_python_file.parent)
        module_info = analyzer._analyze_file(sample_python_file)

        # Find the async_sample_function
        async_func = next(
            func
            for func in module_info.functions
            if func.name == "async_sample_function"
        )

        assert isinstance(async_func, FunctionInfo)
        assert async_func.is_async
        assert "delay" in async_func.parameters
        assert async_func.docstring is not None
        assert "An async function for testing" in async_func.docstring

    def test_extract_class_info(self, sample_python_file: Path) -> None:
        """Test extraction of class information."""
        analyzer = PythonProjectAnalyzer(sample_python_file.parent)
        module_info = analyzer._analyze_file(sample_python_file)

        # Find the SampleClass
        sample_class = next(
            cls for cls in module_info.classes if cls.name == "SampleClass"
        )

        assert (
            sample_class.docstring
            and "A sample class for testing" in sample_class.docstring
        )
        assert len(sample_class.methods) >= 2  # __init__ and public_method

        # Check method extraction
        method_names = [method.name for method in sample_class.methods]
        assert "__init__" in method_names
        assert "public_method" in method_names

    def test_extract_imports(self, sample_python_file: Path) -> None:
        """Test extraction of import statements."""
        analyzer = PythonProjectAnalyzer(sample_python_file.parent)
        module_info = analyzer._analyze_file(sample_python_file)

        # Should have imports from typing
        assert "typing" in module_info.imports


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_analyze_python_project_function(
        self, sample_project_structure: Path
    ) -> None:
        """Test the analyze_python_project utility function."""
        structure = analyze_python_project(sample_project_structure)

        assert isinstance(structure, ProjectStructure)
        assert structure.project_name == "sample_project"
        assert len(structure.modules) >= 1

    def test_analyze_python_project_invalid_path(self, temp_dir: Path) -> None:
        """Test the utility function with invalid path."""
        invalid_path = temp_dir / "nonexistent"

        with pytest.raises(ProjectAnalysisError):
            analyze_python_project(invalid_path)
