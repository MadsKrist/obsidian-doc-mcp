"""Incremental build system for documentation generation.

This module provides functionality to track changes and enable incremental
documentation builds, improving performance for large projects.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FileState:
    """Represents the state of a file for change detection."""

    path: str
    size: int
    mtime: float
    hash: str
    last_build: float = 0.0


@dataclass
class BuildState:
    """Represents the complete build state of a project."""

    project_path: str
    last_full_build: float = 0.0
    files: dict[str, FileState] = field(default_factory=dict)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    outputs: dict[str, list[str]] = field(default_factory=dict)  # source -> generated files
    build_version: str = "1.0"


class IncrementalBuildManager:
    """Manages incremental documentation builds."""

    def __init__(self, project_path: Path, build_cache_file: str = ".mcp-docs-build.json"):
        """Initialize the incremental build manager.

        Args:
            project_path: Root path of the project
            build_cache_file: Name of the build cache file
        """
        self.project_path = Path(project_path)
        self.build_cache_file = self.project_path / build_cache_file
        self.build_state = BuildState(project_path=str(project_path))
        self._load_build_state()

        logger.info(f"Initialized incremental build manager for: {project_path}")

    def _load_build_state(self) -> None:
        """Load build state from cache file."""
        if not self.build_cache_file.exists():
            logger.debug("No build cache found, starting fresh")
            return

        try:
            with open(self.build_cache_file, encoding="utf-8") as f:
                data = json.load(f)

            self.build_state = BuildState(
                project_path=data["project_path"],
                last_full_build=data.get("last_full_build", 0.0),
                build_version=data.get("build_version", "1.0"),
                files={
                    path: FileState(**file_data)
                    for path, file_data in data.get("files", {}).items()
                },
                dependencies=data.get("dependencies", {}),
                outputs=data.get("outputs", {}),
            )

            logger.info(f"Loaded build state with {len(self.build_state.files)} tracked files")

        except Exception as e:
            logger.warning(f"Failed to load build state: {e}")
            self.build_state = BuildState(project_path=str(self.project_path))

    def _save_build_state(self) -> None:
        """Save build state to cache file."""
        try:
            data = {
                "project_path": self.build_state.project_path,
                "last_full_build": self.build_state.last_full_build,
                "build_version": self.build_state.build_version,
                "files": {
                    path: {
                        "path": file_state.path,
                        "size": file_state.size,
                        "mtime": file_state.mtime,
                        "hash": file_state.hash,
                        "last_build": file_state.last_build,
                    }
                    for path, file_state in self.build_state.files.items()
                },
                "dependencies": self.build_state.dependencies,
                "outputs": self.build_state.outputs,
            }

            with open(self.build_cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved build state with {len(self.build_state.files)} files")

        except Exception as e:
            logger.warning(f"Failed to save build state: {e}")

    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file content."""
        try:
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return ""

    def _get_current_file_state(self, file_path: Path) -> FileState | None:
        """Get current state of a file."""
        if not file_path.exists():
            return None

        try:
            stat = file_path.stat()
            return FileState(
                path=str(file_path),
                size=stat.st_size,
                mtime=stat.st_mtime,
                hash=self._get_file_hash(file_path),
            )
        except Exception:
            return None

    def is_file_changed(self, file_path: Path) -> bool:
        """Check if a file has changed since last build.

        Args:
            file_path: Path to the file to check

        Returns:
            True if file has changed or is new, False otherwise
        """
        file_key = str(file_path)
        current_state = self._get_current_file_state(file_path)

        if not current_state:
            # File doesn't exist now, but might have been tracked before
            return file_key in self.build_state.files

        if file_key not in self.build_state.files:
            # New file
            return True

        previous_state = self.build_state.files[file_key]

        # Check if file has changed
        return (
            current_state.size != previous_state.size
            or current_state.mtime != previous_state.mtime
            or current_state.hash != previous_state.hash
        )

    def get_changed_files(self, file_paths: list[Path]) -> set[Path]:
        """Get list of files that have changed since last build.

        Args:
            file_paths: List of files to check

        Returns:
            Set of changed file paths
        """
        changed_files = set()

        for file_path in file_paths:
            if self.is_file_changed(file_path):
                changed_files.add(file_path)

        # Also check for deleted files
        for tracked_path in self.build_state.files:
            if not Path(tracked_path).exists():
                changed_files.add(Path(tracked_path))

        logger.info(f"Found {len(changed_files)} changed files out of {len(file_paths)} total")
        return changed_files

    def get_dependent_files(self, changed_file: Path) -> set[Path]:
        """Get files that depend on the changed file.

        Args:
            changed_file: Path to the file that changed

        Returns:
            Set of files that depend on the changed file
        """
        dependent_files = set()
        changed_key = str(changed_file)

        # Find files that import or depend on the changed file
        for file_path, deps in self.build_state.dependencies.items():
            if changed_key in deps:
                dependent_files.add(Path(file_path))

        return dependent_files

    def mark_files_built(
        self,
        file_paths: list[Path],
        generated_files: dict[str, list[str]] | None = None,
    ) -> None:
        """Mark files as built and update their state.

        Args:
            file_paths: List of files that were built
            generated_files: Dictionary mapping source files to generated output files
        """
        current_time = time.time()
        generated_files = generated_files or {}

        for file_path in file_paths:
            if not file_path.exists():
                # File was deleted, remove from tracking
                file_key = str(file_path)
                if file_key in self.build_state.files:
                    del self.build_state.files[file_key]
                continue

            current_state = self._get_current_file_state(file_path)
            if current_state:
                current_state.last_build = current_time
                self.build_state.files[str(file_path)] = current_state

        # Update output mappings
        for source_file, outputs in generated_files.items():
            self.build_state.outputs[source_file] = outputs

        self._save_build_state()

    def mark_full_build(self) -> None:
        """Mark that a full build was completed."""
        self.build_state.last_full_build = time.time()
        self._save_build_state()
        logger.info("Marked full build completion")

    def update_dependencies(self, dependencies: dict[str, list[str]]) -> None:
        """Update dependency information.

        Args:
            dependencies: Dictionary mapping files to their dependencies
        """
        self.build_state.dependencies.update(dependencies)
        self._save_build_state()

    def should_force_full_build(self, force_after_hours: float = 24.0) -> bool:
        """Check if a full build should be forced.

        Args:
            force_after_hours: Force full build after this many hours

        Returns:
            True if full build should be forced
        """
        if self.build_state.last_full_build == 0:
            return True  # Never had a full build

        hours_since_full_build = (time.time() - self.build_state.last_full_build) / 3600
        return hours_since_full_build > force_after_hours

    def get_outdated_outputs(self) -> set[str]:
        """Get output files that may be outdated based on source changes.

        Returns:
            Set of output file paths that may need regeneration
        """
        outdated_outputs = set()

        for source_file, outputs in self.build_state.outputs.items():
            source_path = Path(source_file)
            if self.is_file_changed(source_path):
                outdated_outputs.update(outputs)

        return outdated_outputs

    def clean_orphaned_outputs(self) -> list[str]:
        """Clean up output files whose source files no longer exist.

        Returns:
            List of cleaned output file paths
        """
        cleaned_files = []
        sources_to_remove = []

        for source_file, outputs in self.build_state.outputs.items():
            if not Path(source_file).exists():
                # Source file deleted, clean up its outputs
                for output_file in outputs:
                    output_path = Path(output_file)
                    if output_path.exists():
                        try:
                            output_path.unlink()
                            cleaned_files.append(output_file)
                        except Exception as e:
                            logger.warning(f"Failed to clean output file {output_file}: {e}")

                sources_to_remove.append(source_file)

        # Remove orphaned source mappings
        for source_file in sources_to_remove:
            del self.build_state.outputs[source_file]

        if cleaned_files:
            self._save_build_state()
            logger.info(f"Cleaned {len(cleaned_files)} orphaned output files")

        return cleaned_files

    def get_build_stats(self) -> dict[str, Any]:
        """Get build statistics and status information.

        Returns:
            Dictionary with build statistics
        """
        current_time = time.time()

        return {
            "project_path": self.build_state.project_path,
            "tracked_files": len(self.build_state.files),
            "last_full_build": self.build_state.last_full_build,
            "hours_since_full_build": (current_time - self.build_state.last_full_build) / 3600
            if self.build_state.last_full_build > 0
            else float("inf"),
            "dependency_mappings": len(self.build_state.dependencies),
            "output_mappings": len(self.build_state.outputs),
            "build_version": self.build_state.build_version,
            "cache_file_exists": self.build_cache_file.exists(),
        }

    def clear_build_cache(self) -> None:
        """Clear the build cache and start fresh."""
        self.build_state = BuildState(project_path=str(self.project_path))
        if self.build_cache_file.exists():
            self.build_cache_file.unlink()
        logger.info("Build cache cleared")
