# CLAUDE.md - MCP Python Documentation Server

## 🚨 CRITICAL WORKFLOW INSTRUCTIONS

### At the Start of Every New Conversation:
1. **ALWAYS read `PLANNING.md`** - Contains current project roadmap and priorities
2. **Check `TASKS.md`** - Review current tasks and status before starting work
3. **Mark completed tasks immediately** - Update status as work is completed
4. **Add newly discovered tasks** - Add new items to `TASKS.md` with priority

### Package Management:
- **ALWAYS use `uv`** for package management (NOT pip)
- `uv add <package>` instead of `pip install`
- `uv sync` to sync dependencies
- `uv run` to execute commands in virtual environment

## Current Project Status

**Mission**: MCP server for automated Python → Obsidian documentation generation
**Architecture**: Complete pipeline implemented (AST analysis → Sphinx → Obsidian conversion)
**Status**: Production-ready core with comprehensive test coverage (57% overall, >90% on core modules)

## Key System Components

### Core Modules (Production Ready)
- **`docs_generator/analyzer.py`** - AST-based Python project analysis (88% coverage)
- **`docs_generator/sphinx_integration.py`** - Sphinx documentation generation (99% coverage)
- **`docs_generator/obsidian_converter.py`** - HTML to Obsidian markdown (93% coverage)
- **`config/project_config.py`** - Configuration management (92% coverage)

### MCP Server Integration
- **`server/mcp_server.py`** - Main MCP protocol handler
- **`server/tools/`** - MCP tools for documentation operations
- **`server/resources/`** - MCP resources for project information

### Performance Optimization (Ready)
- **`utils/memory_optimizer.py`** - Memory-efficient processing (92% coverage)
- **`utils/parallel_processor.py`** - Parallel documentation generation (95% coverage)
- **`utils/incremental_build.py`** - Smart incremental updates (90% coverage)

## Essential Development Information

### Configuration (`.mcp-docs.yaml`)
```yaml
project:
  source_paths: ["src/", "lib/"]
  exclude_patterns: ["tests/", "*.pyc"]

obsidian:
  vault_path: "/path/to/obsidian/vault"
  docs_folder: "Projects/MyProject"
  use_wikilinks: true

sphinx:
  extensions: ["sphinx.ext.autodoc", "sphinx.ext.napoleon"]
  theme: "sphinx_rtd_theme"
```

### Code Standards
- PEP 8 compliance, 88-character line limit
- Type hints required, Google/NumPy docstrings
- 100% pre-commit hook compliance (Black, Ruff, Pyright)
- >90% test coverage target for new modules

## Quick Development Reference

### Key Files
- **`PLANNING.md`** - ⚠️ Current roadmap and priorities
- **`TASKS.md`** - ⚠️ Current tasks and status
- **`pyproject.toml`** - Dependencies managed by uv
- **`server/mcp_server.py`** - Main MCP entry point
- **Core pipeline**: `analyzer.py` → `sphinx_integration.py` → `obsidian_converter.py`

### Essential Commands
```bash
# Development workflow
uv sync                              # Sync dependencies
uv run pytest tests/                 # Run test suite (320 tests)
uv run python -m server.mcp_server   # Start MCP server

# Quality gates (automated via pre-commit)
uv run black .                       # Code formatting
uv run ruff check .                  # Linting
uv run pyright                       # Type checking

# Testing specific modules
uv run pytest tests/unit/test_analyzer.py
uv run pytest tests/integration/ -v
```

### Performance Targets
- **Generation**: <30s for 10K lines
- **Memory**: <500MB during processing
- **Incremental**: <5s for single file changes
- **Test Coverage**: >90% for new modules (current: 57% overall)

## Development History (Summary)

### Completed Milestones
- **✅ Milestone 0**: Project foundation with modern Python tooling and CI/CD
- **✅ Milestone 2**: Complete Sphinx → Obsidian documentation pipeline
- **✅ Milestone 4**: Performance optimization features with comprehensive testing
- **✅ Code Quality**: 100% pre-commit compliance, type safety, 57% test coverage

### Current Status (Aug 15, 2025)
- **Production-ready core modules** with >90% test coverage
- **320 passing tests** with comprehensive functionality validation
- **Complete documentation pipeline** from Python AST → Obsidian markdown
- **Quality foundation** established for production deployment

---

*This document is streamlined to focus on essential development information. Detailed session histories and completed implementations have been archived.*
