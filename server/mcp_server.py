"""Main MCP Server implementation for Python documentation generation.

This module contains the core MCP server that handles communication with
Claude Code and orchestrates the documentation generation pipeline.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Resource, ServerCapabilities, TextContent, Tool
from pydantic import AnyUrl

from config.project_config import Config, ConfigManager
from docs_generator.analyzer import PythonProjectAnalyzer
from server.resources.configuration import RESOURCE_DEFINITION as configuration_def
from server.resources.documentation_status import (
    RESOURCE_DEFINITION as documentation_status_def,
)
from server.resources.project_structure import (
    RESOURCE_DEFINITION as project_structure_def,
)

# Import all the resources
from server.tools.configure_project import TOOL_DEFINITION as configure_project_def
from server.tools.configure_project import configure_project_tool

# Import all the tools
from server.tools.generate_docs import TOOL_DEFINITION as generate_docs_def
from server.tools.generate_docs import generate_docs_tool
from server.tools.link_analysis import TOOL_DEFINITION as link_analysis_def
from server.tools.link_analysis import link_analysis_tool
from server.tools.update_docs import TOOL_DEFINITION as update_docs_def
from server.tools.update_docs import update_docs_tool
from server.tools.validate_docs import TOOL_DEFINITION as validate_docs_def
from server.tools.validate_docs import validate_docs_tool

logger = logging.getLogger(__name__)


class DocumentationMCPServer:
    """Main MCP server for Python documentation generation.

    This server provides tools and resources for analyzing Python projects
    and generating Obsidian-compatible documentation.
    """

    def __init__(self) -> None:
        """Initialize the MCP server."""
        self.name = "obsidian-doc-mcp"
        self.version = "0.1.0"
        self.server = Server(self.name)
        self.config_manager = ConfigManager()

        # Register handlers
        self._register_tool_handlers()
        self._register_resource_handlers()

        logger.info(f"Initialized {self.name} v{self.version}")

    def _register_tool_handlers(self) -> None:
        """Register MCP tool handlers."""

        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """List available tools."""
            return [
                # Documentation generation tools
                Tool(
                    name=generate_docs_def["name"],
                    description=generate_docs_def["description"],
                    inputSchema=generate_docs_def["inputSchema"],
                ),
                Tool(
                    name=update_docs_def["name"],
                    description=update_docs_def["description"],
                    inputSchema=update_docs_def["inputSchema"],
                ),
                Tool(
                    name=configure_project_def["name"],
                    description=configure_project_def["description"],
                    inputSchema=configure_project_def["inputSchema"],
                ),
                Tool(
                    name=validate_docs_def["name"],
                    description=validate_docs_def["description"],
                    inputSchema=validate_docs_def["inputSchema"],
                ),
                Tool(
                    name=link_analysis_def["name"],
                    description=link_analysis_def["description"],
                    inputSchema=link_analysis_def["inputSchema"],
                ),
                # Legacy tools for compatibility
                Tool(
                    name="analyze_project",
                    description="Analyze a Python project structure and extract "
                    "documentation information",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_path": {
                                "type": "string",
                                "description": "Path to the Python project to analyze",
                            },
                            "config_path": {
                                "type": "string",
                                "description": "Optional path to configuration file",
                                "default": None,
                            },
                        },
                        "required": ["project_path"],
                    },
                ),
                Tool(
                    name="health_check",
                    description="Check the health and status of the MCP server",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                ),
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            """Handle tool calls."""
            logger.info(f"Tool called: {name} with args: {arguments}")

            try:
                # Handle new MCP tools
                if name == "generate_docs":
                    result = await generate_docs_tool(**arguments)
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                elif name == "update_docs":
                    result = await update_docs_tool(**arguments)
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                elif name == "configure_project":
                    result = await configure_project_tool(**arguments)
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                elif name == "validate_docs":
                    result = await validate_docs_tool(**arguments)
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                elif name == "link_analysis":
                    result = await link_analysis_tool(**arguments)
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                # Handle legacy tools
                elif name == "analyze_project":
                    return await self._handle_analyze_project(arguments)
                elif name == "health_check":
                    return await self._handle_health_check(arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")

            except Exception as e:
                logger.exception(f"Error in tool {name}")
                error_result = {
                    "status": "error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "tool": name,
                }
                return [TextContent(type="text", text=json.dumps(error_result, indent=2))]

    def _register_resource_handlers(self) -> None:
        """Register MCP resource handlers."""

        @self.server.list_resources()
        async def handle_list_resources() -> list[Resource]:
            """List available resources."""
            return [
                # Project-specific resources
                Resource(
                    uri=AnyUrl("mcp://project/structure"),
                    name=project_structure_def["name"],
                    description=project_structure_def["description"],
                    mimeType="application/json",
                ),
                Resource(
                    uri=AnyUrl("mcp://project/documentation_status"),
                    name=documentation_status_def["name"],
                    description=documentation_status_def["description"],
                    mimeType="application/json",
                ),
                Resource(
                    uri=AnyUrl("mcp://project/configuration"),
                    name=configuration_def["name"],
                    description=configuration_def["description"],
                    mimeType="application/json",
                ),
                # Legacy server resources
                Resource(
                    uri=AnyUrl("mcp://server/status"),
                    name="Server Status",
                    description="Current status and health information of the MCP server",
                    mimeType="application/json",
                ),
                Resource(
                    uri=AnyUrl("mcp://server/capabilities"),
                    name="Server Capabilities",
                    description="List of server capabilities and supported operations",
                    mimeType="application/json",
                ),
            ]

        @self.server.read_resource()
        async def handle_read_resource(uri: AnyUrl) -> str:
            """Handle resource reading requests."""
            uri_str = str(uri)
            logger.info(f"Resource requested: {uri_str}")

            try:
                if uri_str == "mcp://server/status":
                    return await self._get_server_status()
                elif uri_str == "mcp://server/capabilities":
                    return await self._get_server_capabilities()
                elif uri_str == "mcp://project/structure":
                    # For resources that need project_path, we'll need to get it from context
                    # For now, return schema information
                    return json.dumps(project_structure_def["schema"], indent=2)
                elif uri_str == "mcp://project/documentation_status":
                    return json.dumps(documentation_status_def["schema"], indent=2)
                elif uri_str == "mcp://project/configuration":
                    return json.dumps(configuration_def["schema"], indent=2)
                else:
                    raise ValueError(f"Unknown resource: {uri_str}")

            except Exception as e:
                logger.exception(f"Error reading resource {uri_str}")
                error_result = {
                    "status": "error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "resource": uri_str,
                }
                return json.dumps(error_result, indent=2)

    async def _handle_analyze_project(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle project analysis tool call."""
        try:
            project_path = Path(arguments["project_path"])
            config_path = arguments.get("config_path")

            if not project_path.exists():
                return [
                    TextContent(
                        type="text",
                        text=f"Error: Project path does not exist: {project_path}",
                    )
                ]

            # Load configuration
            config = None
            if config_path:
                config_path = Path(config_path)
                if config_path.exists():
                    config = self.config_manager.load_config(config_path)
                else:
                    return [
                        TextContent(
                            type="text",
                            text=f"Error: Config file does not exist: {config_path}",
                        )
                    ]
            else:
                # Try to find config file automatically
                for config_name in [".mcp-docs.yaml", ".mcp-docs.yml", "mcp-docs.yaml"]:
                    config_file = project_path / config_name
                    if config_file.exists():
                        config = self.config_manager.load_config(config_file)
                        break

            if not config:
                config = Config()  # Use default configuration

            # Analyze the project
            analyzer = PythonProjectAnalyzer(project_path)
            project_structure = analyzer.analyze_project(
                exclude_patterns=config.project.exclude_patterns
            )

            # Format the results
            result = {
                "project_name": project_structure.project_name,
                "total_modules": len(project_structure.modules),
                "total_packages": len(project_structure.packages),
                "modules": [
                    {
                        "name": module.name,
                        "file_path": str(module.file_path),
                        "docstring": module.docstring,
                        "is_package": module.is_package,
                        "functions_count": len(module.functions),
                        "classes_count": len(module.classes),
                        "imports_count": len(module.imports),
                    }
                    for module in project_structure.modules
                ],
                "dependencies": {
                    "internal": list(project_structure.internal_dependencies),
                    "external": list(project_structure.external_dependencies),
                },
            }

            import json

            return [
                TextContent(
                    type="text",
                    text="Project analysis completed successfully:\n\n"
                    f"{json.dumps(result, indent=2)}",
                )
            ]

        except Exception as e:
            logger.exception("Error analyzing project")
            return [TextContent(type="text", text=f"Error analyzing project: {str(e)}")]

    async def _handle_health_check(self, _arguments: dict[str, Any]) -> list[TextContent]:
        """Handle health check tool call."""
        try:
            status = {
                "server_name": self.name,
                "version": self.version,
                "status": "healthy",
                "timestamp": str(asyncio.get_event_loop().time()),
                "capabilities": {
                    "project_analysis": True,
                    "configuration_management": True,
                    "file_operations": True,
                },
            }

            import json

            return [
                TextContent(
                    type="text",
                    text=f"Health check passed:\n\n{json.dumps(status, indent=2)}",
                )
            ]

        except Exception as e:
            logger.exception("Error in health check")
            return [TextContent(type="text", text=f"Health check failed: {str(e)}")]

    async def _get_server_status(self) -> str:
        """Get server status resource."""
        status = {
            "name": self.name,
            "version": self.version,
            "status": "running",
            "uptime": asyncio.get_event_loop().time(),
            "tools_registered": 7,  # 5 new tools + 2 legacy
            "resources_registered": 5,  # 3 new resources + 2 legacy
            "features": {
                "documentation_generation": True,
                "obsidian_integration": True,
                "sphinx_integration": True,
                "project_analysis": True,
                "configuration_management": True,
                "validation_and_quality": True,
                "link_analysis": True,
            },
        }
        return json.dumps(status, indent=2)

    async def _get_server_capabilities(self) -> str:
        """Get server capabilities resource."""
        capabilities = {
            "protocol_version": "2024-11-05",
            "tools": [
                # New MCP tools
                {
                    "name": "generate_docs",
                    "description": "Generate complete documentation for a Python project",
                },
                {
                    "name": "update_docs",
                    "description": "Update existing documentation incrementally",
                },
                {
                    "name": "configure_project",
                    "description": "Set up or modify project documentation configuration",
                },
                {
                    "name": "validate_docs",
                    "description": "Validate documentation completeness and quality",
                },
                {
                    "name": "link_analysis",
                    "description": "Analyze cross-references and detect dead links",
                },
                # Legacy tools
                {
                    "name": "analyze_project",
                    "description": "Analyze Python project structure and documentation",
                },
                {
                    "name": "health_check",
                    "description": "Check server health and status",
                },
            ],
            "resources": [
                # New MCP resources
                {
                    "uri": "mcp://project/structure",
                    "description": "Real-time project structure access with search and filtering",
                },
                {
                    "uri": "mcp://project/documentation_status",
                    "description": "Documentation coverage metrics and quality scores",
                },
                {
                    "uri": "mcp://project/configuration",
                    "description": "Project configuration access, editing, and validation",
                },
                # Legacy resources
                {
                    "uri": "mcp://server/status",
                    "description": "Server status information",
                },
                {
                    "uri": "mcp://server/capabilities",
                    "description": "Server capabilities listing",
                },
            ],
            "supported_formats": {
                "input": ["Python (.py)", "YAML configuration", "TOML configuration"],
                "output": [
                    "Obsidian Markdown",
                    "Sphinx HTML",
                    "Cross-referenced documentation",
                ],
            },
            "integrations": ["Obsidian", "Sphinx", "Claude Code", "MCP Protocol"],
        }
        return json.dumps(capabilities, indent=2)


async def main() -> None:
    """Main entry point for the MCP server."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        # Create and start the MCP server
        server = DocumentationMCPServer()

        logger.info(f"Starting {server.name} v{server.version}")

        # Run the server using stdio transport
        async with stdio_server() as streams:
            await server.server.run(
                streams[0],
                streams[1],
                InitializationOptions(
                    server_name=server.name,
                    server_version=server.version,
                    capabilities=ServerCapabilities(),
                ),
            )

    except Exception:
        logger.exception("Error starting MCP server")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
