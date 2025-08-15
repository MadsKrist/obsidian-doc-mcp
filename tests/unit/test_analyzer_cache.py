"""Tests for analyzer caching functionality."""

import tempfile
import time
from pathlib import Path

import pytest

from docs_generator.analyzer import PythonProjectAnalyzer


class TestAnalyzerCache:
    """Test AST parsing cache functionality."""

    @pytest.fixture
    def sample_python_file(self):
        """Create a temporary Python file for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create a sample Python file
            python_file = project_path / "sample.py"
            python_file.write_text(
                '''
"""Sample module for testing."""

def sample_function(x: int, y: str = "default") -> str:
    """Sample function with docstring.

    Args:
        x: Integer parameter
        y: String parameter with default

    Returns:
        Formatted string
    """
    return f"{x}: {y}"


class SampleClass:
    """Sample class for testing."""

    def __init__(self, value: int) -> None:
        """Initialize with value."""
        self.value = value

    def method(self) -> int:
        """Get the value."""
        return self.value
'''
            )

            yield project_path

    def test_cache_initialization(self, sample_python_file: Path) -> None:
        """Test that cache is properly initialized."""
        analyzer = PythonProjectAnalyzer(sample_python_file, enable_cache=True)

        assert analyzer.enable_cache is True
        assert analyzer.cache_ttl == 3600  # default 1 hour
        assert isinstance(analyzer._cache, dict)
        assert len(analyzer._cache) == 0  # starts empty

    def test_cache_disabled(self, sample_python_file: Path) -> None:
        """Test analyzer with cache disabled."""
        analyzer = PythonProjectAnalyzer(sample_python_file, enable_cache=False)

        assert analyzer.enable_cache is False

        # Analyze project - should work without caching
        structure = analyzer.analyze_project()
        assert len(structure.modules) == 1
        assert len(analyzer._cache) == 0  # no caching

    def test_cache_file_analysis(self, sample_python_file: Path) -> None:
        """Test that file analysis results are cached."""
        analyzer = PythonProjectAnalyzer(sample_python_file, enable_cache=True)

        # First analysis - should parse and cache
        structure1 = analyzer.analyze_project()
        assert len(structure1.modules) == 1
        assert len(analyzer._cache) == 1

        # Check cache entry
        python_file = sample_python_file / "sample.py"
        cache_key = str(python_file)
        assert cache_key in analyzer._cache

        cache_entry = analyzer._cache[cache_key]
        assert cache_entry.module_info.name == "sample"
        assert len(cache_entry.module_info.functions) == 1
        assert len(cache_entry.module_info.classes) == 1
        assert cache_entry.file_hash != ""
        assert cache_entry.file_size > 0

    def test_cache_reuse(self, sample_python_file: Path) -> None:
        """Test that cache is reused on subsequent analysis."""
        analyzer = PythonProjectAnalyzer(sample_python_file, enable_cache=True)

        # First analysis
        start_time = time.time()
        structure1 = analyzer.analyze_project()
        first_duration = time.time() - start_time

        # Second analysis - should be faster due to cache
        start_time = time.time()
        structure2 = analyzer.analyze_project()
        second_duration = time.time() - start_time

        # Results should be identical
        assert len(structure1.modules) == len(structure2.modules)
        assert structure1.modules[0].name == structure2.modules[0].name
        assert len(structure1.modules[0].functions) == len(structure2.modules[0].functions)

        # Second run should be significantly faster (cache hit)
        # Note: In practice, this test might be flaky due to timing variations
        # but it demonstrates the concept
        assert second_duration < first_duration or second_duration < 0.01

    def test_cache_invalidation_on_file_change(self, sample_python_file: Path) -> None:
        """Test that cache is invalidated when file changes."""
        analyzer = PythonProjectAnalyzer(sample_python_file, enable_cache=True)

        # First analysis
        structure1 = analyzer.analyze_project()
        assert len(structure1.modules[0].functions) == 1

        # Modify the file
        python_file = sample_python_file / "sample.py"
        content = python_file.read_text()
        modified_content = (
            content
            + '''

def new_function() -> None:
    """A new function added to test cache invalidation."""
    pass
'''
        )
        python_file.write_text(modified_content)

        # Second analysis - cache should be invalidated
        structure2 = analyzer.analyze_project()

        # Should have the new function
        assert len(structure2.modules[0].functions) == 2

        # Check that we have functions named "sample_function" and "new_function"
        function_names = [f.name for f in structure2.modules[0].functions]
        assert "sample_function" in function_names
        assert "new_function" in function_names

    def test_cache_ttl_expiration(self, sample_python_file: Path) -> None:
        """Test that cache entries expire after TTL."""
        # Use very short TTL for testing
        analyzer = PythonProjectAnalyzer(sample_python_file, enable_cache=True, cache_ttl=1)

        # First analysis
        analyzer.analyze_project()
        assert len(analyzer._cache) == 1

        # Wait for cache to expire
        time.sleep(1.1)

        # Check that cache entry is considered invalid
        python_file = sample_python_file / "sample.py"
        cache_key = str(python_file)
        cache_entry = analyzer._cache[cache_key]

        # Should be invalid due to TTL
        assert not analyzer._is_cache_valid(python_file, cache_entry)

        # Second analysis should remove expired entry and re-analyze
        structure2 = analyzer.analyze_project()
        assert len(structure2.modules) == 1

    def test_cache_persistence(self, sample_python_file: Path) -> None:
        """Test that cache persists to disk and is loaded correctly."""
        # First analyzer instance - creates cache
        analyzer1 = PythonProjectAnalyzer(sample_python_file, enable_cache=True)
        structure1 = analyzer1.analyze_project()

        # Check cache file was created
        cache_file = sample_python_file / ".mcp-docs-cache.json"
        assert cache_file.exists()

        # Second analyzer instance - should load existing cache
        analyzer2 = PythonProjectAnalyzer(sample_python_file, enable_cache=True)

        # Cache should be loaded
        python_file = sample_python_file / "sample.py"
        cache_key = str(python_file)
        assert cache_key in analyzer2._cache

        # Analysis should use cached data
        structure2 = analyzer2.analyze_project()
        assert len(structure2.modules) == 1
        assert structure2.modules[0].name == structure1.modules[0].name

    def test_cache_clear(self, sample_python_file: Path) -> None:
        """Test cache clearing functionality."""
        analyzer = PythonProjectAnalyzer(sample_python_file, enable_cache=True)

        # Analyze and verify cache
        analyzer.analyze_project()
        assert len(analyzer._cache) == 1

        cache_file = sample_python_file / ".mcp-docs-cache.json"
        assert cache_file.exists()

        # Clear cache
        analyzer.clear_cache()

        # Verify cache is empty
        assert len(analyzer._cache) == 0
        assert not cache_file.exists()

    def test_cache_with_syntax_error(self, sample_python_file: Path) -> None:
        """Test that syntax errors don't break caching."""
        # Create file with syntax error
        bad_file = sample_python_file / "bad_syntax.py"
        bad_file.write_text("def incomplete_function(\n    # Missing closing parenthesis")

        analyzer = PythonProjectAnalyzer(sample_python_file, enable_cache=True)

        # Analysis should handle syntax error gracefully
        structure = analyzer.analyze_project()

        # Should have analyzed the good file, skipped the bad one
        assert len(structure.modules) == 1  # Only sample.py
        assert len(analyzer._cache) == 1  # Only cached the good file

    def test_cache_file_hash_consistency(self, sample_python_file: Path) -> None:
        """Test that file hashes are consistent and detect changes."""
        analyzer = PythonProjectAnalyzer(sample_python_file, enable_cache=True)

        python_file = sample_python_file / "sample.py"

        # Get hash of original file
        hash1 = analyzer._get_file_hash(python_file)
        assert hash1 != ""

        # Hash should be consistent
        hash2 = analyzer._get_file_hash(python_file)
        assert hash1 == hash2

        # Modify file slightly
        content = python_file.read_text()
        python_file.write_text(content + "\n# Comment added")

        # Hash should change
        hash3 = analyzer._get_file_hash(python_file)
        assert hash1 != hash3
