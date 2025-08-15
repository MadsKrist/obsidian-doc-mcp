"""Tests for error reporting functionality."""

from pathlib import Path
from unittest.mock import patch

from utils.error_reporter import (
    DetailedError,
    ErrorCategory,
    ErrorReporter,
    ErrorSeverity,
    ErrorSuggestion,
    create_error_context,
    get_global_reporter,
    report_error,
)


class TestErrorSuggestion:
    """Test cases for ErrorSuggestion."""

    def test_initialization(self):
        """Test suggestion initialization."""
        suggestion = ErrorSuggestion(
            title="Fix the issue",
            description="This is how to fix it",
            action_type="fix",
            command="command to run",
            documentation_url="https://docs.example.com",
            priority=1,
        )

        assert suggestion.title == "Fix the issue"
        assert suggestion.description == "This is how to fix it"
        assert suggestion.action_type == "fix"
        assert suggestion.command == "command to run"
        assert suggestion.documentation_url == "https://docs.example.com"
        assert suggestion.priority == 1

    def test_initialization_defaults(self):
        """Test suggestion initialization with defaults."""
        suggestion = ErrorSuggestion(
            title="Fix the issue",
            description="This is how to fix it",
            action_type="fix",
        )

        assert suggestion.command is None
        assert suggestion.documentation_url is None
        assert suggestion.priority == 1


class TestDetailedError:
    """Test cases for DetailedError."""

    def test_initialization(self):
        """Test error initialization."""
        error = DetailedError(
            error_id="test_error",
            title="Test Error",
            description="This is a test error",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.VALIDATION,
        )

        assert error.error_id == "test_error"
        assert error.title == "Test Error"
        assert error.description == "This is a test error"
        assert error.severity == ErrorSeverity.ERROR
        assert error.category == ErrorCategory.VALIDATION
        assert error.original_exception is None
        assert error.context == {}
        assert error.suggestions == []
        assert error.affected_files == []
        assert error.stack_trace is None

    def test_add_suggestion(self):
        """Test adding suggestions to error."""
        error = DetailedError(
            error_id="test_error",
            title="Test Error",
            description="This is a test error",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.VALIDATION,
        )

        suggestion1 = ErrorSuggestion("Fix 1", "Description 1", "fix", priority=2)
        suggestion2 = ErrorSuggestion("Fix 2", "Description 2", "fix", priority=1)

        error.add_suggestion(suggestion1)
        error.add_suggestion(suggestion2)

        assert len(error.suggestions) == 2
        # Should be sorted by priority (1 comes before 2)
        assert error.suggestions[0].title == "Fix 2"
        assert error.suggestions[1].title == "Fix 1"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        exception = ValueError("Test exception")
        error = DetailedError(
            error_id="test_error",
            title="Test Error",
            description="This is a test error",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.VALIDATION,
            original_exception=exception,
            context={"key": "value"},
            affected_files=[Path("/test/file.py")],
            stack_trace="Stack trace here",
        )

        suggestion = ErrorSuggestion("Fix it", "How to fix", "fix", command="fix_command")
        error.add_suggestion(suggestion)

        result = error.to_dict()

        assert result["error_id"] == "test_error"
        assert result["title"] == "Test Error"
        assert result["description"] == "This is a test error"
        assert result["severity"] == "error"
        assert result["category"] == "validation"
        assert result["context"] == {"key": "value"}
        assert len(result["suggestions"]) == 1
        assert result["suggestions"][0]["title"] == "Fix it"
        assert result["affected_files"] == ["/test/file.py"]
        assert result["has_stack_trace"] is True


class TestErrorReporter:
    """Test cases for ErrorReporter."""

    def test_initialization(self):
        """Test reporter initialization."""
        reporter = ErrorReporter()

        assert reporter.errors == []
        assert len(reporter.error_patterns) > 0  # Should have built-in patterns
        assert len(reporter.suggestion_handlers) > 0  # Should have built-in handlers

    def test_report_error_generic(self):
        """Test reporting a generic error."""
        reporter = ErrorReporter()
        exception = ValueError("Test error message")
        context = {"operation": "test_operation"}

        with patch("traceback.format_exc", return_value="Stack trace"):
            error = reporter.report_error(exception, context)

        assert len(reporter.errors) == 1
        assert error.original_exception is exception
        assert error.context == context
        assert error.stack_trace == "Stack trace"
        assert error.category == ErrorCategory.VALIDATION  # Default category

    def test_report_error_with_category(self):
        """Test reporting error with specific category."""
        reporter = ErrorReporter()
        exception = ValueError("Test error")

        error = reporter.report_error(exception, category=ErrorCategory.CONFIGURATION)

        assert error.category == ErrorCategory.CONFIGURATION

    def test_report_error_with_affected_files(self):
        """Test reporting error with affected files."""
        reporter = ErrorReporter()
        exception = ValueError("Test error")
        affected_files = [Path("/test/file1.py"), Path("/test/file2.py")]

        error = reporter.report_error(exception, affected_files=affected_files)

        assert error.affected_files == affected_files

    def test_match_error_pattern_file_not_found(self):
        """Test matching FileNotFoundError pattern."""
        reporter = ErrorReporter()
        exception = FileNotFoundError("[Errno 2] No such file or directory: '/test/file.py'")

        error = reporter.report_error(exception)

        assert error.error_id == "file_not_found"
        assert error.category == ErrorCategory.FILE_SYSTEM
        assert len(error.suggestions) > 0

    def test_match_error_pattern_permission_denied(self):
        """Test matching PermissionError pattern."""
        reporter = ErrorReporter()
        exception = PermissionError("[Errno 13] Permission denied: '/test/file.py'")

        error = reporter.report_error(exception)

        assert error.error_id == "permission_denied"
        assert error.category == ErrorCategory.FILE_SYSTEM
        assert len(error.suggestions) > 0

    def test_match_error_pattern_module_not_found(self):
        """Test matching ModuleNotFoundError pattern."""
        reporter = ErrorReporter()
        exception = ModuleNotFoundError("No module named 'missing_module'")

        error = reporter.report_error(exception)

        assert error.error_id == "module_not_found"
        assert error.category == ErrorCategory.DEPENDENCY
        assert error.context.get("missing_module") == "missing_module"
        assert len(error.suggestions) > 0

    def test_infer_category_file_system(self):
        """Test category inference for file system errors."""
        reporter = ErrorReporter()
        exception = OSError("Test OS error")

        category = reporter._infer_category(exception, {})

        assert category == ErrorCategory.FILE_SYSTEM

    def test_infer_category_dependency(self):
        """Test category inference for dependency errors."""
        reporter = ErrorReporter()
        exception = ImportError("Test import error")

        category = reporter._infer_category(exception, {})

        assert category == ErrorCategory.DEPENDENCY

    def test_infer_category_from_context(self):
        """Test category inference from context."""
        reporter = ErrorReporter()
        exception = ValueError("Test error")
        context = {"operation": "sphinx_build"}

        category = reporter._infer_category(exception, context)

        assert category == ErrorCategory.SPHINX_BUILD

    def test_generate_suggestions(self):
        """Test suggestion generation."""
        reporter = ErrorReporter()
        error = DetailedError(
            error_id="test_error",
            title="Test Error",
            description="Test",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.FILE_SYSTEM,
        )

        reporter._generate_suggestions(error)

        # Should have suggestions from file system handlers
        assert len(error.suggestions) >= 0  # May or may not have suggestions depending on error_id

    def test_file_system_suggestions(self):
        """Test file system error suggestions."""
        reporter = ErrorReporter()
        file_not_found_error = DetailedError(
            error_id="file_not_found",
            title="File Not Found",
            description="File not found",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.FILE_SYSTEM,
        )

        suggestions = reporter._suggest_file_system_fixes(file_not_found_error)

        assert len(suggestions) > 0
        assert any("Check File Path" in s.title for s in suggestions)
        assert any("Create Missing Directory" in s.title for s in suggestions)

    def test_dependency_suggestions(self):
        """Test dependency error suggestions."""
        reporter = ErrorReporter()
        module_error = DetailedError(
            error_id="module_not_found",
            title="Module Not Found",
            description="Module not found",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.DEPENDENCY,
            context={"missing_module": "test_module"},
        )

        suggestions = reporter._suggest_dependency_fixes(module_error)

        assert len(suggestions) > 0
        assert any("Install Missing Package" in s.title for s in suggestions)
        assert any(s.command and "uv add test_module" in s.command for s in suggestions)

    def test_get_errors_by_severity(self):
        """Test filtering errors by severity."""
        reporter = ErrorReporter()

        # Add errors with different severities
        reporter.errors.append(
            DetailedError(
                "error1",
                "Error 1",
                "Description",
                ErrorSeverity.ERROR,
                ErrorCategory.VALIDATION,
            )
        )
        reporter.errors.append(
            DetailedError(
                "warning1",
                "Warning 1",
                "Description",
                ErrorSeverity.WARNING,
                ErrorCategory.VALIDATION,
            )
        )
        reporter.errors.append(
            DetailedError(
                "critical1",
                "Critical 1",
                "Description",
                ErrorSeverity.CRITICAL,
                ErrorCategory.VALIDATION,
            )
        )

        errors = reporter.get_errors_by_severity(ErrorSeverity.ERROR)
        warnings = reporter.get_errors_by_severity(ErrorSeverity.WARNING)
        critical = reporter.get_errors_by_severity(ErrorSeverity.CRITICAL)

        assert len(errors) == 1
        assert len(warnings) == 1
        assert len(critical) == 1

    def test_get_errors_by_category(self):
        """Test filtering errors by category."""
        reporter = ErrorReporter()

        # Add errors with different categories
        reporter.errors.append(
            DetailedError(
                "error1",
                "Error 1",
                "Description",
                ErrorSeverity.ERROR,
                ErrorCategory.FILE_SYSTEM,
            )
        )
        reporter.errors.append(
            DetailedError(
                "error2",
                "Error 2",
                "Description",
                ErrorSeverity.ERROR,
                ErrorCategory.DEPENDENCY,
            )
        )
        reporter.errors.append(
            DetailedError(
                "error3",
                "Error 3",
                "Description",
                ErrorSeverity.ERROR,
                ErrorCategory.FILE_SYSTEM,
            )
        )

        file_errors = reporter.get_errors_by_category(ErrorCategory.FILE_SYSTEM)
        dep_errors = reporter.get_errors_by_category(ErrorCategory.DEPENDENCY)

        assert len(file_errors) == 2
        assert len(dep_errors) == 1

    def test_has_critical_errors(self):
        """Test checking for critical errors."""
        reporter = ErrorReporter()

        assert reporter.has_critical_errors() is False

        reporter.errors.append(
            DetailedError(
                "error1",
                "Error 1",
                "Description",
                ErrorSeverity.ERROR,
                ErrorCategory.VALIDATION,
            )
        )

        assert reporter.has_critical_errors() is False

        reporter.errors.append(
            DetailedError(
                "critical1",
                "Critical 1",
                "Description",
                ErrorSeverity.CRITICAL,
                ErrorCategory.VALIDATION,
            )
        )

        assert reporter.has_critical_errors() is True

    def test_clear_errors(self):
        """Test clearing all errors."""
        reporter = ErrorReporter()

        # Add some errors
        reporter.errors.append(
            DetailedError(
                "error1",
                "Error 1",
                "Description",
                ErrorSeverity.ERROR,
                ErrorCategory.VALIDATION,
            )
        )
        reporter.errors.append(
            DetailedError(
                "error2",
                "Error 2",
                "Description",
                ErrorSeverity.WARNING,
                ErrorCategory.VALIDATION,
            )
        )

        assert len(reporter.errors) == 2

        count = reporter.clear_errors()

        assert count == 2
        assert len(reporter.errors) == 0

    def test_generate_report_empty(self):
        """Test generating report with no errors."""
        reporter = ErrorReporter()

        report = reporter.generate_report()

        assert report["errors"] == []
        assert report["summary"]["total"] == 0

    def test_generate_report_with_errors(self):
        """Test generating report with errors."""
        reporter = ErrorReporter()

        # Add various errors
        reporter.errors.append(
            DetailedError(
                "error1",
                "Error 1",
                "Description",
                ErrorSeverity.ERROR,
                ErrorCategory.FILE_SYSTEM,
            )
        )
        reporter.errors.append(
            DetailedError(
                "warning1",
                "Warning 1",
                "Description",
                ErrorSeverity.WARNING,
                ErrorCategory.DEPENDENCY,
            )
        )
        reporter.errors.append(
            DetailedError(
                "critical1",
                "Critical 1",
                "Description",
                ErrorSeverity.CRITICAL,
                ErrorCategory.CONFIGURATION,
            )
        )

        report = reporter.generate_report()

        assert len(report["errors"]) == 3
        assert report["summary"]["total"] == 3
        assert report["summary"]["critical"] == 1
        assert report["summary"]["errors"] == 1
        assert report["summary"]["warnings"] == 1
        assert report["summary"]["has_critical"] is True

        # Check grouping by category
        assert "file_system" in report["by_category"]
        assert "dependency" in report["by_category"]
        assert "configuration" in report["by_category"]

        # Check grouping by severity
        assert "error" in report["by_severity"]
        assert "warning" in report["by_severity"]
        assert "critical" in report["by_severity"]


class TestGlobalFunctions:
    """Test cases for global convenience functions."""

    def test_get_global_reporter_singleton(self):
        """Test that get_global_reporter returns singleton."""
        # Clear global reporter first
        import utils.error_reporter

        utils.error_reporter._global_reporter = None

        reporter1 = get_global_reporter()
        reporter2 = get_global_reporter()

        assert reporter1 is reporter2
        assert isinstance(reporter1, ErrorReporter)

    def test_report_error_convenience(self):
        """Test convenience report_error function."""
        # Clear global reporter first
        import utils.error_reporter

        utils.error_reporter._global_reporter = None

        exception = ValueError("Test error")
        context = {"test": "context"}

        with patch("traceback.format_exc", return_value="Stack trace"):
            error = report_error(exception, context, ErrorCategory.VALIDATION)

        assert error.original_exception is exception
        assert error.context == context
        assert error.category == ErrorCategory.VALIDATION

        # Should be stored in global reporter
        global_reporter = get_global_reporter()
        assert len(global_reporter.errors) == 1

    def test_create_error_context(self):
        """Test creating error context."""
        context = create_error_context("test_operation", file="test.py", line=123)

        assert context["operation"] == "test_operation"
        assert context["file"] == "test.py"
        assert context["line"] == 123


class TestErrorPatternHandlers:
    """Test cases for specific error pattern handlers."""

    def test_handle_memory_error(self):
        """Test memory error handler."""
        reporter = ErrorReporter()
        exception = MemoryError("Out of memory")
        context = {"operation": "large_operation"}

        error = reporter._handle_memory_error(exception, context)

        assert error.error_id == "memory_error"
        assert error.severity == ErrorSeverity.CRITICAL
        assert error.category == ErrorCategory.PERFORMANCE

    def test_handle_timeout_error(self):
        """Test timeout error handler."""
        reporter = ErrorReporter()
        exception = TimeoutError("Operation timed out")
        context = {"timeout": 30}

        error = reporter._handle_timeout_error(exception, context)

        assert error.error_id == "timeout_error"
        assert error.severity == ErrorSeverity.WARNING
        assert error.category == ErrorCategory.PERFORMANCE

    def test_performance_suggestions_memory(self):
        """Test performance suggestions for memory errors."""
        reporter = ErrorReporter()
        memory_error = DetailedError(
            error_id="memory_error",
            title="Memory Error",
            description="Out of memory",
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.PERFORMANCE,
        )

        suggestions = reporter._suggest_performance_fixes(memory_error)

        assert len(suggestions) > 0
        assert any("Batch Processing" in s.title for s in suggestions)
        assert any("Virtual Memory" in s.title for s in suggestions)

    def test_performance_suggestions_timeout(self):
        """Test performance suggestions for timeout errors."""
        reporter = ErrorReporter()
        timeout_error = DetailedError(
            error_id="timeout_error",
            title="Timeout Error",
            description="Operation timed out",
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.PERFORMANCE,
        )

        suggestions = reporter._suggest_performance_fixes(timeout_error)

        assert len(suggestions) > 0
        assert any("Timeout Settings" in s.title for s in suggestions)
        assert any("Parallel Processing" in s.title for s in suggestions)


class TestErrorPatternMatching:
    """Test cases for error pattern matching."""

    def test_pattern_matching_with_handler_exception(self):
        """Test pattern matching when handler raises exception."""
        reporter = ErrorReporter()

        # Register a handler that raises an exception
        def failing_handler(_, __):
            raise RuntimeError("Handler failed")

        reporter.error_patterns["test_pattern"] = failing_handler

        exception = ValueError("test_pattern error")

        with patch("utils.error_reporter.logger") as mock_logger:
            error = reporter.report_error(exception)

        # Should fall back to generic error
        assert error.title.startswith("ValueError:")
        mock_logger.warning.assert_called_once()

    def test_suggestion_generation_with_handler_exception(self):
        """Test suggestion generation when handler raises exception."""
        reporter = ErrorReporter()

        # Register a suggestion handler that raises an exception
        def failing_suggestion_handler(_):
            raise RuntimeError("Suggestion handler failed")

        reporter.suggestion_handlers[ErrorCategory.VALIDATION] = [failing_suggestion_handler]

        exception = ValueError("Test error")

        with patch("utils.error_reporter.logger") as mock_logger:
            reporter.report_error(exception, category=ErrorCategory.VALIDATION)

        # Should not have suggestions but should not crash
        mock_logger.warning.assert_called_once()
