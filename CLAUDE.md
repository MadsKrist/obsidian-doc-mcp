# CLAUDE.md - MCP Python Documentation Server

## Project Overview

**Project Name**: MCP Python Documentation Server  
**Purpose**: Generate Python project documentation in Obsidian-compatible format using Sphinx  
**Target**: Integration with Claude Code for automated documentation workflows  

### Core Mission
Create an MCP server that automatically generates and maintains Python project documentation in Obsidian markdown format, bridging the gap between code development and knowledge management.

## 🚨 CRITICAL WORKFLOW INSTRUCTIONS

### At the Start of Every New Conversation:
1. **ALWAYS read `PLANNING.md`** - This contains the current project roadmap, priorities, and strategic decisions
2. **Check `TASKS.md`** - Review current tasks, their status, and priorities before starting any work
3. **Mark completed tasks immediately** - Update task status as work is completed
4. **Add newly discovered tasks** - When you identify new work items, add them to `TASKS.md` with appropriate priority

### Package Management:
- **ALWAYS use `uv`** for package management (NOT pip)
- Use `uv add <package>` instead of `pip install <package>`
- Use `uv remove <package>` instead of `pip uninstall <package>`
- Use `uv sync` to sync dependencies
- Use `uv run` to execute commands in the virtual environment

## Architecture Overview

### System Components
```
obsidian-doc-mcp/
├── PLANNING.md                    # ⚠️  MUST READ: Project roadmap and strategy
├── TASKS.md                       # ⚠️  MUST CHECK: Current tasks and priorities  
├── CLAUDE.md                      # This file - development guide
├── pyproject.toml                 # uv dependency management
├── server/
│   ├── mcp_server.py          # Main MCP server implementation
│   ├── tools/                 # MCP tools (generate_docs, update_docs, etc.)
│   └── resources/             # MCP resources (project_structure, config, etc.)
├── docs_generator/
│   ├── analyzer.py            # Python AST analysis and code parsing
│   ├── sphinx_integration.py  # Sphinx doc generation and configuration
│   └── obsidian_converter.py  # Sphinx → Obsidian markdown conversion
├── config/
│   ├── project_config.py      # Configuration management
│   └── templates/             # Jinja2 templates for doc generation
└── utils/
    ├── file_utils.py          # File system operations
    └── obsidian_utils.py      # Obsidian vault management
```

### Key Dependencies
- **mcp**: Model Context Protocol SDK
- **sphinx**: Documentation generation engine
- **obsidiantools**: Obsidian vault management (`uv add obsidiantools`)
- **jinja2**: Template engine for customizable output
- **pyyaml**: Configuration file parsing
- **ast**: Python AST parsing (built-in)

*Note: All dependencies should be managed through `uv` and defined in `pyproject.toml`*

### Data Flow
1. **Discovery** → Scan Python project for modules, classes, functions
2. **Analysis** → Extract docstrings, signatures, and structure using AST
3. **Sphinx Generation** → Create initial documentation with autodoc
4. **Obsidian Conversion** → Transform to markdown with wikilinks
5. **Vault Integration** → Place docs in proper Obsidian folder structure

## Development Guidelines

### Code Style
- Follow PEP 8 for Python code style
- Use type hints for all function signatures
- Docstrings in Google/NumPy format (compatible with Sphinx napoleon)
- Maximum line length: 88 characters (Black formatter compatible)

### Project Structure Conventions
- Each major component should be in its own module
- Use dependency injection for configuration and external services
- Separate pure functions from stateful operations
- Keep MCP protocol handlers thin - delegate to business logic

### Error Handling
- Use custom exception classes for different error types:
  - `ProjectAnalysisError`: Issues parsing Python code
  - `SphinxGenerationError`: Sphinx build failures
  - `ObsidianConversionError`: Markdown conversion issues
  - `MCPServerError`: Protocol-level errors
- Always provide actionable error messages with context
- Log errors with appropriate severity levels

### Configuration Management
- Support both YAML and TOML configuration formats
- Use `.mcp-docs.yaml` as the default config file name
- Provide sensible defaults for all configuration options
- Validate configuration on startup with clear error messages

## MCP Implementation Details

### Tools to Implement
```python
# server/tools/generate_docs.py
async def generate_docs(project_path: str, config_override: dict = None) -> dict:
    """Generate complete documentation for a Python project."""
    
# server/tools/update_docs.py  
async def update_docs(project_path: str, changed_files: list = None) -> dict:
    """Incrementally update documentation for changed files."""
    
# server/tools/configure_project.py
async def configure_project(project_path: str, config: dict) -> dict:
    """Set up or modify documentation configuration."""
    
# server/tools/validate_docs.py
async def validate_docs(project_path: str) -> dict:
    """Check documentation completeness and consistency."""
    
# server/tools/link_analysis.py
async def link_analysis(vault_path: str, project_folder: str) -> dict:
    """Analyze and optimize cross-references in documentation."""
```

### Resources to Implement
```python
# server/resources/project_structure.py
async def get_project_structure(project_path: str) -> dict:
    """Return analyzed project structure and metadata."""
    
# server/resources/documentation_status.py
async def get_documentation_status(project_path: str) -> dict:
    """Current state of project documentation coverage."""
    
# server/resources/configuration.py
async def get_configuration(project_path: str) -> dict:
    """Project-specific documentation settings."""
```

## Key Algorithms and Logic

### Python Project Analysis
```python
# docs_generator/analyzer.py
def analyze_python_project(project_path: Path) -> ProjectStructure:
    """
    Core algorithm for analyzing Python projects:
    1. Discover all .py files (respecting .gitignore)
    2. Parse each file with AST to extract:
       - Module docstrings
       - Class definitions and docstrings
       - Function signatures and docstrings
       - Import dependencies
    3. Build dependency graph
    4. Identify public vs private members
    5. Extract type hints and return types
    """
```

### Sphinx Integration Strategy
```python
# docs_generator/sphinx_integration.py
def generate_sphinx_docs(project_structure: ProjectStructure, config: Config) -> SphinxOutput:
    """
    Sphinx generation workflow:
    1. Create temporary Sphinx project structure
    2. Generate conf.py with appropriate extensions
    3. Create .rst files for each module using autodoc
    4. Build HTML documentation with cross-references
    5. Return structured output for conversion
    """
```

### Obsidian Conversion Logic
```python
# docs_generator/obsidian_converter.py
def convert_to_obsidian(sphinx_output: SphinxOutput, config: Config) -> ObsidianDocs:
    """
    Conversion strategy:
    1. Parse Sphinx HTML output to extract content structure
    2. Convert HTML to markdown preserving formatting
    3. Transform Sphinx cross-references to Obsidian wikilinks
    4. Generate appropriate folder structure
    5. Add Obsidian-specific metadata (tags, aliases)
    6. Create index files and navigation structure
    """
```

## Configuration Schema

### Project Configuration (`.mcp-docs.yaml`)
```yaml
project:
  name: "Project Name"
  version: "1.0.0"
  source_paths: ["src/", "lib/"]           # Paths to scan for Python files
  exclude_patterns: ["tests/", "*.pyc"]    # Patterns to ignore
  include_private: false                   # Include private methods/classes

obsidian:
  vault_path: "/path/to/obsidian/vault"    # Obsidian vault location
  docs_folder: "Projects/MyProject"        # Folder within vault for docs
  use_wikilinks: true                      # Use [[wikilinks]] vs [markdown](links)
  tag_prefix: "code/"                      # Prefix for generated tags
  template_folder: "Templates/Code"        # Custom templates location

sphinx:
  extensions:                              # Sphinx extensions to use
    - "sphinx.ext.autodoc"
    - "sphinx.ext.napoleon"
    - "sphinx.ext.viewcode"
  theme: "sphinx_rtd_theme"               # Sphinx theme for initial generation
  custom_config: "docs/conf.py"          # Path to custom Sphinx config

output:
  generate_index: true                     # Create main index file
  cross_reference_external: true          # Link to external documentation
  include_source_links: true              # Include links back to source code
  group_by_module: true                   # Organize docs by module structure
```

## Testing Strategy

### Unit Tests
- Test each component in isolation with mocked dependencies
- Use pytest with fixtures for common test data
- Mock file system operations and external dependencies
- Test error conditions and edge cases

### Integration Tests
- Test complete documentation generation workflow
- Use temporary directories for file operations
- Test with real Python projects of varying complexity
- Verify Obsidian vault integration doesn't corrupt existing files

### Test Data
- Maintain sample Python projects in `tests/fixtures/`
- Include projects with different structures:
  - Simple single-module project
  - Complex multi-package project
  - Project with unusual docstring formats
  - Project with type hints and modern Python features

## Development Workflow

### Local Development Setup
```bash
# 1. Clone and setup environment
git clone <repo-url>
cd mcp-python-docs-server

# 2. Install dependencies using uv
uv sync                    # Install all dependencies from pyproject.toml
uv add --dev pytest       # Add development dependencies if needed

# 3. Run tests
uv run pytest tests/

# 4. Run MCP server locally
uv run python -m server.mcp_server
```

### Common Development Tasks

#### Adding a New MCP Tool
1. Create tool module in `server/tools/`
2. Implement async function with proper error handling
3. Add tool registration in `server/mcp_server.py`
4. Write unit tests for the tool
5. Update this CLAUDE.md with tool documentation

#### Extending Configuration Options
1. Update configuration schema in `config/project_config.py`
2. Add validation logic for new options
3. Update default configuration template
4. Modify relevant components to use new options
5. Add tests for new configuration behavior

#### Adding Support for New Documentation Features
1. Identify where the feature fits in the pipeline
2. Extend the appropriate component (analyzer, sphinx_integration, or obsidian_converter)
3. Update configuration schema if needed
4. Add tests with sample input/output
5. Consider backward compatibility

## Performance Considerations

### Optimization Targets
- **Generation Time**: < 30 seconds for projects up to 10,000 lines
- **Memory Usage**: < 500MB during processing
- **Incremental Updates**: < 5 seconds for single file changes

### Performance Strategies
- Cache AST parsing results for unchanged files
- Use incremental Sphinx builds when possible
- Parallel processing for independent modules
- Lazy loading of large project structures
- Efficient file watching for update triggers

## Security and Safety

### Code Safety
- Sandbox Sphinx execution to prevent arbitrary code execution
- Validate all file paths to prevent directory traversal
- Never execute user code during analysis (AST parsing only)
- Sanitize all user inputs and configuration values

### Data Safety
- Never modify original source code files
- Create backups before modifying Obsidian vault
- Validate Obsidian vault structure before writing
- Use atomic file operations where possible

## Integration Points

### Claude Code Integration
- Server should start automatically when project contains `.mcp-docs.yaml`
- Provide context-aware suggestions for documentation improvements
- Integrate with existing development workflows
- Support for triggering updates on file save

### Obsidian Integration
- Respect existing vault structure and conventions
- Support common Obsidian plugins (templater, dataview, etc.)
- Preserve manual edits to generated documentation
- Generate appropriate metadata for Obsidian features

## Troubleshooting Common Issues

### Project Analysis Failures
- **Syntax Errors**: Skip malformed files with warning, don't fail entire project
- **Import Errors**: Handle missing dependencies gracefully
- **Complex AST**: Provide fallback for unsupported Python constructs

### Sphinx Generation Issues
- **Extension Conflicts**: Provide minimal safe configuration as fallback
- **Theme Issues**: Fall back to basic theme if custom theme fails
- **Build Failures**: Capture Sphinx warnings and errors for user feedback

### Obsidian Integration Problems
- **Vault Access**: Check permissions and provide clear error messages
- **Folder Conflicts**: Handle existing files and folders gracefully
- **Link Resolution**: Validate wikilinks and fix broken references

## Future Enhancement Areas

### Short-term Improvements
- Support for Jupyter notebooks in documentation
- Integration with popular Python documentation tools (pdoc, mkdocs)
- Advanced templating for custom documentation formats
- Better handling of complex type annotations

### Long-term Vision
- AI-powered documentation quality assessment
- Automatic generation of usage examples
- Integration with version control for documentation history
- Support for multiple programming languages

## Quick Reference

### Key Files for New Contributors
- **`PLANNING.md`** - ⚠️ **READ FIRST** - Project roadmap, priorities, and strategic decisions
- **`TASKS.md`** - ⚠️ **CHECK BEFORE WORK** - Current tasks, status, and priorities
- **`CLAUDE.md`** - This development guide and reference
- **`pyproject.toml`** - Project dependencies managed by uv
- `server/mcp_server.py` - Main entry point and MCP protocol handling
- `docs_generator/analyzer.py` - Core Python project analysis logic
- `docs_generator/obsidian_converter.py` - Sphinx to Obsidian conversion
- `config/project_config.py` - Configuration management and validation

### Environment Variables
- `MCP_DOCS_LOG_LEVEL` - Set logging level (DEBUG, INFO, WARNING, ERROR)
- `MCP_DOCS_CONFIG_PATH` - Override default configuration file location
- `MCP_DOCS_TEMP_DIR` - Custom temporary directory for Sphinx builds

### Useful Commands
```bash
# Run with debug logging
MCP_DOCS_LOG_LEVEL=DEBUG uv run python -m server.mcp_server

# Test with specific project
uv run python -m docs_generator.analyzer /path/to/python/project

# Validate configuration
uv run python -m config.project_config validate /path/to/.mcp-docs.yaml

# Add new dependency
uv add sphinx jinja2

# Add development dependency
uv add --dev pytest black

# Remove dependency
uv remove package-name

# Sync all dependencies
uv sync
```

---

This document should be updated as the project evolves. When making significant architectural changes, please update the relevant sections to keep this guide accurate and useful for future development sessions.