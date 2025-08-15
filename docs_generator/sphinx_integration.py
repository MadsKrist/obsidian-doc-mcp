"""Sphinx integration for Python documentation generation.

This module provides functionality to generate documentation using Sphinx,
including dynamic configuration generation, project structure creation,
and build process management.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any

from config.project_config import Config
from docs_generator.analyzer import ProjectStructure
from utils.file_utils import (
    ensure_directory,
    temporary_directory,
    write_file_atomically,
)

logger = logging.getLogger(__name__)


class SphinxGenerationError(Exception):
    """Raised when Sphinx documentation generation fails."""

    pass


class SphinxProject:
    """Represents a Sphinx documentation project."""

    def __init__(self, project_structure: ProjectStructure, config: Config) -> None:
        """Initialize Sphinx project.

        Args:
            project_structure: Analyzed Python project structure
            config: Configuration settings
        """
        self.project_structure = project_structure
        self.config = config
        self.project_path: Path | None = None
        self.build_path: Path | None = None
        self.source_path: Path | None = None

    def generate_conf_py(self) -> str:
        """Generate Sphinx conf.py configuration content.

        Returns:
            Generated conf.py content as string
        """
        project_name = self.project_structure.project_name
        version = "1.0.0"  # Default version, could be extracted from setup.py/pyproject.toml

        # Base configuration
        conf_content = f'''"""Configuration file for Sphinx documentation."""

import os
import sys

# Add the project root to Python path for autodoc
sys.path.insert(0, os.path.abspath("../../{project_name}"))

# Project information
project = "{project_name}"
copyright = "2024, {project_name} Team"
author = "{project_name} Team"
version = "{version}"
release = "{version}"

# Extensions
extensions = [
'''

        # Add configured extensions
        for extension in self.config.sphinx.extensions:
            conf_content += f'    "{extension}",\n'

        conf_content += """]

# Extension configurations
autodoc_default_flags = ['members', 'undoc-members', 'show-inheritance']
autodoc_member_order = 'bysource'

# Napoleon settings (for Google/NumPy style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True

# Theme configuration
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

# Output file settings
html_show_sourcelink = True
html_show_sphinx = True
html_show_copyright = True

# Source settings
source_suffix = '.rst'
master_doc = 'index'

# Exclude patterns
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# Code highlighting
pygments_style = 'sphinx'

# Add any paths that contain templates here
templates_path = ['_templates']

# Options for HTML output
html_theme_options = {
    'collapse_navigation': False,
    'sticky_navigation': True,
    'navigation_depth': 4,
    'includehidden': True,
    'titles_only': False
}
"""

        return conf_content

    def generate_index_rst(self) -> str:
        """Generate main index.rst file content.

        Returns:
            Generated index.rst content
        """
        project_name = self.project_structure.project_name
        title_underline = "=" * len(f"{project_name} Documentation")

        index_content = f"""{project_name} Documentation
{title_underline}

Welcome to the {project_name} documentation. This documentation is automatically
generated from the Python source code using Sphinx.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   modules
   api/modules

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
"""

        return index_content

    def generate_modules_rst(self) -> str:
        """Generate modules.rst file with module listings.

        Returns:
            Generated modules.rst content
        """
        project_name = self.project_structure.project_name

        modules_content = f"""API Reference
=============

This section contains the complete API reference for {project_name}.

.. toctree::
   :maxdepth: 4

"""

        # Add each package/module
        packages = set()
        for module in self.project_structure.modules:
            if module.package_path:
                # This is part of a package
                top_package = module.package_path.split(".")[0]
                packages.add(top_package)
            else:
                # This is a standalone module
                if not module.name.startswith("_"):  # Skip private modules
                    modules_content += f"   {module.name}\n"

        # Add packages
        for package in sorted(packages):
            modules_content += f"   {package}\n"

        return modules_content

    def generate_module_rst_files(self, output_dir: Path) -> None:
        """Generate individual .rst files for modules and packages.

        Args:
            output_dir: Directory to write .rst files to
        """
        api_dir = output_dir / "api"
        ensure_directory(api_dir)

        # Generate rst files for each module
        processed_packages = set()

        for module in self.project_structure.modules:
            if module.name.startswith("_"):
                continue  # Skip private modules

            # Determine the rst file name and content
            if module.is_package:
                # This is a package __init__.py
                package_name = module.package_path or module.name
                if package_name in processed_packages:
                    continue
                processed_packages.add(package_name)

                rst_filename = f"{package_name}.rst"
                rst_content = self._generate_package_rst(package_name)
            else:
                # This is a regular module
                rst_filename = f"{module.name}.rst"
                rst_content = self._generate_module_rst(module.name)

            rst_path = api_dir / rst_filename
            write_file_atomically(rst_path, rst_content)

    def _generate_package_rst(self, package_name: str) -> str:
        """Generate RST content for a package.

        Args:
            package_name: Name of the package

        Returns:
            RST content for the package
        """
        title = f"{package_name} package"
        title_underline = "=" * len(title)

        content = f"""{title}
{title_underline}

.. automodule:: {package_name}
   :members:
   :undoc-members:
   :show-inheritance:

Submodules
----------

"""

        # Find all modules in this package
        package_modules = []
        for module in self.project_structure.modules:
            if module.package_path == package_name and not module.is_package:
                package_modules.append(module.name)

        # Add submodule sections
        for module_name in sorted(package_modules):
            module_title = f"{module_name} module"
            module_underline = "-" * len(module_title)
            content += f"""
{module_title}
{module_underline}

.. automodule:: {module_name}
   :members:
   :undoc-members:
   :show-inheritance:
"""

        return content

    def _generate_module_rst(self, module_name: str) -> str:
        """Generate RST content for a module.

        Args:
            module_name: Name of the module

        Returns:
            RST content for the module
        """
        title = f"{module_name} module"
        title_underline = "=" * len(title)

        content = f"""{title}
{title_underline}

.. automodule:: {module_name}
   :members:
   :undoc-members:
   :show-inheritance:
"""

        return content

    def create_project_structure(self, temp_dir: Path) -> None:
        """Create the Sphinx project structure in a temporary directory.

        Args:
            temp_dir: Temporary directory to create project in
        """
        self.project_path = temp_dir / "sphinx_project"
        self.source_path = self.project_path / "source"
        self.build_path = self.project_path / "_build"

        # Create directory structure
        ensure_directory(self.source_path)
        ensure_directory(self.build_path)
        ensure_directory(self.source_path / "_static")
        ensure_directory(self.source_path / "_templates")

        # Generate and write configuration files
        conf_py_content = self.generate_conf_py()
        write_file_atomically(self.source_path / "conf.py", conf_py_content)

        index_rst_content = self.generate_index_rst()
        write_file_atomically(self.source_path / "index.rst", index_rst_content)

        modules_rst_content = self.generate_modules_rst()
        write_file_atomically(self.source_path / "modules.rst", modules_rst_content)

        # Generate individual module RST files
        self.generate_module_rst_files(self.source_path)

        # Create a simple custom.css file
        css_content = """/* Custom CSS for documentation */
.wy-nav-content-wrap {
    background: #fcfcfc;
}

.rst-content .highlight > pre {
    background-color: #f8f8f8;
}
"""
        ensure_directory(self.source_path / "_static")
        write_file_atomically(self.source_path / "_static" / "custom.css", css_content)

    def build_documentation(self) -> dict[str, Any]:
        """Build the Sphinx documentation.

        Returns:
            Dictionary containing build results and metadata

        Raises:
            SphinxGenerationError: If build fails
        """
        if not self.project_path or not self.source_path or not self.build_path:
            raise SphinxGenerationError("Project structure not created")

        html_output_dir = self.build_path / "html"
        ensure_directory(html_output_dir)

        # Build command
        cmd = [
            "sphinx-build",
            "-b",
            "html",  # HTML builder
            "-W",  # Treat warnings as errors
            "-q",  # Quiet mode
            str(self.source_path),  # Source directory
            str(html_output_dir),  # Output directory
        ]

        try:
            logger.info(f"Building Sphinx documentation with command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                check=False,
            )

            if result.returncode != 0:
                error_msg = f"Sphinx build failed with return code {result.returncode}"
                if result.stderr:
                    error_msg += f"\nStderr: {result.stderr}"
                if result.stdout:
                    error_msg += f"\nStdout: {result.stdout}"

                logger.error(error_msg)
                raise SphinxGenerationError(error_msg)

            # Successful build
            logger.info("Sphinx documentation built successfully")

            return {
                "success": True,
                "output_dir": str(html_output_dir),
                "source_dir": str(self.source_path),
                "build_dir": str(self.build_path),
                "stdout": result.stdout,
                "stderr": result.stderr,
                "files_generated": list(html_output_dir.rglob("*.html")),
            }

        except subprocess.TimeoutExpired as e:
            raise SphinxGenerationError("Sphinx build timed out after 5 minutes") from e
        except FileNotFoundError as e:
            raise SphinxGenerationError(
                "sphinx-build command not found. Please install Sphinx."
            ) from e
        except Exception as e:
            raise SphinxGenerationError(f"Unexpected error during Sphinx build: {e}") from e


class SphinxDocumentationGenerator:
    """Main class for generating Sphinx documentation."""

    def __init__(self, config: Config) -> None:
        """Initialize the Sphinx documentation generator.

        Args:
            config: Configuration settings
        """
        self.config = config

    def generate_documentation(self, project_structure: ProjectStructure) -> dict[str, Any]:
        """Generate complete Sphinx documentation for a project.

        Args:
            project_structure: Analyzed Python project structure

        Returns:
            Dictionary containing generation results and metadata

        Raises:
            SphinxGenerationError: If documentation generation fails
        """
        try:
            with temporary_directory(prefix="sphinx_docs_") as temp_dir:
                logger.info(f"Generating Sphinx documentation in {temp_dir}")

                # Create Sphinx project
                sphinx_project = SphinxProject(project_structure, self.config)
                sphinx_project.create_project_structure(temp_dir)

                # Build documentation
                build_result = sphinx_project.build_documentation()

                # Copy results to permanent location if needed
                # For now, we return the temporary results
                return {
                    "project_name": project_structure.project_name,
                    "temp_dir": str(temp_dir),
                    "sphinx_project": sphinx_project,
                    "build_result": build_result,
                    "modules_processed": len(project_structure.modules),
                    "packages_processed": len(project_structure.packages),
                }

        except Exception as e:
            logger.exception("Failed to generate Sphinx documentation")
            raise SphinxGenerationError(f"Documentation generation failed: {e}") from e

    def validate_sphinx_installation(self) -> bool:
        """Check if Sphinx is properly installed and available.

        Returns:
            True if Sphinx is available, False otherwise
        """
        try:
            result = subprocess.run(
                ["sphinx-build", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"Sphinx is available: {result.stdout.strip()}")
                return True
            else:
                logger.warning(f"Sphinx check failed: {result.stderr}")
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Sphinx not available: {e}")
            return False


def generate_sphinx_documentation(
    project_structure: ProjectStructure, config: Config
) -> dict[str, Any]:
    """Convenience function to generate Sphinx documentation.

    Args:
        project_structure: Analyzed Python project structure
        config: Configuration settings

    Returns:
        Dictionary containing generation results

    Raises:
        SphinxGenerationError: If generation fails
    """
    generator = SphinxDocumentationGenerator(config)
    return generator.generate_documentation(project_structure)
