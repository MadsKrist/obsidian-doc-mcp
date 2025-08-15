"""Progress tracking and indicators for long-running operations.

This module provides progress tracking capabilities with support for nested operations,
time estimation, and real-time updates for documentation generation tasks.
"""

import logging
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ProgressStatus(Enum):
    """Status of a progress-tracked operation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProgressInfo:
    """Information about progress of an operation."""

    name: str
    status: ProgressStatus = ProgressStatus.PENDING
    current: int = 0
    total: int = 0
    message: str = ""
    start_time: float | None = None
    end_time: float | None = None
    elapsed_time: float = 0.0
    estimated_remaining: float | None = None
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage."""
        if self.total <= 0:
            return 0.0
        return min(100.0, (self.current / self.total) * 100.0)

    @property
    def is_complete(self) -> bool:
        """Check if operation is complete."""
        return self.status in {
            ProgressStatus.COMPLETED,
            ProgressStatus.FAILED,
            ProgressStatus.CANCELLED,
        }

    @property
    def is_running(self) -> bool:
        """Check if operation is currently running."""
        return self.status == ProgressStatus.RUNNING

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "status": self.status.value,
            "current": self.current,
            "total": self.total,
            "progress_percentage": self.progress_percentage,
            "message": self.message,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "elapsed_time": self.elapsed_time,
            "estimated_remaining": self.estimated_remaining,
            "parent": self.parent,
            "children": self.children.copy(),
            "metadata": self.metadata.copy(),
            "is_complete": self.is_complete,
            "is_running": self.is_running,
        }


class ProgressTracker:
    """Tracks progress of multiple concurrent operations."""

    def __init__(self):
        """Initialize the progress tracker."""
        self._operations: dict[str, ProgressInfo] = {}
        self._update_callbacks: list[Callable[[str, ProgressInfo], None]] = []
        self._lock = threading.RLock()

    def start_operation(
        self,
        name: str,
        total: int = 0,
        message: str = "",
        parent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProgressInfo:
        """Start tracking a new operation.

        Args:
            name: Unique name for the operation
            total: Total number of units to process (0 for indeterminate)
            message: Initial status message
            parent: Name of parent operation for nested tracking
            metadata: Additional metadata for the operation

        Returns:
            ProgressInfo object for the started operation

        Raises:
            ValueError: If operation name already exists
        """
        with self._lock:
            if name in self._operations:
                raise ValueError(f"Operation '{name}' already exists")

            progress = ProgressInfo(
                name=name,
                status=ProgressStatus.RUNNING,
                total=total,
                message=message,
                start_time=time.time(),
                parent=parent,
                metadata=metadata or {},
            )

            self._operations[name] = progress

            # Add to parent's children if specified
            if parent and parent in self._operations:
                self._operations[parent].children.append(name)

            logger.debug(f"Started operation: {name} (total: {total})")
            self._notify_callbacks(name, progress)

            return progress

    def update_progress(
        self,
        name: str,
        current: int | None = None,
        increment: int | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProgressInfo:
        """Update progress of an existing operation.

        Args:
            name: Name of the operation to update
            current: Set current progress value
            increment: Increment current progress by this amount
            message: Update status message
            metadata: Update metadata (merges with existing)

        Returns:
            Updated ProgressInfo object

        Raises:
            KeyError: If operation doesn't exist
        """
        with self._lock:
            if name not in self._operations:
                raise KeyError(f"Operation '{name}' not found")

            progress = self._operations[name]

            if current is not None:
                progress.current = current
            elif increment is not None:
                progress.current += increment

            if message is not None:
                progress.message = message

            if metadata:
                progress.metadata.update(metadata)

            # Update elapsed time
            if progress.start_time:
                progress.elapsed_time = time.time() - progress.start_time

            # Estimate remaining time based on current progress
            if (
                progress.total > 0
                and progress.current > 0
                and progress.elapsed_time > 0
            ):
                rate = progress.current / progress.elapsed_time
                remaining_items = progress.total - progress.current
                progress.estimated_remaining = (
                    remaining_items / rate if rate > 0 else None
                )

            logger.debug(
                f"Updated operation: {name} ({progress.current}/{progress.total})"
            )
            self._notify_callbacks(name, progress)

            return progress

    def complete_operation(
        self,
        name: str,
        status: ProgressStatus = ProgressStatus.COMPLETED,
        message: str | None = None,
    ) -> ProgressInfo:
        """Mark an operation as complete.

        Args:
            name: Name of the operation to complete
            status: Final status (COMPLETED, FAILED, or CANCELLED)
            message: Final status message

        Returns:
            Final ProgressInfo object

        Raises:
            KeyError: If operation doesn't exist
            ValueError: If status is not a completion status
        """
        if status not in {
            ProgressStatus.COMPLETED,
            ProgressStatus.FAILED,
            ProgressStatus.CANCELLED,
        }:
            raise ValueError(f"Invalid completion status: {status}")

        with self._lock:
            if name not in self._operations:
                raise KeyError(f"Operation '{name}' not found")

            progress = self._operations[name]
            progress.status = status
            progress.end_time = time.time()

            if progress.start_time:
                progress.elapsed_time = progress.end_time - progress.start_time

            if message is not None:
                progress.message = message

            # If completing successfully and total was 0, set current to 1 for visual completion
            if status == ProgressStatus.COMPLETED and progress.total == 0:
                progress.current = 1
                progress.total = 1

            logger.debug(f"Completed operation: {name} ({status.value})")
            self._notify_callbacks(name, progress)

            return progress

    def get_operation(self, name: str) -> ProgressInfo | None:
        """Get progress information for an operation.

        Args:
            name: Name of the operation

        Returns:
            ProgressInfo object or None if not found
        """
        with self._lock:
            return self._operations.get(name)

    def get_all_operations(self) -> dict[str, ProgressInfo]:
        """Get all tracked operations.

        Returns:
            Dictionary of operation name to ProgressInfo
        """
        with self._lock:
            return self._operations.copy()

    def get_active_operations(self) -> dict[str, ProgressInfo]:
        """Get only running operations.

        Returns:
            Dictionary of active operation name to ProgressInfo
        """
        with self._lock:
            return {
                name: progress
                for name, progress in self._operations.items()
                if progress.is_running
            }

    def get_operation_tree(self, root: str | None = None) -> dict[str, Any]:
        """Get operations organized as a tree structure.

        Args:
            root: Root operation name (None for all top-level operations)

        Returns:
            Tree structure with operations and their children
        """
        with self._lock:
            if root:
                if root not in self._operations:
                    return {}
                return self._build_tree_node(root)
            else:
                # Get all top-level operations (no parent)
                top_level = [
                    name
                    for name, progress in self._operations.items()
                    if not progress.parent
                ]
                return {
                    "children": {
                        name: self._build_tree_node(name) for name in top_level
                    }
                }

    def _build_tree_node(self, name: str) -> dict[str, Any]:
        """Build a tree node for an operation and its children."""
        progress = self._operations[name]
        node = progress.to_dict()

        # Add children recursively
        if progress.children:
            node["children"] = {
                child_name: self._build_tree_node(child_name)
                for child_name in progress.children
                if child_name in self._operations
            }
        else:
            node["children"] = {}

        return node

    def add_update_callback(
        self, callback: Callable[[str, ProgressInfo], None]
    ) -> None:
        """Add a callback to be notified of progress updates.

        Args:
            callback: Function that takes (operation_name, progress_info)
        """
        with self._lock:
            self._update_callbacks.append(callback)

    def remove_update_callback(
        self, callback: Callable[[str, ProgressInfo], None]
    ) -> None:
        """Remove an update callback.

        Args:
            callback: Function to remove
        """
        with self._lock:
            if callback in self._update_callbacks:
                self._update_callbacks.remove(callback)

    def _notify_callbacks(self, name: str, progress: ProgressInfo) -> None:
        """Notify all registered callbacks of a progress update."""
        for callback in self._update_callbacks:
            try:
                callback(name, progress)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")

    def clear_completed(self) -> int:
        """Remove completed operations from tracking.

        Returns:
            Number of operations removed
        """
        with self._lock:
            to_remove = [
                name
                for name, progress in self._operations.items()
                if progress.is_complete
            ]

            for name in to_remove:
                # Remove from parent's children list
                progress = self._operations[name]
                if progress.parent and progress.parent in self._operations:
                    parent = self._operations[progress.parent]
                    if name in parent.children:
                        parent.children.remove(name)

                del self._operations[name]

            logger.debug(f"Cleared {len(to_remove)} completed operations")
            return len(to_remove)

    def cancel_operation(self, name: str, message: str = "Operation cancelled") -> bool:
        """Cancel a running operation.

        Args:
            name: Name of the operation to cancel
            message: Cancellation message

        Returns:
            True if operation was cancelled, False if not found or already complete
        """
        with self._lock:
            if name not in self._operations:
                return False

            progress = self._operations[name]
            if progress.is_complete:
                return False

            self.complete_operation(name, ProgressStatus.CANCELLED, message)
            return True

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics of all operations.

        Returns:
            Dictionary with summary statistics
        """
        with self._lock:
            total_ops = len(self._operations)
            running_ops = len(self.get_active_operations())
            completed_ops = len(
                [
                    p
                    for p in self._operations.values()
                    if p.status == ProgressStatus.COMPLETED
                ]
            )
            failed_ops = len(
                [
                    p
                    for p in self._operations.values()
                    if p.status == ProgressStatus.FAILED
                ]
            )
            cancelled_ops = len(
                [
                    p
                    for p in self._operations.values()
                    if p.status == ProgressStatus.CANCELLED
                ]
            )

            # Calculate overall progress for determinate operations
            total_items = sum(p.total for p in self._operations.values() if p.total > 0)
            completed_items = sum(
                p.current for p in self._operations.values() if p.total > 0
            )
            overall_progress = (
                (completed_items / total_items * 100) if total_items > 0 else 0.0
            )

            return {
                "total_operations": total_ops,
                "running_operations": running_ops,
                "completed_operations": completed_ops,
                "failed_operations": failed_ops,
                "cancelled_operations": cancelled_ops,
                "overall_progress_percentage": overall_progress,
                "total_items": total_items,
                "completed_items": completed_items,
            }


@contextmanager
def track_progress(
    tracker: ProgressTracker,
    name: str,
    total: int = 0,
    message: str = "",
    parent: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Context manager for tracking an operation's progress.

    Args:
        tracker: ProgressTracker instance
        name: Unique name for the operation
        total: Total number of units to process
        message: Initial status message
        parent: Name of parent operation
        metadata: Additional metadata

    Yields:
        ProgressInfo object for updating progress
    """
    progress = tracker.start_operation(name, total, message, parent, metadata)

    try:
        yield progress
        tracker.complete_operation(name, ProgressStatus.COMPLETED)
    except Exception as e:
        tracker.complete_operation(
            name, ProgressStatus.FAILED, f"Operation failed: {str(e)}"
        )
        raise


# Global progress tracker instance
_global_tracker: ProgressTracker | None = None


def get_global_tracker() -> ProgressTracker:
    """Get or create the global progress tracker."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = ProgressTracker()
    return _global_tracker


def track_operation(
    name: str,
    total: int = 0,
    message: str = "",
    parent: str | None = None,
    metadata: dict[str, Any] | None = None,
    tracker: ProgressTracker | None = None,
):
    """Decorator for tracking function execution progress.

    Args:
        name: Name for the operation
        total: Total units to process
        message: Initial message
        parent: Parent operation name
        metadata: Additional metadata
        tracker: ProgressTracker instance (uses global if None)

    Returns:
        Decorated function
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            t = tracker or get_global_tracker()

            with track_progress(t, name, total, message, parent, metadata):
                result = func(*args, **kwargs)

            return result

        return wrapper

    return decorator


class ProgressFormatter:
    """Formats progress information for display."""

    @staticmethod
    def format_progress_bar(
        progress: ProgressInfo,
        width: int = 40,
        fill_char: str = "█",
        empty_char: str = "░",
    ) -> str:
        """Format a progress bar for console display.

        Args:
            progress: ProgressInfo to format
            width: Width of the progress bar
            fill_char: Character for completed portion
            empty_char: Character for remaining portion

        Returns:
            Formatted progress bar string
        """
        if progress.total <= 0:
            # Indeterminate progress - show spinner or simple indicator
            return f"[{'Working...':<{width}}]"

        percentage = progress.progress_percentage
        filled_width = int(width * percentage / 100)
        bar = fill_char * filled_width + empty_char * (width - filled_width)

        return f"[{bar}] {percentage:5.1f}%"

    @staticmethod
    def format_time_estimate(progress: ProgressInfo) -> str:
        """Format time information for display.

        Args:
            progress: ProgressInfo to format

        Returns:
            Formatted time string
        """
        elapsed = f"{progress.elapsed_time:.1f}s"

        if progress.estimated_remaining:
            remaining = f"{progress.estimated_remaining:.1f}s"
            return f"Elapsed: {elapsed}, Remaining: ~{remaining}"
        else:
            return f"Elapsed: {elapsed}"

    @staticmethod
    def format_operation_status(
        progress: ProgressInfo, include_bar: bool = True
    ) -> str:
        """Format complete operation status.

        Args:
            progress: ProgressInfo to format
            include_bar: Whether to include progress bar

        Returns:
            Formatted status string
        """
        status_line = f"{progress.name}: {progress.message}"

        if include_bar and progress.total > 0:
            bar = ProgressFormatter.format_progress_bar(progress)
            status_line += f" {bar}"

        if progress.is_running:
            time_info = ProgressFormatter.format_time_estimate(progress)
            status_line += f" ({time_info})"

        return status_line
