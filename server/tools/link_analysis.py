"""
MCP tool for cross-reference analysis and link optimization.

This module implements the link_analysis MCP tool that provides comprehensive
cross-reference analysis, dead link detection, and link graph visualization data.
"""

import logging
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from config.project_config import Config, ConfigManager
from utils.obsidian_utils import ObsidianVaultManager

logger = logging.getLogger(__name__)


class LinkAnalysisError(Exception):
    """Exception raised during link analysis."""

    pass


class LinkAnalyzer:
    """Analyzes cross-references and link relationships in documentation."""

    def __init__(self, config: Config):
        """Initialize the link analyzer.

        Args:
            config: Project configuration
        """
        self.config = config
        self.vault_manager: ObsidianVaultManager | None = None

        # Initialize vault manager if vault path is configured
        if config.obsidian.vault_path:
            try:
                self.vault_manager = ObsidianVaultManager(
                    Path(config.obsidian.vault_path)
                )
            except Exception as e:
                logger.warning(f"Failed to initialize vault manager: {e}")

    async def analyze_links(self) -> dict[str, Any]:
        """Perform comprehensive link analysis.

        Returns:
            Link analysis results with graph data and recommendations

        Raises:
            LinkAnalysisError: If analysis fails
        """
        try:
            results = {
                "status": "success",
                "analysis_timestamp": None,
                "link_graph": {},
                "statistics": {},
                "dead_links": [],
                "orphaned_files": [],
                "link_clusters": [],
                "recommendations": [],
                "visualization_data": {},
            }

            if not self.vault_manager:
                results["status"] = "warning"
                results["message"] = "Obsidian vault not configured - analysis limited"
                return results

            # Step 1: Build comprehensive link graph
            logger.info("Building link graph from documentation")
            link_graph = await self._build_link_graph()
            results["link_graph"] = link_graph

            # Step 2: Calculate link statistics
            logger.info("Calculating link statistics")
            statistics = await self._calculate_statistics(link_graph)
            results["statistics"] = statistics

            # Step 3: Identify dead links
            logger.info("Identifying dead links")
            dead_links = await self._find_dead_links(link_graph)
            results["dead_links"] = dead_links

            # Step 4: Find orphaned files
            logger.info("Finding orphaned files")
            orphaned_files = await self._find_orphaned_files(link_graph)
            results["orphaned_files"] = orphaned_files

            # Step 5: Identify link clusters
            logger.info("Identifying link clusters")
            clusters = await self._identify_clusters(link_graph)
            results["link_clusters"] = clusters

            # Step 6: Generate visualization data
            logger.info("Generating visualization data")
            viz_data = await self._generate_visualization_data(link_graph)
            results["visualization_data"] = viz_data

            # Step 7: Generate recommendations
            recommendations = await self._generate_recommendations(results)
            results["recommendations"] = recommendations

            # Set analysis timestamp
            from datetime import datetime

            results["analysis_timestamp"] = datetime.now().isoformat()

            logger.info("Link analysis completed successfully")
            return results

        except Exception as e:
            logger.error(f"Link analysis failed: {e}")
            raise LinkAnalysisError(f"Failed to analyze links: {e}") from e

    async def _build_link_graph(self) -> dict[str, Any]:
        """Build a comprehensive graph of all links in the documentation.

        Returns:
            Link graph with nodes and edges
        """
        if not self.vault_manager:
            return {"nodes": {}, "edges": []}

        graph = {
            "nodes": {},  # file_name -> node data
            "edges": [],  # list of {source, target, type, metadata}
            "metadata": {"total_files": 0, "total_links": 0},
        }

        try:
            docs_folder = (
                Path(self.vault_manager.vault_path) / self.config.obsidian.docs_folder
            )
            if not docs_folder.exists():
                return graph

            # Find all markdown files
            md_files = list(docs_folder.rglob("*.md"))
            graph["metadata"]["total_files"] = len(md_files)

            for md_file in md_files:
                await self._analyze_file_links(md_file, docs_folder, graph)

        except Exception as e:
            logger.warning(f"Failed to build link graph: {e}")

        return graph

    async def _analyze_file_links(
        self, file_path: Path, docs_folder: Path, graph: dict[str, Any]
    ) -> None:
        """Analyze links in a single file and add to the graph.

        Args:
            file_path: Path to the file to analyze
            docs_folder: Path to the documentation folder
            graph: Graph dictionary to update
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            file_name = file_path.stem
            relative_path = file_path.relative_to(docs_folder)

            # Add node if not exists
            if file_name not in graph["nodes"]:
                graph["nodes"][file_name] = {
                    "name": file_name,
                    "path": str(relative_path),
                    "size": len(content),
                    "outbound_links": 0,
                    "inbound_links": 0,
                    "word_count": len(content.split()),
                    "headings": self._extract_headings(content),
                }

            # Find wikilinks [[link]] and [[link|display]]
            wikilink_pattern = r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]"
            wikilinks = re.findall(wikilink_pattern, content)

            for link_target, display_text in wikilinks:
                graph["edges"].append(
                    {
                        "source": file_name,
                        "target": link_target,
                        "type": "wikilink",
                        "display_text": display_text or link_target,
                        "valid": (docs_folder / f"{link_target}.md").exists(),
                    }
                )

                graph["nodes"][file_name]["outbound_links"] += 1
                graph["metadata"]["total_links"] += 1

                # Create target node if it doesn't exist (might be broken link)
                if link_target not in graph["nodes"]:
                    target_file = docs_folder / f"{link_target}.md"
                    graph["nodes"][link_target] = {
                        "name": link_target,
                        "path": f"{link_target}.md",
                        "size": 0,
                        "exists": target_file.exists(),
                        "outbound_links": 0,
                        "inbound_links": 0,
                        "word_count": 0,
                        "headings": [],
                    }

                graph["nodes"][link_target]["inbound_links"] += 1

            # Find markdown links [text](url)
            markdown_link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
            md_links = re.findall(markdown_link_pattern, content)

            for link_text, link_url in md_links:
                if not link_url.startswith("http"):
                    # Internal markdown link
                    target_name = Path(link_url).stem
                    graph["edges"].append(
                        {
                            "source": file_name,
                            "target": target_name,
                            "type": "markdown_link",
                            "display_text": link_text,
                            "url": link_url,
                            "valid": (docs_folder / link_url).exists(),
                        }
                    )

                    graph["nodes"][file_name]["outbound_links"] += 1
                    graph["metadata"]["total_links"] += 1

        except Exception as e:
            logger.warning(f"Failed to analyze links in {file_path}: {e}")

    def _extract_headings(self, content: str) -> list[dict[str, Any]]:
        """Extract headings from markdown content.

        Args:
            content: Markdown content

        Returns:
            List of heading information
        """
        headings = []
        for match in re.finditer(r"^(#+)\s+(.+)$", content, re.MULTILINE):
            level = len(match.group(1))
            text = match.group(2).strip()
            headings.append(
                {
                    "level": level,
                    "text": text,
                    "anchor": self._text_to_anchor(text),
                }
            )
        return headings

    def _text_to_anchor(self, text: str) -> str:
        """Convert heading text to anchor format.

        Args:
            text: Heading text

        Returns:
            Anchor string
        """
        # Simple anchor conversion - could be enhanced
        anchor = text.lower().replace(" ", "-")
        anchor = re.sub(r"[^\w\-]", "", anchor)
        return anchor

    async def _calculate_statistics(self, link_graph: dict[str, Any]) -> dict[str, Any]:
        """Calculate comprehensive link statistics.

        Args:
            link_graph: Built link graph

        Returns:
            Link statistics
        """
        stats = {
            "total_files": len(link_graph["nodes"]),
            "total_links": len(link_graph["edges"]),
            "total_words": 0,
            "link_types": defaultdict(int),
            "link_validity": {"valid": 0, "broken": 0},
            "connectivity": {
                "connected_files": 0,
                "isolated_files": 0,
                "average_links_per_file": 0.0,
            },
            "hub_files": [],  # Files with many inbound links
            "authority_files": [],  # Files with many outbound links
        }

        # Calculate basic statistics
        for node in link_graph["nodes"].values():
            stats["total_words"] += node.get("word_count", 0)
            if node["inbound_links"] > 0 or node["outbound_links"] > 0:
                stats["connectivity"]["connected_files"] += 1
            else:
                stats["connectivity"]["isolated_files"] += 1

        # Link type and validity statistics
        for edge in link_graph["edges"]:
            stats["link_types"][edge["type"]] += 1
            if edge.get("valid", False):
                stats["link_validity"]["valid"] += 1
            else:
                stats["link_validity"]["broken"] += 1

        # Average links per file
        if stats["total_files"] > 0:
            stats["connectivity"]["average_links_per_file"] = (
                stats["total_links"] / stats["total_files"]
            )

        # Identify hub and authority files
        nodes_by_inbound = sorted(
            link_graph["nodes"].values(), key=lambda x: x["inbound_links"], reverse=True
        )
        nodes_by_outbound = sorted(
            link_graph["nodes"].values(),
            key=lambda x: x["outbound_links"],
            reverse=True,
        )

        stats["hub_files"] = [
            {"name": node["name"], "inbound_links": node["inbound_links"]}
            for node in nodes_by_inbound[:5]
            if node["inbound_links"] > 0
        ]

        stats["authority_files"] = [
            {"name": node["name"], "outbound_links": node["outbound_links"]}
            for node in nodes_by_outbound[:5]
            if node["outbound_links"] > 0
        ]

        return stats

    async def _find_dead_links(
        self, link_graph: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Find all dead/broken links in the documentation.

        Args:
            link_graph: Built link graph

        Returns:
            List of dead links with details
        """
        dead_links = []

        for edge in link_graph["edges"]:
            if not edge.get("valid", False):
                target_node = link_graph["nodes"].get(edge["target"], {})
                dead_links.append(
                    {
                        "source": edge["source"],
                        "target": edge["target"],
                        "type": edge["type"],
                        "display_text": edge.get("display_text", edge["target"]),
                        "target_exists": target_node.get("exists", False),
                        "severity": "high" if edge["type"] == "wikilink" else "medium",
                        "suggestion": self._suggest_link_fix(edge, link_graph),
                    }
                )

        return dead_links

    def _suggest_link_fix(
        self, broken_edge: dict[str, Any], link_graph: dict[str, Any]
    ) -> str:
        """Suggest a fix for a broken link.

        Args:
            broken_edge: Information about the broken link
            link_graph: Complete link graph

        Returns:
            Suggestion string
        """
        target = broken_edge["target"]

        # Find similar file names
        existing_files = [
            name
            for name in link_graph["nodes"].keys()
            if link_graph["nodes"][name].get("exists", True)
        ]

        # Simple similarity check - could be enhanced with fuzzy matching
        similar_files = [
            name
            for name in existing_files
            if target.lower() in name.lower() or name.lower() in target.lower()
        ]

        if similar_files:
            return f"Consider linking to: {', '.join(similar_files[:3])}"
        else:
            return f"Create missing file: {target}.md"

    async def _find_orphaned_files(
        self, link_graph: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Find files that have no inbound links (orphaned).

        Args:
            link_graph: Built link graph

        Returns:
            List of orphaned files
        """
        orphaned = []

        for node in link_graph["nodes"].values():
            if node.get("exists", True) and node["inbound_links"] == 0:
                # Skip index files - they're typically meant to be entry points
                if node["name"].lower() not in ["index", "readme", "home"]:
                    orphaned.append(
                        {
                            "name": node["name"],
                            "path": node["path"],
                            "size": node["size"],
                            "word_count": node["word_count"],
                            "outbound_links": node["outbound_links"],
                            "suggestion": self._suggest_orphan_fix(node, link_graph),
                        }
                    )

        return orphaned

    def _suggest_orphan_fix(
        self, orphan_node: dict[str, Any], link_graph: dict[str, Any]
    ) -> str:
        """Suggest how to fix an orphaned file.

        Args:
            orphan_node: Information about the orphaned file
            link_graph: Complete link graph

        Returns:
            Suggestion string
        """
        if orphan_node["outbound_links"] > 0:
            return "Add links to this file from related pages"
        else:
            return "Consider linking this file from index or removing if unused"

    async def _identify_clusters(
        self, link_graph: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Identify clusters of strongly connected files.

        Args:
            link_graph: Built link graph

        Returns:
            List of link clusters
        """
        clusters = []

        # Build adjacency list for clustering analysis
        adjacency = defaultdict(set)
        for edge in link_graph["edges"]:
            if edge.get("valid", False):
                adjacency[edge["source"]].add(edge["target"])
                adjacency[edge["target"]].add(edge["source"])  # Treat as undirected

        # Find connected components using BFS
        visited = set()
        cluster_id = 0

        for node_name in link_graph["nodes"]:
            if node_name not in visited and link_graph["nodes"][node_name].get(
                "exists", True
            ):
                cluster = self._bfs_cluster(node_name, adjacency, visited)
                if len(cluster) > 1:  # Only include clusters with multiple files
                    cluster_nodes = [link_graph["nodes"][name] for name in cluster]
                    total_words = sum(node["word_count"] for node in cluster_nodes)

                    clusters.append(
                        {
                            "id": cluster_id,
                            "size": len(cluster),
                            "files": list(cluster),
                            "total_words": total_words,
                            "internal_links": self._count_internal_links(
                                cluster, link_graph
                            ),
                            "external_links": self._count_external_links(
                                cluster, link_graph
                            ),
                        }
                    )
                    cluster_id += 1

        # Sort clusters by size (largest first)
        clusters.sort(key=lambda x: x["size"], reverse=True)
        return clusters

    def _bfs_cluster(
        self, start_node: str, adjacency: dict[str, set], visited: set
    ) -> set[str]:
        """Find connected component using BFS.

        Args:
            start_node: Starting node for BFS
            adjacency: Adjacency list representation
            visited: Set of already visited nodes

        Returns:
            Set of nodes in the connected component
        """
        cluster = set()
        queue = deque([start_node])
        visited.add(start_node)

        while queue:
            node = queue.popleft()
            cluster.add(node)

            for neighbor in adjacency[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return cluster

    def _count_internal_links(
        self, cluster: set[str], link_graph: dict[str, Any]
    ) -> int:
        """Count links within a cluster.

        Args:
            cluster: Set of nodes in the cluster
            link_graph: Complete link graph

        Returns:
            Number of internal links
        """
        count = 0
        for edge in link_graph["edges"]:
            if edge["source"] in cluster and edge["target"] in cluster:
                count += 1
        return count

    def _count_external_links(
        self, cluster: set[str], link_graph: dict[str, Any]
    ) -> int:
        """Count links from cluster to external files.

        Args:
            cluster: Set of nodes in the cluster
            link_graph: Complete link graph

        Returns:
            Number of external links
        """
        count = 0
        for edge in link_graph["edges"]:
            if edge["source"] in cluster and edge["target"] not in cluster:
                count += 1
        return count

    async def _generate_visualization_data(
        self, link_graph: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate data for link graph visualization.

        Args:
            link_graph: Built link graph

        Returns:
            Visualization-ready data
        """
        viz_data = {
            "nodes": [],
            "edges": [],
            "layout_suggestions": {},
        }

        # Prepare nodes for visualization
        for node_name, node_data in link_graph["nodes"].items():
            if node_data.get("exists", True):
                viz_data["nodes"].append(
                    {
                        "id": node_name,
                        "label": node_name,
                        "size": max(
                            5, min(50, node_data["word_count"] // 50)
                        ),  # Scale size
                        "inbound": node_data["inbound_links"],
                        "outbound": node_data["outbound_links"],
                        "group": self._determine_node_group(node_data),
                    }
                )

        # Prepare edges for visualization
        for edge in link_graph["edges"]:
            if edge.get("valid", False):
                viz_data["edges"].append(
                    {
                        "source": edge["source"],
                        "target": edge["target"],
                        "type": edge["type"],
                        "weight": 1,  # Could be enhanced with link strength
                    }
                )

        # Layout suggestions
        viz_data["layout_suggestions"] = {
            "recommended_layout": "force_directed"
            if len(viz_data["nodes"]) > 20
            else "circular",
            "clustering_enabled": len(viz_data["nodes"]) > 10,
            "highlight_hubs": True,
        }

        return viz_data

    def _determine_node_group(self, node_data: dict[str, Any]) -> str:
        """Determine visualization group for a node.

        Args:
            node_data: Node information

        Returns:
            Group identifier
        """
        if node_data["inbound_links"] > 5:
            return "hub"
        elif node_data["outbound_links"] > 5:
            return "authority"
        elif node_data["inbound_links"] == 0:
            return "orphan"
        else:
            return "regular"

    async def _generate_recommendations(self, results: dict[str, Any]) -> list[str]:
        """Generate link optimization recommendations.

        Args:
            results: Complete analysis results

        Returns:
            List of recommendation strings
        """
        recommendations = []
        stats = results.get("statistics", {})
        dead_links = results.get("dead_links", [])
        orphaned_files = results.get("orphaned_files", [])
        clusters = results.get("link_clusters", [])

        # Dead link recommendations
        if dead_links:
            high_priority = [link for link in dead_links if link["severity"] == "high"]
            if high_priority:
                recommendations.append(
                    f"Fix {len(high_priority)} high-priority broken wikilinks"
                )
            if len(dead_links) > len(high_priority):
                recommendations.append(
                    f"Review and fix {len(dead_links) - len(high_priority)} "
                    "additional broken links"
                )

        # Orphaned file recommendations
        if orphaned_files:
            recommendations.append(
                f"Connect {len(orphaned_files)} orphaned files to improve discoverability"
            )

        # Connectivity recommendations
        connectivity = stats.get("connectivity", {})
        if connectivity.get("isolated_files", 0) > 0:
            recommendations.append(
                f"Link {connectivity['isolated_files']} isolated files "
                "to improve documentation navigation"
            )

        # Link density recommendations
        avg_links = connectivity.get("average_links_per_file", 0)
        if avg_links < 2:
            recommendations.append(
                "Consider adding more cross-references to improve documentation connectivity"
            )
        elif avg_links > 10:
            recommendations.append(
                "High link density detected - consider organizing into topic clusters"
            )

        # Cluster recommendations
        if len(clusters) > 3:
            recommendations.append(
                f"Documentation has {len(clusters)} distinct clusters - "
                "consider creating topic index pages"
            )

        # Link validity recommendations
        validity = stats.get("link_validity", {})
        total_links = validity.get("valid", 0) + validity.get("broken", 0)
        if total_links > 0:
            validity_ratio = validity.get("valid", 0) / total_links
            if validity_ratio < 0.9:
                recommendations.append(
                    f"Link validity is {validity_ratio:.1%} - "
                    "focus on fixing broken references"
                )

        # Hub file recommendations
        hub_files = stats.get("hub_files", [])
        if hub_files and hub_files[0]["inbound_links"] > 10:
            recommendations.append(
                f"'{hub_files[0]['name']}' is a major hub - "
                "ensure it has comprehensive content"
            )

        return recommendations


async def link_analysis_tool(
    project_path: str,
    config_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    MCP tool implementation for cross-reference analysis and link optimization.

    Args:
        project_path: Path to the Python project root
        config_override: Optional configuration overrides

    Returns:
        Comprehensive link analysis results with graph data and recommendations

    Raises:
        LinkAnalysisError: If analysis fails
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

        # Initialize analyzer
        analyzer = LinkAnalyzer(config)

        # Perform analysis
        results = await analyzer.analyze_links()

        return results

    except Exception as e:
        logger.error(f"link_analysis_tool failed: {e}")
        return {"status": "error", "error": str(e), "error_type": type(e).__name__}


# Tool metadata for MCP registration
TOOL_DEFINITION = {
    "name": "link_analysis",
    "description": "Analyze cross-references, detect dead links, and optimize documentation connectivity",
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
