"""Tests for obsidian_utils module."""

from unittest.mock import patch

import pytest

from utils.obsidian_utils import (
    ObsidianVaultManager,
    VaultNotFoundError,
    VaultValidationError,
    create_obsidian_frontmatter,
    discover_vault,
    validate_vault_structure,
)


class TestObsidianVaultManager:
    """Test cases for ObsidianVaultManager."""

    def test_init_with_valid_vault(self, temp_obsidian_vault):
        """Test initializing with a valid vault."""
        manager = ObsidianVaultManager(temp_obsidian_vault)
        assert manager.vault_path == temp_obsidian_vault

    def test_init_with_nonexistent_vault(self, tmp_path):
        """Test initializing with nonexistent vault."""
        vault_path = tmp_path / "nonexistent"
        with pytest.raises(VaultNotFoundError):
            ObsidianVaultManager(vault_path)

    def test_init_with_file_instead_of_directory(self, tmp_path):
        """Test initializing with file instead of directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")
        with pytest.raises(VaultValidationError):
            ObsidianVaultManager(file_path)

    def test_init_creates_obsidian_dir_if_missing(self, tmp_path):
        """Test that .obsidian directory is created if missing."""
        ObsidianVaultManager(tmp_path)
        assert (tmp_path / ".obsidian").exists()

    def test_ensure_folder_exists(self, temp_obsidian_vault):
        """Test ensuring folder exists."""
        manager = ObsidianVaultManager(temp_obsidian_vault)
        folder_path = manager.ensure_folder_exists("test/nested/folder")

        expected_path = temp_obsidian_vault / "test/nested/folder"
        assert folder_path == expected_path
        assert folder_path.exists()
        assert folder_path.is_dir()

    def test_backup_file_existing(self, temp_obsidian_vault):
        """Test backing up an existing file."""
        manager = ObsidianVaultManager(temp_obsidian_vault)

        # Create a file to backup
        test_file = temp_obsidian_vault / "test.md"
        test_file.write_text("original content")

        with patch("utils.obsidian_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20240101_120000"
            backup_path = manager.backup_file(test_file)

        assert backup_path is not None
        assert backup_path.exists()
        assert "backup_20240101_120000" in backup_path.name
        assert backup_path.read_text() == "original content"

    def test_backup_file_nonexistent(self, temp_obsidian_vault):
        """Test backing up a nonexistent file."""
        manager = ObsidianVaultManager(temp_obsidian_vault)

        nonexistent_file = temp_obsidian_vault / "nonexistent.md"
        backup_path = manager.backup_file(nonexistent_file)

        assert backup_path is None

    def test_safe_write_file_new(self, temp_obsidian_vault):
        """Test safely writing to a new file."""
        manager = ObsidianVaultManager(temp_obsidian_vault)

        file_path = temp_obsidian_vault / "new_folder" / "new_file.md"
        content = "# New Content"

        result_path, backup_path = manager.safe_write_file(file_path, content)

        assert result_path == file_path
        assert backup_path is None
        assert file_path.exists()
        assert file_path.read_text() == content

    def test_safe_write_file_existing_with_backup(self, temp_obsidian_vault):
        """Test safely writing to existing file with backup."""
        manager = ObsidianVaultManager(temp_obsidian_vault)

        # Create existing file
        file_path = temp_obsidian_vault / "existing.md"
        file_path.write_text("original content")

        content = "# New Content"

        with patch("utils.obsidian_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20240101_120000"
            result_path, backup_path = manager.safe_write_file(file_path, content)

        assert result_path == file_path
        assert backup_path is not None
        assert backup_path.exists()
        assert file_path.read_text() == content
        assert backup_path.read_text() == "original content"

    def test_safe_write_file_existing_without_backup(self, temp_obsidian_vault):
        """Test safely writing to existing file without backup."""
        manager = ObsidianVaultManager(temp_obsidian_vault)

        # Create existing file
        file_path = temp_obsidian_vault / "existing.md"
        file_path.write_text("original content")

        content = "# New Content"
        result_path, backup_path = manager.safe_write_file(
            file_path, content, create_backup=False
        )

        assert result_path == file_path
        assert backup_path is None
        assert file_path.read_text() == content

    def test_generate_index_file(self, temp_obsidian_vault):
        """Test generating an index file."""
        manager = ObsidianVaultManager(temp_obsidian_vault)

        # Create some test files
        files = [
            temp_obsidian_vault / "doc1.md",
            temp_obsidian_vault / "doc2.md",
            temp_obsidian_vault / "config.yaml",
        ]
        for f in files:
            f.write_text("content")

        folder_path = temp_obsidian_vault
        title = "Test Index"

        content = manager.generate_index_file(folder_path, title, files)

        assert "# Test Index" in content
        assert "Generated on" in content
        assert "[[doc1.md|Doc1]]" in content
        assert "[[doc2.md|Doc2]]" in content
        assert "[config.yaml]" in content
        assert "## Other Files" in content

    def test_get_existing_files(self, temp_obsidian_vault):
        """Test getting existing files in a folder."""
        manager = ObsidianVaultManager(temp_obsidian_vault)

        # Create test structure
        test_folder = temp_obsidian_vault / "test_folder"
        test_folder.mkdir()

        (test_folder / "file1.md").write_text("content")
        (test_folder / "file2.txt").write_text("content")
        (test_folder / ".hidden").write_text("content")  # Should be ignored

        subfolder = test_folder / "subfolder"
        subfolder.mkdir()
        (subfolder / "file3.md").write_text("content")

        files = manager.get_existing_files("test_folder")

        assert len(files) == 3  # Should not include .hidden
        file_names = [f.name for f in files]
        assert "file1.md" in file_names
        assert "file2.txt" in file_names
        assert "file3.md" in file_names
        assert ".hidden" not in file_names

    def test_get_existing_files_nonexistent_folder(self, temp_obsidian_vault):
        """Test getting files from nonexistent folder."""
        manager = ObsidianVaultManager(temp_obsidian_vault)
        files = manager.get_existing_files("nonexistent")
        assert files == []

    def test_validate_wikilinks(self, temp_obsidian_vault):
        """Test validating wikilinks in content."""
        manager = ObsidianVaultManager(temp_obsidian_vault)

        # Create some files to link to
        (temp_obsidian_vault / "existing_file.md").write_text("content")
        (temp_obsidian_vault / "another_file.txt").write_text("content")

        content = """
        This is a test with [[existing_file]] and [[nonexistent_file]].
        Also [[another_file|Display Name]] and [[existing_file|Custom Display]].
        """

        results = manager.validate_wikilinks(content)

        assert results["existing_file"] is True
        assert results["nonexistent_file"] is False
        assert results["another_file"] is True

    def test_create_template_file(self, temp_obsidian_vault):
        """Test creating a template file."""
        manager = ObsidianVaultManager(temp_obsidian_vault)

        template_name = "test_template"
        template_content = "# {{title}}\n\nContent goes here..."

        template_path = manager.create_template_file(template_name, template_content)

        expected_path = temp_obsidian_vault / "Templates" / "test_template.md"
        assert template_path == expected_path
        assert template_path.exists()
        assert template_path.read_text() == template_content
        assert (temp_obsidian_vault / "Templates").exists()


class TestVaultDiscovery:
    """Test cases for vault discovery functions."""

    def test_discover_vault_found(self, temp_obsidian_vault):
        """Test discovering vault from subdirectory."""
        # Create a subdirectory
        subdir = temp_obsidian_vault / "sub" / "nested"
        subdir.mkdir(parents=True)

        discovered = discover_vault(subdir)
        assert discovered == temp_obsidian_vault

    def test_discover_vault_not_found(self, tmp_path):
        """Test discovering vault when none exists."""
        discovered = discover_vault(tmp_path)
        assert discovered is None

    def test_discover_vault_from_root(self, temp_obsidian_vault):
        """Test discovering vault from vault root."""
        discovered = discover_vault(temp_obsidian_vault)
        assert discovered == temp_obsidian_vault


class TestVaultValidation:
    """Test cases for vault validation functions."""

    def test_validate_vault_structure_valid(self, temp_obsidian_vault):
        """Test validating a valid vault structure."""
        # Create app.json
        (temp_obsidian_vault / ".obsidian" / "app.json").write_text(
            '{"theme": "obsidian"}'
        )

        issues = validate_vault_structure(temp_obsidian_vault)
        assert len(issues) == 0

    def test_validate_vault_structure_missing_obsidian_dir(self, tmp_path):
        """Test validating vault without .obsidian directory."""
        issues = validate_vault_structure(tmp_path)
        assert any("Missing .obsidian directory" in issue for issue in issues)

    def test_validate_vault_structure_missing_app_json(self, temp_obsidian_vault):
        """Test validating vault without app.json."""
        issues = validate_vault_structure(temp_obsidian_vault)
        assert any("Missing app.json configuration file" in issue for issue in issues)

    def test_validate_vault_structure_nonexistent(self, tmp_path):
        """Test validating nonexistent vault."""
        nonexistent = tmp_path / "nonexistent"
        issues = validate_vault_structure(nonexistent)
        assert any("does not exist" in issue for issue in issues)

    def test_validate_vault_structure_file_instead_of_dir(self, tmp_path):
        """Test validating file instead of directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        issues = validate_vault_structure(file_path)
        assert any("not a directory" in issue for issue in issues)


class TestFrontmatterCreation:
    """Test cases for frontmatter creation."""

    def test_create_obsidian_frontmatter_basic(self):
        """Test creating basic frontmatter."""
        title = "Test Document"
        tags = ["python", "documentation"]

        with patch("utils.obsidian_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = (
                "2024-01-01T12:00:00"
            )
            frontmatter = create_obsidian_frontmatter(title, tags)

        assert "---" in frontmatter
        assert "title: Test Document" in frontmatter
        assert "- python" in frontmatter
        assert "- documentation" in frontmatter
        assert "created: '2024-01-01T12:00:00'" in frontmatter

    def test_create_obsidian_frontmatter_with_source(self):
        """Test creating frontmatter with source file."""
        title = "Test Document"
        tags = ["python"]
        source_file = "src/module.py"

        with patch("utils.obsidian_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = (
                "2024-01-01T12:00:00"
            )
            frontmatter = create_obsidian_frontmatter(title, tags, source_file)

        assert "source: src/module.py" in frontmatter

    def test_create_obsidian_frontmatter_empty_tags(self):
        """Test creating frontmatter with empty tags."""
        title = "Test Document"
        tags = []

        frontmatter = create_obsidian_frontmatter(title, tags)
        assert "tags: []" in frontmatter


@pytest.fixture
def temp_obsidian_vault(tmp_path):
    """Create a temporary Obsidian vault for testing."""
    vault_path = tmp_path / "test_vault"
    vault_path.mkdir()

    # Create .obsidian directory
    obsidian_dir = vault_path / ".obsidian"
    obsidian_dir.mkdir()

    return vault_path
