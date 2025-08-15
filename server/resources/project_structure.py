"""
MCP resource for real-time project structure access.

This module implements the project_structure MCP resource that provides
real-time access to Python project structure with filtering and search capabilities.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from config.project_config import Config, ConfigManager
from docs_generator.analyzer import PythonProjectAnalyzer

logger = logging.getLogger(__name__)


class ProjectStructureError(Exception):
    """Exception raised during project structure operations."""

    pass


class ProjectStructureResource:
    """Provides real-time access to project structure information."""

    def __init__(self, project_path: Path, config: Config | None = None):
        """Initialize the project structure resource.

        Args:
            project_path: Path to the Python project root
            config: Optional project configuration
        """
        self.project_path = project_path
        self.config = config or Config()
        self.analyzer = PythonProjectAnalyzer(project_path)
        self._cached_structure = None
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes cache TTL

    async def get_structure(
        self,
        refresh: bool = False,
        include_private: bool | None = None,
        filter_patterns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get the current project structure.

        Args:
            refresh: Force refresh of cached structure
            include_private: Override config setting for private members
            filter_patterns: Additional patterns to filter files

        Returns:
            Project structure data

        Raises:
            ProjectStructureError: If structure analysis fails
        """
        try:
            # Check cache validity
            if not refresh and self._is_cache_valid():
                logger.debug("Returning cached project structure")
                if self._cached_structure:
                    return self._apply_filters(
                        self._cached_structure, include_private, filter_patterns
                    )

            # Analyze project structure
            logger.info("Analyzing project structure")
            exclude_patterns = self.config.project.exclude_patterns.copy()

            # Add filter patterns if provided
            if filter_patterns:
                exclude_patterns.extend(filter_patterns)

            project_structure = self.analyzer.analyze_project(exclude_patterns)

            # Convert to serializable format
            structure_data = await self._convert_to_dict(project_structure)

            # Cache the result
            self._cached_structure = structure_data
            self._cache_timestamp = datetime.now()

            logger.info(f"Project structure cached: {len(structure_data['modules'])} modules")

            return self._apply_filters(structure_data, include_private, filter_patterns)

        except Exception as e:
            logger.error(f"Failed to get project structure: {e}")
            raise ProjectStructureError(f"Failed to analyze project structure: {e}") from e

    async def search_structure(
        self,
        query: str,
        search_type: str = "all",
        case_sensitive: bool = False,
    ) -> dict[str, Any]:
        """Search within the project structure.

        Args:
            query: Search query string
            search_type: Type of search ('all', 'modules', 'classes', 'functions')
            case_sensitive: Whether to perform case-sensitive search

        Returns:
            Search results

        Raises:
            ProjectStructureError: If search fails
        """
        try:
            # Get current structure
            structure = await self.get_structure()

            search_results = {
                "query": query,
                "search_type": search_type,
                "case_sensitive": case_sensitive,
                "results": {
                    "modules": [],
                    "classes": [],
                    "functions": [],
                },
                "total_matches": 0,
                "search_timestamp": datetime.now().isoformat(),
            }

            query_lower = query.lower() if not case_sensitive else query

            # Search modules
            if search_type in ["all", "modules"]:
                for module in structure["modules"]:
                    module_name = module["name"] if case_sensitive else module["name"].lower()
                    if query_lower in module_name or self._search_in_text(
                        module.get("docstring", ""), query, case_sensitive
                    ):
                        search_results["results"]["modules"].append(
                            {
                                "name": module["name"],
                                "file_path": module["file_path"],
                                "docstring": module.get("docstring", "")[:200] + "..."
                                if len(module.get("docstring", "")) > 200
                                else module.get("docstring", ""),
                                "match_type": "name" if query_lower in module_name else "docstring",
                            }
                        )

            # Search classes
            if search_type in ["all", "classes"]:
                for module in structure["modules"]:
                    for class_info in module["classes"]:
                        class_name = (
                            class_info["name"] if case_sensitive else class_info["name"].lower()
                        )
                        if query_lower in class_name or self._search_in_text(
                            class_info.get("docstring", ""), query, case_sensitive
                        ):
                            search_results["results"]["classes"].append(
                                {
                                    "name": class_info["name"],
                                    "module": module["name"],
                                    "file_path": module["file_path"],
                                    "line_number": class_info["line_number"],
                                    "docstring": class_info.get("docstring", "")[:200] + "..."
                                    if len(class_info.get("docstring", "")) > 200
                                    else class_info.get("docstring", ""),
                                    "match_type": "name"
                                    if query_lower in class_name
                                    else "docstring",
                                }
                            )

            # Search functions
            if search_type in ["all", "functions"]:
                for module in structure["modules"]:
                    for func_info in module["functions"]:
                        func_name = (
                            func_info["name"] if case_sensitive else func_info["name"].lower()
                        )
                        if query_lower in func_name or self._search_in_text(
                            func_info.get("docstring", ""), query, case_sensitive
                        ):
                            search_results["results"]["functions"].append(
                                {
                                    "name": func_info["name"],
                                    "module": module["name"],
                                    "file_path": module["file_path"],
                                    "line_number": func_info["line_number"],
                                    "signature": func_info.get("signature", ""),
                                    "docstring": func_info.get("docstring", "")[:200] + "..."
                                    if len(func_info.get("docstring", "")) > 200
                                    else func_info.get("docstring", ""),
                                    "match_type": "name"
                                    if query_lower in func_name
                                    else "docstring",
                                }
                            )

            # Calculate total matches
            search_results["total_matches"] = sum(
                len(results) for results in search_results["results"].values()
            )

            logger.info(f"Search for '{query}' found {search_results['total_matches']} matches")
            return search_results

        except Exception as e:
            logger.error(f"Failed to search project structure: {e}")
            raise ProjectStructureError(f"Failed to search project structure: {e}") from e

    async def get_file_info(self, file_path: str) -> dict[str, Any]:
        """Get detailed information about a specific file.

        Args:
            file_path: Path to the file (relative to project root)

        Returns:
            Detailed file information

        Raises:
            ProjectStructureError: If file analysis fails
        """
        try:
            full_path = self.project_path / file_path
            if not full_path.exists():
                raise ProjectStructureError(f"File not found: {file_path}")

            if not full_path.suffix == ".py":
                raise ProjectStructureError(f"Not a Python file: {file_path}")

            # Analyze the specific file
            module_info = self.analyzer._analyze_file(full_path)
            if not module_info:
                raise ProjectStructureError(f"Failed to analyze file: {file_path}")

            # Convert to detailed dictionary
            file_info = {
                "file_path": str(file_path),
                "absolute_path": str(full_path),
                "name": module_info.name,
                "docstring": module_info.docstring,
                "line_count": self._count_lines(full_path),
                "size_bytes": full_path.stat().st_size,
                "last_modified": datetime.fromtimestamp(full_path.stat().st_mtime).isoformat(),
                "classes": [],
                "functions": [],
                "imports": module_info.imports,
                "analysis_timestamp": datetime.now().isoformat(),
            }

            # Add class information
            for class_info in module_info.classes:
                class_data = {
                    "name": class_info.name,
                    "line_number": class_info.line_number,
                    "docstring": class_info.docstring,
                    "methods": [],
                    "base_classes": class_info.base_classes,
                    "decorators": class_info.decorators,
                    "is_private": class_info.is_private,
                }

                # Add method information
                for method in class_info.methods:
                    class_data["methods"].append(
                        {
                            "name": method.name,
                            "line_number": method.line_number,
                            "signature": method.signature,
                            "docstring": method.docstring,
                            "is_property": method.is_property,
                            "is_staticmethod": method.is_staticmethod,
                            "is_classmethod": method.is_classmethod,
                            "is_private": method.is_private,
                            "decorators": method.decorators,
                        }
                    )

                file_info["classes"].append(class_data)

            # Add function information
            for func_info in module_info.functions:
                file_info["functions"].append(
                    {
                        "name": func_info.name,
                        "line_number": func_info.line_number,
                        "signature": func_info.signature,
                        "docstring": func_info.docstring,
                        "is_async": func_info.is_async,
                        "is_private": func_info.is_private,
                        "parameters": func_info.parameters,
                        "return_type": func_info.return_type,
                        "decorators": func_info.decorators,
                    }
                )

            return file_info

        except Exception as e:
            logger.error(f"Failed to get file info for {file_path}: {e}")
            raise ProjectStructureError(f"Failed to analyze file {file_path}: {e}") from e

    async def get_changes(self, since: str | None = None) -> dict[str, Any]:
        """Get project structure changes since a specific timestamp.

        Args:
            since: ISO timestamp to check changes since (optional)

        Returns:
            Information about changes

        Raises:
            ProjectStructureError: If change detection fails
        """
        try:
            changes = {
                "since": since,
                "current_timestamp": datetime.now().isoformat(),
                "has_changes": True,  # Simplified - always assume changes for now
                "changed_files": [],
                "new_files": [],
                "deleted_files": [],
                "summary": {
                    "total_changes": 0,
                    "modules_changed": 0,
                    "classes_changed": 0,
                    "functions_changed": 0,
                },
            }

            if since:
                try:
                    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))

                    # Find files modified since timestamp
                    for py_file in self.project_path.rglob("*.py"):
                        if py_file.stat().st_mtime > since_dt.timestamp():
                            relative_path = str(py_file.relative_to(self.project_path))
                            changes["changed_files"].append(
                                {
                                    "file_path": relative_path,
                                    "last_modified": datetime.fromtimestamp(
                                        py_file.stat().st_mtime
                                    ).isoformat(),
                                    "change_type": "modified",
                                }
                            )

                    changes["summary"]["total_changes"] = len(changes["changed_files"])
                    changes["has_changes"] = changes["summary"]["total_changes"] > 0

                except ValueError:
                    logger.warning(f"Invalid timestamp format: {since}")
                    changes["error"] = f"Invalid timestamp format: {since}"

            else:
                # No since timestamp - return current state summary
                structure = await self.get_structure()
                changes["summary"]["modules_changed"] = len(structure["modules"])
                changes["summary"]["total_changes"] = changes["summary"]["modules_changed"]

            return changes

        except Exception as e:
            logger.error(f"Failed to get project changes: {e}")
            raise ProjectStructureError(f"Failed to detect changes: {e}") from e

    def _is_cache_valid(self) -> bool:
        """Check if the cached structure is still valid.

        Returns:
            True if cache is valid, False otherwise
        """
        if not self._cached_structure or not self._cache_timestamp:
            return False

        elapsed = datetime.now() - self._cache_timestamp
        return elapsed.total_seconds() < self._cache_ttl

    async def _convert_to_dict(self, project_structure) -> dict[str, Any]:
        """Convert ProjectStructure object to serializable dictionary.

        Args:
            project_structure: ProjectStructure object

        Returns:
            Serializable dictionary representation
        """
        structure_dict = {
            "project_name": project_structure.project_name,
            "root_path": str(project_structure.root_path),
            "modules": [],
            "packages": dict(project_structure.packages),
            "dependencies": list(project_structure.dependencies),
            "external_dependencies": list(project_structure.external_dependencies),
            "internal_dependencies": list(project_structure.internal_dependencies),
            "dependency_graph": dict(project_structure.dependency_graph),
            "analysis_timestamp": datetime.now().isoformat(),
            "statistics": {
                "total_modules": len(project_structure.modules),
                "total_classes": 0,
                "total_functions": 0,
                "total_lines": 0,
            },
        }

        for module in project_structure.modules:
            module_dict = {
                "name": module.name,
                "file_path": str(module.file_path),
                "docstring": module.docstring,
                "classes": [],
                "functions": [],
                "imports": module.imports,
            }

            # Add class information
            for class_info in module.classes:
                class_dict = {
                    "name": class_info.name,
                    "line_number": class_info.line_number,
                    "docstring": class_info.docstring,
                    "base_classes": class_info.base_classes,
                    "methods": [],
                    "decorators": class_info.decorators,
                    "is_private": class_info.is_private,
                }

                # Add method information
                for method in class_info.methods:
                    class_dict["methods"].append(
                        {
                            "name": method.name,
                            "line_number": method.line_number,
                            "signature": method.signature,
                            "docstring": method.docstring,
                            "is_property": method.is_property,
                            "is_staticmethod": method.is_staticmethod,
                            "is_classmethod": method.is_classmethod,
                            "is_private": method.is_private,
                        }
                    )

                module_dict["classes"].append(class_dict)
                structure_dict["statistics"]["total_classes"] += 1

            # Add function information
            for func_info in module.functions:
                module_dict["functions"].append(
                    {
                        "name": func_info.name,
                        "line_number": func_info.line_number,
                        "signature": func_info.signature,
                        "docstring": func_info.docstring,
                        "is_async": func_info.is_async,
                        "is_private": func_info.is_private,
                        "parameters": func_info.parameters,
                        "return_type": func_info.return_type,
                    }
                )
                structure_dict["statistics"]["total_functions"] += 1

            structure_dict["modules"].append(module_dict)

        return structure_dict

    def _apply_filters(
        self,
        structure: dict[str, Any],
        include_private: bool | None,
        filter_patterns: list[str] | None,
    ) -> dict[str, Any]:
        """Apply filtering options to the structure data.

        Args:
            structure: Original structure data
            include_private: Whether to include private members
            filter_patterns: Patterns to filter out

        Returns:
            Filtered structure data
        """
        # Create a copy to avoid modifying the cached version
        filtered = structure.copy()

        # Apply private member filtering
        if include_private is not None:
            config_include_private = include_private
        else:
            config_include_private = self.config.project.include_private

        if not config_include_private:
            # Filter out private members
            for module in filtered["modules"]:
                module["classes"] = [
                    cls for cls in module["classes"] if not cls.get("is_private", False)
                ]
                module["functions"] = [
                    func for func in module["functions"] if not func.get("is_private", False)
                ]

                # Filter private methods from classes
                for cls in module["classes"]:
                    cls["methods"] = [
                        method for method in cls["methods"] if not method.get("is_private", False)
                    ]

        return filtered

    def _search_in_text(self, text: str, query: str, case_sensitive: bool) -> bool:
        """Search for query in text.

        Args:
            text: Text to search in
            query: Query string
            case_sensitive: Whether search is case sensitive

        Returns:
            True if query found in text
        """
        if not text:
            return False

        search_text = text if case_sensitive else text.lower()
        search_query = query if case_sensitive else query.lower()

        return search_query in search_text

    def _count_lines(self, file_path: Path) -> int:
        """Count lines in a file.

        Args:
            file_path: Path to the file

        Returns:
            Number of lines in the file
        """
        try:
            with file_path.open("r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0


async def get_project_structure_resource(
    project_path: str,
    config_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    MCP resource handler for project structure access.

    Args:
        project_path: Path to the Python project root
        config_override: Optional configuration overrides

    Returns:
        Project structure resource data

    Raises:
        ProjectStructureError: If resource access fails
    """
    try:
        # Load configuration
        config_manager = ConfigManager()
        config_path = Path(project_path) / ".mcp-docs.yaml"
        if config_path.exists():
            config = config_manager.load_config(config_path)
        else:
            config = Config()

        # Apply overrides if provided
        if config_override:
            for key, value in config_override.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Initialize resource
        resource = ProjectStructureResource(Path(project_path), config)

        # Get current structure
        structure = await resource.get_structure()

        return {
            "resource_type": "project_structure",
            "data": structure,
            "capabilities": {
                "search": True,
                "filtering": True,
                "change_detection": True,
                "file_analysis": True,
            },
        }

    except Exception as e:
        logger.error(f"get_project_structure_resource failed: {e}")
        return {
            "resource_type": "project_structure",
            "error": str(e),
            "error_type": type(e).__name__,
        }


# Resource metadata for MCP registration
RESOURCE_DEFINITION = {
    "name": "project_structure",
    "description": "Real-time access to Python project structure with search and filtering",
    "schema": {
        "type": "object",
        "properties": {
            "project_name": {"type": "string"},
            "root_path": {"type": "string"},
            "modules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "file_path": {"type": "string"},
                        "docstring": {"type": "string"},
                        "classes": {"type": "array"},
                        "functions": {"type": "array"},
                    },
                },
            },
            "statistics": {
                "type": "object",
                "properties": {
                    "total_modules": {"type": "integer"},
                    "total_classes": {"type": "integer"},
                    "total_functions": {"type": "integer"},
                },
            },
        },
    },
}
