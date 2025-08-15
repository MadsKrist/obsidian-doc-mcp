"""
MCP tool for documentation validation and quality assessment.

This module implements the validate_docs MCP tool that provides comprehensive
documentation completeness checking, link validation, and quality assessment.
"""

import asyncio
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from config.project_config import Config, ConfigManager
from docs_generator.analyzer import PythonProjectAnalyzer
from utils.obsidian_utils import ObsidianVaultManager

logger = logging.getLogger(__name__)


class DocumentationValidationError(Exception):
    """Exception raised during documentation validation."""

    pass


class DocumentationValidator:
    """Validates documentation completeness and quality."""

    def __init__(self, config: Config):
        """Initialize the documentation validator.

        Args:
            config: Project configuration
        """
        self.config = config
        self.project_path = Path(config.project.source_paths[0])
        self.analyzer = PythonProjectAnalyzer(self.project_path)
        self.vault_manager: ObsidianVaultManager | None = None

        # Initialize vault manager if vault path is configured
        if config.obsidian.vault_path:
            try:
                self.vault_manager = ObsidianVaultManager(
                    Path(config.obsidian.vault_path)
                )
            except Exception as e:
                logger.warning(f"Failed to initialize vault manager: {e}")

    async def validate_documentation(self) -> dict[str, Any]:
        """Perform comprehensive documentation validation.

        Returns:
            Validation results with scores and recommendations

        Raises:
            DocumentationValidationError: If validation fails
        """
        try:
            results = {
                "status": "success",
                "overall_score": 0.0,
                "validation_timestamp": None,
                "checks_performed": [],
                "completeness": {},
                "quality": {},
                "links": {},
                "issues": [],
                "recommendations": [],
                "statistics": {},
            }

            # Step 1: Analyze project structure
            logger.info("Analyzing project structure for validation")
            project_structure = await self._analyze_project()
            results["checks_performed"].append("project_analysis")
            results["statistics"]["total_modules"] = len(project_structure.modules)

            # Step 2: Check documentation completeness
            logger.info("Checking documentation completeness")
            completeness_results = await self._check_completeness(project_structure)
            results["checks_performed"].append("completeness_check")
            results["completeness"] = completeness_results

            # Step 3: Validate existing documentation quality
            if self.vault_manager:
                logger.info("Validating documentation quality")
                quality_results = await self._validate_quality()
                results["checks_performed"].append("quality_validation")
                results["quality"] = quality_results

                # Step 4: Validate links and cross-references
                logger.info("Validating links and cross-references")
                link_results = await self._validate_links()
                results["checks_performed"].append("link_validation")
                results["links"] = link_results

            else:
                results["issues"].append(
                    {
                        "type": "configuration",
                        "severity": "warning",
                        "message": "Obsidian vault not configured - quality validation limited",
                        "category": "setup",
                    }
                )

            # Step 5: Calculate overall score
            overall_score = self._calculate_overall_score(results)
            results["overall_score"] = overall_score

            # Step 6: Generate recommendations
            recommendations = await self._generate_recommendations(results)
            results["recommendations"] = recommendations

            # Set validation timestamp
            from datetime import datetime

            results["validation_timestamp"] = datetime.now().isoformat()

            logger.info(f"Documentation validation completed: {overall_score:.1f}/10.0")
            return results

        except Exception as e:
            logger.error(f"Documentation validation failed: {e}")
            raise DocumentationValidationError(
                f"Failed to validate documentation: {e}"
            ) from e

    async def _analyze_project(self):
        """Analyze the Python project structure."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.analyzer.analyze_project,
                self.config.project.exclude_patterns,
            )
        except Exception as e:
            raise DocumentationValidationError(f"Project analysis failed: {e}") from e

    async def _check_completeness(self, project_structure) -> dict[str, Any]:
        """Check documentation completeness against project structure.

        Args:
            project_structure: Analyzed project structure

        Returns:
            Completeness check results
        """
        completeness = {
            "score": 0.0,
            "total_items": 0,
            "documented_items": 0,
            "missing_documentation": [],
            "coverage_by_type": {
                "modules": {"total": 0, "documented": 0, "coverage": 0.0},
                "classes": {"total": 0, "documented": 0, "coverage": 0.0},
                "functions": {"total": 0, "documented": 0, "coverage": 0.0},
            },
        }

        total_items = 0
        documented_items = 0

        # Check module documentation
        for module in project_structure.modules:
            total_items += 1
            completeness["coverage_by_type"]["modules"]["total"] += 1

            if module.docstring and module.docstring.strip():
                documented_items += 1
                completeness["coverage_by_type"]["modules"]["documented"] += 1
            else:
                completeness["missing_documentation"].append(
                    {
                        "type": "module",
                        "name": module.name,
                        "file": str(module.file_path),
                        "line": 1,
                        "severity": "medium",
                    }
                )

            # Check class documentation
            for class_info in module.classes:
                total_items += 1
                completeness["coverage_by_type"]["classes"]["total"] += 1

                if class_info.docstring and class_info.docstring.strip():
                    documented_items += 1
                    completeness["coverage_by_type"]["classes"]["documented"] += 1
                else:
                    completeness["missing_documentation"].append(
                        {
                            "type": "class",
                            "name": f"{module.name}.{class_info.name}",
                            "file": str(module.file_path),
                            "line": class_info.line_number,
                            "severity": "high",
                        }
                    )

            # Check function documentation
            for func_info in module.functions:
                # Skip private functions if not including private
                if func_info.is_private and not self.config.project.include_private:
                    continue

                total_items += 1
                completeness["coverage_by_type"]["functions"]["total"] += 1

                if func_info.docstring and func_info.docstring.strip():
                    documented_items += 1
                    completeness["coverage_by_type"]["functions"]["documented"] += 1
                else:
                    severity = "low" if func_info.is_private else "medium"
                    completeness["missing_documentation"].append(
                        {
                            "type": "function",
                            "name": f"{module.name}.{func_info.name}",
                            "file": str(module.file_path),
                            "line": func_info.line_number,
                            "severity": severity,
                        }
                    )

        # Calculate coverage percentages
        for item_type in completeness["coverage_by_type"]:
            type_data = completeness["coverage_by_type"][item_type]
            if type_data["total"] > 0:
                type_data["coverage"] = (
                    type_data["documented"] / type_data["total"] * 100
                )

        # Calculate overall completeness score
        completeness["total_items"] = total_items
        completeness["documented_items"] = documented_items
        if total_items > 0:
            completeness["score"] = documented_items / total_items * 100
        else:
            completeness["score"] = 100.0

        return completeness

    async def _validate_quality(self) -> dict[str, Any]:
        """Validate the quality of existing documentation.

        Returns:
            Quality validation results
        """
        if not self.vault_manager:
            return {
                "score": 0.0,
                "issues": [],
                "message": "Vault manager not available",
            }

        quality = {
            "score": 0.0,
            "total_files": 0,
            "issues": [],
            "checks": {
                "structure": {"passed": 0, "total": 0},
                "content": {"passed": 0, "total": 0},
                "formatting": {"passed": 0, "total": 0},
                "metadata": {"passed": 0, "total": 0},
            },
        }

        try:
            docs_folder = (
                Path(self.vault_manager.vault_path) / self.config.obsidian.docs_folder
            )
            if not docs_folder.exists():
                quality["issues"].append(
                    {
                        "type": "structure",
                        "severity": "high",
                        "message": f"Documentation folder does not exist: {docs_folder}",
                        "category": "missing",
                    }
                )
                return quality

            # Find all markdown files
            md_files = list(docs_folder.rglob("*.md"))
            quality["total_files"] = len(md_files)

            for md_file in md_files:
                await self._validate_file_quality(md_file, quality)

            # Calculate quality score
            total_checks = sum(check["total"] for check in quality["checks"].values())
            passed_checks = sum(check["passed"] for check in quality["checks"].values())

            if total_checks > 0:
                quality["score"] = passed_checks / total_checks * 100
            else:
                quality["score"] = 0.0

        except Exception as e:
            logger.warning(f"Quality validation failed: {e}")
            quality["issues"].append(
                {
                    "type": "validation",
                    "severity": "error",
                    "message": f"Quality validation failed: {e}",
                    "category": "error",
                }
            )

        return quality

    async def _validate_file_quality(
        self, file_path: Path, quality: dict[str, Any]
    ) -> None:
        """Validate the quality of a single documentation file.

        Args:
            file_path: Path to the documentation file
            quality: Quality results dictionary to update
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            if not self.vault_manager:
                return
            relative_path = file_path.relative_to(self.vault_manager.vault_path)

            # Check 1: Structure - has proper heading
            quality["checks"]["structure"]["total"] += 1
            if re.match(r"^# .+", content):
                quality["checks"]["structure"]["passed"] += 1
            else:
                quality["issues"].append(
                    {
                        "type": "structure",
                        "severity": "medium",
                        "message": f"Missing main heading in {relative_path}",
                        "file": str(relative_path),
                        "category": "structure",
                    }
                )

            # Check 2: Content - has meaningful content beyond just headings
            quality["checks"]["content"]["total"] += 1
            content_without_headings = re.sub(
                r"^#+.*$", "", content, flags=re.MULTILINE
            )
            content_text = content_without_headings.strip()
            if len(content_text) > 50:  # Arbitrary threshold for meaningful content
                quality["checks"]["content"]["passed"] += 1
            else:
                quality["issues"].append(
                    {
                        "type": "content",
                        "severity": "medium",
                        "message": f"Insufficient content in {relative_path}",
                        "file": str(relative_path),
                        "category": "content",
                    }
                )

            # Check 3: Formatting - proper markdown formatting
            quality["checks"]["formatting"]["total"] += 1
            formatting_issues = []

            # Check for unmatched brackets
            if content.count("[[") != content.count("]]"):
                formatting_issues.append("unmatched wikilink brackets")

            # Check for unmatched code blocks
            triple_backticks = content.count("```")
            if triple_backticks % 2 != 0:
                formatting_issues.append("unmatched code blocks")

            if not formatting_issues:
                quality["checks"]["formatting"]["passed"] += 1
            else:
                quality["issues"].append(
                    {
                        "type": "formatting",
                        "severity": "low",
                        "message": f"Formatting issues in {relative_path}: {', '.join(formatting_issues)}",
                        "file": str(relative_path),
                        "category": "formatting",
                    }
                )

            # Check 4: Metadata - has YAML frontmatter if expected
            quality["checks"]["metadata"]["total"] += 1
            if content.startswith("---"):
                quality["checks"]["metadata"]["passed"] += 1
            else:
                quality["issues"].append(
                    {
                        "type": "metadata",
                        "severity": "low",
                        "message": f"Missing YAML frontmatter in {relative_path}",
                        "file": str(relative_path),
                        "category": "metadata",
                    }
                )

        except Exception as e:
            logger.warning(f"Failed to validate file {file_path}: {e}")
            quality["issues"].append(
                {
                    "type": "validation",
                    "severity": "error",
                    "message": f"Failed to validate {file_path}: {e}",
                    "file": str(file_path),
                    "category": "error",
                }
            )

    async def _validate_links(self) -> dict[str, Any]:
        """Validate links and cross-references in documentation.

        Returns:
            Link validation results
        """
        if not self.vault_manager:
            return {
                "score": 0.0,
                "issues": [],
                "message": "Vault manager not available",
            }

        links = {
            "score": 0.0,
            "total_links": 0,
            "valid_links": 0,
            "broken_links": [],
            "external_links": [],
            "wikilinks": [],
            "link_statistics": {
                "internal": 0,
                "external": 0,
                "wikilinks": 0,
                "anchors": 0,
            },
        }

        try:
            docs_folder = (
                Path(self.vault_manager.vault_path) / self.config.obsidian.docs_folder
            )
            if not docs_folder.exists():
                return links

            # Find all markdown files
            md_files = list(docs_folder.rglob("*.md"))

            for md_file in md_files:
                await self._validate_file_links(md_file, docs_folder, links)

            # Calculate link validation score
            if links["total_links"] > 0:
                links["score"] = links["valid_links"] / links["total_links"] * 100
            else:
                links["score"] = 100.0

        except Exception as e:
            logger.warning(f"Link validation failed: {e}")
            links["broken_links"].append(
                {
                    "type": "validation_error",
                    "message": f"Link validation failed: {e}",
                    "severity": "error",
                }
            )

        return links

    async def _validate_file_links(
        self, file_path: Path, docs_folder: Path, links: dict[str, Any]
    ) -> None:
        """Validate links in a single documentation file.

        Args:
            file_path: Path to the documentation file
            docs_folder: Path to the documentation folder
            links: Links results dictionary to update
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            if not self.vault_manager:
                return
            relative_path = file_path.relative_to(self.vault_manager.vault_path)

            # Find wikilinks [[link]] and [[link|display]]
            wikilink_pattern = r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]"
            wikilinks = re.findall(wikilink_pattern, content)

            for link_target, display_text in wikilinks:
                links["total_links"] += 1
                links["link_statistics"]["wikilinks"] += 1

                # Check if target file exists
                target_file = docs_folder / f"{link_target}.md"
                if target_file.exists():
                    links["valid_links"] += 1
                    links["wikilinks"].append(
                        {
                            "source": str(relative_path),
                            "target": link_target,
                            "display": display_text or link_target,
                            "status": "valid",
                        }
                    )
                else:
                    links["broken_links"].append(
                        {
                            "type": "wikilink",
                            "source": str(relative_path),
                            "target": link_target,
                            "display": display_text or link_target,
                            "severity": "medium",
                            "message": f"Broken wikilink to {link_target}",
                        }
                    )

            # Find markdown links [text](url) and [text](url#anchor)
            markdown_link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
            md_links = re.findall(markdown_link_pattern, content)

            for link_text, link_url in md_links:
                links["total_links"] += 1

                if link_url.startswith("http"):
                    # External link - just record it
                    links["link_statistics"]["external"] += 1
                    links["valid_links"] += 1  # Assume external links are valid
                    links["external_links"].append(
                        {
                            "source": str(relative_path),
                            "url": link_url,
                            "text": link_text,
                            "status": "external",
                        }
                    )
                elif "#" in link_url:
                    # Anchor link
                    links["link_statistics"]["anchors"] += 1
                    links["valid_links"] += 1  # Assume anchors are valid for now
                else:
                    # Internal file link
                    links["link_statistics"]["internal"] += 1
                    target_file = docs_folder / link_url
                    if target_file.exists():
                        links["valid_links"] += 1
                    else:
                        links["broken_links"].append(
                            {
                                "type": "markdown_link",
                                "source": str(relative_path),
                                "target": link_url,
                                "text": link_text,
                                "severity": "medium",
                                "message": f"Broken markdown link to {link_url}",
                            }
                        )

        except Exception as e:
            logger.warning(f"Failed to validate links in {file_path}: {e}")

    def _calculate_overall_score(self, results: dict[str, Any]) -> float:
        """Calculate overall documentation quality score.

        Args:
            results: Validation results

        Returns:
            Overall score (0.0 to 10.0)
        """
        scores = []
        weights = []

        # Completeness score (40% weight)
        if "completeness" in results and "score" in results["completeness"]:
            scores.append(
                results["completeness"]["score"] / 10.0
            )  # Convert to 0-10 scale
            weights.append(0.4)

        # Quality score (35% weight)
        if "quality" in results and "score" in results["quality"]:
            scores.append(results["quality"]["score"] / 10.0)
            weights.append(0.35)

        # Link validation score (25% weight)
        if "links" in results and "score" in results["links"]:
            scores.append(results["links"]["score"] / 10.0)
            weights.append(0.25)

        # Calculate weighted average
        if scores and weights:
            weighted_sum = sum(score * weight for score, weight in zip(scores, weights, strict=False))
            total_weight = sum(weights)
            return weighted_sum / total_weight * 10.0
        else:
            return 0.0

    async def _generate_recommendations(self, results: dict[str, Any]) -> list[str]:
        """Generate improvement recommendations based on validation results.

        Args:
            results: Validation results

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Completeness recommendations
        if "completeness" in results:
            completeness = results["completeness"]
            if completeness["score"] < 70:
                recommendations.append(
                    f"Documentation completeness is {completeness['score']:.1f}% - "
                    "consider adding docstrings to improve coverage"
                )

            # Type-specific recommendations
            for item_type, data in completeness["coverage_by_type"].items():
                if data["coverage"] < 50:
                    recommendations.append(
                        f"Low {item_type} documentation coverage ({data['coverage']:.1f}%) - "
                        f"add docstrings to {data['total'] - data['documented']} {item_type}"
                    )

        # Quality recommendations
        if "quality" in results:
            quality = results["quality"]
            if quality["score"] < 80:
                recommendations.append(
                    f"Documentation quality score is {quality['score']:.1f}% - "
                    "review formatting and content structure"
                )

            # Count issues by type
            issue_counts = defaultdict(int)
            for issue in quality.get("issues", []):
                issue_counts[issue["type"]] += 1

            for issue_type, count in issue_counts.items():
                if count > 0:
                    recommendations.append(
                        f"Fix {count} {issue_type} issues in documentation files"
                    )

        # Link recommendations
        if "links" in results:
            links = results["links"]
            if links["score"] < 90:
                recommendations.append(
                    f"Link validation score is {links['score']:.1f}% - "
                    f"fix {len(links['broken_links'])} broken links"
                )

            if len(links["broken_links"]) > 0:
                recommendations.append(
                    f"Update {len(links['broken_links'])} broken cross-references"
                )

        # Overall recommendations
        overall_score = results.get("overall_score", 0.0)
        if overall_score < 6.0:
            recommendations.append(
                "Overall documentation quality is below average - "
                "focus on completeness and consistency improvements"
            )
        elif overall_score < 8.0:
            recommendations.append(
                "Good documentation foundation - focus on quality refinements and link maintenance"
            )
        elif overall_score >= 9.0:
            recommendations.append(
                "Excellent documentation quality - consider automating maintenance workflows"
            )

        return recommendations


async def validate_docs_tool(
    project_path: str,
    config_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    MCP tool implementation for documentation validation and quality assessment.

    Args:
        project_path: Path to the Python project root
        config_override: Optional configuration overrides

    Returns:
        Comprehensive validation results with scores and recommendations

    Raises:
        DocumentationValidationError: If validation fails
    """
    try:
        # Load configuration
        config_manager = ConfigManager()
        config_path = Path(project_path) / ".mcp-docs.yaml"
        if config_path.exists():
            config = config_manager.load_config(config_path)
        else:
            # Use default configuration
            config = Config()

        # Apply overrides if provided
        if config_override:
            for key, value in config_override.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Initialize validator
        validator = DocumentationValidator(config)

        # Perform validation
        results = await validator.validate_documentation()

        return results

    except Exception as e:
        logger.error(f"validate_docs_tool failed: {e}")
        return {"status": "error", "error": str(e), "error_type": type(e).__name__}


# Tool metadata for MCP registration
TOOL_DEFINITION = {
    "name": "validate_docs",
    "description": "Validate documentation completeness, quality, and cross-references",
    "inputSchema": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Path to the Python project root directory",
            },
            "config_override": {
                "type": "object",
                "description": "Optional configuration overrides",
                "additionalProperties": True,
                "default": None,
            },
        },
        "required": ["project_path"],
        "additionalProperties": False,
    },
}
