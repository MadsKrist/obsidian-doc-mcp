"""
Obsidian vault management utilities.

This module provides utilities for safely working with Obsidian vaults,
including vault discovery, validation, and safe file operations.
"""

import shutil
from datetime import datetime
from pathlib import Path

import yaml


class ObsidianVaultError(Exception):
    """Base exception for Obsidian vault operations."""

    pass


class VaultNotFoundError(ObsidianVaultError):
    """Raised when an Obsidian vault cannot be found."""

    pass


class VaultValidationError(ObsidianVaultError):
    """Raised when vault validation fails."""

    pass


class ObsidianVaultManager:
    """Manager for Obsidian vault operations."""

    def __init__(self, vault_path: Path):
        """Initialize vault manager.

        Args:
            vault_path: Path to the Obsidian vault

        Raises:
            VaultNotFoundError: If vault doesn't exist
            VaultValidationError: If vault is invalid
        """
        self.vault_path = Path(vault_path)
        self._validate_vault()

    def _validate_vault(self) -> None:
        """Validate that the vault path is a valid Obsidian vault.

        Raises:
            VaultNotFoundError: If vault doesn't exist
            VaultValidationError: If vault is invalid
        """
        if not self.vault_path.exists():
            raise VaultNotFoundError(f"Vault path does not exist: {self.vault_path}")

        if not self.vault_path.is_dir():
            raise VaultValidationError(f"Vault path is not a directory: {self.vault_path}")

        # Check for .obsidian directory (indicates an Obsidian vault)
        obsidian_dir = self.vault_path / ".obsidian"
        if not obsidian_dir.exists():
            # Create .obsidian directory if it doesn't exist (new vault)
            obsidian_dir.mkdir(exist_ok=True)

    def ensure_folder_exists(self, folder_path: str) -> Path:
        """Ensure a folder exists within the vault.

        Args:
            folder_path: Relative path within the vault

        Returns:
            Absolute path to the folder
        """
        full_path = self.vault_path / folder_path
        full_path.mkdir(parents=True, exist_ok=True)
        return full_path

    def backup_file(self, file_path: Path) -> Path | None:
        """Create a backup of an existing file.

        Args:
            file_path: Path to the file to backup

        Returns:
            Path to the backup file, or None if file doesn't exist
        """
        if not file_path.exists():
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = file_path.with_suffix(f".backup_{timestamp}{file_path.suffix}")

        shutil.copy2(file_path, backup_path)
        return backup_path

    def safe_write_file(
        self, file_path: Path, content: str, create_backup: bool = True
    ) -> tuple[Path, Path | None]:
        """Safely write content to a file with optional backup.

        Args:
            file_path: Path to write to
            content: Content to write
            create_backup: Whether to create backup of existing file

        Returns:
            Tuple of (file_path, backup_path)
        """
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Create backup if requested and file exists
        backup_path = None
        if create_backup and file_path.exists():
            backup_path = self.backup_file(file_path)

        # Write content atomically
        temp_path = file_path.with_suffix(f".tmp_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)
            temp_path.replace(file_path)
        except Exception:
            # Clean up temp file if write failed
            if temp_path.exists():
                temp_path.unlink()
            raise

        return file_path, backup_path

    def generate_index_file(self, folder_path: Path, title: str, files: list[Path]) -> str:
        """Generate an index file for a folder.

        Args:
            folder_path: Path to the folder (used for relative path calculation)
            title: Title for the index
            files: List of files to include in index

        Returns:
            Content for the index file
        """
        content_lines = [
            f"# {title}",
            "",
            f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Files",
            "",
        ]

        # Group files by type
        md_files = [f for f in files if f.suffix == ".md"]
        other_files = [f for f in files if f.suffix != ".md"]

        # Add markdown files
        if md_files:
            for file_path in sorted(md_files):
                relative_path = file_path.relative_to(self.vault_path)
                name = file_path.stem.replace("_", " ").title()
                content_lines.append(f"- [[{relative_path.as_posix()}|{name}]]")

        # Add other files
        if other_files:
            content_lines.extend(["", "## Other Files", ""])
            for file_path in sorted(other_files):
                relative_path = file_path.relative_to(self.vault_path)
                content_lines.append(f"- [{file_path.name}]({relative_path.as_posix()})")

        content_lines.append("")
        return "\n".join(content_lines)

    def get_existing_files(self, folder_path: str) -> list[Path]:
        """Get list of existing files in a folder.

        Args:
            folder_path: Relative path within the vault

        Returns:
            List of existing file paths
        """
        full_path = self.vault_path / folder_path
        if not full_path.exists():
            return []

        files = []
        for file_path in full_path.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                files.append(file_path)

        return files

    def validate_wikilinks(self, content: str) -> dict[str, bool]:
        """Validate wikilinks in content.

        Args:
            content: Content to check for wikilinks

        Returns:
            Dictionary mapping wikilinks to their validity status
        """
        import re

        # Find all wikilinks in format [[link]] or [[link|display]]
        wikilink_pattern = r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]"
        links = re.findall(wikilink_pattern, content)

        validation_results = {}
        for link in links:
            # Try different possible paths for the link
            possible_paths = [
                self.vault_path / f"{link}.md",
                self.vault_path / link,
                self.vault_path / f"{link}.txt",
            ]

            # Check if any of the possible paths exist
            exists = any(path.exists() for path in possible_paths)
            validation_results[link] = exists

        return validation_results

    def create_template_file(self, template_name: str, template_content: str) -> Path:
        """Create a template file in the vault.

        Args:
            template_name: Name of the template
            template_content: Template content

        Returns:
            Path to the created template file
        """
        templates_folder = self.ensure_folder_exists("Templates")
        template_path = templates_folder / f"{template_name}.md"

        self.safe_write_file(template_path, template_content)
        return template_path


def discover_vault(start_path: Path) -> Path | None:
    """Discover Obsidian vault by searching upward from start path.

    Args:
        start_path: Path to start searching from

    Returns:
        Path to vault root, or None if not found
    """
    current_path = Path(start_path).resolve()

    # Search upward for .obsidian directory
    while current_path != current_path.parent:
        obsidian_dir = current_path / ".obsidian"
        if obsidian_dir.exists() and obsidian_dir.is_dir():
            return current_path
        current_path = current_path.parent

    return None


def validate_vault_structure(vault_path: Path) -> list[str]:
    """Validate vault structure and return any issues found.

    Args:
        vault_path: Path to the vault

    Returns:
        List of validation issues (empty if valid)
    """
    issues = []

    if not vault_path.exists():
        issues.append(f"Vault path does not exist: {vault_path}")
        return issues

    if not vault_path.is_dir():
        issues.append(f"Vault path is not a directory: {vault_path}")
        return issues

    obsidian_dir = vault_path / ".obsidian"
    if not obsidian_dir.exists():
        issues.append("Missing .obsidian directory (not a valid Obsidian vault)")

    # Check for common Obsidian files
    config_file = obsidian_dir / "app.json"
    if not config_file.exists():
        issues.append("Missing app.json configuration file")

    return issues


def create_obsidian_frontmatter(title: str, tags: list[str], source_file: str | None = None) -> str:
    """Create YAML frontmatter for Obsidian notes.

    Args:
        title: Title of the note
        tags: List of tags
        source_file: Optional source file reference

    Returns:
        YAML frontmatter string
    """
    frontmatter = {
        "title": title,
        "tags": tags,
        "created": datetime.now().isoformat(),
    }

    if source_file:
        frontmatter["source"] = source_file

    return "---\n" + yaml.dump(frontmatter, default_flow_style=False) + "---\n"
