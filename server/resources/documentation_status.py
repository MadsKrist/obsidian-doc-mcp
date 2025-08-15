"""
MCP resource for documentation status and coverage metrics.

This module implements the documentation_status MCP resource that provides
coverage metrics, last update timestamps, and quality scores with improvement suggestions.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from config.project_config import Config, ConfigManager
from docs_generator.analyzer import PythonProjectAnalyzer
from utils.obsidian_utils import ObsidianVaultManager

logger = logging.getLogger(__name__)


class DocumentationStatusError(Exception):
    """Exception raised during documentation status operations."""

    pass


class DocumentationStatusResource:
    """Provides documentation status and metrics information."""

    def __init__(self, project_path: Path, config: Config | None = None):
        """Initialize the documentation status resource.

        Args:
            project_path: Path to the Python project root
            config: Optional project configuration
        """
        self.project_path = project_path
        self.config = config or Config()
        self.analyzer = PythonProjectAnalyzer(project_path)
        self.vault_manager: ObsidianVaultManager | None = None

        # Initialize vault manager if vault path is configured
        if config and config.obsidian.vault_path:
            try:
                self.vault_manager = ObsidianVaultManager(
                    Path(config.obsidian.vault_path)
                )
            except Exception as e:
                logger.warning(f"Failed to initialize vault manager: {e}")

    async def get_status(self) -> dict[str, Any]:
        """Get comprehensive documentation status.

        Returns:
            Documentation status with metrics and recommendations

        Raises:
            DocumentationStatusError: If status analysis fails
        """
        try:
            status = {
                "status_timestamp": datetime.now().isoformat(),
                "project_info": {
                    "name": self.config.project.name,
                    "root_path": str(self.project_path),
                    "source_paths": self.config.project.source_paths,
                },
                "coverage": {},
                "quality": {},
                "recent_changes": {},
                "recommendations": [],
                "summary": {},
            }

            # Get coverage metrics
            logger.info("Calculating documentation coverage")
            coverage = await self._calculate_coverage()
            status["coverage"] = coverage

            # Get quality metrics (if vault is configured)
            if self.vault_manager:
                logger.info("Calculating documentation quality")
                quality = await self._calculate_quality()
                status["quality"] = quality
            else:
                status["quality"] = {
                    "score": 0.0,
                    "message": "Quality analysis requires Obsidian vault configuration",
                }

            # Get recent changes
            logger.info("Analyzing recent changes")
            recent_changes = await self._analyze_recent_changes()
            status["recent_changes"] = recent_changes

            # Generate recommendations
            recommendations = await self._generate_recommendations(
                coverage, status["quality"], recent_changes
            )
            status["recommendations"] = recommendations

            # Create summary
            status["summary"] = self._create_summary(status)

            logger.info("Documentation status analysis completed")
            return status

        except Exception as e:
            logger.error(f"Failed to get documentation status: {e}")
            raise DocumentationStatusError(
                f"Failed to analyze documentation status: {e}"
            ) from e

    async def get_coverage_metrics(self, detailed: bool = False) -> dict[str, Any]:
        """Get detailed coverage metrics.

        Args:
            detailed: Whether to include detailed per-item coverage

        Returns:
            Coverage metrics

        Raises:
            DocumentationStatusError: If coverage calculation fails
        """
        try:
            coverage = await self._calculate_coverage()

            if not detailed:
                # Return summary only
                return {
                    "overall_coverage": coverage["overall_coverage"],
                    "by_type": {
                        item_type: data["coverage_percentage"]
                        for item_type, data in coverage["by_type"].items()
                    },
                    "timestamp": coverage["timestamp"],
                }

            return coverage

        except Exception as e:
            logger.error(f"Failed to get coverage metrics: {e}")
            raise DocumentationStatusError(f"Failed to calculate coverage: {e}") from e

    async def get_quality_scores(self) -> dict[str, Any]:
        """Get documentation quality scores.

        Returns:
            Quality scores and issues

        Raises:
            DocumentationStatusError: If quality calculation fails
        """
        try:
            if not self.vault_manager:
                return {
                    "overall_score": 0.0,
                    "message": "Quality scoring requires Obsidian vault configuration",
                    "timestamp": datetime.now().isoformat(),
                }

            quality = await self._calculate_quality()
            return quality

        except Exception as e:
            logger.error(f"Failed to get quality scores: {e}")
            raise DocumentationStatusError(f"Failed to calculate quality: {e}") from e

    async def get_update_history(self, days: int = 30) -> dict[str, Any]:
        """Get documentation update history.

        Args:
            days: Number of days to look back

        Returns:
            Update history information

        Raises:
            DocumentationStatusError: If history analysis fails
        """
        try:
            history = {
                "period_days": days,
                "period_start": (datetime.now()).isoformat(),
                "updates": [],
                "statistics": {
                    "total_updates": 0,
                    "files_modified": 0,
                    "average_updates_per_day": 0.0,
                },
                "timestamp": datetime.now().isoformat(),
            }

            if not self.vault_manager:
                history[
                    "message"
                ] = "Update history requires Obsidian vault configuration"
                return history

            # Get documentation files
            docs_folder = (
                Path(self.vault_manager.vault_path) / self.config.obsidian.docs_folder
            )
            if not docs_folder.exists():
                history["message"] = f"Documentation folder not found: {docs_folder}"
                return history

            # Find recent updates
            cutoff_time = datetime.now().timestamp() - (days * 24 * 60 * 60)
            modified_files = []

            for md_file in docs_folder.rglob("*.md"):
                file_mtime = md_file.stat().st_mtime
                if file_mtime > cutoff_time:
                    relative_path = md_file.relative_to(docs_folder)
                    modified_files.append(
                        {
                            "file": str(relative_path),
                            "last_modified": datetime.fromtimestamp(
                                file_mtime
                            ).isoformat(),
                            "size_bytes": md_file.stat().st_size,
                        }
                    )

            # Sort by modification time (newest first)
            modified_files.sort(key=lambda x: x["last_modified"], reverse=True)

            history["updates"] = modified_files
            history["statistics"]["total_updates"] = len(modified_files)
            history["statistics"]["files_modified"] = len(
                set(f["file"] for f in modified_files)
            )

            if days > 0:
                history["statistics"]["average_updates_per_day"] = (
                    len(modified_files) / days
                )

            return history

        except Exception as e:
            logger.error(f"Failed to get update history: {e}")
            raise DocumentationStatusError(
                f"Failed to analyze update history: {e}"
            ) from e

    async def _calculate_coverage(self) -> dict[str, Any]:
        """Calculate documentation coverage metrics.

        Returns:
            Coverage metrics dictionary
        """
        try:
            # Analyze project structure
            project_structure = self.analyzer.analyze_project(
                self.config.project.exclude_patterns
            )

            coverage = {
                "timestamp": datetime.now().isoformat(),
                "overall_coverage": 0.0,
                "total_items": 0,
                "documented_items": 0,
                "by_type": {
                    "modules": {
                        "total": 0,
                        "documented": 0,
                        "coverage_percentage": 0.0,
                        "missing": [],
                    },
                    "classes": {
                        "total": 0,
                        "documented": 0,
                        "coverage_percentage": 0.0,
                        "missing": [],
                    },
                    "functions": {
                        "total": 0,
                        "documented": 0,
                        "coverage_percentage": 0.0,
                        "missing": [],
                    },
                },
                "missing_documentation": [],
            }

            total_items = 0
            documented_items = 0

            # Check module coverage
            for module in project_structure.modules:
                total_items += 1
                coverage["by_type"]["modules"]["total"] += 1

                if module.docstring and module.docstring.strip():
                    documented_items += 1
                    coverage["by_type"]["modules"]["documented"] += 1
                else:
                    missing_item = {
                        "type": "module",
                        "name": module.name,
                        "file": str(module.file_path),
                        "line": 1,
                    }
                    coverage["by_type"]["modules"]["missing"].append(missing_item)
                    coverage["missing_documentation"].append(missing_item)

                # Check class coverage
                for class_info in module.classes:
                    total_items += 1
                    coverage["by_type"]["classes"]["total"] += 1

                    if class_info.docstring and class_info.docstring.strip():
                        documented_items += 1
                        coverage["by_type"]["classes"]["documented"] += 1
                    else:
                        missing_item = {
                            "type": "class",
                            "name": f"{module.name}.{class_info.name}",
                            "file": str(module.file_path),
                            "line": class_info.line_number,
                        }
                        coverage["by_type"]["classes"]["missing"].append(missing_item)
                        coverage["missing_documentation"].append(missing_item)

                # Check function coverage
                for func_info in module.functions:
                    # Skip private functions if not including them
                    if func_info.is_private and not self.config.project.include_private:
                        continue

                    total_items += 1
                    coverage["by_type"]["functions"]["total"] += 1

                    if func_info.docstring and func_info.docstring.strip():
                        documented_items += 1
                        coverage["by_type"]["functions"]["documented"] += 1
                    else:
                        missing_item = {
                            "type": "function",
                            "name": f"{module.name}.{func_info.name}",
                            "file": str(module.file_path),
                            "line": func_info.line_number,
                        }
                        coverage["by_type"]["functions"]["missing"].append(missing_item)
                        coverage["missing_documentation"].append(missing_item)

            # Calculate percentages
            coverage["total_items"] = total_items
            coverage["documented_items"] = documented_items

            if total_items > 0:
                coverage["overall_coverage"] = (documented_items / total_items) * 100

            for item_type in coverage["by_type"]:
                type_data = coverage["by_type"][item_type]
                if type_data["total"] > 0:
                    type_data["coverage_percentage"] = (
                        type_data["documented"] / type_data["total"]
                    ) * 100

            return coverage

        except Exception as e:
            raise DocumentationStatusError(f"Coverage calculation failed: {e}") from e

    async def _calculate_quality(self) -> dict[str, Any]:
        """Calculate documentation quality metrics.

        Returns:
            Quality metrics dictionary
        """
        if not self.vault_manager:
            return {"overall_score": 0.0, "message": "Vault manager not available"}

        try:
            quality = {
                "timestamp": datetime.now().isoformat(),
                "overall_score": 0.0,
                "total_files": 0,
                "quality_checks": {
                    "structure": {"passed": 0, "total": 0, "score": 0.0},
                    "content": {"passed": 0, "total": 0, "score": 0.0},
                    "formatting": {"passed": 0, "total": 0, "score": 0.0},
                    "links": {"passed": 0, "total": 0, "score": 0.0},
                },
                "issues_by_severity": {
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                },
                "recent_issues": [],
            }

            docs_folder = (
                Path(self.vault_manager.vault_path) / self.config.obsidian.docs_folder
            )
            if not docs_folder.exists():
                quality["message"] = f"Documentation folder not found: {docs_folder}"
                return quality

            # Find all markdown files
            md_files = list(docs_folder.rglob("*.md"))
            quality["total_files"] = len(md_files)

            # Simple quality assessment (basic checks)
            for md_file in md_files:
                await self._assess_file_quality(md_file, quality)

            # Calculate scores
            for check_type in quality["quality_checks"]:
                check_data = quality["quality_checks"][check_type]
                if check_data["total"] > 0:
                    check_data["score"] = (
                        check_data["passed"] / check_data["total"]
                    ) * 100

            # Calculate overall score (weighted average)
            if quality["total_files"] > 0:
                total_checks = sum(
                    check["total"] for check in quality["quality_checks"].values()
                )
                passed_checks = sum(
                    check["passed"] for check in quality["quality_checks"].values()
                )

                if total_checks > 0:
                    quality["overall_score"] = (passed_checks / total_checks) * 100

            return quality

        except Exception as e:
            raise DocumentationStatusError(f"Quality calculation failed: {e}") from e

    async def _assess_file_quality(
        self, file_path: Path, quality: dict[str, Any]
    ) -> None:
        """Assess the quality of a single documentation file.

        Args:
            file_path: Path to the documentation file
            quality: Quality metrics dictionary to update
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            if not self.vault_manager:
                return
            relative_path = file_path.relative_to(Path(self.vault_manager.vault_path))

            # Check 1: Structure (has main heading)
            quality["quality_checks"]["structure"]["total"] += 1
            if content.strip().startswith("# "):
                quality["quality_checks"]["structure"]["passed"] += 1
            else:
                quality["issues_by_severity"]["medium"] += 1
                quality["recent_issues"].append(
                    {
                        "file": str(relative_path),
                        "type": "structure",
                        "severity": "medium",
                        "issue": "Missing main heading",
                    }
                )

            # Check 2: Content (has substantial content)
            quality["quality_checks"]["content"]["total"] += 1
            word_count = len(content.split())
            if word_count > 20:  # Arbitrary threshold
                quality["quality_checks"]["content"]["passed"] += 1
            else:
                quality["issues_by_severity"]["low"] += 1
                quality["recent_issues"].append(
                    {
                        "file": str(relative_path),
                        "type": "content",
                        "severity": "low",
                        "issue": f"Minimal content ({word_count} words)",
                    }
                )

            # Check 3: Formatting (basic markdown)
            quality["quality_checks"]["formatting"]["total"] += 1
            formatting_issues = []

            # Check for unmatched brackets
            if content.count("[[") != content.count("]]"):
                formatting_issues.append("unmatched wikilink brackets")

            if not formatting_issues:
                quality["quality_checks"]["formatting"]["passed"] += 1
            else:
                quality["issues_by_severity"]["low"] += 1
                quality["recent_issues"].append(
                    {
                        "file": str(relative_path),
                        "type": "formatting",
                        "severity": "low",
                        "issue": ", ".join(formatting_issues),
                    }
                )

            # Check 4: Links (basic validation)
            quality["quality_checks"]["links"]["total"] += 1
            # Simple check - assume links are valid for now
            quality["quality_checks"]["links"]["passed"] += 1

        except Exception as e:
            logger.warning(f"Failed to assess quality of {file_path}: {e}")

    async def _analyze_recent_changes(self) -> dict[str, Any]:
        """Analyze recent changes to source files.

        Returns:
            Recent changes information
        """
        try:
            changes = {
                "timestamp": datetime.now().isoformat(),
                "recent_source_changes": [],
                "recent_doc_changes": [],
                "sync_status": "unknown",
                "out_of_sync_files": [],
            }

            # Check for recent source file changes
            cutoff_time = datetime.now().timestamp() - (7 * 24 * 60 * 60)  # 7 days

            for py_file in self.project_path.rglob("*.py"):
                if py_file.stat().st_mtime > cutoff_time:
                    relative_path = py_file.relative_to(self.project_path)
                    if not any(
                        pattern in str(relative_path)
                        for pattern in self.config.project.exclude_patterns
                    ):
                        changes["recent_source_changes"].append(
                            {
                                "file": str(relative_path),
                                "last_modified": datetime.fromtimestamp(
                                    py_file.stat().st_mtime
                                ).isoformat(),
                            }
                        )

            # Check for recent documentation changes if vault is available
            if self.vault_manager:
                docs_folder = (
                    Path(self.vault_manager.vault_path)
                    / self.config.obsidian.docs_folder
                )
                if docs_folder.exists():
                    for md_file in docs_folder.rglob("*.md"):
                        if md_file.stat().st_mtime > cutoff_time:
                            relative_path = md_file.relative_to(docs_folder)
                            changes["recent_doc_changes"].append(
                                {
                                    "file": str(relative_path),
                                    "last_modified": datetime.fromtimestamp(
                                        md_file.stat().st_mtime
                                    ).isoformat(),
                                }
                            )

            # Simple sync status assessment
            source_changes = len(changes["recent_source_changes"])
            doc_changes = len(changes["recent_doc_changes"])

            if source_changes == 0 and doc_changes == 0:
                changes["sync_status"] = "up_to_date"
            elif source_changes > doc_changes:
                changes["sync_status"] = "docs_behind"
            elif doc_changes > source_changes:
                changes["sync_status"] = "docs_ahead"
            else:
                changes["sync_status"] = "synchronized"

            return changes

        except Exception as e:
            logger.warning(f"Failed to analyze recent changes: {e}")
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "sync_status": "error",
            }

    async def _generate_recommendations(
        self, coverage: dict[str, Any], quality: dict[str, Any], changes: dict[str, Any]
    ) -> list[str]:
        """Generate improvement recommendations.

        Args:
            coverage: Coverage metrics
            quality: Quality metrics
            changes: Recent changes information

        Returns:
            List of recommendations
        """
        recommendations = []

        # Coverage-based recommendations
        overall_coverage = coverage.get("overall_coverage", 0)
        if overall_coverage < 50:
            recommendations.append(
                f"Documentation coverage is low ({overall_coverage:.1f}%) - "
                "prioritize adding docstrings to modules and classes"
            )
        elif overall_coverage < 80:
            recommendations.append(
                f"Good progress on documentation coverage ({overall_coverage:.1f}%) - "
                "focus on documenting remaining functions"
            )

        # Type-specific coverage recommendations
        for item_type, data in coverage.get("by_type", {}).items():
            if data["coverage_percentage"] < 30:
                recommendations.append(
                    f"Very low {item_type} documentation coverage ({data['coverage_percentage']:.1f}%) - "
                    f"add docstrings to {data['total'] - data['documented']} {item_type}"
                )

        # Quality-based recommendations
        quality_score = quality.get("overall_score", 0)
        if quality_score < 70 and quality_score > 0:
            recommendations.append(
                f"Documentation quality could be improved (score: {quality_score:.1f}/100) - "
                "review formatting and content structure"
            )

        # Sync-based recommendations
        sync_status = changes.get("sync_status", "unknown")
        if sync_status == "docs_behind":
            recommendations.append(
                "Source code has recent changes - consider regenerating documentation"
            )
        elif sync_status == "docs_ahead":
            recommendations.append(
                "Documentation has been updated recently - ensure it reflects current code"
            )

        # Missing documentation recommendations
        missing_count = len(coverage.get("missing_documentation", []))
        if missing_count > 0:
            recommendations.append(
                f"Add docstrings to {missing_count} undocumented items for complete coverage"
            )

        return recommendations

    def _create_summary(self, status: dict[str, Any]) -> dict[str, Any]:
        """Create a summary of the documentation status.

        Args:
            status: Full status dictionary

        Returns:
            Summary dictionary
        """
        summary = {
            "overall_health": "unknown",
            "coverage_grade": "F",
            "quality_grade": "F",
            "priority_actions": [],
            "next_steps": [],
        }

        # Calculate overall health
        coverage_score = status.get("coverage", {}).get("overall_coverage", 0)
        quality_score = status.get("quality", {}).get("overall_score", 0)

        # Weighted score (coverage 60%, quality 40%)
        if quality_score > 0:
            overall_score = (coverage_score * 0.6) + (quality_score * 0.4)
        else:
            overall_score = coverage_score

        # Assign grades
        if overall_score >= 90:
            summary["overall_health"] = "excellent"
            summary["coverage_grade"] = "A"
        elif overall_score >= 80:
            summary["overall_health"] = "good"
            summary["coverage_grade"] = "B"
        elif overall_score >= 70:
            summary["overall_health"] = "fair"
            summary["coverage_grade"] = "C"
        elif overall_score >= 60:
            summary["overall_health"] = "poor"
            summary["coverage_grade"] = "D"
        else:
            summary["overall_health"] = "critical"
            summary["coverage_grade"] = "F"

        # Quality grade
        if quality_score >= 90:
            summary["quality_grade"] = "A"
        elif quality_score >= 80:
            summary["quality_grade"] = "B"
        elif quality_score >= 70:
            summary["quality_grade"] = "C"
        elif quality_score >= 60:
            summary["quality_grade"] = "D"

        # Priority actions
        if coverage_score < 50:
            summary["priority_actions"].append("Improve documentation coverage")
        if quality_score > 0 and quality_score < 70:
            summary["priority_actions"].append("Address quality issues")
        if status.get("recent_changes", {}).get("sync_status") == "docs_behind":
            summary["priority_actions"].append(
                "Update documentation to match recent code changes"
            )

        # Next steps
        recommendations = status.get("recommendations", [])
        summary["next_steps"] = recommendations[:3]  # Top 3 recommendations

        return summary


async def get_documentation_status_resource(
    project_path: str,
    config_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    MCP resource handler for documentation status access.

    Args:
        project_path: Path to the Python project root
        config_override: Optional configuration overrides

    Returns:
        Documentation status resource data

    Raises:
        DocumentationStatusError: If resource access fails
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
        resource = DocumentationStatusResource(Path(project_path), config)

        # Get current status
        status = await resource.get_status()

        return {
            "resource_type": "documentation_status",
            "data": status,
            "capabilities": {
                "coverage_tracking": True,
                "quality_assessment": True,
                "change_detection": True,
                "recommendations": True,
            },
        }

    except Exception as e:
        logger.error(f"get_documentation_status_resource failed: {e}")
        return {
            "resource_type": "documentation_status",
            "error": str(e),
            "error_type": type(e).__name__,
        }


# Resource metadata for MCP registration
RESOURCE_DEFINITION = {
    "name": "documentation_status",
    "description": "Documentation coverage metrics, quality scores, and improvement recommendations",
    "schema": {
        "type": "object",
        "properties": {
            "coverage": {
                "type": "object",
                "properties": {
                    "overall_coverage": {"type": "number"},
                    "by_type": {"type": "object"},
                    "missing_documentation": {"type": "array"},
                },
            },
            "quality": {
                "type": "object",
                "properties": {
                    "overall_score": {"type": "number"},
                    "quality_checks": {"type": "object"},
                },
            },
            "summary": {
                "type": "object",
                "properties": {
                    "overall_health": {"type": "string"},
                    "coverage_grade": {"type": "string"},
                    "quality_grade": {"type": "string"},
                },
            },
        },
    },
}
