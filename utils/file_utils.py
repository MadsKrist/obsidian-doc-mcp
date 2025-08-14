"""File system utilities for safe file operations.

This module provides utilities for safe file operations including path validation,
atomic file operations, temporary directory management, and backup creation.
"""

import hashlib
import logging
import os
import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


class FileOperationError(Exception):
    """Raised when file operations fail."""

    pass


class PathValidationError(Exception):
    """Raised when path validation fails."""

    pass


def validate_path(path: Path, base_path: Path | None = None) -> Path:
    """Validate and resolve a file path safely.

    Args:
        path: Path to validate
        base_path: Optional base path to restrict operations to

    Returns:
        Resolved absolute path

    Raises:
        PathValidationError: If path is invalid or outside base_path
    """
    try:
        resolved_path = path.resolve()
    except (OSError, ValueError) as e:
        raise PathValidationError(f"Invalid path '{path}': {e}") from e

    # Check for path traversal attempts
    if ".." in str(path):
        logger.warning(f"Path traversal attempt detected: {path}")

    # If base_path is specified, ensure the resolved path is within it
    if base_path:
        try:
            base_resolved = base_path.resolve()
            resolved_path.relative_to(base_resolved)
        except ValueError as e:
            raise PathValidationError(
                f"Path '{resolved_path}' is outside base path '{base_resolved}'"
            ) from e
        except OSError as e:
            raise PathValidationError(f"Invalid base path '{base_path}': {e}") from e

    return resolved_path


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing or replacing invalid characters.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for filesystem use
    """
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    sanitized = filename
    for char in invalid_chars:
        sanitized = sanitized.replace(char, "_")

    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(". \t\n\r")

    # Ensure filename is not empty
    if not sanitized:
        sanitized = "unnamed_file"

    # Limit filename length (most filesystems support 255 chars)
    if len(sanitized) > 250:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[: 250 - len(ext)] + ext

    return sanitized


def ensure_directory(directory: Path) -> None:
    """Ensure a directory exists, creating it if necessary.

    Args:
        directory: Directory path to create

    Raises:
        FileOperationError: If directory cannot be created
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Directory ensured: {directory}")
    except OSError as e:
        raise FileOperationError(
            f"Failed to create directory '{directory}': {e}"
        ) from e


def copy_file_safely(
    source: Path, destination: Path, create_backup: bool = True
) -> None:
    """Copy a file safely with optional backup creation.

    Args:
        source: Source file path
        destination: Destination file path
        create_backup: Whether to create backup of existing destination

    Raises:
        FileOperationError: If copy operation fails
    """
    try:
        source = validate_path(source)
        destination = validate_path(destination)

        if not source.exists():
            raise FileOperationError(f"Source file does not exist: {source}")

        # Create destination directory if needed
        ensure_directory(destination.parent)

        # Create backup of existing destination if requested
        if create_backup and destination.exists():
            create_backup_file(destination)

        # Copy the file
        shutil.copy2(source, destination)
        logger.debug(f"File copied: {source} -> {destination}")

    except Exception as e:
        raise FileOperationError(f"Failed to copy file: {e}") from e


def move_file_safely(
    source: Path, destination: Path, create_backup: bool = True
) -> None:
    """Move a file safely with optional backup creation.

    Args:
        source: Source file path
        destination: Destination file path
        create_backup: Whether to create backup of existing destination

    Raises:
        FileOperationError: If move operation fails
    """
    try:
        source = validate_path(source)
        destination = validate_path(destination)

        if not source.exists():
            raise FileOperationError(f"Source file does not exist: {source}")

        # Create destination directory if needed
        ensure_directory(destination.parent)

        # Create backup of existing destination if requested
        if create_backup and destination.exists():
            create_backup_file(destination)

        # Move the file
        shutil.move(str(source), str(destination))
        logger.debug(f"File moved: {source} -> {destination}")

    except Exception as e:
        raise FileOperationError(f"Failed to move file: {e}") from e


def write_file_atomically(
    file_path: Path, content: str, encoding: str = "utf-8", create_backup: bool = True
) -> None:
    """Write content to a file atomically using a temporary file.

    Args:
        file_path: Target file path
        content: Content to write
        encoding: File encoding
        create_backup: Whether to create backup of existing file

    Raises:
        FileOperationError: If write operation fails
    """
    try:
        file_path = validate_path(file_path)

        # Create directory if needed
        ensure_directory(file_path.parent)

        # Create backup of existing file if requested
        if create_backup and file_path.exists():
            create_backup_file(file_path)

        # Write to temporary file first
        temp_file = file_path.with_suffix(file_path.suffix + ".tmp")
        try:
            with open(temp_file, "w", encoding=encoding) as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())  # Ensure data is written to disk

            # Atomically replace the original file
            temp_file.replace(file_path)
            logger.debug(f"File written atomically: {file_path}")

        except Exception as e:
            # Clean up temporary file on error
            if temp_file.exists():
                temp_file.unlink()
            raise e

    except Exception as e:
        raise FileOperationError(f"Failed to write file atomically: {e}") from e


def read_file_safely(file_path: Path, encoding: str = "utf-8") -> str:
    """Read a file safely with proper error handling.

    Args:
        file_path: File path to read
        encoding: File encoding

    Returns:
        File content as string

    Raises:
        FileOperationError: If read operation fails
    """
    try:
        file_path = validate_path(file_path)

        if not file_path.exists():
            raise FileOperationError(f"File does not exist: {file_path}")

        if not file_path.is_file():
            raise FileOperationError(f"Path is not a file: {file_path}")

        with open(file_path, encoding=encoding) as f:
            content = f.read()

        logger.debug(f"File read safely: {file_path}")
        return content

    except UnicodeDecodeError as e:
        raise FileOperationError(f"Failed to decode file '{file_path}': {e}") from e
    except Exception as e:
        raise FileOperationError(f"Failed to read file: {e}") from e


def create_backup_file(file_path: Path) -> Path:
    """Create a backup of a file with timestamp.

    Args:
        file_path: File to backup

    Returns:
        Path to backup file

    Raises:
        FileOperationError: If backup creation fails
    """
    try:
        file_path = validate_path(file_path)

        if not file_path.exists():
            raise FileOperationError(f"Cannot backup non-existent file: {file_path}")

        # Generate backup filename with timestamp
        timestamp = str(int(Path.cwd().stat().st_mtime))
        backup_path = file_path.with_suffix(f".backup.{timestamp}{file_path.suffix}")

        # Ensure unique backup filename
        counter = 1
        while backup_path.exists():
            backup_path = file_path.with_suffix(
                f".backup.{timestamp}.{counter}{file_path.suffix}"
            )
            counter += 1

        # Copy the file to backup location
        shutil.copy2(file_path, backup_path)
        logger.info(f"Backup created: {backup_path}")

        return backup_path

    except Exception as e:
        raise FileOperationError(f"Failed to create backup: {e}") from e


def calculate_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """Calculate hash of a file for integrity checking.

    Args:
        file_path: File to hash
        algorithm: Hash algorithm to use

    Returns:
        Hexadecimal hash string

    Raises:
        FileOperationError: If hash calculation fails
    """
    try:
        file_path = validate_path(file_path)

        if not file_path.exists():
            raise FileOperationError(f"Cannot hash non-existent file: {file_path}")

        hasher = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)

        return hasher.hexdigest()

    except ValueError as e:
        raise FileOperationError(f"Invalid hash algorithm '{algorithm}': {e}") from e
    except Exception as e:
        raise FileOperationError(f"Failed to calculate file hash: {e}") from e


def verify_file_integrity(
    file_path: Path, expected_hash: str, algorithm: str = "sha256"
) -> bool:
    """Verify file integrity using hash comparison.

    Args:
        file_path: File to verify
        expected_hash: Expected hash value
        algorithm: Hash algorithm to use

    Returns:
        True if file integrity is verified

    Raises:
        FileOperationError: If verification fails
    """
    try:
        actual_hash = calculate_file_hash(file_path, algorithm)
        return actual_hash.lower() == expected_hash.lower()
    except Exception as e:
        raise FileOperationError(f"Failed to verify file integrity: {e}") from e


@contextmanager
def temporary_directory(prefix: str = "mcp_docs_") -> Generator[Path, None, None]:
    """Context manager for temporary directory creation and cleanup.

    Args:
        prefix: Prefix for temporary directory name

    Yields:
        Path to temporary directory

    Raises:
        FileOperationError: If temporary directory operations fail
    """
    temp_dir = None
    try:
        temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        logger.debug(f"Created temporary directory: {temp_dir}")
        yield temp_dir
    except Exception as e:
        raise FileOperationError(f"Failed to create temporary directory: {e}") from e
    finally:
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(
                    f"Failed to clean up temporary directory {temp_dir}: {e}"
                )


@contextmanager
def temporary_file(
    suffix: str = "", prefix: str = "mcp_docs_", dir: Path | None = None
) -> Generator[Path, None, None]:
    """Context manager for temporary file creation and cleanup.

    Args:
        suffix: File suffix
        prefix: File prefix
        dir: Directory for temporary file

    Yields:
        Path to temporary file

    Raises:
        FileOperationError: If temporary file operations fail
    """
    temp_file = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir)
        os.close(fd)  # Close the file descriptor
        temp_file = Path(temp_path)
        logger.debug(f"Created temporary file: {temp_file}")
        yield temp_file
    except Exception as e:
        raise FileOperationError(f"Failed to create temporary file: {e}") from e
    finally:
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
                logger.debug(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")


def is_safe_to_overwrite(file_path: Path, size_threshold: int = 1024 * 1024) -> bool:
    """Check if it's safe to overwrite a file based on size and other heuristics.

    Args:
        file_path: File to check
        size_threshold: Size threshold in bytes (default: 1MB)

    Returns:
        True if file appears safe to overwrite
    """
    try:
        # Check if file is a symbolic link BEFORE resolving the path
        if file_path.is_symlink():
            logger.warning(f"Symbolic link detected: {file_path}")
            return False

        file_path = validate_path(file_path)

        if not file_path.exists():
            return True

        # Check file size
        file_size = file_path.stat().st_size
        if file_size > size_threshold:
            logger.warning(f"Large file detected ({file_size} bytes): {file_path}")
            return False

        # Check file permissions
        if not os.access(file_path, os.W_OK):
            logger.warning(f"File is not writable: {file_path}")
            return False

        return True

    except Exception as e:
        logger.error(f"Failed to check file safety: {e}")
        return False


def cleanup_old_backups(
    directory: Path,
    pattern: str = "*.backup.*",
    max_age_days: int = 30,
    keep_count: int = 5,
) -> int:
    """Clean up old backup files in a directory.

    Args:
        directory: Directory to clean
        pattern: Glob pattern for backup files
        max_age_days: Maximum age in days to keep backups
        keep_count: Minimum number of recent backups to keep

    Returns:
        Number of files cleaned up

    Raises:
        FileOperationError: If cleanup fails
    """
    try:
        directory = validate_path(directory)

        if not directory.exists() or not directory.is_dir():
            return 0

        import time

        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 3600

        backup_files = list(directory.glob(pattern))
        if not backup_files:
            return 0

        # Sort by modification time (newest first)
        backup_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        cleaned_count = 0
        for i, backup_file in enumerate(backup_files):
            # Always keep the most recent backups
            if i < keep_count:
                continue

            # Check if file is older than max_age
            file_age = current_time - backup_file.stat().st_mtime
            if file_age > max_age_seconds:
                try:
                    backup_file.unlink()
                    cleaned_count += 1
                    logger.debug(f"Cleaned up old backup: {backup_file}")
                except Exception as e:
                    logger.warning(f"Failed to remove backup {backup_file}: {e}")

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old backup files")

        return cleaned_count

    except Exception as e:
        raise FileOperationError(f"Failed to cleanup old backups: {e}") from e
