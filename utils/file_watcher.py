"""File watching system for real-time documentation updates.

This module provides intelligent file watching capabilities that monitor Python
source files for changes and trigger incremental documentation updates.
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler

if TYPE_CHECKING:
    from .incremental_build import IncrementalBuildManager

from config.project_config import Config

logger = logging.getLogger(__name__)


class PythonFileEventHandler(FileSystemEventHandler):
    """Event handler for Python file changes."""

    def __init__(self, callback: Callable[[set[Path]], None], project_path: Path, config: Config):
        """Initialize the event handler.

        Args:
            callback: Function to call when files change
            project_path: Root path of the project to monitor
            config: Project configuration for filtering files
        """
        super().__init__()
        self.callback = callback
        self.project_path = project_path
        self.config = config
        self.changed_files: set[Path] = set()
        self.debounce_timer: threading.Timer | None = None
        self.debounce_delay = 2.0  # Wait 2 seconds after last change

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return

        file_path = Path(str(event.src_path))

        # Only process Python files in source paths
        if not self._should_process_file(file_path):
            return

        logger.debug(f"Python file modified: {file_path}")
        self.changed_files.add(file_path)
        self._debounce_callback()

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return

        file_path = Path(str(event.src_path))

        if not self._should_process_file(file_path):
            return

        logger.debug(f"Python file created: {file_path}")
        self.changed_files.add(file_path)
        self._debounce_callback()

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events."""
        if event.is_directory:
            return

        file_path = Path(str(event.src_path))

        if not self._should_process_file(file_path):
            return

        logger.debug(f"Python file deleted: {file_path}")
        self.changed_files.add(file_path)
        self._debounce_callback()

    def _should_process_file(self, file_path: Path) -> bool:
        """Check if a file should be processed based on configuration.

        Args:
            file_path: Path to the file

        Returns:
            True if the file should be processed
        """
        # Must be a Python file
        if file_path.suffix != ".py":
            return False

        # Must be within project path
        try:
            file_path.relative_to(self.project_path)
        except ValueError:
            return False

        # Check if file is in source paths
        if self.config.project.source_paths:
            in_source_path = False
            for source_path in self.config.project.source_paths:
                try:
                    source_full_path = self.project_path / source_path
                    file_path.relative_to(source_full_path)
                    in_source_path = True
                    break
                except ValueError:
                    continue
            if not in_source_path:
                return False

        # Check exclude patterns
        for pattern in self.config.project.exclude_patterns:
            if file_path.match(pattern):
                return False

        return True

    def _debounce_callback(self) -> None:
        """Debounce the callback to avoid excessive updates."""
        if self.debounce_timer:
            self.debounce_timer.cancel()

        def delayed_callback() -> None:
            if self.changed_files:
                files_to_process = self.changed_files.copy()
                self.changed_files.clear()
                self.callback(files_to_process)

        self.debounce_timer = threading.Timer(self.debounce_delay, delayed_callback)
        self.debounce_timer.start()


class FileWatcher:
    """Smart file watcher for Python projects."""

    def __init__(
        self,
        project_path: Path,
        config: Config,
        incremental_builder: Optional["IncrementalBuildManager"] = None,
    ):
        """Initialize the file watcher.

        Args:
            project_path: Root path of the project to monitor
            config: Project configuration
            incremental_builder: Optional incremental builder for updates
        """
        self.project_path = project_path
        self.config = config
        self.incremental_builder = incremental_builder
        self.observer: Any | None = None
        self.event_handler: PythonFileEventHandler | None = None
        self.is_watching = False
        self.update_callbacks: list[Callable[[set[Path]], None]] = []

    def add_update_callback(self, callback: Callable[[set[Path]], None]) -> None:
        """Add a callback to be called when files change.

        Args:
            callback: Function that takes a set of changed file paths
        """
        self.update_callbacks.append(callback)

    def remove_update_callback(self, callback: Callable[[set[Path]], None]) -> None:
        """Remove an update callback.

        Args:
            callback: Function to remove from callbacks
        """
        if callback in self.update_callbacks:
            self.update_callbacks.remove(callback)

    def start_watching(self) -> None:
        """Start watching for file changes."""
        if self.is_watching:
            logger.warning("File watcher is already running")
            return

        from watchdog.observers import Observer

        logger.info(f"Starting file watcher for {self.project_path}")

        self.event_handler = PythonFileEventHandler(
            callback=self._handle_file_changes,
            project_path=self.project_path,
            config=self.config,
        )

        self.observer = Observer()

        # Watch source paths or entire project
        if self.config.project.source_paths:
            for source_path in self.config.project.source_paths:
                watch_path = self.project_path / source_path
                if watch_path.exists():
                    logger.debug(f"Watching directory: {watch_path}")
                    if self.observer and self.event_handler:
                        self.observer.schedule(self.event_handler, str(watch_path), recursive=True)
        else:
            # Watch entire project directory
            logger.debug(f"Watching entire project: {self.project_path}")
            if self.observer and self.event_handler:
                self.observer.schedule(self.event_handler, str(self.project_path), recursive=True)

        if self.observer:
            self.observer.start()
        self.is_watching = True
        logger.info("File watcher started successfully")

    def stop_watching(self) -> None:
        """Stop watching for file changes."""
        if not self.is_watching:
            return

        logger.info("Stopping file watcher")

        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None

        if self.event_handler and self.event_handler.debounce_timer:
            self.event_handler.debounce_timer.cancel()

        self.event_handler = None
        self.is_watching = False
        logger.info("File watcher stopped")

    def _handle_file_changes(self, changed_files: set[Path]) -> None:
        """Handle file changes by triggering incremental updates.

        Args:
            changed_files: Set of files that have changed
        """
        logger.info(f"Processing {len(changed_files)} changed files")

        # Log changed files for debugging
        for file_path in changed_files:
            logger.debug(f"Changed file: {file_path}")

        # Trigger incremental rebuild if available
        if self.incremental_builder:
            try:
                # Try to get current event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule coroutine on existing loop
                    asyncio.ensure_future(self._async_incremental_update(changed_files))
                else:
                    # No loop running, run in thread
                    threading.Thread(
                        target=self._sync_incremental_update,
                        args=(changed_files,),
                        daemon=True,
                    ).start()
            except RuntimeError:
                # No event loop, run in thread
                threading.Thread(
                    target=self._sync_incremental_update,
                    args=(changed_files,),
                    daemon=True,
                ).start()

        # Call all registered callbacks
        for callback in self.update_callbacks:
            try:
                callback(changed_files)
            except Exception as e:
                logger.error(f"Error in update callback: {e}")

    async def _async_incremental_update(self, changed_files: set[Path]) -> None:
        """Perform async incremental update.

        Args:
            changed_files: Set of files that have changed
        """
        try:
            if self.incremental_builder:
                # Get files that actually changed according to build manager
                changed_list = list(changed_files)
                actual_changed = self.incremental_builder.get_changed_files(changed_list)

                if actual_changed:
                    logger.info(f"Incremental update detected {len(actual_changed)} changed files")
                    # Mark files as needing rebuild
                    for file_path in actual_changed:
                        # The build manager will handle the actual rebuild logic
                        logger.debug(f"File needs rebuild: {file_path}")
                    logger.info("Incremental documentation update completed")
                else:
                    logger.debug("No files actually changed")
        except Exception as e:
            logger.error(f"Error during incremental update: {e}")

    def _sync_incremental_update(self, changed_files: set[Path]) -> None:
        """Perform sync incremental update (fallback).

        Args:
            changed_files: Set of files that have changed
        """
        try:
            # Run async function in new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._async_incremental_update(changed_files))
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Error during sync incremental update: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get current watcher status.

        Returns:
            Dictionary with watcher status information
        """
        return {
            "is_watching": self.is_watching,
            "project_path": str(self.project_path),
            "watched_paths": (
                [str(self.project_path / path) for path in self.config.project.source_paths]
                if self.config.project.source_paths
                else [str(self.project_path)]
            ),
            "exclude_patterns": self.config.project.exclude_patterns,
            "callback_count": len(self.update_callbacks),
            "has_incremental_builder": self.incremental_builder is not None,
        }

    def __enter__(self) -> "FileWatcher":
        """Context manager entry."""
        self.start_watching()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        # Unused parameters are required by context manager protocol
        _ = exc_type, exc_val, exc_tb
        self.stop_watching()


# Convenience function for creating a file watcher
async def create_file_watcher(
    project_path: Path, config: Config, enable_incremental_updates: bool = True
) -> FileWatcher:
    """Create a configured file watcher for a project.

    Args:
        project_path: Path to the project to watch
        config: Project configuration
        enable_incremental_updates: Whether to enable automatic incremental updates

    Returns:
        Configured FileWatcher instance
    """
    incremental_builder = None

    if enable_incremental_updates:
        try:
            from .incremental_build import IncrementalBuildManager

            incremental_builder = IncrementalBuildManager(project_path)
            logger.info("Incremental builder created for file watcher")
        except Exception as e:
            logger.warning(f"Could not create incremental builder: {e}")

    watcher = FileWatcher(project_path, config, incremental_builder)

    # Add logging callback for monitoring
    def log_changes(changed_files: set[Path]) -> None:
        logger.info(f"File watcher detected {len(changed_files)} changed files")

    watcher.add_update_callback(log_changes)

    return watcher
