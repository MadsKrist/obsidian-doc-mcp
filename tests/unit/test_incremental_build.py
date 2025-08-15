"""Tests for incremental build functionality."""

import tempfile
import time
from pathlib import Path

import pytest

from utils.incremental_build import BuildState, FileState, IncrementalBuildManager


class TestFileState:
    """Test FileState dataclass."""

    def test_file_state_creation(self):
        """Test FileState creation."""
        state = FileState(path="/test/file.py", size=1024, mtime=time.time(), hash="abcdef123456")

        assert state.path == "/test/file.py"
        assert state.size == 1024
        assert state.hash == "abcdef123456"
        assert state.last_build == 0.0  # default value


class TestBuildState:
    """Test BuildState dataclass."""

    def test_build_state_creation(self):
        """Test BuildState creation."""
        state = BuildState(project_path="/test/project")

        assert state.project_path == "/test/project"
        assert state.last_full_build == 0.0
        assert len(state.files) == 0
        assert len(state.dependencies) == 0
        assert len(state.outputs) == 0
        assert state.build_version == "1.0"


class TestIncrementalBuildManager:
    """Test IncrementalBuildManager functionality."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create some sample Python files
            (project_path / "main.py").write_text(
                '''
"""Main module."""

def main():
    """Main function."""
    return "Hello World"
'''
            )

            (project_path / "utils.py").write_text(
                '''
"""Utilities module."""

def helper():
    """Helper function."""
    return "Helper"
'''
            )

            yield project_path

    def test_manager_initialization(self, temp_project):
        """Test manager initialization."""
        manager = IncrementalBuildManager(temp_project)

        assert manager.project_path == temp_project
        assert manager.build_cache_file == temp_project / ".mcp-docs-build.json"
        assert manager.build_state.project_path == str(temp_project)
        assert len(manager.build_state.files) == 0

    def test_cache_file_creation_and_loading(self, temp_project):
        """Test build cache persistence."""
        # Create manager and add some state
        manager1 = IncrementalBuildManager(temp_project)

        python_file = temp_project / "main.py"
        manager1.mark_files_built([python_file])

        # Verify cache file was created
        assert manager1.build_cache_file.exists()

        # Create new manager instance - should load existing state
        manager2 = IncrementalBuildManager(temp_project)

        assert len(manager2.build_state.files) == 1
        assert str(python_file) in manager2.build_state.files

    def test_file_change_detection_new_file(self, temp_project):
        """Test detection of new files."""
        manager = IncrementalBuildManager(temp_project)

        python_file = temp_project / "main.py"

        # New file should be detected as changed
        assert manager.is_file_changed(python_file) is True

    def test_file_change_detection_unchanged_file(self, temp_project):
        """Test detection of unchanged files."""
        manager = IncrementalBuildManager(temp_project)

        python_file = temp_project / "main.py"

        # Mark file as built
        manager.mark_files_built([python_file])

        # File should not be changed now
        assert manager.is_file_changed(python_file) is False

    def test_file_change_detection_modified_file(self, temp_project):
        """Test detection of modified files."""
        manager = IncrementalBuildManager(temp_project)

        python_file = temp_project / "main.py"

        # Mark file as built
        manager.mark_files_built([python_file])
        assert manager.is_file_changed(python_file) is False

        # Modify the file
        time.sleep(0.1)  # Ensure different mtime
        python_file.write_text(
            '''
"""Modified main module."""

def main():
    """Modified main function."""
    return "Modified Hello World"
'''
        )

        # File should be detected as changed
        assert manager.is_file_changed(python_file) is True

    def test_get_changed_files(self, temp_project):
        """Test getting list of changed files."""
        manager = IncrementalBuildManager(temp_project)

        main_py = temp_project / "main.py"
        utils_py = temp_project / "utils.py"

        all_files = [main_py, utils_py]

        # All files should be changed (new)
        changed = manager.get_changed_files(all_files)
        assert len(changed) == 2
        assert main_py in changed
        assert utils_py in changed

        # Mark one file as built
        manager.mark_files_built([main_py])

        # Only utils.py should be changed now
        changed = manager.get_changed_files(all_files)
        assert len(changed) == 1
        assert utils_py in changed
        assert main_py not in changed

    def test_dependency_tracking(self, temp_project):
        """Test dependency tracking functionality."""
        manager = IncrementalBuildManager(temp_project)

        main_py = temp_project / "main.py"
        utils_py = temp_project / "utils.py"

        # Set up dependencies (main.py depends on utils.py)
        dependencies = {str(main_py): [str(utils_py)], str(utils_py): []}
        manager.update_dependencies(dependencies)

        # Get dependent files
        dependents = manager.get_dependent_files(utils_py)
        assert len(dependents) == 1
        assert main_py in dependents

        # No dependents for main.py
        dependents = manager.get_dependent_files(main_py)
        assert len(dependents) == 0

    def test_full_build_tracking(self, temp_project):
        """Test full build timestamp tracking."""
        manager = IncrementalBuildManager(temp_project)

        # Initially no full build
        assert manager.build_state.last_full_build == 0.0
        assert manager.should_force_full_build() is True

        # Mark full build
        manager.mark_full_build()
        assert manager.build_state.last_full_build > 0
        assert manager.should_force_full_build() is False

        # Test TTL-based full build forcing
        assert manager.should_force_full_build(force_after_hours=0.0) is True

    def test_output_file_tracking(self, temp_project):
        """Test output file tracking and cleanup."""
        manager = IncrementalBuildManager(temp_project)

        main_py = temp_project / "main.py"
        output_files = ["docs/main.md", "docs/main.html"]

        # Track generated files
        manager.mark_files_built([main_py], {str(main_py): output_files})

        # Verify outputs are tracked
        assert str(main_py) in manager.build_state.outputs
        assert manager.build_state.outputs[str(main_py)] == output_files

    def test_orphaned_output_cleanup(self, temp_project):
        """Test cleanup of orphaned output files."""
        manager = IncrementalBuildManager(temp_project)

        # Create and track a file
        temp_file = temp_project / "temp.py"
        temp_file.write_text("# temp file")

        # Create mock output files
        output_dir = temp_project / "output"
        output_dir.mkdir()
        output1 = output_dir / "temp.md"
        output2 = output_dir / "temp.html"
        output1.write_text("# Temp doc")
        output2.write_text("<h1>Temp</h1>")

        # Track the outputs
        manager.mark_files_built([temp_file], {str(temp_file): [str(output1), str(output2)]})

        # Delete source file
        temp_file.unlink()

        # Clean orphaned outputs
        cleaned = manager.clean_orphaned_outputs()

        assert len(cleaned) == 2
        assert str(output1) in cleaned
        assert str(output2) in cleaned
        assert not output1.exists()
        assert not output2.exists()

    def test_file_hash_consistency(self, temp_project):
        """Test file hash calculation consistency."""
        manager = IncrementalBuildManager(temp_project)

        python_file = temp_project / "main.py"

        # Hash should be consistent
        hash1 = manager._get_file_hash(python_file)
        hash2 = manager._get_file_hash(python_file)
        assert hash1 == hash2
        assert hash1 != ""

        # Hash should change when file changes
        original_content = python_file.read_text()
        python_file.write_text(original_content + "\n# Added comment")

        hash3 = manager._get_file_hash(python_file)
        assert hash1 != hash3

    def test_build_stats(self, temp_project):
        """Test build statistics reporting."""
        manager = IncrementalBuildManager(temp_project)

        main_py = temp_project / "main.py"
        manager.mark_files_built([main_py])
        manager.mark_full_build()

        stats = manager.get_build_stats()

        assert stats["project_path"] == str(temp_project)
        assert stats["tracked_files"] == 1
        assert stats["last_full_build"] > 0
        assert stats["hours_since_full_build"] < 1  # Should be very recent
        assert stats["build_version"] == "1.0"
        assert stats["cache_file_exists"] is True

    def test_cache_clearing(self, temp_project):
        """Test build cache clearing."""
        manager = IncrementalBuildManager(temp_project)

        # Add some state
        main_py = temp_project / "main.py"
        manager.mark_files_built([main_py])
        manager.mark_full_build()

        assert len(manager.build_state.files) == 1
        assert manager.build_cache_file.exists()

        # Clear cache
        manager.clear_build_cache()

        assert len(manager.build_state.files) == 0
        assert manager.build_state.last_full_build == 0.0
        assert not manager.build_cache_file.exists()

    def test_invalid_cache_file_handling(self, temp_project):
        """Test handling of corrupted cache files."""
        # Create invalid cache file
        cache_file = temp_project / ".mcp-docs-build.json"
        cache_file.write_text("invalid json content {")

        # Manager should handle gracefully
        manager = IncrementalBuildManager(temp_project)

        # Should start with empty state
        assert len(manager.build_state.files) == 0
        assert manager.build_state.last_full_build == 0.0

    def test_nonexistent_file_handling(self, temp_project):
        """Test handling of nonexistent files."""
        manager = IncrementalBuildManager(temp_project)

        nonexistent = temp_project / "nonexistent.py"

        # Should handle gracefully
        assert manager.is_file_changed(nonexistent) is False

        changed = manager.get_changed_files([nonexistent])
        assert len(changed) == 0

        # Should not crash when marking nonexistent file as built
        manager.mark_files_built([nonexistent])

    def test_concurrent_access_safety(self, temp_project):
        """Test basic thread safety (simplified test)."""
        manager1 = IncrementalBuildManager(temp_project)
        manager2 = IncrementalBuildManager(temp_project)

        main_py = temp_project / "main.py"

        # Both managers should work independently
        manager1.mark_files_built([main_py])

        # manager2 should load the state created by manager1
        manager2._load_build_state()
        assert len(manager2.build_state.files) == 1
