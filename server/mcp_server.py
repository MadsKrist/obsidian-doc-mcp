"""Main MCP Server implementation for Python documentation generation.

This module contains the core MCP server that handles communication with
Claude Code and orchestrates the documentation generation pipeline.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

from config.project_config import Config, ConfigManager
from docs_generator.analyzer import PythonProjectAnalyzer

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
        async def handle_call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent]:
            """Handle tool calls."""
            logger.info(f"Tool called: {name} with args: {arguments}")

            if name == "analyze_project":
                return await self._handle_analyze_project(arguments)
            elif name == "health_check":
                return await self._handle_health_check(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")

    def _register_resource_handlers(self) -> None:
        """Register MCP resource handlers."""

        @self.server.list_resources()
        async def handle_list_resources() -> list[Resource]:
            """List available resources."""
            return [
                Resource(
                    uri="status",
                    name="Server Status",
                    description="Current status and health information of "
                    "the MCP server",
                    mimeType="application/json",
                ),
                Resource(
                    uri="capabilities",
                    name="Server Capabilities",
                    description="List of server capabilities and supported operations",
                    mimeType="application/json",
                ),
            ]

    async def _handle_analyze_project(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
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

    async def _handle_health_check(
        self, _arguments: dict[str, Any]
    ) -> list[TextContent]:
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
        import json

        status = {
            "name": self.name,
            "version": self.version,
            "status": "running",
            "uptime": asyncio.get_event_loop().time(),
            "tools_registered": 2,
            "resources_registered": 2,
        }
        return json.dumps(status, indent=2)

    async def _get_server_capabilities(self) -> str:
        """Get server capabilities resource."""
        import json

        capabilities = {
            "protocol_version": "2024-11-05",
            "tools": [
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
                {"uri": "server://status", "description": "Server status information"},
                {
                    "uri": "server://capabilities",
                    "description": "Server capabilities listing",
                },
            ],
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
                    server_name=server.name, server_version=server.version
                ),
            )

    except Exception:
        logger.exception("Error starting MCP server")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
