# Obsidian Doc MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI](https://github.com/madskristensen/obsidian-doc-mcp/workflows/CI/badge.svg)](https://github.com/madskristensen/obsidian-doc-mcp/actions)
[![codecov](https://codecov.io/gh/madskristensen/obsidian-doc-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/madskristensen/obsidian-doc-mcp)

An MCP (Model Context Protocol) server for generating Python project documentation in Obsidian-compatible format using Sphinx. This tool bridges the gap between code development and knowledge management by automatically creating and maintaining comprehensive, discoverable documentation.

## Vision

**"Documentation that writes itself and grows with your knowledge"**

Transform your Python development workflow by creating seamless, automated documentation that lives where you think - in your knowledge management system. Never lose track of your code architecture through automatically updated documentation that builds personal knowledge graphs connecting code concepts across projects.

## Features

- **Automatic Code Analysis**: Uses Python AST parsing to extract docstrings, signatures, and structure
- **Sphinx Integration**: Leverages the industry-standard Sphinx documentation system
- **Obsidian-Compatible Output**: Generates markdown with wikilinks for seamless knowledge management
- **MCP Protocol**: Native integration with Claude Code and other MCP-compatible tools
- **Zero Configuration**: Works out of the box with sensible defaults
- **Customizable Templates**: Extensible Jinja2 templates for different documentation styles
- **Smart Organization**: Automatically organizes documentation by module structure
- **Incremental Updates**: Efficient updates for changed files only

## Requirements

- Python 3.11 or higher
- Claude Code (for MCP integration) or other MCP-compatible client
- Obsidian (for viewing generated documentation)

## Installation

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/madskristensen/obsidian-doc-mcp.git
cd obsidian-doc-mcp

# Install dependencies using uv
uv sync

# Install development dependencies (optional)
uv sync --dev
```

### Using pip

```bash
# Clone and install
git clone https://github.com/madskristensen/obsidian-doc-mcp.git
cd obsidian-doc-mcp
pip install -e .

# For development
pip install -e .[dev]
```

## Quick Start

### 1. Configure Your Project

Create a `.mcp-docs.yaml` configuration file in your Python project:

```yaml
project:
  name: "My Python Project"
  version: "1.0.0"
  source_paths: ["src/", "lib/"]
  exclude_patterns: ["tests/", "*.pyc"]

obsidian:
  vault_path: "/path/to/your/obsidian/vault"
  docs_folder: "Projects/MyProject"
  use_wikilinks: true

output:
  generate_index: true
  include_source_links: true
```

### 2. Start the MCP Server

```bash
# Using uv
uv run obsidian-doc-mcp

# Or directly with Python
python -m server.mcp_server
```

### 3. Use with Claude Code

The server will automatically register with Claude Code when it detects a `.mcp-docs.yaml` file in your project. You can then use commands like:

- Generate complete documentation
- Update documentation for changed files
- Analyze project structure
- Validate documentation completeness

## Documentation Structure

The generated documentation follows this structure in your Obsidian vault:

```
Your Vault/
└── Projects/
    └── YourProject/
        ├── index.md                 # Project overview
        ├── modules/
        │   ├── module1.md          # Module documentation
        │   └── module2.md
        ├── classes/
        │   ├── Class1.md           # Class documentation
        │   └── Class2.md
        └── functions/
            ├── function1.md        # Function documentation
            └── function2.md
```

## Configuration Options

### Project Settings
- `name`: Project name for documentation
- `version`: Project version
- `source_paths`: List of directories to scan for Python files
- `exclude_patterns`: Patterns to exclude from analysis
- `include_private`: Whether to include private methods and classes

### Obsidian Integration
- `vault_path`: Path to your Obsidian vault
- `docs_folder`: Folder within vault for documentation
- `use_wikilinks`: Use `[[wikilinks]]` vs `[markdown](links)`
- `tag_prefix`: Prefix for generated tags
- `template_folder`: Custom templates location

### Sphinx Configuration
- `extensions`: Sphinx extensions to use
- `theme`: Sphinx theme for initial generation
- `custom_config`: Path to custom Sphinx configuration

### Output Options
- `generate_index`: Create main index file
- `cross_reference_external`: Link to external documentation
- `include_source_links`: Include links back to source code
- `group_by_module`: Organize docs by module structure

## Development

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/madskristensen/obsidian-doc-mcp.git
cd obsidian-doc-mcp

# Install development dependencies
uv sync --dev

# Set up pre-commit hooks
uv run pre-commit install
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run specific test file
uv run pytest tests/test_analyzer.py
```

### Code Quality

This project uses several tools to maintain code quality:

```bash
# Format code
uv run black .

# Lint code
uv run ruff check .

# Type checking
uv run mypy .

# Run all quality checks
uv run pre-commit run --all-files
```

## Architecture

The project follows a modular architecture:

- **`server/`**: MCP server implementation and protocol handlers
- **`docs_generator/`**: Core documentation generation logic
  - `analyzer.py`: Python AST analysis and code parsing
  - `sphinx_integration.py`: Sphinx doc generation (coming soon)
  - `obsidian_converter.py`: Sphinx → Obsidian conversion (coming soon)
- **`config/`**: Configuration management and validation
- **`utils/`**: Utility functions for file operations and Obsidian integration

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and quality checks
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Related Projects

- [MCP (Model Context Protocol)](https://github.com/modelcontextprotocol/specification)
- [Claude Code](https://claude.ai/code)
- [Sphinx Documentation](https://www.sphinx-doc.org/)
- [Obsidian](https://obsidian.md/)
- [obsidiantools](https://github.com/mfarragher/obsidiantools)

## Support

If you have any questions or run into issues:

1. Check the [documentation](https://github.com/madskristensen/obsidian-doc-mcp#readme)
2. Search existing [issues](https://github.com/madskristensen/obsidian-doc-mcp/issues)
3. Open a new issue if you can't find an answer

## Roadmap

- [x] **v0.1.0**: Core infrastructure and project setup
- [ ] **v0.2.0**: Basic Python project analysis
- [ ] **v0.3.0**: Sphinx integration and HTML generation
- [ ] **v0.4.0**: Obsidian markdown conversion
- [ ] **v0.5.0**: MCP tools implementation
- [ ] **v1.0.0**: First stable release

For detailed roadmap and current development status, see [PLANNING.md](PLANNING.md) and [TASKS.md](TASKS.md).

---

**Made with love for the Python and Obsidian communities**
