"""Tests for progress tracking functionality."""

# Remove unused import time
from unittest.mock import Mock, patch

import pytest

from utils.progress_tracker import (
    ProgressFormatter,
    ProgressInfo,
    ProgressStatus,
    ProgressTracker,
    get_global_tracker,
    track_operation,
    track_progress,
)


class TestProgressInfo:
    """Test cases for ProgressInfo."""

    def test_initialization(self):
        """Test progress info initialization."""
        progress = ProgressInfo(name="test_operation", total=100, message="Testing...")

        assert progress.name == "test_operation"
        assert progress.status == ProgressStatus.PENDING
        assert progress.current == 0
        assert progress.total == 100
        assert progress.message == "Testing..."
        assert progress.start_time is None
        assert progress.end_time is None
        assert progress.elapsed_time == 0.0
        assert progress.estimated_remaining is None
        assert progress.parent is None
        assert progress.children == []
        assert progress.metadata == {}

    def test_progress_percentage(self):
        """Test progress percentage calculation."""
        progress = ProgressInfo(name="test", total=100, current=25)
        assert progress.progress_percentage == 25.0

        progress.current = 50
        assert progress.progress_percentage == 50.0

        # Test edge cases
        progress.total = 0
        assert progress.progress_percentage == 0.0

        progress.total = 100
        progress.current = 150  # Over 100%
        assert progress.progress_percentage == 100.0

    def test_is_complete(self):
        """Test completion status checking."""
        progress = ProgressInfo(name="test")

        assert not progress.is_complete

        progress.status = ProgressStatus.COMPLETED
        assert progress.is_complete

        progress.status = ProgressStatus.FAILED
        assert progress.is_complete

        progress.status = ProgressStatus.CANCELLED
        assert progress.is_complete

        progress.status = ProgressStatus.RUNNING
        assert not progress.is_complete

    def test_is_running(self):
        """Test running status checking."""
        progress = ProgressInfo(name="test")

        assert not progress.is_running

        progress.status = ProgressStatus.RUNNING
        assert progress.is_running

        progress.status = ProgressStatus.COMPLETED
        assert not progress.is_running

    def test_to_dict(self):
        """Test conversion to dictionary."""
        progress = ProgressInfo(
            name="test_operation",
            status=ProgressStatus.RUNNING,
            current=25,
            total=100,
            message="Working...",
            start_time=1000.0,
            elapsed_time=5.0,
            parent="parent_op",
            children=["child1", "child2"],
            metadata={"key": "value"},
        )

        result = progress.to_dict()

        assert result["name"] == "test_operation"
        assert result["status"] == "running"
        assert result["current"] == 25
        assert result["total"] == 100
        assert result["progress_percentage"] == 25.0
        assert result["message"] == "Working..."
        assert result["start_time"] == 1000.0
        assert result["elapsed_time"] == 5.0
        assert result["parent"] == "parent_op"
        assert result["children"] == ["child1", "child2"]
        assert result["metadata"] == {"key": "value"}
        assert result["is_complete"] is False
        assert result["is_running"] is True


class TestProgressTracker:
    """Test cases for ProgressTracker."""

    def test_initialization(self):
        """Test tracker initialization."""
        tracker = ProgressTracker()

        assert tracker._operations == {}
        assert tracker._update_callbacks == []

    def test_start_operation(self):
        """Test starting an operation."""
        tracker = ProgressTracker()

        with patch("time.time", return_value=1000.0):
            progress = tracker.start_operation(
                name="test_op",
                total=100,
                message="Starting...",
                metadata={"type": "test"},
            )

        assert progress.name == "test_op"
        assert progress.status == ProgressStatus.RUNNING
        assert progress.total == 100
        assert progress.message == "Starting..."
        assert progress.start_time == 1000.0
        assert progress.metadata == {"type": "test"}

        # Verify it's stored in tracker
        assert "test_op" in tracker._operations
        assert tracker._operations["test_op"] is progress

    def test_start_operation_duplicate_name(self):
        """Test starting operation with duplicate name."""
        tracker = ProgressTracker()

        tracker.start_operation("test_op", total=100)

        with pytest.raises(ValueError, match="Operation 'test_op' already exists"):
            tracker.start_operation("test_op", total=50)

    def test_start_operation_with_parent(self):
        """Test starting operation with parent."""
        tracker = ProgressTracker()

        parent_progress = tracker.start_operation("parent_op", total=10)
        child_progress = tracker.start_operation(
            "child_op", total=5, parent="parent_op"
        )

        assert child_progress.parent == "parent_op"
        assert "child_op" in parent_progress.children

    def test_update_progress_current(self):
        """Test updating progress with current value."""
        tracker = ProgressTracker()

        with patch("time.time", side_effect=[1000.0, 1005.0]):
            tracker.start_operation("test_op", total=100)
            progress = tracker.update_progress(
                "test_op", current=25, message="25% done"
            )

        assert progress.current == 25
        assert progress.message == "25% done"
        assert progress.elapsed_time == 5.0

    def test_update_progress_increment(self):
        """Test updating progress with increment."""
        tracker = ProgressTracker()

        tracker.start_operation("test_op", total=100)
        tracker.update_progress("test_op", current=20)
        progress = tracker.update_progress("test_op", increment=5)

        assert progress.current == 25

    def test_update_progress_with_metadata(self):
        """Test updating progress with metadata."""
        tracker = ProgressTracker()

        tracker.start_operation("test_op", total=100, metadata={"stage": "init"})
        progress = tracker.update_progress(
            "test_op", metadata={"stage": "processing", "files": 10}
        )

        assert progress.metadata["stage"] == "processing"
        assert progress.metadata["files"] == 10

    def test_update_progress_nonexistent(self):
        """Test updating nonexistent operation."""
        tracker = ProgressTracker()

        with pytest.raises(KeyError, match="Operation 'nonexistent' not found"):
            tracker.update_progress("nonexistent", current=50)

    def test_update_progress_time_estimation(self):
        """Test time estimation during progress update."""
        tracker = ProgressTracker()

        with patch("time.time", side_effect=[1000.0, 1010.0]):
            tracker.start_operation("test_op", total=100)
            progress = tracker.update_progress("test_op", current=20)

        # Rate: 20 items in 10 seconds = 2 items/second
        # Remaining: 80 items / 2 items/second = 40 seconds
        assert progress.estimated_remaining == 40.0

    def test_complete_operation(self):
        """Test completing an operation."""
        tracker = ProgressTracker()

        with patch("time.time", side_effect=[1000.0, 1015.0]):
            tracker.start_operation("test_op", total=100)
            progress = tracker.complete_operation(
                "test_op", ProgressStatus.COMPLETED, "Finished!"
            )

        assert progress.status == ProgressStatus.COMPLETED
        assert progress.message == "Finished!"
        assert progress.end_time == 1015.0
        assert progress.elapsed_time == 15.0
        assert progress.is_complete is True

    def test_complete_operation_indeterminate(self):
        """Test completing indeterminate operation."""
        tracker = ProgressTracker()

        tracker.start_operation("test_op", total=0)
        progress = tracker.complete_operation("test_op", ProgressStatus.COMPLETED)

        # Should set current and total to 1 for visual completion
        assert progress.current == 1
        assert progress.total == 1
        assert progress.progress_percentage == 100.0

    def test_complete_operation_invalid_status(self):
        """Test completing operation with invalid status."""
        tracker = ProgressTracker()

        tracker.start_operation("test_op", total=100)

        with pytest.raises(ValueError, match="Invalid completion status"):
            tracker.complete_operation("test_op", ProgressStatus.RUNNING)

    def test_complete_operation_nonexistent(self):
        """Test completing nonexistent operation."""
        tracker = ProgressTracker()

        with pytest.raises(KeyError, match="Operation 'nonexistent' not found"):
            tracker.complete_operation("nonexistent", ProgressStatus.COMPLETED)

    def test_get_operation(self):
        """Test getting operation info."""
        tracker = ProgressTracker()

        progress = tracker.start_operation("test_op", total=100)

        retrieved = tracker.get_operation("test_op")
        assert retrieved is progress

        nonexistent = tracker.get_operation("nonexistent")
        assert nonexistent is None

    def test_get_all_operations(self):
        """Test getting all operations."""
        tracker = ProgressTracker()

        tracker.start_operation("op1", total=100)
        tracker.start_operation("op2", total=50)

        all_ops = tracker.get_all_operations()
        assert len(all_ops) == 2
        assert "op1" in all_ops
        assert "op2" in all_ops

    def test_get_active_operations(self):
        """Test getting only active operations."""
        tracker = ProgressTracker()

        tracker.start_operation("active_op", total=100)
        tracker.start_operation("completed_op", total=50)
        tracker.complete_operation("completed_op", ProgressStatus.COMPLETED)

        active_ops = tracker.get_active_operations()
        assert len(active_ops) == 1
        assert "active_op" in active_ops
        assert "completed_op" not in active_ops

    def test_get_operation_tree_single_level(self):
        """Test getting operation tree with single level."""
        tracker = ProgressTracker()

        tracker.start_operation("op1", total=100)
        tracker.start_operation("op2", total=50)

        tree = tracker.get_operation_tree()

        assert "children" in tree
        assert len(tree["children"]) == 2
        assert "op1" in tree["children"]
        assert "op2" in tree["children"]

    def test_get_operation_tree_nested(self):
        """Test getting operation tree with nested operations."""
        tracker = ProgressTracker()

        tracker.start_operation("parent", total=100)
        tracker.start_operation("child1", total=30, parent="parent")
        tracker.start_operation("child2", total=20, parent="parent")

        tree = tracker.get_operation_tree("parent")

        assert tree["name"] == "parent"
        assert len(tree["children"]) == 2
        assert "child1" in tree["children"]
        assert "child2" in tree["children"]

    def test_get_operation_tree_nonexistent(self):
        """Test getting tree for nonexistent operation."""
        tracker = ProgressTracker()

        tree = tracker.get_operation_tree("nonexistent")
        assert tree == {}

    def test_update_callbacks(self):
        """Test progress update callbacks."""
        tracker = ProgressTracker()
        callback1 = Mock()
        callback2 = Mock()

        tracker.add_update_callback(callback1)
        tracker.add_update_callback(callback2)

        progress = tracker.start_operation("test_op", total=100)

        callback1.assert_called_once_with("test_op", progress)
        callback2.assert_called_once_with("test_op", progress)

        # Test removing callback
        tracker.remove_update_callback(callback1)
        callback1.reset_mock()
        callback2.reset_mock()

        tracker.update_progress("test_op", current=50)

        callback1.assert_not_called()
        callback2.assert_called_once()

    def test_callback_error_handling(self):
        """Test handling of callback errors."""
        tracker = ProgressTracker()

        error_callback = Mock(side_effect=Exception("Callback error"))
        success_callback = Mock()

        tracker.add_update_callback(error_callback)
        tracker.add_update_callback(success_callback)

        with patch("utils.progress_tracker.logger") as mock_logger:
            tracker.start_operation("test_op", total=100)

        # Error should be logged but not propagated
        mock_logger.error.assert_called_once()
        success_callback.assert_called_once()

    def test_clear_completed(self):
        """Test clearing completed operations."""
        tracker = ProgressTracker()

        # Create operations with different statuses
        tracker.start_operation("running_op", total=100)
        tracker.start_operation("completed_op", total=50)
        tracker.start_operation("failed_op", total=25)
        tracker.start_operation("parent_op", total=10)
        tracker.start_operation("child_op", total=5, parent="parent_op")

        # Complete some operations
        tracker.complete_operation("completed_op", ProgressStatus.COMPLETED)
        tracker.complete_operation("failed_op", ProgressStatus.FAILED)
        tracker.complete_operation("child_op", ProgressStatus.COMPLETED)

        cleared_count = tracker.clear_completed()

        assert cleared_count == 3
        remaining_ops = tracker.get_all_operations()
        assert len(remaining_ops) == 2
        assert "running_op" in remaining_ops
        assert "parent_op" in remaining_ops

        # Check that child was removed from parent's children list
        parent = remaining_ops["parent_op"]
        assert "child_op" not in parent.children

    def test_cancel_operation(self):
        """Test cancelling an operation."""
        tracker = ProgressTracker()

        tracker.start_operation("test_op", total=100)

        success = tracker.cancel_operation("test_op", "User cancelled")
        assert success is True

        progress = tracker.get_operation("test_op")
        assert progress is not None
        assert progress.status == ProgressStatus.CANCELLED
        assert progress.message == "User cancelled"

    def test_cancel_nonexistent_operation(self):
        """Test cancelling nonexistent operation."""
        tracker = ProgressTracker()

        success = tracker.cancel_operation("nonexistent")
        assert success is False

    def test_cancel_completed_operation(self):
        """Test cancelling already completed operation."""
        tracker = ProgressTracker()

        tracker.start_operation("test_op", total=100)
        tracker.complete_operation("test_op", ProgressStatus.COMPLETED)

        success = tracker.cancel_operation("test_op")
        assert success is False

    def test_get_summary(self):
        """Test getting summary statistics."""
        tracker = ProgressTracker()

        # Create operations with different statuses
        tracker.start_operation("running_op", total=100)
        tracker.update_progress("running_op", current=30)

        tracker.start_operation("completed_op", total=50)
        tracker.update_progress("completed_op", current=50)
        tracker.complete_operation("completed_op", ProgressStatus.COMPLETED)

        tracker.start_operation("failed_op", total=25)
        tracker.update_progress("failed_op", current=10)
        tracker.complete_operation("failed_op", ProgressStatus.FAILED)

        tracker.start_operation("indeterminate_op", total=0)

        summary = tracker.get_summary()

        assert summary["total_operations"] == 4
        assert summary["running_operations"] == 2  # running_op and indeterminate_op
        assert summary["completed_operations"] == 1
        assert summary["failed_operations"] == 1
        assert summary["cancelled_operations"] == 0
        assert summary["total_items"] == 175  # 100 + 50 + 25
        assert summary["completed_items"] == 90  # 30 + 50 + 10
        assert summary["overall_progress_percentage"] == pytest.approx(51.43, abs=0.01)


class TestContextManagerAndDecorators:
    """Test cases for context managers and decorators."""

    def test_track_progress_context_manager_success(self):
        """Test track_progress context manager with successful execution."""
        tracker = ProgressTracker()

        with patch("time.time", side_effect=[1000.0, 1010.0, 1015.0]):
            with track_progress(
                tracker, "test_context", total=100, message="Testing"
            ) as progress:
                assert progress.name == "test_context"
                assert progress.status == ProgressStatus.RUNNING
                tracker.update_progress("test_context", current=50)

        # Should be completed after context
        final_progress = tracker.get_operation("test_context")
        assert final_progress is not None
        assert final_progress.status == ProgressStatus.COMPLETED

    def test_track_progress_context_manager_exception(self):
        """Test track_progress context manager with exception."""
        tracker = ProgressTracker()

        with pytest.raises(ValueError):
            with track_progress(tracker, "test_context", total=100):
                raise ValueError("Test error")

        # Should be marked as failed
        progress = tracker.get_operation("test_context")
        assert progress is not None
        assert progress.status == ProgressStatus.FAILED
        assert "Test error" in progress.message

    def test_track_operation_decorator(self):
        """Test track_operation decorator."""
        tracker = ProgressTracker()

        @track_operation("test_function", total=10, tracker=tracker)
        def test_function(x, y):
            return x + y

        result = test_function(2, 3)

        assert result == 5
        progress = tracker.get_operation("test_function")
        assert progress is not None
        assert progress.status == ProgressStatus.COMPLETED

    def test_track_operation_decorator_global_tracker(self):
        """Test track_operation decorator with global tracker."""
        # Clear global tracker
        import utils.progress_tracker

        utils.progress_tracker._global_tracker = None

        @track_operation("global_test", total=5)
        def test_function():
            return "test_result"

        result = test_function()

        assert result == "test_result"

        # Check global tracker was used
        global_tracker = get_global_tracker()
        progress = global_tracker.get_operation("global_test")
        assert progress is not None
        assert progress.status == ProgressStatus.COMPLETED

    def test_get_global_tracker_singleton(self):
        """Test that get_global_tracker returns singleton."""
        # Clear global tracker
        import utils.progress_tracker

        utils.progress_tracker._global_tracker = None

        tracker1 = get_global_tracker()
        tracker2 = get_global_tracker()

        assert tracker1 is tracker2
        assert isinstance(tracker1, ProgressTracker)


class TestProgressFormatter:
    """Test cases for ProgressFormatter."""

    def test_format_progress_bar_determinate(self):
        """Test formatting determinate progress bar."""
        progress = ProgressInfo(name="test", total=100, current=25)

        bar = ProgressFormatter.format_progress_bar(progress, width=20)

        # Should have 5 filled chars (25% of 20) and 15 empty chars
        assert "█" * 5 in bar
        assert "░" * 15 in bar
        assert "25.0%" in bar

    def test_format_progress_bar_indeterminate(self):
        """Test formatting indeterminate progress bar."""
        progress = ProgressInfo(name="test", total=0, current=0)

        bar = ProgressFormatter.format_progress_bar(progress, width=20)

        assert "Working..." in bar

    def test_format_progress_bar_custom_chars(self):
        """Test formatting progress bar with custom characters."""
        progress = ProgressInfo(name="test", total=100, current=50)

        bar = ProgressFormatter.format_progress_bar(
            progress, width=10, fill_char="#", empty_char="-"
        )

        assert "#" * 5 in bar
        assert "-" * 5 in bar

    def test_format_time_estimate_with_remaining(self):
        """Test formatting time estimate with remaining time."""
        progress = ProgressInfo(name="test", elapsed_time=10.5, estimated_remaining=5.2)

        time_str = ProgressFormatter.format_time_estimate(progress)

        assert "10.5s" in time_str
        assert "5.2s" in time_str
        assert "Elapsed:" in time_str
        assert "Remaining:" in time_str

    def test_format_time_estimate_no_remaining(self):
        """Test formatting time estimate without remaining time."""
        progress = ProgressInfo(name="test", elapsed_time=15.0)

        time_str = ProgressFormatter.format_time_estimate(progress)

        assert "15.0s" in time_str
        assert "Elapsed:" in time_str
        assert "Remaining:" not in time_str

    def test_format_operation_status_complete(self):
        """Test formatting complete operation status."""
        progress = ProgressInfo(
            name="test_operation",
            status=ProgressStatus.RUNNING,
            total=100,
            current=75,
            message="Processing files",
            elapsed_time=10.0,
            estimated_remaining=3.3,
        )

        status = ProgressFormatter.format_operation_status(progress)

        assert "test_operation: Processing files" in status
        assert "75.0%" in status
        assert "10.0s" in status
        assert "3.3s" in status

    def test_format_operation_status_no_bar(self):
        """Test formatting operation status without progress bar."""
        progress = ProgressInfo(name="test_operation", message="Starting up")

        status = ProgressFormatter.format_operation_status(progress, include_bar=False)

        assert status == "test_operation: Starting up"
        assert "%" not in status

    def test_format_operation_status_completed(self):
        """Test formatting completed operation status."""
        progress = ProgressInfo(
            name="test_operation", status=ProgressStatus.COMPLETED, message="Done!"
        )

        status = ProgressFormatter.format_operation_status(progress)

        assert "test_operation: Done!" in status
        # Should not include time info for completed operations
        assert "Elapsed:" not in status
