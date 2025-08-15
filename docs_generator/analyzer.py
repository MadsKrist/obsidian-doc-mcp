"""Python project analysis and AST parsing.

This module provides functionality to analyze Python projects by parsing
source code with the AST module and extracting documentation information.
"""

import ast
import fnmatch
import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FunctionInfo:
    """Information about a function or method."""

    name: str
    signature: str
    docstring: str | None = None
    line_number: int = 0
    is_async: bool = False
    is_method: bool = False
    is_property: bool = False
    is_staticmethod: bool = False
    is_classmethod: bool = False
    is_private: bool = False
    parameters: list[str] = field(default_factory=list)
    parameter_types: dict[str, str] = field(default_factory=dict)
    return_type: str | None = None
    decorators: list[str] = field(default_factory=list)


@dataclass
class ClassInfo:
    """Information about a class."""

    name: str
    docstring: str | None = None
    line_number: int = 0
    is_private: bool = False
    base_classes: list[str] = field(default_factory=list)
    methods: list[FunctionInfo] = field(default_factory=list)
    properties: list[FunctionInfo] = field(default_factory=list)
    class_variables: dict[str, str] = field(default_factory=dict)
    decorators: list[str] = field(default_factory=list)


@dataclass
class ModuleInfo:
    """Information about a Python module."""

    name: str
    file_path: Path
    docstring: str | None = None
    imports: list[str] = field(default_factory=list)
    from_imports: dict[str, list[str]] = field(default_factory=dict)
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    constants: dict[str, str] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)
    is_package: bool = False
    package_path: str = ""


@dataclass
class ProjectStructure:
    """Complete structure of a Python project."""

    project_name: str
    root_path: Path
    modules: list[ModuleInfo] = field(default_factory=list)
    packages: dict[str, list[str]] = field(default_factory=dict)
    dependencies: set[str] = field(default_factory=set)
    external_dependencies: set[str] = field(default_factory=set)
    internal_dependencies: set[str] = field(default_factory=set)
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class CacheEntry:
    """Cache entry for parsed AST data."""

    module_info: ModuleInfo
    file_hash: str
    timestamp: float
    file_size: int


class ProjectAnalysisError(Exception):
    """Exception raised when project analysis fails."""

    pass


class PythonProjectAnalyzer:
    """Analyzes Python projects to extract documentation information."""

    def __init__(
        self, project_path: Path, enable_cache: bool = True, cache_ttl: int = 3600
    ) -> None:
        """Initialize the analyzer.

        Args:
            project_path: Path to the Python project root
            enable_cache: Whether to enable AST parsing cache
            cache_ttl: Cache time-to-live in seconds (default: 1 hour)
        """
        self.project_path = Path(project_path)
        if not self.project_path.exists():
            raise ProjectAnalysisError(f"Project path does not exist: {project_path}")

        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        self._cache: dict[str, CacheEntry] = {}
        self._cache_file = self.project_path / ".mcp-docs-cache.json"

        if self.enable_cache:
            self._load_cache()

        logger.info(
            f"Initialized analyzer for project: {self.project_path} (cache: {enable_cache})"
        )

    def _load_cache(self) -> None:
        """Load AST parsing cache from disk."""
        if not self._cache_file.exists():
            logger.debug("No cache file found, starting with empty cache")
            return

        try:
            with open(self._cache_file, encoding="utf-8") as f:
                cache_data = json.load(f)

            current_time = time.time()
            for file_path_str, entry_data in cache_data.items():
                # Check if cache entry is still valid (TTL)
                if current_time - entry_data["timestamp"] > self.cache_ttl:
                    continue

                # Reconstruct ModuleInfo from cached data
                module_data = entry_data["module_info"]

                # Reconstruct data classes
                functions = [
                    FunctionInfo(**func_data)
                    for func_data in module_data.get("functions", [])
                ]
                classes = []
                for class_data in module_data.get("classes", []):
                    methods = [
                        FunctionInfo(**method_data)
                        for method_data in class_data.get("methods", [])
                    ]
                    properties = [
                        FunctionInfo(**prop_data)
                        for prop_data in class_data.get("properties", [])
                    ]
                    class_info = ClassInfo(
                        name=class_data["name"],
                        docstring=class_data.get("docstring"),
                        line_number=class_data.get("line_number", 0),
                        is_private=class_data.get("is_private", False),
                        base_classes=class_data.get("base_classes", []),
                        methods=methods,
                        properties=properties,
                        class_variables=class_data.get("class_variables", {}),
                        decorators=class_data.get("decorators", []),
                    )
                    classes.append(class_info)

                module_info = ModuleInfo(
                    name=module_data["name"],
                    file_path=Path(module_data["file_path"]),
                    docstring=module_data.get("docstring"),
                    imports=module_data.get("imports", []),
                    from_imports=module_data.get("from_imports", {}),
                    classes=classes,
                    functions=functions,
                    constants=module_data.get("constants", {}),
                    variables=module_data.get("variables", {}),
                    is_package=module_data.get("is_package", False),
                    package_path=module_data.get("package_path", ""),
                )

                cache_entry = CacheEntry(
                    module_info=module_info,
                    file_hash=entry_data["file_hash"],
                    timestamp=entry_data["timestamp"],
                    file_size=entry_data["file_size"],
                )

                self._cache[file_path_str] = cache_entry

            logger.info(f"Loaded {len(self._cache)} entries from cache")

        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            self._cache = {}

    def _save_cache(self) -> None:
        """Save AST parsing cache to disk."""
        if not self.enable_cache:
            return

        try:
            cache_data = {}
            for file_path_str, cache_entry in self._cache.items():
                # Convert dataclasses to dictionaries for JSON serialization
                module_data = {
                    "name": cache_entry.module_info.name,
                    "file_path": str(cache_entry.module_info.file_path),
                    "docstring": cache_entry.module_info.docstring,
                    "imports": cache_entry.module_info.imports,
                    "from_imports": cache_entry.module_info.from_imports,
                    "constants": cache_entry.module_info.constants,
                    "variables": cache_entry.module_info.variables,
                    "is_package": cache_entry.module_info.is_package,
                    "package_path": cache_entry.module_info.package_path,
                    "functions": [
                        asdict(func) for func in cache_entry.module_info.functions
                    ],
                    "classes": [],
                }

                for class_info in cache_entry.module_info.classes:
                    class_data = asdict(class_info)
                    # Convert Path objects to strings in methods and properties
                    for method in class_data.get("methods", []):
                        if "file_path" in method and isinstance(
                            method["file_path"], Path
                        ):
                            method["file_path"] = str(method["file_path"])
                    for prop in class_data.get("properties", []):
                        if "file_path" in prop and isinstance(prop["file_path"], Path):
                            prop["file_path"] = str(prop["file_path"])
                    module_data["classes"].append(class_data)

                cache_data[file_path_str] = {
                    "module_info": module_data,
                    "file_hash": cache_entry.file_hash,
                    "timestamp": cache_entry.timestamp,
                    "file_size": cache_entry.file_size,
                }

            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)

            logger.debug(f"Saved {len(cache_data)} entries to cache")

        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _get_file_hash(self, file_path: Path) -> str:
        """Get SHA-256 hash of file contents."""
        try:
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return ""

    def _is_cache_valid(self, file_path: Path, cache_entry: CacheEntry) -> bool:
        """Check if cache entry is still valid for the given file."""
        if not file_path.exists():
            return False

        # Check if file has been modified
        file_stat = file_path.stat()
        current_size = file_stat.st_size
        current_hash = self._get_file_hash(file_path)

        return (
            cache_entry.file_size == current_size
            and cache_entry.file_hash == current_hash
            and time.time() - cache_entry.timestamp < self.cache_ttl
        )

    def clear_cache(self) -> None:
        """Clear the AST parsing cache."""
        self._cache.clear()
        if self._cache_file.exists():
            self._cache_file.unlink()
        logger.info("Cache cleared")

    def analyze_project(
        self, exclude_patterns: list[str] | None = None
    ) -> ProjectStructure:
        """Analyze the entire Python project.

        Args:
            exclude_patterns: List of patterns to exclude from analysis

        Returns:
            ProjectStructure containing all analyzed information

        Raises:
            ProjectAnalysisError: If analysis fails
        """
        logger.info("Starting project analysis")

        exclude_patterns = exclude_patterns or [
            "__pycache__",
            "*.pyc",
            "tests/",
            ".git/",
        ]

        try:
            python_files = self._discover_python_files(exclude_patterns)
            logger.info(f"Found {len(python_files)} Python files to analyze")

            project_name = self.project_path.name
            structure = ProjectStructure(
                project_name=project_name, root_path=self.project_path
            )

            for file_path in python_files:
                try:
                    module_info = self._analyze_file(file_path)
                    structure.modules.append(module_info)
                    structure.dependencies.update(module_info.imports)
                except Exception as e:
                    logger.warning(f"Failed to analyze {file_path}: {e}")
                    continue

            # Build enhanced dependency information
            self._build_dependency_analysis(structure)
            self._build_package_structure(structure)

            # Save cache after successful analysis
            if self.enable_cache:
                self._save_cache()

            logger.info(
                f"Analysis complete. Found {len(structure.modules)} modules, "
                f"{len(structure.packages)} packages"
            )
            return structure

        except Exception as e:
            raise ProjectAnalysisError(f"Project analysis failed: {e}") from e

    def _discover_python_files(self, exclude_patterns: list[str]) -> list[Path]:
        """Discover all Python files in the project.

        Args:
            exclude_patterns: Patterns to exclude

        Returns:
            List of Python file paths
        """
        python_files = []

        for file_path in self.project_path.rglob("*.py"):
            # Convert to relative path for pattern matching
            relative_path = file_path.relative_to(self.project_path)

            # Check if file should be excluded using glob patterns
            should_exclude = False
            for pattern in exclude_patterns:
                # Check exact file name match
                if file_path.name == pattern:
                    should_exclude = True
                    break
                # Check glob pattern match on relative path
                if fnmatch.fnmatch(str(relative_path), pattern):
                    should_exclude = True
                    break
                # Check parent directory matches
                if fnmatch.fnmatch(str(relative_path.parent), pattern):
                    should_exclude = True
                    break
                # Also check if any parent directory matches pattern
                for parent in relative_path.parents:
                    if fnmatch.fnmatch(str(parent), pattern):
                        should_exclude = True
                        break

            if should_exclude:
                continue

            python_files.append(file_path)

        return sorted(python_files)

    def _analyze_file(self, file_path: Path) -> ModuleInfo:
        """Analyze a single Python file.

        Args:
            file_path: Path to the Python file

        Returns:
            ModuleInfo containing extracted information

        Raises:
            ProjectAnalysisError: If file analysis fails
        """
        logger.debug(f"Analyzing file: {file_path}")

        # Check cache first if enabled
        file_path_str = str(file_path)
        if self.enable_cache and file_path_str in self._cache:
            cache_entry = self._cache[file_path_str]
            if self._is_cache_valid(file_path, cache_entry):
                logger.debug(f"Using cached analysis for: {file_path}")
                return cache_entry.module_info
            else:
                logger.debug(f"Cache entry expired for: {file_path}")
                del self._cache[file_path_str]

        try:
            with open(file_path, encoding="utf-8") as f:
                source_code = f.read()
        except Exception as e:
            raise ProjectAnalysisError(f"Could not read {file_path}: {e}") from e

        try:
            tree = ast.parse(source_code, filename=str(file_path))
        except SyntaxError as e:
            raise ProjectAnalysisError(f"Syntax error in {file_path}: {e}") from e

        # Extract module name and package information
        relative_path = file_path.relative_to(self.project_path)
        is_package = file_path.name == "__init__.py"

        if is_package:
            # For __init__.py files, the module name is the package path itself
            if relative_path.parent == Path("."):
                full_module_name = file_path.parent.name
                package_path = ""
            else:
                package_path = str(relative_path.parent).replace("/", ".")
                full_module_name = package_path
        else:
            # For regular .py files
            module_name = file_path.stem
            if relative_path.parent == Path("."):
                package_path = ""
                full_module_name = module_name
            else:
                package_path = str(relative_path.parent).replace("/", ".")
                full_module_name = f"{package_path}.{module_name}"

        module_info = ModuleInfo(
            name=full_module_name,
            file_path=file_path,
            docstring=ast.get_docstring(tree),
            is_package=is_package,
            package_path=package_path,
        )

        # Visit AST nodes to extract information
        visitor = _ModuleVisitor(module_info)
        visitor.visit(tree)

        # Cache the analysis result if caching is enabled
        if self.enable_cache:
            file_stat = file_path.stat()
            cache_entry = CacheEntry(
                module_info=module_info,
                file_hash=self._get_file_hash(file_path),
                timestamp=time.time(),
                file_size=file_stat.st_size,
            )
            self._cache[file_path_str] = cache_entry

        return module_info

    def _build_dependency_analysis(self, structure: ProjectStructure) -> None:
        """Build enhanced dependency analysis."""
        internal_modules = {module.name for module in structure.modules}

        for module in structure.modules:
            module_deps = []

            for import_name in module.imports:
                # Check if it's an internal dependency
                if import_name in internal_modules or any(
                    import_name.startswith(f"{internal}.")
                    for internal in internal_modules
                ):
                    structure.internal_dependencies.add(import_name)
                    module_deps.append(import_name)
                else:
                    # Check if it's a standard library module
                    if self._is_stdlib_module(import_name):
                        continue  # Skip stdlib modules
                    structure.external_dependencies.add(import_name)

            structure.dependency_graph[module.name] = module_deps

    def _build_package_structure(self, structure: ProjectStructure) -> None:
        """Build package structure information."""
        for module in structure.modules:
            if module.package_path:
                package_parts = module.package_path.split(".")
                current_package = ""

                for part in package_parts:
                    if current_package:
                        current_package += f".{part}"
                    else:
                        current_package = part

                    if current_package not in structure.packages:
                        structure.packages[current_package] = []

                    # Add module to the most specific package
                    if current_package == module.package_path:
                        structure.packages[current_package].append(module.name)

    def _is_stdlib_module(self, module_name: str) -> bool:
        """Check if a module is part of the Python standard library."""
        # Get the top-level module name
        top_level = module_name.split(".")[0]

        # Common stdlib modules - this is a simplified check
        stdlib_modules = {
            "os",
            "sys",
            "json",
            "xml",
            "urllib",
            "http",
            "collections",
            "itertools",
            "functools",
            "operator",
            "re",
            "string",
            "io",
            "pathlib",
            "datetime",
            "time",
            "random",
            "math",
            "statistics",
            "logging",
            "threading",
            "multiprocessing",
            "subprocess",
            "socket",
            "asyncio",
            "unittest",
            "doctest",
            "argparse",
            "configparser",
            "csv",
            "sqlite3",
            "pickle",
            "copy",
            "types",
            "typing",
            "dataclasses",
            "enum",
            "abc",
            "contextlib",
            "warnings",
            "traceback",
            "inspect",
            "ast",
            "dis",
            "keyword",
            "token",
            "tokenize",
            "struct",
            "codecs",
            "locale",
            "gettext",
        }

        return top_level in stdlib_modules


class _ModuleVisitor(ast.NodeVisitor):
    """AST visitor to extract module information."""

    def __init__(self, module_info: ModuleInfo) -> None:
        self.module_info = module_info
        self.current_class: ClassInfo | None = None
        self._builtin_types = {
            "int",
            "float",
            "str",
            "bool",
            "list",
            "dict",
            "tuple",
            "set",
            "frozenset",
            "bytes",
            "bytearray",
            "complex",
            "None",
            "Any",
            "Optional",
            "Union",
            "List",
            "Dict",
            "Tuple",
            "Set",
        }

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition."""
        decorators = [self._get_decorator_name(dec) for dec in node.decorator_list]
        is_property = "property" in decorators
        is_staticmethod = "staticmethod" in decorators
        is_classmethod = "classmethod" in decorators
        is_private = node.name.startswith("_")

        func_info = FunctionInfo(
            name=node.name,
            signature=self._get_function_signature(node),
            docstring=ast.get_docstring(node),
            line_number=node.lineno,
            is_async=False,
            is_method=self.current_class is not None,
            is_property=is_property,
            is_staticmethod=is_staticmethod,
            is_classmethod=is_classmethod,
            is_private=is_private,
            parameters=[arg.arg for arg in node.args.args],
            parameter_types=self._get_parameter_types(node),
            return_type=self._get_annotation_string(node.returns),
            decorators=decorators,
        )

        if self.current_class:
            if is_property:
                self.current_class.properties.append(func_info)
            else:
                self.current_class.methods.append(func_info)
        else:
            self.module_info.functions.append(func_info)

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition."""
        decorators = [self._get_decorator_name(dec) for dec in node.decorator_list]
        is_property = "property" in decorators
        is_staticmethod = "staticmethod" in decorators
        is_classmethod = "classmethod" in decorators
        is_private = node.name.startswith("_")

        func_info = FunctionInfo(
            name=node.name,
            signature=self._get_function_signature(node),
            docstring=ast.get_docstring(node),
            line_number=node.lineno,
            is_async=True,
            is_method=self.current_class is not None,
            is_property=is_property,
            is_staticmethod=is_staticmethod,
            is_classmethod=is_classmethod,
            is_private=is_private,
            parameters=[arg.arg for arg in node.args.args],
            parameter_types=self._get_parameter_types(node),
            return_type=self._get_annotation_string(node.returns),
            decorators=decorators,
        )

        if self.current_class:
            if is_property:
                self.current_class.properties.append(func_info)
            else:
                self.current_class.methods.append(func_info)
        else:
            self.module_info.functions.append(func_info)

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition."""
        decorators = [self._get_decorator_name(dec) for dec in node.decorator_list]
        is_private = node.name.startswith("_")

        class_info = ClassInfo(
            name=node.name,
            docstring=ast.get_docstring(node),
            line_number=node.lineno,
            is_private=is_private,
            base_classes=[self._get_base_class_name(base) for base in node.bases],
            decorators=decorators,
        )

        # Set current class for method processing
        old_class = self.current_class
        self.current_class = class_info

        # Visit class body to collect class variables and methods
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                # Class variable with type annotation
                var_name = item.target.id
                var_type = self._get_annotation_string(item.annotation)
                class_info.class_variables[var_name] = var_type
            elif isinstance(item, ast.Assign):
                # Class variable assignment
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        var_name = target.id
                        # Try to infer type from value
                        var_type = self._infer_type_from_value(item.value)
                        class_info.class_variables[var_name] = var_type

        # Visit class body for methods and nested classes
        self.generic_visit(node)

        # Restore previous class context
        self.current_class = old_class

        # Add class to module
        self.module_info.classes.append(class_info)

    def visit_Import(self, node: ast.Import) -> None:
        """Visit import statement."""
        for alias in node.names:
            self.module_info.imports.append(alias.name)

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit from-import statement."""
        if node.module:
            # Store from-imports separately for better tracking
            imported_names = [alias.name for alias in node.names]
            self.module_info.from_imports[node.module] = imported_names
            self.module_info.imports.append(node.module)

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit assignment statement for module-level constants and variables."""
        if self.current_class is None:  # Only process module-level assignments
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id
                    # Check if it looks like a constant (ALL_CAPS)
                    if var_name.isupper():
                        var_type = self._infer_type_from_value(node.value)
                        self.module_info.constants[var_name] = var_type
                    else:
                        var_type = self._infer_type_from_value(node.value)
                        self.module_info.variables[var_name] = var_type

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Visit annotated assignment statement."""
        if self.current_class is None and isinstance(node.target, ast.Name):
            var_name = node.target.id
            var_type = self._get_annotation_string(node.annotation)

            # Check if it looks like a constant (ALL_CAPS)
            if var_name.isupper():
                self.module_info.constants[var_name] = var_type
            else:
                self.module_info.variables[var_name] = var_type

        self.generic_visit(node)

    def _get_function_signature(self, node) -> str:
        """Generate function signature string with type annotations."""
        args = []

        # Handle regular arguments
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_type = self._get_annotation_string(arg.annotation)
                arg_str += f": {arg_type}"
            args.append(arg_str)

        # Handle *args
        if node.args.vararg:
            arg_str = f"*{node.args.vararg.arg}"
            if node.args.vararg.annotation:
                arg_type = self._get_annotation_string(node.args.vararg.annotation)
                arg_str += f": {arg_type}"
            args.append(arg_str)

        # Handle **kwargs
        if node.args.kwarg:
            arg_str = f"**{node.args.kwarg.arg}"
            if node.args.kwarg.annotation:
                arg_type = self._get_annotation_string(node.args.kwarg.annotation)
                arg_str += f": {arg_type}"
            args.append(arg_str)

        # Handle keyword-only arguments
        for arg in node.args.kwonlyargs:
            arg_str = arg.arg
            if arg.annotation:
                arg_type = self._get_annotation_string(arg.annotation)
                arg_str += f": {arg_type}"
            args.append(arg_str)

        signature = f"{node.name}({', '.join(args)})"

        # Add return type annotation
        if node.returns:
            return_type = self._get_annotation_string(node.returns)
            signature += f" -> {return_type}"

        return signature

    def _get_parameter_types(self, node) -> dict[str, str]:
        """Extract parameter type annotations."""
        param_types = {}

        for arg in node.args.args:
            if arg.annotation:
                param_types[arg.arg] = self._get_annotation_string(arg.annotation)

        if node.args.vararg and node.args.vararg.annotation:
            param_types[node.args.vararg.arg] = self._get_annotation_string(
                node.args.vararg.annotation
            )

        if node.args.kwarg and node.args.kwarg.annotation:
            param_types[node.args.kwarg.arg] = self._get_annotation_string(
                node.args.kwarg.annotation
            )

        for arg in node.args.kwonlyargs:
            if arg.annotation:
                param_types[arg.arg] = self._get_annotation_string(arg.annotation)

        return param_types

    def _get_annotation_string(self, annotation) -> str:
        """Convert AST annotation to string representation."""
        if annotation is None:
            return ""

        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Attribute):
            return f"{self._get_annotation_string(annotation.value)}.{annotation.attr}"
        elif isinstance(annotation, ast.Subscript):
            # Handle generic types like List[str], Dict[str, int]
            value = self._get_annotation_string(annotation.value)
            slice_value = self._get_annotation_string(annotation.slice)
            return f"{value}[{slice_value}]"
        elif isinstance(annotation, ast.Tuple):
            # Handle tuple types like Tuple[str, int]
            elements = [self._get_annotation_string(elt) for elt in annotation.elts]
            return ", ".join(elements)
        elif isinstance(annotation, ast.Constant):
            # Handle string literals in annotations (forward references)
            return str(annotation.value)
        elif hasattr(annotation, "id"):
            return annotation.id
        else:
            return str(annotation)

    def _get_decorator_name(self, decorator) -> str:
        """Extract decorator name from AST node."""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Attribute):
            return f"{self._get_decorator_name(decorator.value)}.{decorator.attr}"
        elif isinstance(decorator, ast.Call):
            return self._get_decorator_name(decorator.func)
        else:
            return str(decorator)

    def _infer_type_from_value(self, value) -> str:
        """Infer type from AST value node."""
        if isinstance(value, ast.Constant):
            if isinstance(value.value, str):
                return "str"
            elif isinstance(value.value, int):
                return "int"
            elif isinstance(value.value, float):
                return "float"
            elif isinstance(value.value, bool):
                return "bool"
            elif value.value is None:
                return "None"
        elif isinstance(value, ast.List):
            return "list"
        elif isinstance(value, ast.Dict):
            return "dict"
        elif isinstance(value, ast.Tuple):
            return "tuple"
        elif isinstance(value, ast.Set):
            return "set"
        elif isinstance(value, ast.Name):
            return value.id
        elif isinstance(value, ast.Call):
            return self._get_annotation_string(value.func)

        return "Any"

    def _get_base_class_name(self, base) -> str:
        """Get base class name from AST node."""
        if isinstance(base, ast.Name):
            return base.id
        elif isinstance(base, ast.Attribute):
            return f"{self._get_base_class_name(base.value)}.{base.attr}"
        else:
            return str(base)


def analyze_python_project(
    project_path: Path, exclude_patterns: list[str] | None = None
) -> ProjectStructure:
    """Analyze a Python project and return its structure.

    Args:
        project_path: Path to the Python project root
        exclude_patterns: List of patterns to exclude from analysis

    Returns:
        ProjectStructure containing all analyzed information

    Raises:
        ProjectAnalysisError: If analysis fails
    """
    analyzer = PythonProjectAnalyzer(project_path)
    return analyzer.analyze_project(exclude_patterns)
