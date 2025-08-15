"""Tests for file watcher functionality."""

import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from watchdog.events import FileCreatedEvent, FileDeletedEvent, FileModifiedEvent

from config.project_config import Config, ProjectConfig
from utils.file_watcher import FileWatcher, PythonFileEventHandler, create_file_watcher


@pytest.fixture
def project_config():
    """Create a test project configuration."""
    return Config(
        project=ProjectConfig(
            name="test-project",
            source_paths=["src"],
            exclude_patterns=["*.pyc", "test_*"],
        )
    )


@pytest.fixture
def project_path(tmp_path):
    """Create a temporary project directory."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()

    # Create source directory
    src_dir = project_dir / "src"
    src_dir.mkdir()

    # Create test files
    (src_dir / "module1.py").write_text("# Module 1")
    (src_dir / "module2.py").write_text("# Module 2")
    (project_dir / "setup.py").write_text("# Setup")

    return project_dir


class TestPythonFileEventHandler:
    """Test cases for PythonFileEventHandler."""

    def test_initialization(self, project_path, project_config):
        """Test handler initialization."""
        callback = Mock()
        handler = PythonFileEventHandler(callback, project_path, project_config)

        assert handler.callback is callback
        assert handler.project_path == project_path
        assert handler.config is project_config
        assert handler.changed_files == set()
        assert handler.debounce_timer is None
        assert handler.debounce_delay == 2.0

    def test_should_process_file_python_file(self, project_path, project_config):
        """Test file filtering for Python files."""
        callback = Mock()
        handler = PythonFileEventHandler(callback, project_path, project_config)

        # Python file in source path should be processed
        python_file = project_path / "src" / "module.py"
        assert handler._should_process_file(python_file) is True

        # Non-Python file should not be processed
        text_file = project_path / "src" / "file.txt"
        assert handler._should_process_file(text_file) is False

    def test_should_process_file_source_paths(self, project_path, project_config):
        """Test file filtering based on source paths."""
        callback = Mock()
        handler = PythonFileEventHandler(callback, project_path, project_config)

        # File in source path
        src_file = project_path / "src" / "module.py"
        assert handler._should_process_file(src_file) is True

        # File outside source path
        root_file = project_path / "setup.py"
        assert handler._should_process_file(root_file) is False

    def test_should_process_file_exclude_patterns(self, project_path, project_config):
        """Test file filtering based on exclude patterns."""
        callback = Mock()
        handler = PythonFileEventHandler(callback, project_path, project_config)

        # Normal Python file
        normal_file = project_path / "src" / "module.py"
        assert handler._should_process_file(normal_file) is True

        # Excluded by pattern
        pyc_file = project_path / "src" / "module.pyc"
        assert handler._should_process_file(pyc_file) is False

        test_file = project_path / "src" / "test_module.py"
        assert handler._should_process_file(test_file) is False

    def test_should_process_file_outside_project(self, project_path, project_config):
        """Test file filtering for files outside project."""
        callback = Mock()
        handler = PythonFileEventHandler(callback, project_path, project_config)

        # File outside project
        outside_file = Path("/tmp/external.py")
        assert handler._should_process_file(outside_file) is False

    def test_on_modified_event(self, project_path, project_config):
        """Test handling of file modification events."""
        callback = Mock()
        handler = PythonFileEventHandler(callback, project_path, project_config)

        # Mock the debounce method to avoid timing issues
        handler._debounce_callback = Mock()

        # Create modification event for Python file
        python_file = project_path / "src" / "module.py"
        event = FileModifiedEvent(str(python_file))

        handler.on_modified(event)

        assert python_file in handler.changed_files
        handler._debounce_callback.assert_called_once()

    def test_on_modified_directory_ignored(self, project_path, project_config):
        """Test that directory modification events are ignored."""
        callback = Mock()
        handler = PythonFileEventHandler(callback, project_path, project_config)
        handler._debounce_callback = Mock()

        # Create directory modification event
        event = FileModifiedEvent(str(project_path / "src"))
        event.is_directory = True

        handler.on_modified(event)

        assert len(handler.changed_files) == 0
        handler._debounce_callback.assert_not_called()

    def test_on_created_event(self, project_path, project_config):
        """Test handling of file creation events."""
        callback = Mock()
        handler = PythonFileEventHandler(callback, project_path, project_config)
        handler._debounce_callback = Mock()

        # Create creation event for Python file
        python_file = project_path / "src" / "new_module.py"
        event = FileCreatedEvent(str(python_file))

        handler.on_created(event)

        assert python_file in handler.changed_files
        handler._debounce_callback.assert_called_once()

    def test_on_deleted_event(self, project_path, project_config):
        """Test handling of file deletion events."""
        callback = Mock()
        handler = PythonFileEventHandler(callback, project_path, project_config)
        handler._debounce_callback = Mock()

        # Create deletion event for Python file
        python_file = project_path / "src" / "deleted_module.py"
        event = FileDeletedEvent(str(python_file))

        handler.on_deleted(event)

        assert python_file in handler.changed_files
        handler._debounce_callback.assert_called_once()

    def test_debounce_callback(self, project_path, project_config):
        """Test debouncing of callback execution."""
        callback = Mock()
        handler = PythonFileEventHandler(callback, project_path, project_config)

        # Add some changed files
        file1 = project_path / "src" / "file1.py"
        file2 = project_path / "src" / "file2.py"
        handler.changed_files.update([file1, file2])

        # Call debounce
        handler._debounce_callback()

        # Callback should not be called immediately
        callback.assert_not_called()
        assert handler.debounce_timer is not None

        # Wait for debounce delay and check callback
        time.sleep(0.1)  # Short wait for timer setup
        handler.debounce_timer.join(timeout=3.0)

        # Should have been called with the files
        callback.assert_called_once()
        call_args = callback.call_args[0][0]
        assert file1 in call_args
        assert file2 in call_args
        assert len(handler.changed_files) == 0


class TestFileWatcher:
    """Test cases for FileWatcher."""

    def test_initialization(self, project_path, project_config):
        """Test watcher initialization."""
        watcher = FileWatcher(project_path, project_config)

        assert watcher.project_path == project_path
        assert watcher.config is project_config
        assert watcher.incremental_builder is None
        assert watcher.observer is None
        assert watcher.event_handler is None
        assert watcher.is_watching is False
        assert watcher.update_callbacks == []

    def test_initialization_with_incremental_builder(
        self, project_path, project_config
    ):
        """Test watcher initialization with incremental builder."""
        mock_builder = Mock()
        watcher = FileWatcher(project_path, project_config, mock_builder)

        assert watcher.incremental_builder is mock_builder

    def test_add_remove_update_callback(self, project_path, project_config):
        """Test adding and removing update callbacks."""
        watcher = FileWatcher(project_path, project_config)
        callback1 = Mock()
        callback2 = Mock()

        # Add callbacks
        watcher.add_update_callback(callback1)
        watcher.add_update_callback(callback2)

        assert len(watcher.update_callbacks) == 2
        assert callback1 in watcher.update_callbacks
        assert callback2 in watcher.update_callbacks

        # Remove callback
        watcher.remove_update_callback(callback1)

        assert len(watcher.update_callbacks) == 1
        assert callback1 not in watcher.update_callbacks
        assert callback2 in watcher.update_callbacks

    def test_remove_nonexistent_callback(self, project_path, project_config):
        """Test removing a callback that doesn't exist."""
        watcher = FileWatcher(project_path, project_config)
        callback = Mock()

        # Should not raise error
        watcher.remove_update_callback(callback)
        assert len(watcher.update_callbacks) == 0

    @patch("utils.file_watcher.Observer")
    def test_start_watching_source_paths(
        self, mock_observer_class, project_path, project_config
    ):
        """Test starting file watching with specific source paths."""
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer

        watcher = FileWatcher(project_path, project_config)
        watcher.start_watching()

        assert watcher.is_watching is True
        assert watcher.observer is mock_observer
        assert watcher.event_handler is not None

        # Should schedule watching for source directory
        mock_observer.schedule.assert_called_once()
        args = mock_observer.schedule.call_args[0]
        assert args[0] is watcher.event_handler
        assert args[1] == str(project_path / "src")
        assert mock_observer.schedule.call_args[1]["recursive"] is True

        mock_observer.start.assert_called_once()

    @patch("utils.file_watcher.Observer")
    def test_start_watching_entire_project(self, mock_observer_class, project_path):
        """Test starting file watching for entire project."""
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer

        # Config without source paths
        config = Config(project=ProjectConfig(name="test-project", source_paths=[]))

        watcher = FileWatcher(project_path, config)
        watcher.start_watching()

        # Should schedule watching for entire project
        mock_observer.schedule.assert_called_once()
        args = mock_observer.schedule.call_args[0]
        assert args[1] == str(project_path)

    @patch("utils.file_watcher.Observer")
    def test_start_watching_already_watching(
        self, mock_observer_class, project_path, project_config
    ):
        """Test starting file watching when already watching."""
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer

        watcher = FileWatcher(project_path, project_config)
        watcher.is_watching = True

        with patch("utils.file_watcher.logger") as mock_logger:
            watcher.start_watching()
            mock_logger.warning.assert_called_once_with(
                "File watcher is already running"
            )

        # Should not create new observer
        mock_observer_class.assert_not_called()

    @patch("utils.file_watcher.Observer")
    def test_stop_watching(self, mock_observer_class, project_path, project_config):
        """Test stopping file watching."""
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer

        watcher = FileWatcher(project_path, project_config)
        watcher.start_watching()

        # Add mock timer to event handler
        mock_timer = Mock()
        if watcher.event_handler:
            watcher.event_handler.debounce_timer = mock_timer

        watcher.stop_watching()

        assert watcher.is_watching is False
        assert watcher.observer is None
        assert watcher.event_handler is None

        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()
        mock_timer.cancel.assert_called_once()

    def test_stop_watching_not_watching(self, project_path, project_config):
        """Test stopping file watching when not watching."""
        watcher = FileWatcher(project_path, project_config)

        # Should not raise error
        watcher.stop_watching()
        assert watcher.is_watching is False

    def test_handle_file_changes_with_callbacks(self, project_path, project_config):
        """Test handling file changes with registered callbacks."""
        watcher = FileWatcher(project_path, project_config)

        callback1 = Mock()
        callback2 = Mock()
        watcher.add_update_callback(callback1)
        watcher.add_update_callback(callback2)

        changed_files = {project_path / "src" / "module.py"}

        watcher._handle_file_changes(changed_files)

        callback1.assert_called_once_with(changed_files)
        callback2.assert_called_once_with(changed_files)

    def test_handle_file_changes_callback_error(self, project_path, project_config):
        """Test handling file changes when callback raises error."""
        watcher = FileWatcher(project_path, project_config)

        # Callback that raises error
        error_callback = Mock(side_effect=Exception("Callback error"))
        success_callback = Mock()

        watcher.add_update_callback(error_callback)
        watcher.add_update_callback(success_callback)

        changed_files = {project_path / "src" / "module.py"}

        with patch("utils.file_watcher.logger") as mock_logger:
            watcher._handle_file_changes(changed_files)

        # Error should be logged but other callbacks should still run
        mock_logger.error.assert_called_once()
        success_callback.assert_called_once_with(changed_files)

    @pytest.mark.asyncio
    async def test_handle_file_changes_with_incremental_builder(
        self, project_path, project_config
    ):
        """Test handling file changes with incremental builder."""
        mock_builder = Mock()
        mock_builder.get_changed_files = Mock(return_value=set())

        watcher = FileWatcher(project_path, project_config, mock_builder)

        changed_files = {project_path / "src" / "module.py"}

        # Mock asyncio components for the test
        with patch("asyncio.get_event_loop") as mock_get_loop, patch(
            "asyncio.ensure_future"
        ) as mock_ensure_future:
            mock_loop = Mock()
            mock_loop.is_running.return_value = True
            mock_get_loop.return_value = mock_loop

            watcher._handle_file_changes(changed_files)
            mock_ensure_future.assert_called_once()

    def test_get_status(self, project_path, project_config):
        """Test getting watcher status."""
        mock_builder = Mock()
        watcher = FileWatcher(project_path, project_config, mock_builder)

        callback = Mock()
        watcher.add_update_callback(callback)

        status = watcher.get_status()

        assert status["is_watching"] is False
        assert status["project_path"] == str(project_path)
        assert status["watched_paths"] == [str(project_path / "src")]
        assert status["exclude_patterns"] == ["*.pyc", "test_*"]
        assert status["callback_count"] == 1
        assert status["has_incremental_builder"] is True

    def test_context_manager(self, project_path, project_config):
        """Test using FileWatcher as context manager."""
        watcher = FileWatcher(project_path, project_config)
        watcher.start_watching = Mock()
        watcher.stop_watching = Mock()

        with watcher as w:
            assert w is watcher
            watcher.start_watching.assert_called_once()

        watcher.stop_watching.assert_called_once()


class TestCreateFileWatcher:
    """Test cases for create_file_watcher function."""

    @pytest.mark.asyncio
    async def test_create_file_watcher_with_incremental_updates(
        self, project_path, project_config
    ):
        """Test creating file watcher with incremental updates enabled."""
        with patch(
            "utils.incremental_build.IncrementalBuildManager"
        ) as mock_builder_class:
            mock_builder = Mock()
            mock_builder_class.return_value = mock_builder

            watcher = await create_file_watcher(project_path, project_config, True)

            assert isinstance(watcher, FileWatcher)
            assert watcher.project_path == project_path
            assert watcher.config is project_config
            assert watcher.incremental_builder is mock_builder
            assert len(watcher.update_callbacks) == 1  # Log callback added

            mock_builder_class.assert_called_once_with(project_path)

    @pytest.mark.asyncio
    async def test_create_file_watcher_without_incremental_updates(
        self, project_path, project_config
    ):
        """Test creating file watcher without incremental updates."""
        watcher = await create_file_watcher(project_path, project_config, False)

        assert isinstance(watcher, FileWatcher)
        assert watcher.incremental_builder is None
        assert len(watcher.update_callbacks) == 1  # Log callback added

    @pytest.mark.asyncio
    async def test_create_file_watcher_builder_error(
        self, project_path, project_config
    ):
        """Test creating file watcher when incremental builder creation fails."""
        with patch(
            "utils.incremental_build.IncrementalBuildManager"
        ) as mock_builder_class:
            mock_builder_class.side_effect = Exception("Builder error")

            with patch("utils.file_watcher.logger") as mock_logger:
                watcher = await create_file_watcher(project_path, project_config, True)

                mock_logger.warning.assert_called_once()

            assert watcher.incremental_builder is None
            assert len(watcher.update_callbacks) == 1  # Log callback still added
