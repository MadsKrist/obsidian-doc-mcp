"""Tests for file system utilities."""

import hashlib
import os
import time
from pathlib import Path

import pytest

from utils.file_utils import (
    FileOperationError,
    PathValidationError,
    calculate_file_hash,
    cleanup_old_backups,
    copy_file_safely,
    create_backup_file,
    ensure_directory,
    is_safe_to_overwrite,
    move_file_safely,
    read_file_safely,
    sanitize_filename,
    temporary_directory,
    temporary_file,
    validate_path,
    verify_file_integrity,
    write_file_atomically,
)


class TestPathValidation:
    """Test path validation functions."""

    def test_validate_path_basic(self, tmp_path: Path) -> None:
        """Test basic path validation."""
        test_path = tmp_path / "test.txt"
        validated = validate_path(test_path)
        assert validated.is_absolute()
        assert validated == test_path.resolve()

    def test_validate_path_with_base_path(self, tmp_path: Path) -> None:
        """Test path validation with base path restriction."""
        base_path = tmp_path
        test_path = tmp_path / "subdir" / "test.txt"

        validated = validate_path(test_path, base_path)
        assert validated.is_absolute()
        assert validated == test_path.resolve()

    def test_validate_path_outside_base_fails(self, tmp_path: Path) -> None:
        """Test that paths outside base path are rejected."""
        base_path = tmp_path / "restricted"
        outside_path = tmp_path / "outside.txt"

        with pytest.raises(PathValidationError, match="outside base path"):
            validate_path(outside_path, base_path)

    def test_validate_path_traversal_warning(self, tmp_path: Path, caplog) -> None:
        """Test that path traversal attempts are logged."""
        test_path = tmp_path / ".." / "test.txt"

        # Should still validate but log warning
        validated = validate_path(test_path)
        assert "Path traversal attempt detected" in caplog.text
        assert validated.is_absolute()

    def test_sanitize_filename_basic(self) -> None:
        """Test basic filename sanitization."""
        assert sanitize_filename("normal_file.txt") == "normal_file.txt"
        assert sanitize_filename("file with spaces.txt") == "file with spaces.txt"

    def test_sanitize_filename_invalid_chars(self) -> None:
        """Test sanitization of invalid characters."""
        assert sanitize_filename("file<>:?*.txt") == "file_____.txt"
        assert sanitize_filename('file"name|test.txt') == "file_name_test.txt"

    def test_sanitize_filename_edge_cases(self) -> None:
        """Test edge cases in filename sanitization."""
        assert sanitize_filename("") == "unnamed_file"
        assert sanitize_filename("   ") == "unnamed_file"
        assert sanitize_filename("...") == "unnamed_file"

        # Test long filename truncation
        long_name = "a" * 300 + ".txt"
        sanitized = sanitize_filename(long_name)
        assert len(sanitized) <= 250
        assert sanitized.endswith(".txt")


class TestDirectoryOperations:
    """Test directory operations."""

    def test_ensure_directory_creates_dir(self, tmp_path: Path) -> None:
        """Test directory creation."""
        test_dir = tmp_path / "new_dir" / "nested"
        ensure_directory(test_dir)

        assert test_dir.exists()
        assert test_dir.is_dir()

    def test_ensure_directory_existing_dir(self, tmp_path: Path) -> None:
        """Test ensuring existing directory doesn't fail."""
        test_dir = tmp_path / "existing"
        test_dir.mkdir()

        # Should not raise exception
        ensure_directory(test_dir)
        assert test_dir.exists()

    def test_ensure_directory_permission_error(self, tmp_path: Path, monkeypatch) -> None:
        """Test directory creation with permission error."""

        def mock_mkdir(self, parents=False, exist_ok=False):
            raise OSError("Permission denied")

        monkeypatch.setattr(Path, "mkdir", mock_mkdir)

        with pytest.raises(FileOperationError, match="Failed to create directory"):
            ensure_directory(tmp_path / "test")


class TestFileOperations:
    """Test file operations."""

    def test_copy_file_safely_basic(self, tmp_path: Path) -> None:
        """Test basic file copying."""
        source = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"

        source.write_text("test content")
        copy_file_safely(source, dest)

        assert dest.exists()
        assert dest.read_text() == "test content"

    def test_copy_file_safely_with_backup(self, tmp_path: Path) -> None:
        """Test file copying with backup creation."""
        source = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"

        source.write_text("new content")
        dest.write_text("old content")

        copy_file_safely(source, dest, create_backup=True)

        assert dest.read_text() == "new content"

        # Check backup was created
        backups = list(tmp_path.glob("dest.backup.*"))
        assert len(backups) == 1
        assert backups[0].read_text() == "old content"

    def test_copy_file_nonexistent_source(self, tmp_path: Path) -> None:
        """Test copying non-existent source file."""
        source = tmp_path / "nonexistent.txt"
        dest = tmp_path / "dest.txt"

        with pytest.raises(FileOperationError, match="Source file does not exist"):
            copy_file_safely(source, dest)

    def test_move_file_safely_basic(self, tmp_path: Path) -> None:
        """Test basic file moving."""
        source = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"

        source.write_text("test content")
        move_file_safely(source, dest)

        assert not source.exists()
        assert dest.exists()
        assert dest.read_text() == "test content"

    def test_write_file_atomically(self, tmp_path: Path) -> None:
        """Test atomic file writing."""
        file_path = tmp_path / "atomic.txt"
        content = "atomic content"

        write_file_atomically(file_path, content)

        assert file_path.exists()
        assert file_path.read_text() == content

    def test_write_file_atomically_with_backup(self, tmp_path: Path) -> None:
        """Test atomic writing with backup."""
        file_path = tmp_path / "atomic.txt"

        # Create existing file
        file_path.write_text("original content")

        write_file_atomically(file_path, "new content", create_backup=True)

        assert file_path.read_text() == "new content"

        # Check backup exists
        backups = list(tmp_path.glob("atomic.backup.*"))
        assert len(backups) == 1
        assert backups[0].read_text() == "original content"

    def test_read_file_safely(self, tmp_path: Path) -> None:
        """Test safe file reading."""
        file_path = tmp_path / "test.txt"
        content = "test content with üñíçødé"

        file_path.write_text(content, encoding="utf-8")

        result = read_file_safely(file_path)
        assert result == content

    def test_read_file_nonexistent(self, tmp_path: Path) -> None:
        """Test reading non-existent file."""
        file_path = tmp_path / "nonexistent.txt"

        with pytest.raises(FileOperationError, match="File does not exist"):
            read_file_safely(file_path)

    def test_read_file_not_a_file(self, tmp_path: Path) -> None:
        """Test reading a directory instead of file."""
        with pytest.raises(FileOperationError, match="Path is not a file"):
            read_file_safely(tmp_path)


class TestBackupOperations:
    """Test backup operations."""

    def test_create_backup_file(self, tmp_path: Path) -> None:
        """Test backup file creation."""
        source = tmp_path / "source.txt"
        source.write_text("content to backup")

        backup_path = create_backup_file(source)

        assert backup_path.exists()
        assert backup_path.read_text() == "content to backup"
        assert ".backup." in backup_path.name

    def test_create_backup_nonexistent_file(self, tmp_path: Path) -> None:
        """Test backup of non-existent file fails."""
        source = tmp_path / "nonexistent.txt"

        with pytest.raises(FileOperationError, match="Cannot backup non-existent file"):
            create_backup_file(source)

    def test_create_backup_unique_names(self, tmp_path: Path) -> None:
        """Test that backup files get unique names."""
        source = tmp_path / "source.txt"
        source.write_text("content")

        backup1 = create_backup_file(source)

        # Create another backup immediately
        backup2 = create_backup_file(source)

        assert backup1 != backup2
        assert backup1.exists()
        assert backup2.exists()


class TestHashOperations:
    """Test hash and integrity operations."""

    def test_calculate_file_hash(self, tmp_path: Path) -> None:
        """Test file hash calculation."""
        file_path = tmp_path / "test.txt"
        content = "test content for hashing"
        file_path.write_text(content)

        # Calculate expected hash
        expected = hashlib.sha256(content.encode()).hexdigest()

        result = calculate_file_hash(file_path)
        assert result == expected

    def test_calculate_file_hash_different_algorithm(self, tmp_path: Path) -> None:
        """Test hash calculation with different algorithm."""
        file_path = tmp_path / "test.txt"
        content = "test content"
        file_path.write_text(content)

        md5_hash = calculate_file_hash(file_path, "md5")
        sha1_hash = calculate_file_hash(file_path, "sha1")

        assert len(md5_hash) == 32  # MD5 hex length
        assert len(sha1_hash) == 40  # SHA1 hex length
        assert md5_hash != sha1_hash

    def test_calculate_hash_invalid_algorithm(self, tmp_path: Path) -> None:
        """Test hash calculation with invalid algorithm."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        with pytest.raises(FileOperationError, match="Invalid hash algorithm"):
            calculate_file_hash(file_path, "invalid_algorithm")

    def test_verify_file_integrity_success(self, tmp_path: Path) -> None:
        """Test successful file integrity verification."""
        file_path = tmp_path / "test.txt"
        content = "integrity test content"
        file_path.write_text(content)

        expected_hash = hashlib.sha256(content.encode()).hexdigest()

        assert verify_file_integrity(file_path, expected_hash) is True

    def test_verify_file_integrity_failure(self, tmp_path: Path) -> None:
        """Test failed file integrity verification."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        wrong_hash = "0" * 64  # Invalid hash

        assert verify_file_integrity(file_path, wrong_hash) is False


class TestTemporaryOperations:
    """Test temporary file and directory operations."""

    def test_temporary_directory_context(self) -> None:
        """Test temporary directory context manager."""
        temp_path = None

        with temporary_directory() as temp_dir:
            temp_path = temp_dir
            assert temp_dir.exists()
            assert temp_dir.is_dir()

            # Create a test file
            test_file = temp_dir / "test.txt"
            test_file.write_text("test")
            assert test_file.exists()

        # Directory should be cleaned up
        assert not temp_path.exists()

    def test_temporary_directory_custom_prefix(self) -> None:
        """Test temporary directory with custom prefix."""
        with temporary_directory(prefix="custom_test_") as temp_dir:
            assert "custom_test_" in temp_dir.name

    def test_temporary_file_context(self) -> None:
        """Test temporary file context manager."""
        temp_path = None

        with temporary_file(suffix=".txt", prefix="test_") as temp_file:
            temp_path = temp_file
            assert temp_file.exists()
            assert temp_file.is_file()
            assert temp_file.suffix == ".txt"
            assert "test_" in temp_file.name

            # Write to the file
            temp_file.write_text("temporary content")
            assert temp_file.read_text() == "temporary content"

        # File should be cleaned up
        assert not temp_path.exists()

    def test_temporary_file_in_custom_dir(self, tmp_path: Path) -> None:
        """Test temporary file in custom directory."""
        with temporary_file(dir=tmp_path) as temp_file:
            assert temp_file.parent == tmp_path


class TestSafetyChecks:
    """Test safety check functions."""

    def test_is_safe_to_overwrite_nonexistent(self, tmp_path: Path) -> None:
        """Test safety check for non-existent file."""
        file_path = tmp_path / "nonexistent.txt"
        assert is_safe_to_overwrite(file_path) is True

    def test_is_safe_to_overwrite_small_file(self, tmp_path: Path) -> None:
        """Test safety check for small file."""
        file_path = tmp_path / "small.txt"
        file_path.write_text("small content")

        assert is_safe_to_overwrite(file_path) is True

    def test_is_safe_to_overwrite_large_file(self, tmp_path: Path) -> None:
        """Test safety check for large file."""
        file_path = tmp_path / "large.txt"
        large_content = "x" * (2 * 1024 * 1024)  # 2MB
        file_path.write_text(large_content)

        # Should be unsafe due to size
        assert is_safe_to_overwrite(file_path, size_threshold=1024 * 1024) is False

    def test_is_safe_to_overwrite_symlink(self, tmp_path: Path) -> None:
        """Test safety check for symbolic link."""
        target_file = tmp_path / "target.txt"
        target_file.write_text("target content")

        symlink_file = tmp_path / "link.txt"
        symlink_file.symlink_to(target_file)

        assert is_safe_to_overwrite(symlink_file) is False


class TestCleanupOperations:
    """Test cleanup operations."""

    def test_cleanup_old_backups_no_files(self, tmp_path: Path) -> None:
        """Test cleanup with no backup files."""
        result = cleanup_old_backups(tmp_path)
        assert result == 0

    def test_cleanup_old_backups_basic(self, tmp_path: Path) -> None:
        """Test basic backup cleanup."""
        # Create some backup files with different ages
        old_backup = tmp_path / "file.backup.123.txt"
        recent_backup = tmp_path / "file.backup.456.txt"

        old_backup.write_text("old")
        recent_backup.write_text("recent")

        # Modify timestamps to simulate age
        current_time = time.time()
        old_time = current_time - (40 * 24 * 3600)  # 40 days ago
        recent_time = current_time - (10 * 24 * 3600)  # 10 days ago

        os.utime(old_backup, (old_time, old_time))
        os.utime(recent_backup, (recent_time, recent_time))

        # Cleanup files older than 30 days, keeping at least 1
        result = cleanup_old_backups(tmp_path, max_age_days=30, keep_count=1)

        assert result == 1  # Should have cleaned up 1 file
        assert not old_backup.exists()
        assert recent_backup.exists()  # Should be kept

    def test_cleanup_old_backups_keep_minimum(self, tmp_path: Path) -> None:
        """Test that minimum number of backups are kept."""
        # Create 3 old backup files
        backups = []
        current_time = time.time()

        for i in range(3):
            backup = tmp_path / f"file.backup.{i}.txt"
            backup.write_text(f"backup {i}")

            # All are old (40 days)
            old_time = current_time - (40 * 24 * 3600) - i  # Slightly different times
            os.utime(backup, (old_time, old_time))
            backups.append(backup)

        # Keep minimum of 2 files
        result = cleanup_old_backups(tmp_path, max_age_days=30, keep_count=2)

        assert result == 1  # Should clean up 1 file

        # Check that 2 most recent are kept
        existing_backups = [b for b in backups if b.exists()]
        assert len(existing_backups) == 2

    def test_cleanup_old_backups_nonexistent_dir(self, tmp_path: Path) -> None:
        """Test cleanup on non-existent directory."""
        nonexistent = tmp_path / "nonexistent"
        result = cleanup_old_backups(nonexistent)
        assert result == 0
