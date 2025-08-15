"""Obsidian converter for transforming Sphinx HTML to Obsidian markdown.

This module handles the conversion of Sphinx-generated HTML documentation
into Obsidian-compatible markdown format with wikilinks and proper structure.
"""

import logging
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md

from config.project_config import Config
from utils.file_utils import ensure_directory, write_file_atomically

logger = logging.getLogger(__name__)


class ObsidianConversionError(Exception):
    """Raised when Obsidian conversion fails."""

    pass


class ObsidianConverter:
    """Converts Sphinx HTML documentation to Obsidian markdown format."""

    def __init__(self, config: Config) -> None:
        """Initialize the Obsidian converter.

        Args:
            config: Configuration settings
        """
        self.config = config
        self._link_mapping: dict[str, str] = {}
        self._file_mapping: dict[str, str] = {}

    def convert_html_directory(
        self, html_dir: Path, output_dir: Path
    ) -> dict[str, Any]:
        """Convert a directory of HTML files to Obsidian markdown.

        Args:
            html_dir: Directory containing Sphinx HTML output
            output_dir: Directory to write Obsidian markdown files

        Returns:
            Dictionary containing conversion results

        Raises:
            ObsidianConversionError: If conversion fails
        """
        try:
            ensure_directory(output_dir)

            # First pass: collect all HTML files and create file mapping
            html_files = list(html_dir.rglob("*.html"))
            self._build_file_mapping(html_files, html_dir, output_dir)

            converted_files = []
            errors = []

            # Second pass: convert each HTML file
            for html_file in html_files:
                try:
                    relative_path = html_file.relative_to(html_dir)

                    # Skip certain files
                    if self._should_skip_file(relative_path):
                        continue

                    markdown_content = self._convert_html_file(html_file)
                    output_file = self._get_output_file_path(
                        html_file, html_dir, output_dir
                    )

                    # Add Obsidian metadata
                    final_content = self._add_obsidian_metadata(
                        markdown_content, html_file, relative_path
                    )

                    ensure_directory(output_file.parent)
                    write_file_atomically(output_file, final_content)

                    converted_files.append(
                        {
                            "source": str(html_file),
                            "output": str(output_file),
                            "relative_path": str(relative_path),
                        }
                    )

                except Exception as e:
                    error_msg = f"Failed to convert {html_file}: {e}"
                    logger.warning(error_msg)
                    errors.append(error_msg)

            # Create index file if configured
            if self.config.output.generate_index:
                index_content = self._generate_obsidian_index(converted_files)
                index_file = output_dir / "index.md"
                write_file_atomically(index_file, index_content)
                converted_files.append(
                    {
                        "source": "generated",
                        "output": str(index_file),
                        "relative_path": "index.md",
                    }
                )

            return {
                "success": True,
                "converted_files": converted_files,
                "total_files": len(converted_files),
                "errors": errors,
                "output_directory": str(output_dir),
            }

        except Exception as e:
            logger.exception("Failed to convert HTML directory")
            raise ObsidianConversionError(f"Directory conversion failed: {e}") from e

    def _build_file_mapping(
        self, html_files: list[Path], html_dir: Path, output_dir: Path
    ) -> None:
        """Build mapping of HTML files to markdown filenames.

        Args:
            html_files: List of HTML files to process
            html_dir: Source HTML directory
            output_dir: Output markdown directory
        """
        for html_file in html_files:
            relative_path = html_file.relative_to(html_dir)

            if self._should_skip_file(relative_path):
                continue

            output_file = self._get_output_file_path(html_file, html_dir, output_dir)

            # Create mapping from HTML path to markdown path
            html_key = str(relative_path).replace("\\", "/")
            markdown_key = str(output_file.relative_to(output_dir)).replace("\\", "/")

            self._file_mapping[html_key] = markdown_key

            # Also create mapping without .html extension for links
            if html_key.endswith(".html"):
                base_key = html_key[:-5]  # Remove .html
                self._link_mapping[base_key] = markdown_key[:-3]  # Remove .md

    def _should_skip_file(self, relative_path: Path) -> bool:
        """Check if a file should be skipped during conversion.

        Args:
            relative_path: Relative path from HTML root

        Returns:
            True if file should be skipped
        """
        skip_patterns = [
            "genindex.html",
            "search.html",
            "modindex.html",
            "_sources",
            "_static",
            ".doctree",
        ]

        path_str = str(relative_path)
        return any(pattern in path_str for pattern in skip_patterns)

    def _get_output_file_path(
        self, html_file: Path, html_dir: Path, output_dir: Path
    ) -> Path:
        """Get the output markdown file path for an HTML file.

        Args:
            html_file: Source HTML file
            html_dir: Source HTML directory
            output_dir: Output markdown directory

        Returns:
            Path to output markdown file
        """
        relative_path = html_file.relative_to(html_dir)

        # Convert to markdown extension
        if relative_path.suffix == ".html":
            markdown_name = relative_path.with_suffix(".md")
        else:
            markdown_name = relative_path

        return output_dir / markdown_name

    def _convert_html_file(self, html_file: Path) -> str:
        """Convert a single HTML file to markdown.

        Args:
            html_file: Path to HTML file

        Returns:
            Converted markdown content

        Raises:
            ObsidianConversionError: If conversion fails
        """
        try:
            with open(html_file, encoding="utf-8") as f:
                html_content = f.read()

            # Parse HTML
            soup = BeautifulSoup(html_content, "html.parser")

            # Extract main content (Sphinx typically uses div with role="main")
            main_content = soup.find("div", {"role": "main"})
            if not main_content:
                # Fallback to body content
                main_content = soup.find("body")
                if not main_content:
                    main_content = soup

            # Create new soup with just the main content if it's a tag
            if isinstance(main_content, Tag):
                content_soup = BeautifulSoup(str(main_content), "html.parser")
            else:
                content_soup = soup

            # Clean up HTML before conversion
            cleaned_html = self._clean_html_for_conversion(content_soup)

            # Convert to markdown
            markdown = md(
                str(cleaned_html),
                heading_style="atx",  # Use # style headers
                bullets="-",  # Use - for bullet lists
                strip=["script", "style"],  # Remove script and style tags
            )

            # Post-process markdown for Obsidian
            processed_markdown = self._process_markdown_for_obsidian(markdown)

            return processed_markdown

        except Exception as e:
            raise ObsidianConversionError(f"Failed to convert HTML file: {e}") from e

    def _clean_html_for_conversion(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Clean HTML content before markdown conversion.

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            Cleaned HTML content
        """
        # Remove navigation elements
        for element in soup.find_all(["nav", "header", "footer"]):
            element.decompose()

        # Remove Sphinx-specific elements
        for class_name in [
            "headerlink",
            "viewcode-link",
            "reference external",
            "sphinxsidebar",
            "relations",
            "download",
            "modindex-jumpbox",
            "genindex-jumpbox",
            "highlight",
            "highlight-python",
            "search",
        ]:
            for element in soup.find_all(attrs={"class": re.compile(class_name)}):
                element.decompose()

        # Convert code blocks to preserve formatting
        for pre_tag in soup.find_all("pre"):
            if isinstance(pre_tag, Tag):
                code_tag = pre_tag.find("code")
                if code_tag and isinstance(code_tag, Tag):
                    # This is a code block, preserve it
                    code_content = pre_tag.get_text()
                    # Determine language from classes if available
                    language = ""
                    if code_tag.get("class"):
                        classes = code_tag.get("class")
                        if isinstance(classes, list):
                            for cls in classes:
                                if isinstance(cls, str):
                                    if cls.startswith("language-"):
                                        language = cls[9:]  # Remove "language-" prefix
                                        break
                                    elif cls in [
                                        "python",
                                        "py",
                                        "javascript",
                                        "js",
                                        "bash",
                                        "shell",
                                    ]:
                                        language = cls
                                        break

                    # Replace with markdown code block
                    new_content = f"```{language}\n{code_content}\n```"
                    pre_tag.replace_with(BeautifulSoup(new_content, "html.parser"))

        return soup

    def _process_markdown_for_obsidian(self, markdown: str) -> str:
        """Process markdown content for Obsidian compatibility.

        Args:
            markdown: Raw markdown content

        Returns:
            Obsidian-compatible markdown
        """
        # Convert HTML links to wikilinks if configured
        if self.config.obsidian.use_wikilinks:
            markdown = self._convert_links_to_wikilinks(markdown)

        # Clean up extra whitespace
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)

        # Fix code block formatting
        markdown = re.sub(r"```(\w+)?\n\n+", r"```\1\n", markdown)

        # Clean up list formatting
        markdown = re.sub(r"\n+(\s*[-*+])", r"\n\1", markdown)

        # Remove excessive escaping that markdownify adds
        markdown = markdown.replace(r"\_", "_")
        markdown = markdown.replace(r"\*", "*")

        return markdown.strip()

    def _convert_links_to_wikilinks(self, markdown: str) -> str:
        """Convert markdown links to Obsidian wikilinks.

        Args:
            markdown: Markdown content with regular links

        Returns:
            Markdown with wikilinks
        """
        # Pattern to match markdown links [text](url)
        link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"

        def replace_link(match: re.Match[str]) -> str:
            text = match.group(1)
            url = match.group(2)

            # Skip external links
            if url.startswith(("http://", "https://", "mailto:", "ftp://")):
                return match.group(0)  # Keep original

            # Handle Sphinx-specific references
            if "#" in url:
                clean_url, anchor = url.split("#", 1)
                # Convert Sphinx anchors to more readable format
                anchor = self._convert_sphinx_anchor(anchor)
            else:
                clean_url = url
                anchor = None

            # Remove file extensions
            if clean_url.endswith(".html"):
                clean_url = clean_url[:-5]  # Remove .html

            # Look up in link mapping
            target = clean_url
            if clean_url in self._link_mapping:
                target = self._link_mapping[clean_url]
                # Remove .md extension for wikilinks
                if target.endswith(".md"):
                    target = target[:-3]

            # Create wikilink with optional anchor
            if anchor and self.config.obsidian.use_wikilinks:
                target_with_anchor = f"{target}#{anchor}"
                if text.lower() == target.replace("/", " ").lower() or text == url:
                    return f"[[{target_with_anchor}]]"
                else:
                    return f"[[{target_with_anchor}|{text}]]"
            else:
                # Create wikilink
                if text.lower() == target.replace("/", " ").lower() or text == url:
                    return f"[[{target}]]"
                else:
                    return f"[[{target}|{text}]]"

        return re.sub(link_pattern, replace_link, markdown)

    def _convert_sphinx_anchor(self, anchor: str) -> str:
        """Convert Sphinx-style anchors to more readable format.

        Args:
            anchor: Sphinx anchor (e.g., 'module.Class.method')

        Returns:
            Readable anchor format
        """
        # Convert dots to spaces for better readability
        if "." in anchor:
            parts = anchor.split(".")
            # Keep the last part as the main identifier
            return parts[-1].replace("-", " ")

        # Convert dashes to spaces
        return anchor.replace("-", " ")

    def _add_obsidian_metadata(
        self, content: str, html_file: Path, relative_path: Path
    ) -> str:
        """Add Obsidian metadata (frontmatter) to markdown content.

        Args:
            content: Markdown content
            html_file: Source HTML file
            relative_path: Relative path from HTML root

        Returns:
            Markdown with frontmatter
        """
        # Extract title from content or filename
        title = self._extract_title_from_content(content) or relative_path.stem

        # Generate tags
        tags = self._generate_tags(relative_path)

        # Create frontmatter
        frontmatter = "---\n"
        frontmatter += f"title: {title}\n"

        if tags:
            frontmatter += f"tags: [{', '.join(tags)}]\n"

        frontmatter += f"source: {html_file.name}\n"
        frontmatter += f"created: {html_file.stat().st_mtime}\n"
        frontmatter += "type: documentation\n"
        frontmatter += "---\n\n"

        return frontmatter + content

    def _extract_title_from_content(self, content: str) -> str | None:
        """Extract title from markdown content.

        Args:
            content: Markdown content

        Returns:
            Extracted title or None if not found
        """
        # Look for first H1 header
        match = re.search(r"^# (.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()

        return None

    def _generate_tags(self, relative_path: Path) -> list[str]:
        """Generate Obsidian tags for a file.

        Args:
            relative_path: Relative path from HTML root

        Returns:
            List of tags
        """
        tags = []

        # Add configured tag prefix
        if self.config.obsidian.tag_prefix:
            tags.append(self.config.obsidian.tag_prefix.rstrip("/"))

        # Add path-based tags
        path_parts = relative_path.parts[:-1]  # Exclude filename
        for part in path_parts:
            if not part.startswith("_"):  # Skip private directories
                tag = f"{self.config.obsidian.tag_prefix}{part}"
                tags.append(tag)

        return tags

    def _generate_obsidian_index(self, converted_files: list[dict[str, Any]]) -> str:
        """Generate an index file for Obsidian.

        Args:
            converted_files: List of converted file information

        Returns:
            Index file content
        """
        content = f"# {self.config.project.name} Documentation\n\n"
        content += (
            "This documentation was automatically generated from Python source code.\n\n"
        )

        # Group files by directory
        files_by_dir: dict[str, list[dict[str, Any]]] = {}

        for file_info in converted_files:
            rel_path = Path(file_info["relative_path"])
            dir_name = str(rel_path.parent) if rel_path.parent != Path(".") else "Root"

            if dir_name not in files_by_dir:
                files_by_dir[dir_name] = []
            files_by_dir[dir_name].append(file_info)

        # Generate index sections
        for dir_name, files in sorted(files_by_dir.items()):
            if dir_name != "Root":
                content += f"\n## {dir_name}\n\n"
            else:
                content += "\n## Documentation Files\n\n"

            for file_info in sorted(files, key=lambda x: x["relative_path"]):
                rel_path = Path(file_info["relative_path"])
                if rel_path.name == "index.md":
                    continue  # Skip self-reference

                # Create wikilink or regular link based on configuration
                filename = rel_path.stem
                if self.config.obsidian.use_wikilinks:
                    content += f"- [[{filename}]]\n"
                else:
                    content += f"- [{filename}]({file_info['relative_path']})\n"

        content += "\n---\n"
        content += "*Generated automatically by obsidian-doc-mcp*\n"

        return content


def convert_sphinx_to_obsidian(
    html_dir: Path, output_dir: Path, config: Config
) -> dict[str, Any]:
    """Convenience function to convert Sphinx HTML to Obsidian markdown.

    Args:
        html_dir: Directory containing Sphinx HTML output
        output_dir: Directory to write Obsidian markdown files
        config: Configuration settings

    Returns:
        Dictionary containing conversion results

    Raises:
        ObsidianConversionError: If conversion fails
    """
    converter = ObsidianConverter(config)
    return converter.convert_html_directory(html_dir, output_dir)
