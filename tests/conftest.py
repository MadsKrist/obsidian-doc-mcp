"""Pytest configuration and shared fixtures.

This module provides common pytest fixtures and configuration
for testing the MCP Python documentation server.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from config.project_config import Config, ConfigManager
from docs_generator.analyzer import PythonProjectAnalyzer


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing.

    Yields:
        Path: Temporary directory path
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_python_file(temp_dir: Path) -> Path:
    """Create a sample Python file for testing.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path: Path to the created sample file
    """
    sample_code = '''"""Sample module for testing.

This is a sample Python module used for testing the documentation
generation functionality.
"""

from typing import List, Optional


class SampleClass:
    """A sample class for testing documentation generation.

    This class demonstrates various Python constructs that should
    be properly documented.
    """

    def __init__(self, name: str) -> None:
        """Initialize the sample class.

        Args:
            name: The name for this instance
        """
        self.name = name
        self._private_attr = "private"

    def public_method(self, value: int) -> str:
        """A public method for testing.

        Args:
            value: Some integer value

        Returns:
            str: A formatted string
        """
        return f"{self.name}: {value}"

    def _private_method(self) -> None:
        """A private method that should be excluded by default."""
        pass

    @property
    def name_property(self) -> str:
        """Get the name as a property."""
        return self.name


def sample_function(items: List[str], default: Optional[str] = None) -> int:
    """A sample function for testing.

    Args:
        items: List of string items
        default: Optional default value

    Returns:
        int: Number of items

    Raises:
        ValueError: If items is empty and no default provided
    """
    if not items and default is None:
        raise ValueError("Items cannot be empty without default")

    return len(items)


async def async_sample_function(delay: float = 1.0) -> str:
    """An async function for testing.

    Args:
        delay: Delay in seconds

    Returns:
        str: Success message
    """
    # In real code would use asyncio.sleep
    return f"Completed after {delay}s"


# Module-level constant
SAMPLE_CONSTANT = "test_value"
'''

    sample_file = temp_dir / "sample.py"
    sample_file.write_text(sample_code)
    return sample_file


@pytest.fixture
def sample_project_structure(temp_dir: Path) -> Path:
    """Create a sample Python project structure for testing.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path: Path to the project root
    """
    project_root = temp_dir / "sample_project"
    project_root.mkdir()

    # Create package structure
    src_dir = project_root / "src" / "sample_package"
    src_dir.mkdir(parents=True)

    # Create __init__.py
    init_file = src_dir / "__init__.py"
    init_file.write_text('"""Sample package for testing."""\n\n__version__ = "0.1.0"\n')

    # Create main module
    main_file = src_dir / "main.py"
    main_file.write_text(
        '''"""Main module of the sample package."""

def main() -> None:
    """Main entry point."""
    print("Hello from sample package!")


if __name__ == "__main__":
    main()
'''
    )

    # Create utils module
    utils_file = src_dir / "utils.py"
    utils_file.write_text(
        '''"""Utility functions for the sample package."""

from typing import Any, Dict


def helper_function(data: Dict[str, Any]) -> str:
    """Helper function for processing data.

    Args:
        data: Dictionary of data to process

    Returns:
        str: Processed data as string
    """
    return str(data)
'''
    )

    return project_root


@pytest.fixture
def config_manager() -> ConfigManager:
    """Create a ConfigManager instance for testing.

    Returns:
        ConfigManager: Configured manager instance
    """
    return ConfigManager()


@pytest.fixture
def default_config() -> Config:
    """Create a default configuration for testing.

    Returns:
        Config: Default configuration instance
    """
    return Config()


@pytest.fixture
def analyzer_for_project(sample_project_structure: Path) -> PythonProjectAnalyzer:
    """Create a PythonProjectAnalyzer for the sample project.

    Args:
        sample_project_structure: Sample project fixture

    Returns:
        PythonProjectAnalyzer: Analyzer instance
    """
    return PythonProjectAnalyzer(sample_project_structure)
