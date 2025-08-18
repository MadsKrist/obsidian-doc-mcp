"""Detailed error reporting and suggestion system.

This module provides comprehensive error reporting with actionable suggestions
for common issues in the documentation generation process.
"""

import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Severity levels for errors."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Categories of errors."""

    CONFIGURATION = "configuration"
    PROJECT_ANALYSIS = "project_analysis"
    SPHINX_BUILD = "sphinx_build"
    OBSIDIAN_CONVERSION = "obsidian_conversion"
    FILE_SYSTEM = "file_system"
    DEPENDENCY = "dependency"
    PERFORMANCE = "performance"
    VALIDATION = "validation"


@dataclass
class ErrorSuggestion:
    """A suggested solution for an error."""

    title: str
    description: str
    action_type: str  # "fix", "workaround", "investigate", "configure"
    command: str | None = None
    documentation_url: str | None = None
    priority: int = 1  # 1=high, 2=medium, 3=low


@dataclass
class DetailedError:
    """Comprehensive error information with suggestions."""

    error_id: str
    title: str
    description: str
    severity: ErrorSeverity
    category: ErrorCategory
    original_exception: Exception | None = None
    context: dict[str, Any] = field(default_factory=dict)
    suggestions: list[ErrorSuggestion] = field(default_factory=list)
    affected_files: list[Path] = field(default_factory=list)
    stack_trace: str | None = None

    def add_suggestion(self, suggestion: ErrorSuggestion) -> None:
        """Add a suggestion to this error."""
        self.suggestions.append(suggestion)
        self.suggestions.sort(key=lambda s: s.priority)

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary representation."""
        return {
            "error_id": self.error_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "category": self.category.value,
            "context": self.context.copy(),
            "suggestions": [
                {
                    "title": s.title,
                    "description": s.description,
                    "action_type": s.action_type,
                    "command": s.command,
                    "documentation_url": s.documentation_url,
                    "priority": s.priority,
                }
                for s in self.suggestions
            ],
            "affected_files": [str(f).replace("\\", "/") for f in self.affected_files],
            "has_stack_trace": self.stack_trace is not None,
        }


class ErrorReporter:
    """Comprehensive error reporting and suggestion system."""

    def __init__(self):
        """Initialize the error reporter."""
        self.errors: list[DetailedError] = []
        self.error_patterns: dict[str, Callable[[Exception, dict[str, Any]], DetailedError]] = {}
        self.suggestion_handlers: dict[
            ErrorCategory, list[Callable[[DetailedError], list[ErrorSuggestion]]]
        ] = {}

        # Register built-in error patterns and suggestion handlers
        self._register_builtin_patterns()
        self._register_builtin_suggestions()

    def report_error(
        self,
        exception: Exception,
        context: dict[str, Any] | None = None,
        category: ErrorCategory | None = None,
        affected_files: list[Path] | None = None,
    ) -> DetailedError:
        """Report an error with detailed analysis and suggestions.

        Args:
            exception: The original exception
            context: Additional context information
            category: Error category (auto-detected if None)
            affected_files: Files affected by this error

        Returns:
            DetailedError object with suggestions
        """
        context = context or {}
        affected_files = affected_files or []

        # Try to match against known error patterns
        detailed_error = self._match_error_pattern(exception, context)

        if not detailed_error:
            # Create generic error if no pattern matches
            detailed_error = self._create_generic_error(exception, context, category)

        # Add stack trace
        detailed_error.stack_trace = traceback.format_exc()
        detailed_error.affected_files.extend(affected_files)

        # Generate suggestions
        self._generate_suggestions(detailed_error)

        # Store the error
        self.errors.append(detailed_error)

        logger.error(f"Error reported: {detailed_error.title} ({detailed_error.error_id})")
        return detailed_error

    def _match_error_pattern(
        self, exception: Exception, context: dict[str, Any]
    ) -> DetailedError | None:
        """Try to match exception against known patterns."""
        exception_str = str(exception).lower()
        exception_type = type(exception).__name__

        for pattern, handler in self.error_patterns.items():
            if pattern in exception_str or pattern == exception_type:
                try:
                    return handler(exception, context)
                except Exception as e:
                    logger.warning(f"Error pattern handler failed: {e}")

        return None

    def _create_generic_error(
        self,
        exception: Exception,
        context: dict[str, Any],
        category: ErrorCategory | None,
    ) -> DetailedError:
        """Create a generic error when no specific pattern matches."""
        error_id = f"generic_{type(exception).__name__}_{hash(str(exception)) % 10000:04d}"

        # Try to infer category from context or exception type
        if not category:
            category = self._infer_category(exception, context)

        return DetailedError(
            error_id=error_id,
            title=f"{type(exception).__name__}: {str(exception)[:100]}",
            description=str(exception),
            severity=ErrorSeverity.ERROR,
            category=category,
            original_exception=exception,
            context=context,
        )

    def _infer_category(self, exception: Exception, context: dict[str, Any]) -> ErrorCategory:
        """Infer error category from exception and context."""
        exception_str = str(exception).lower()

        # File system errors
        if isinstance(exception, FileNotFoundError | PermissionError | OSError):
            return ErrorCategory.FILE_SYSTEM

        # Import/dependency errors
        if isinstance(exception, ImportError | ModuleNotFoundError):
            return ErrorCategory.DEPENDENCY

        # Configuration errors
        if "config" in exception_str or "configuration" in exception_str:
            return ErrorCategory.CONFIGURATION

        # Sphinx-related errors
        if "sphinx" in exception_str or context.get("operation") == "sphinx_build":
            return ErrorCategory.SPHINX_BUILD

        # Obsidian-related errors
        if "obsidian" in exception_str or context.get("operation") == "obsidian_conversion":
            return ErrorCategory.OBSIDIAN_CONVERSION

        # Default to validation
        return ErrorCategory.VALIDATION

    def _generate_suggestions(self, error: DetailedError) -> None:
        """Generate suggestions for an error."""
        handlers = self.suggestion_handlers.get(error.category, [])

        for handler in handlers:
            try:
                suggestions = handler(error)
                for suggestion in suggestions:
                    error.add_suggestion(suggestion)
            except Exception as e:
                logger.warning(f"Suggestion handler failed: {e}")

    def _register_builtin_patterns(self) -> None:
        """Register built-in error patterns."""

        # File not found errors
        self.error_patterns["[Errno 2] No such file or directory"] = self._handle_file_not_found
        self.error_patterns["FileNotFoundError"] = self._handle_file_not_found

        # Permission errors
        self.error_patterns["[Errno 13] Permission denied"] = self._handle_permission_denied
        self.error_patterns["PermissionError"] = self._handle_permission_denied

        # Import errors
        self.error_patterns["ModuleNotFoundError"] = self._handle_module_not_found
        self.error_patterns["ImportError"] = self._handle_import_error

        # Sphinx build errors
        self.error_patterns["sphinx"] = self._handle_sphinx_error

        # Configuration errors
        self.error_patterns["configuration"] = self._handle_config_error

        # Memory errors
        self.error_patterns["MemoryError"] = self._handle_memory_error

        # Timeout errors
        self.error_patterns["TimeoutError"] = self._handle_timeout_error

    def _register_builtin_suggestions(self) -> None:
        """Register built-in suggestion handlers."""
        self.suggestion_handlers[ErrorCategory.FILE_SYSTEM] = [self._suggest_file_system_fixes]
        self.suggestion_handlers[ErrorCategory.DEPENDENCY] = [self._suggest_dependency_fixes]
        self.suggestion_handlers[ErrorCategory.CONFIGURATION] = [self._suggest_config_fixes]
        self.suggestion_handlers[ErrorCategory.SPHINX_BUILD] = [self._suggest_sphinx_fixes]
        self.suggestion_handlers[ErrorCategory.OBSIDIAN_CONVERSION] = [self._suggest_obsidian_fixes]
        self.suggestion_handlers[ErrorCategory.PERFORMANCE] = [self._suggest_performance_fixes]

    # Error pattern handlers

    def _handle_file_not_found(
        self, exception: Exception, context: dict[str, Any]
    ) -> DetailedError:
        """Handle file not found errors."""
        return DetailedError(
            error_id="file_not_found",
            title="File or Directory Not Found",
            description=f"The system cannot find the specified file or directory: {exception}",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.FILE_SYSTEM,
            original_exception=exception,
            context=context,
        )

    def _handle_permission_denied(
        self, exception: Exception, context: dict[str, Any]
    ) -> DetailedError:
        """Handle permission denied errors."""
        return DetailedError(
            error_id="permission_denied",
            title="Permission Denied",
            description=f"Access denied to file or directory: {exception}",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.FILE_SYSTEM,
            original_exception=exception,
            context=context,
        )

    def _handle_module_not_found(
        self, exception: Exception, context: dict[str, Any]
    ) -> DetailedError:
        """Handle module not found errors."""
        module_name = str(exception).split("'")[1] if "'" in str(exception) else "unknown"

        return DetailedError(
            error_id="module_not_found",
            title="Python Module Not Found",
            description=f"Required Python module '{module_name}' is not installed or available",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.DEPENDENCY,
            original_exception=exception,
            context={**context, "missing_module": module_name},
        )

    def _handle_import_error(self, exception: Exception, context: dict[str, Any]) -> DetailedError:
        """Handle import errors."""
        return DetailedError(
            error_id="import_error",
            title="Python Import Error",
            description=f"Failed to import required module or component: {exception}",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.DEPENDENCY,
            original_exception=exception,
            context=context,
        )

    def _handle_sphinx_error(self, exception: Exception, context: dict[str, Any]) -> DetailedError:
        """Handle Sphinx build errors."""
        return DetailedError(
            error_id="sphinx_build_error",
            title="Sphinx Documentation Build Failed",
            description=f"Sphinx failed to build documentation: {exception}",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.SPHINX_BUILD,
            original_exception=exception,
            context=context,
        )

    def _handle_config_error(self, exception: Exception, context: dict[str, Any]) -> DetailedError:
        """Handle configuration errors."""
        return DetailedError(
            error_id="configuration_error",
            title="Configuration Error",
            description=f"Invalid or missing configuration: {exception}",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.CONFIGURATION,
            original_exception=exception,
            context=context,
        )

    def _handle_memory_error(self, exception: Exception, context: dict[str, Any]) -> DetailedError:
        """Handle memory errors."""
        return DetailedError(
            error_id="memory_error",
            title="Insufficient Memory",
            description="Operation failed due to insufficient available memory",
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.PERFORMANCE,
            original_exception=exception,
            context=context,
        )

    def _handle_timeout_error(self, exception: Exception, context: dict[str, Any]) -> DetailedError:
        """Handle timeout errors."""
        return DetailedError(
            error_id="timeout_error",
            title="Operation Timed Out",
            description=f"Operation exceeded maximum allowed time: {exception}",
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.PERFORMANCE,
            original_exception=exception,
            context=context,
        )

    # Suggestion handlers

    def _suggest_file_system_fixes(self, error: DetailedError) -> list[ErrorSuggestion]:
        """Suggest fixes for file system errors."""
        suggestions = []

        if error.error_id == "file_not_found":
            suggestions.extend(
                [
                    ErrorSuggestion(
                        title="Check File Path",
                        description="Verify the file path is correct and the file exists",
                        action_type="investigate",
                        priority=1,
                    ),
                    ErrorSuggestion(
                        title="Create Missing Directory",
                        description="Create the missing directory structure",
                        action_type="fix",
                        command="mkdir -p <directory_path>",
                        priority=2,
                    ),
                    ErrorSuggestion(
                        title="Update Configuration",
                        description="Update project configuration to point to correct paths",
                        action_type="configure",
                        priority=3,
                    ),
                ]
            )

        elif error.error_id == "permission_denied":
            suggestions.extend(
                [
                    ErrorSuggestion(
                        title="Check File Permissions",
                        description=(
                            "Verify you have read/write permissions for the file or directory"
                        ),
                        action_type="investigate",
                        command="ls -la <file_path>",
                        priority=1,
                    ),
                    ErrorSuggestion(
                        title="Fix Permissions",
                        description="Update file permissions to allow access",
                        action_type="fix",
                        command="chmod 755 <directory_path>",
                        priority=2,
                    ),
                    ErrorSuggestion(
                        title="Run as Administrator",
                        description="Run the operation with elevated privileges",
                        action_type="workaround",
                        priority=3,
                    ),
                ]
            )

        return suggestions

    def _suggest_dependency_fixes(self, error: DetailedError) -> list[ErrorSuggestion]:
        """Suggest fixes for dependency errors."""
        suggestions = []

        if error.error_id in ["module_not_found", "import_error"]:
            module_name = error.context.get("missing_module", "unknown")

            suggestions.extend(
                [
                    ErrorSuggestion(
                        title="Install Missing Package",
                        description=f"Install the required Python package: {module_name}",
                        action_type="fix",
                        command=f"uv add {module_name}",
                        priority=1,
                    ),
                    ErrorSuggestion(
                        title="Check Virtual Environment",
                        description="Ensure you're using the correct Python virtual environment",
                        action_type="investigate",
                        command="uv sync",
                        priority=2,
                    ),
                    ErrorSuggestion(
                        title="Update Dependencies",
                        description="Update all project dependencies to latest versions",
                        action_type="fix",
                        command="uv sync --upgrade",
                        priority=3,
                    ),
                ]
            )

        return suggestions

    def _suggest_config_fixes(self, _: DetailedError) -> list[ErrorSuggestion]:
        """Suggest fixes for configuration errors."""
        return [
            ErrorSuggestion(
                title="Validate Configuration",
                description="Check configuration file syntax and required fields",
                action_type="investigate",
                priority=1,
            ),
            ErrorSuggestion(
                title="Create Default Configuration",
                description="Generate a default configuration file",
                action_type="fix",
                priority=2,
            ),
            ErrorSuggestion(
                title="Check Documentation",
                description="Review configuration documentation and examples",
                action_type="investigate",
                documentation_url="https://docs.example.com/configuration",
                priority=3,
            ),
        ]

    def _suggest_sphinx_fixes(self, _: DetailedError) -> list[ErrorSuggestion]:
        """Suggest fixes for Sphinx build errors."""
        return [
            ErrorSuggestion(
                title="Check Sphinx Configuration",
                description="Verify conf.py settings and required extensions",
                action_type="investigate",
                priority=1,
            ),
            ErrorSuggestion(
                title="Install Sphinx Extensions",
                description="Install any missing Sphinx extensions",
                action_type="fix",
                command="uv add sphinx sphinx-rtd-theme",
                priority=2,
            ),
            ErrorSuggestion(
                title="Clean Build Directory",
                description="Remove existing build files and rebuild",
                action_type="fix",
                priority=3,
            ),
        ]

    def _suggest_obsidian_fixes(self, _: DetailedError) -> list[ErrorSuggestion]:
        """Suggest fixes for Obsidian conversion errors."""
        return [
            ErrorSuggestion(
                title="Check Obsidian Vault Path",
                description="Verify the Obsidian vault path is correct and accessible",
                action_type="investigate",
                priority=1,
            ),
            ErrorSuggestion(
                title="Create Obsidian Folder",
                description="Create the target folder in your Obsidian vault",
                action_type="fix",
                priority=2,
            ),
            ErrorSuggestion(
                title="Check Markdown Syntax",
                description="Verify generated markdown is valid",
                action_type="investigate",
                priority=3,
            ),
        ]

    def _suggest_performance_fixes(self, error: DetailedError) -> list[ErrorSuggestion]:
        """Suggest fixes for performance errors."""
        suggestions = []

        if error.error_id == "memory_error":
            suggestions.extend(
                [
                    ErrorSuggestion(
                        title="Enable Batch Processing",
                        description="Process files in smaller batches to reduce memory usage",
                        action_type="configure",
                        priority=1,
                    ),
                    ErrorSuggestion(
                        title="Close Unused Applications",
                        description="Free up system memory by closing unnecessary applications",
                        action_type="workaround",
                        priority=2,
                    ),
                    ErrorSuggestion(
                        title="Increase Virtual Memory",
                        description="Increase system swap/virtual memory settings",
                        action_type="configure",
                        priority=3,
                    ),
                ]
            )

        elif error.error_id == "timeout_error":
            suggestions.extend(
                [
                    ErrorSuggestion(
                        title="Increase Timeout Settings",
                        description="Configure longer timeout values for large projects",
                        action_type="configure",
                        priority=1,
                    ),
                    ErrorSuggestion(
                        title="Enable Parallel Processing",
                        description="Use parallel processing to speed up operations",
                        action_type="configure",
                        priority=2,
                    ),
                    ErrorSuggestion(
                        title="Reduce Project Scope",
                        description="Process smaller subsets of the project",
                        action_type="workaround",
                        priority=3,
                    ),
                ]
            )

        return suggestions

    # Utility methods

    def get_errors_by_severity(self, severity: ErrorSeverity) -> list[DetailedError]:
        """Get all errors of a specific severity."""
        return [error for error in self.errors if error.severity == severity]

    def get_errors_by_category(self, category: ErrorCategory) -> list[DetailedError]:
        """Get all errors of a specific category."""
        return [error for error in self.errors if error.category == category]

    def has_critical_errors(self) -> bool:
        """Check if there are any critical errors."""
        return any(error.severity == ErrorSeverity.CRITICAL for error in self.errors)

    def clear_errors(self) -> int:
        """Clear all errors and return the count that were cleared."""
        count = len(self.errors)
        self.errors.clear()
        logger.debug(f"Cleared {count} errors")
        return count

    def generate_report(self) -> dict[str, Any]:
        """Generate a comprehensive error report."""
        if not self.errors:
            return {"errors": [], "summary": {"total": 0}}

        # Group errors by category and severity
        by_category = {}
        by_severity = {}

        for error in self.errors:
            category = error.category.value
            severity = error.severity.value

            by_category.setdefault(category, []).append(error.to_dict())
            by_severity.setdefault(severity, []).append(error.to_dict())

        return {
            "errors": [error.to_dict() for error in self.errors],
            "by_category": by_category,
            "by_severity": by_severity,
            "summary": {
                "total": len(self.errors),
                "critical": len(self.get_errors_by_severity(ErrorSeverity.CRITICAL)),
                "errors": len(self.get_errors_by_severity(ErrorSeverity.ERROR)),
                "warnings": len(self.get_errors_by_severity(ErrorSeverity.WARNING)),
                "info": len(self.get_errors_by_severity(ErrorSeverity.INFO)),
                "has_critical": self.has_critical_errors(),
            },
        }


# Global error reporter instance
_global_reporter: ErrorReporter | None = None


def get_global_reporter() -> ErrorReporter:
    """Get or create the global error reporter."""
    global _global_reporter
    if _global_reporter is None:
        _global_reporter = ErrorReporter()
    return _global_reporter


def report_error(
    exception: Exception,
    context: dict[str, Any] | None = None,
    category: ErrorCategory | None = None,
    affected_files: list[Path] | None = None,
) -> DetailedError:
    """Convenience function to report an error using the global reporter."""
    return get_global_reporter().report_error(exception, context, category, affected_files)


def create_error_context(operation: str, **kwargs) -> dict[str, Any]:
    """Create an error context dictionary with standard fields."""
    context = {"operation": operation}
    context.update(kwargs)
    return context
