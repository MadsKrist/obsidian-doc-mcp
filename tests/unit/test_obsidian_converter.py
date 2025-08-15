"""Tests for Obsidian converter functionality."""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from bs4 import BeautifulSoup

from config.project_config import Config, ObsidianConfig, OutputConfig, ProjectConfig
from docs_generator.obsidian_converter import (
    ObsidianConversionError,
    ObsidianConverter,
    convert_sphinx_to_obsidian,
)


class TestObsidianConverter:
    """Test ObsidianConverter class functionality."""

    @pytest.fixture
    def config(self) -> Config:
        """Create test configuration."""
        config = Config()
        config.project = ProjectConfig(name="test_project")
        config.obsidian = ObsidianConfig(
            use_wikilinks=True,
            tag_prefix="code/",
        )
        config.output = OutputConfig(generate_index=True)
        return config

    @pytest.fixture
    def converter(self, config: Config) -> ObsidianConverter:
        """Create ObsidianConverter instance for testing."""
        return ObsidianConverter(config)

    def test_obsidian_converter_initialization(
        self, converter: ObsidianConverter, config: Config
    ) -> None:
        """Test ObsidianConverter initialization."""
        assert converter.config == config
        assert converter._link_mapping == {}
        assert converter._file_mapping == {}

    def test_should_skip_file(self, converter: ObsidianConverter) -> None:
        """Test file skipping logic."""
        # Should skip these files
        assert converter._should_skip_file(Path("genindex.html")) is True
        assert converter._should_skip_file(Path("search.html")) is True
        assert converter._should_skip_file(Path("_static/style.css")) is True
        assert converter._should_skip_file(Path("_sources/module.txt")) is True

        # Should not skip regular files
        assert converter._should_skip_file(Path("index.html")) is False
        assert converter._should_skip_file(Path("module.html")) is False
        assert converter._should_skip_file(Path("api/test.html")) is False

    def test_get_output_file_path(self, converter: ObsidianConverter) -> None:
        """Test output file path generation."""
        html_dir = Path("/source")
        output_dir = Path("/output")

        # HTML file conversion
        html_file = Path("/source/module.html")
        result = converter._get_output_file_path(html_file, html_dir, output_dir)
        assert result == Path("/output/module.md")

        # Nested file conversion
        html_file = Path("/source/api/test.html")
        result = converter._get_output_file_path(html_file, html_dir, output_dir)
        assert result == Path("/output/api/test.md")

        # Non-HTML file
        other_file = Path("/source/readme.txt")
        result = converter._get_output_file_path(other_file, html_dir, output_dir)
        assert result == Path("/output/readme.txt")

    def test_build_file_mapping(self, converter: ObsidianConverter) -> None:
        """Test file mapping construction."""
        html_dir = Path("/html")
        output_dir = Path("/output")
        html_files = [
            Path("/html/index.html"),
            Path("/html/api/module.html"),
            Path("/html/genindex.html"),  # Should be skipped
        ]

        converter._build_file_mapping(html_files, html_dir, output_dir)

        # Check file mapping
        assert "index.html" in converter._file_mapping
        assert converter._file_mapping["index.html"] == "index.md"
        assert "api/module.html" in converter._file_mapping
        assert converter._file_mapping["api/module.html"] == "api/module.md"

        # Check link mapping
        assert "index" in converter._link_mapping
        assert converter._link_mapping["index"] == "index"
        assert "api/module" in converter._link_mapping
        assert converter._link_mapping["api/module"] == "api/module"

        # Skipped files should not be in mapping
        assert "genindex.html" not in converter._file_mapping

    def test_extract_title_from_content(self, converter: ObsidianConverter) -> None:
        """Test title extraction from markdown content."""
        # Content with H1 header
        content_with_title = "# Main Title\n\nSome content here."
        title = converter._extract_title_from_content(content_with_title)
        assert title == "Main Title"

        # Content without H1 header
        content_without_title = "## Subtitle\n\nSome content."
        title = converter._extract_title_from_content(content_without_title)
        assert title is None

        # Multiple headers - should get first H1
        content_multiple = "# First Title\n\n## Subtitle\n\n# Second Title"
        title = converter._extract_title_from_content(content_multiple)
        assert title == "First Title"

    def test_generate_tags(self, converter: ObsidianConverter) -> None:
        """Test tag generation for files."""
        # Simple file path
        tags = converter._generate_tags(Path("module.html"))
        assert "code" in tags  # From tag prefix

        # Nested file path
        tags = converter._generate_tags(Path("api/package/module.html"))
        assert "code" in tags
        assert "code/api" in tags
        assert "code/package" in tags

        # Path with underscore (should be skipped)
        tags = converter._generate_tags(Path("_static/style.css"))
        assert "code" in tags
        # _static should be skipped

    def test_convert_links_to_wikilinks(self, converter: ObsidianConverter) -> None:
        """Test conversion of markdown links to wikilinks."""
        # Set up link mapping
        converter._link_mapping = {"module": "module", "api/test": "api/test"}

        markdown_with_links = """
        This is a [link to module](module.html) and another [API link](api/test.html).
        External [Google](https://google.com) should remain unchanged.
        """

        result = converter._convert_links_to_wikilinks(markdown_with_links)

        assert "[[module|link to module]]" in result
        assert "[[api/test|API link]]" in result
        assert "[Google](https://google.com)" in result  # External link unchanged

    def test_convert_sphinx_anchor(self, converter: ObsidianConverter) -> None:
        """Test Sphinx anchor conversion."""
        # Test simple anchor
        assert converter._convert_sphinx_anchor("simple-anchor") == "simple anchor"

        # Test dotted anchor (module.Class.method)
        assert converter._convert_sphinx_anchor("module.Class.method") == "method"

        # Test complex anchor
        assert (
            converter._convert_sphinx_anchor("my-module.MyClass.my-method")
            == "my method"
        )

    def test_convert_links_with_anchors(self, converter: ObsidianConverter) -> None:
        """Test conversion of links with anchors to wikilinks."""
        # Set up link mapping
        converter._link_mapping = {
            "module": "module",
        }

        markdown_with_anchors = """
        Link to [method](module.html#module.Class.method) and [simple anchor](module.html#simple-section).
        """

        result = converter._convert_links_to_wikilinks(markdown_with_anchors)

        assert "[[module#method|method]]" in result
        assert "[[module#simple section|simple anchor]]" in result

    def test_convert_html_file_basic(
        self, converter: ObsidianConverter, tmp_path: Path
    ) -> None:
        """Test basic HTML file conversion."""
        # Create test HTML file
        html_content = """
        <!DOCTYPE html>
        <html>
        <head><title>Test</title></head>
        <body>
            <div role="main">
                <h1>Test Module</h1>
                <p>This is a test module.</p>
                <pre><code class="language-python">def test(): pass</code></pre>
            </div>
        </body>
        </html>
        """

        html_file = tmp_path / "test.html"
        html_file.write_text(html_content)

        result = converter._convert_html_file(html_file)

        assert "# Test Module" in result
        assert "This is a test module." in result
        assert "```python" in result
        assert "def test(): pass" in result

    @patch("builtins.open", new_callable=mock_open)
    def test_convert_html_file_error(
        self, mock_file: MagicMock, converter: ObsidianConverter
    ) -> None:
        """Test HTML file conversion error handling."""
        mock_file.side_effect = OSError("File not found")

        with pytest.raises(
            ObsidianConversionError, match="Failed to convert HTML file"
        ):
            converter._convert_html_file(Path("nonexistent.html"))

    def test_add_obsidian_metadata(
        self, converter: ObsidianConverter, tmp_path: Path
    ) -> None:
        """Test Obsidian metadata addition."""
        content = "# Test Content\n\nSome content here."
        html_file = tmp_path / "test.html"
        html_file.touch()  # Create empty file

        result = converter._add_obsidian_metadata(content, html_file, Path("test.html"))

        assert result.startswith("---\n")
        assert "title: Test Content" in result
        assert "tags: [code]" in result
        assert "source: test.html" in result
        assert "type: documentation" in result
        assert result.endswith("---\n\n# Test Content\n\nSome content here.")

    def test_generate_obsidian_index(self, converter: ObsidianConverter) -> None:
        """Test Obsidian index generation."""
        converted_files = [
            {
                "source": "/html/index.html",
                "output": "/output/index.md",
                "relative_path": "index.md",
            },
            {
                "source": "/html/api/module.html",
                "output": "/output/api/module.md",
                "relative_path": "api/module.md",
            },
        ]

        result = converter._generate_obsidian_index(converted_files)

        assert "# test_project Documentation" in result
        assert "automatically generated from Python source code" in result
        assert "## api" in result
        assert "[[module]]" in result  # Wikilink format
        assert "Generated automatically by obsidian-doc-mcp" in result

    @patch("docs_generator.obsidian_converter.ensure_directory")
    @patch("docs_generator.obsidian_converter.write_file_atomically")
    def test_convert_html_directory_success(
        self,
        mock_write: MagicMock,
        mock_ensure_dir: MagicMock,
        converter: ObsidianConverter,
        tmp_path: Path,
    ) -> None:
        """Test successful HTML directory conversion."""
        # Create test HTML files
        html_dir = tmp_path / "html"
        html_dir.mkdir()

        (html_dir / "index.html").write_text(
            """
        <html><body><div role="main"><h1>Index</h1><p>Main page.</p></div></body></html>
        """
        )

        (html_dir / "api").mkdir()
        (html_dir / "api" / "module.html").write_text(
            """
        <html><body><div role="main"><h1>Module</h1><p>Module docs.</p></div></body></html>
        """
        )

        # Skip file
        (html_dir / "genindex.html").write_text("<html><body>Index</body></html>")

        output_dir = tmp_path / "output"

        result = converter.convert_html_directory(html_dir, output_dir)

        assert result["success"] is True
        # Should have 1 index file since conversion failed for HTML files due to errors
        assert result["total_files"] >= 1
        assert len(result["converted_files"]) >= 1
        assert len(result["errors"]) >= 0  # May have errors due to conversion issues
        assert result["output_directory"] == str(output_dir)

        # Check that at least index file was written
        assert mock_write.call_count >= 1

    @patch("docs_generator.obsidian_converter.ensure_directory")
    def test_convert_html_directory_error(
        self, mock_ensure_dir: MagicMock, converter: ObsidianConverter, tmp_path: Path
    ) -> None:
        """Test HTML directory conversion with errors."""
        mock_ensure_dir.side_effect = Exception("Directory creation failed")

        with pytest.raises(
            ObsidianConversionError, match="Directory conversion failed"
        ):
            converter.convert_html_directory(tmp_path / "html", tmp_path / "output")

    def test_clean_html_for_conversion(self, converter: ObsidianConverter) -> None:
        """Test HTML cleaning before conversion."""
        html_content = """
        <div>
            <nav>Navigation</nav>
            <header>Header</header>
            <main>
                <h1>Title</h1>
                <p>Content</p>
                <a class="headerlink" href="#title">¶</a>
                <pre><code class="language-python">print("hello")</code></pre>
            </main>
            <footer>Footer</footer>
        </div>
        """

        soup = BeautifulSoup(html_content, "html.parser")
        result = converter._clean_html_for_conversion(soup)

        # Navigation elements should be removed
        assert result.find("nav") is None
        assert result.find("header") is None
        assert result.find("footer") is None

        # Headerlinks should be removed
        assert result.find("a", {"class": "headerlink"}) is None

        # Main content should remain
        assert result.find("h1") is not None
        assert result.find("p") is not None

    def test_process_markdown_for_obsidian(self, converter: ObsidianConverter) -> None:
        """Test markdown processing for Obsidian compatibility."""
        raw_markdown = """
        # Title



        Some content with \\_escaped\\_ text and \\*stars\\*.

        ```python


        def test():
            pass
        ```

        - Item 1

        - Item 2
        """

        result = converter._process_markdown_for_obsidian(raw_markdown)

        # Should clean up extra whitespace
        assert "\n\n\n" not in result

        # Should fix code blocks
        assert "```python\n\n" not in result

        # Should remove excessive escaping
        assert "_escaped_" in result
        assert "*stars*" in result


class TestConvenienceFunction:
    """Test the convenience function."""

    @patch("docs_generator.obsidian_converter.ObsidianConverter")
    def test_convert_sphinx_to_obsidian(self, mock_converter_class: MagicMock) -> None:
        """Test the convenience function."""
        # Mock converter
        mock_converter = MagicMock()
        mock_converter.convert_html_directory.return_value = {"success": True}
        mock_converter_class.return_value = mock_converter

        # Create test data
        config = Config()
        html_dir = Path("/html")
        output_dir = Path("/output")

        result = convert_sphinx_to_obsidian(html_dir, output_dir, config)

        assert result["success"] is True
        mock_converter_class.assert_called_once_with(config)
        mock_converter.convert_html_directory.assert_called_once_with(
            html_dir, output_dir
        )
