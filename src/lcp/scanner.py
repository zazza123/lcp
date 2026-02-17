"""Scanner module for introspecting Python packages."""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import inspect
import pkgutil
import sys
import typing
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, get_type_hints


@dataclass
class ScannedParam:
    """Scanned parameter information."""

    name: str
    type_hint: str | None = None
    default: Any = inspect.Parameter.empty
    kind: str = "positional"
    description: str | None = None

    @property
    def has_default(self) -> bool:
        return self.default is not inspect.Parameter.empty

    @property
    def is_variadic(self) -> bool:
        return self.kind in ("rest", "keyword_rest")


@dataclass
class ScannedSignature:
    """Scanned function/method signature."""

    params: list[ScannedParam] = field(default_factory=list)
    return_type: str | None = None
    is_async: bool = False
    raises: list[str] = field(default_factory=list)


@dataclass
class ScannedSymbol:
    """Scanned symbol information."""

    name: str
    qualified_name: str
    module_path: str
    kind: str  # function, class, method, attribute, constant, module
    summary: str | None = None
    description: str | None = None
    signature: ScannedSignature | None = None
    members: list[ScannedSymbol] = field(default_factory=list)
    source_file: str | None = None
    source_lines: tuple[int, int] | None = None


@dataclass
class ScannedModule:
    """Scanned module information."""

    name: str
    version: str
    symbols: list[ScannedSymbol] = field(default_factory=list)
    submodules: list[ScannedModule] = field(default_factory=list)


def _parse_docstring(docstring: str | None) -> tuple[str | None, str | None]:
    """Parse docstring into summary and description."""
    if not docstring:
        return None, None

    lines = docstring.strip().split("\n")
    if not lines:
        return None, None

    # First paragraph is summary
    summary_lines = []
    description_lines = []
    in_summary = True

    for line in lines:
        stripped = line.strip()
        if in_summary:
            if stripped == "":
                in_summary = False
            else:
                summary_lines.append(stripped)
        else:
            description_lines.append(line)

    summary = " ".join(summary_lines) if summary_lines else None
    description = "\n".join(description_lines).strip() if description_lines else None

    return summary, description if description else None


def _type_to_string(type_hint: Any) -> str | None:
    """Convert a type hint to a string representation."""
    if type_hint is None or type_hint is inspect.Parameter.empty:
        return None

    if type_hint is type(None):
        return "None"

    if isinstance(type_hint, str):
        return type_hint

    # Handle typing module types
    origin = typing.get_origin(type_hint)
    args = typing.get_args(type_hint)

    if origin is not None:
        origin_name = getattr(origin, "__name__", str(origin))
        if origin_name == "Union":
            # Check for Optional (Union with None)
            if len(args) == 2 and type(None) in args:
                other = [a for a in args if a is not type(None)][0]
                return f"Optional[{_type_to_string(other)}]"
            return f"Union[{', '.join(_type_to_string(a) or 'Any' for a in args)}]"
        if args:
            args_str = ", ".join(_type_to_string(a) or "Any" for a in args)
            return f"{origin_name}[{args_str}]"
        return origin_name

    if hasattr(type_hint, "__name__"):
        return type_hint.__name__

    return str(type_hint)


def _get_param_kind(param: inspect.Parameter) -> str:
    """Convert inspect parameter kind to LCP kind."""
    kind_map = {
        inspect.Parameter.POSITIONAL_ONLY: "positional_only",
        inspect.Parameter.POSITIONAL_OR_KEYWORD: "positional",
        inspect.Parameter.VAR_POSITIONAL: "rest",
        inspect.Parameter.KEYWORD_ONLY: "keyword_only",
        inspect.Parameter.VAR_KEYWORD: "rest",
    }
    return kind_map.get(param.kind, "positional")


def _scan_signature(obj: Any) -> ScannedSignature | None:
    """Scan a callable's signature."""
    try:
        sig = inspect.signature(obj)
    except (ValueError, TypeError):
        return None

    # Try to get type hints
    try:
        hints = get_type_hints(obj)
    except Exception:
        hints = {}

    params = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue

        type_hint = hints.get(name, param.annotation)
        params.append(
            ScannedParam(
                name=name,
                type_hint=_type_to_string(type_hint)
                if type_hint is not inspect.Parameter.empty
                else None,
                default=param.default,
                kind=_get_param_kind(param),
            )
        )

    return_hint = hints.get("return", sig.return_annotation)
    return_type = (
        _type_to_string(return_hint)
        if return_hint is not inspect.Parameter.empty
        else None
    )

    is_async = inspect.iscoroutinefunction(obj) or inspect.isasyncgenfunction(obj)

    return ScannedSignature(params=params, return_type=return_type, is_async=is_async)


def _is_public(name: str, include_private: bool = False) -> bool:
    """Check if a name is public."""
    if include_private:
        return True
    # Allow specific dunder methods that are part of public API
    public_dunders = {
        "__init__",
        "__call__",
        "__iter__",
        "__next__",
        "__enter__",
        "__exit__",
        "__getitem__",
        "__setitem__",
        "__delitem__",
        "__len__",
        "__contains__",
        "__str__",
        "__repr__",
        "__eq__",
        "__hash__",
        "__bool__",
        "__add__",
        "__sub__",
        "__mul__",
        "__truediv__",
        "__floordiv__",
        "__mod__",
        "__pow__",
        "__and__",
        "__or__",
        "__xor__",
        "__lt__",
        "__le__",
        "__gt__",
        "__ge__",
        "__ne__",
    }
    if name in public_dunders:
        return True
    return not name.startswith("_")


def _get_source_info(obj: Any) -> tuple[str | None, tuple[int, int] | None]:
    """Get source file and line numbers for an object."""
    try:
        source_file = inspect.getfile(obj)
        source_lines = inspect.getsourcelines(obj)
        start_line = source_lines[1]
        end_line = start_line + len(source_lines[0]) - 1
        return source_file, (start_line, end_line)
    except (TypeError, OSError):
        return None, None


def _scan_class(
    cls: type, module_path: str, include_private: bool = False
) -> ScannedSymbol:
    """Scan a class and its members."""
    summary, description = _parse_docstring(cls.__doc__)
    source_file, source_lines = _get_source_info(cls)

    # Scan __init__ signature as the class signature
    init_sig = None
    if hasattr(cls, "__init__"):
        init_sig = _scan_signature(cls.__init__)

    members: list[ScannedSymbol] = []

    # Scan methods and attributes
    for name, obj in inspect.getmembers(cls):
        if not _is_public(name, include_private):
            continue

        # Skip inherited members from object/type
        if name in dir(object) or name in dir(type):
            if name not in cls.__dict__:
                continue

        member_summary, member_desc = _parse_docstring(getattr(obj, "__doc__", None))

        if inspect.isfunction(obj) or inspect.ismethod(obj):
            sig = _scan_signature(obj)
            members.append(
                ScannedSymbol(
                    name=name,
                    qualified_name=f"{cls.__name__}#{name}",
                    module_path=module_path,
                    kind="method",
                    summary=member_summary,
                    description=member_desc,
                    signature=sig,
                )
            )
        elif isinstance(obj, property):
            prop_summary, prop_desc = _parse_docstring(obj.fget.__doc__ if obj.fget else None)
            members.append(
                ScannedSymbol(
                    name=name,
                    qualified_name=f"{cls.__name__}#{name}",
                    module_path=module_path,
                    kind="attribute",
                    summary=prop_summary,
                    description=prop_desc,
                )
            )

    return ScannedSymbol(
        name=cls.__name__,
        qualified_name=cls.__name__,
        module_path=module_path,
        kind="class",
        summary=summary,
        description=description,
        signature=init_sig,
        members=members,
        source_file=source_file,
        source_lines=source_lines,
    )


def _scan_function(
    func: Any, module_path: str, name: str | None = None
) -> ScannedSymbol:
    """Scan a function."""
    func_name = name or func.__name__
    summary, description = _parse_docstring(func.__doc__)
    sig = _scan_signature(func)
    source_file, source_lines = _get_source_info(func)

    return ScannedSymbol(
        name=func_name,
        qualified_name=func_name,
        module_path=module_path,
        kind="function",
        summary=summary,
        description=description,
        signature=sig,
        source_file=source_file,
        source_lines=source_lines,
    )


def _is_constant(name: str, value: Any) -> bool:
    """Check if a value looks like a constant."""
    # Constants are typically UPPER_CASE
    if not name.isupper():
        return False
    # Must be a simple type
    return isinstance(value, (int, float, str, bytes, bool, type(None), tuple, frozenset))


def scan_module(
    module: ModuleType, include_private: bool = False, _visited: set | None = None
) -> list[ScannedSymbol]:
    """Scan a module for symbols."""
    if _visited is None:
        _visited = set()

    module_id = id(module)
    if module_id in _visited:
        return []
    _visited.add(module_id)

    module_path = module.__name__
    symbols: list[ScannedSymbol] = []

    # Add module as a symbol
    mod_summary, mod_desc = _parse_docstring(module.__doc__)
    symbols.append(
        ScannedSymbol(
            name=module_path,
            qualified_name="",  # Empty entity path for modules
            module_path=module_path,
            kind="module",
            summary=mod_summary or f"Module {module_path}",
            description=mod_desc,
        )
    )

    # Get all public names
    if hasattr(module, "__all__"):
        public_names = set(module.__all__)
    else:
        public_names = None

    for name, obj in inspect.getmembers(module):
        # Skip private symbols
        if not _is_public(name, include_private):
            continue

        # If __all__ is defined, respect it
        if public_names is not None and name not in public_names:
            continue

        # Skip imported modules (they belong to their own package)
        if inspect.ismodule(obj):
            continue

        # Check if this symbol is defined in this module
        obj_module = getattr(obj, "__module__", None)
        if obj_module and obj_module != module_path:
            # Skip re-exported symbols (they're documented in their origin module)
            continue

        if inspect.isclass(obj):
            symbols.append(_scan_class(obj, module_path, include_private))
        elif inspect.isfunction(obj):
            symbols.append(_scan_function(obj, module_path, name))
        elif _is_constant(name, obj):
            symbols.append(
                ScannedSymbol(
                    name=name,
                    qualified_name=name,
                    module_path=module_path,
                    kind="constant",
                    summary=f"Constant {name}",
                )
            )

    return symbols


def _get_package_version(package_name: str) -> str:
    """Get the version of an installed package."""
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def _iter_submodules(package: ModuleType) -> list[ModuleType]:
    """Iterate over all submodules of a package, including namespace packages."""
    if not hasattr(package, "__path__"):
        return []

    submodules: list[ModuleType] = []
    discovered: set[str] = set()
    pending_packages: list[ModuleType] = [package]
    visited_packages: set[str] = set()

    while pending_packages:
        current = pending_packages.pop()
        current_name = current.__name__
        if current_name in visited_packages or not hasattr(current, "__path__"):
            continue
        visited_packages.add(current_name)

        for module_info in pkgutil.iter_modules(
            current.__path__, prefix=current_name + "."
        ):
            try:
                submod = importlib.import_module(module_info.name)
            except Exception:
                # Skip modules that fail to import
                continue

            if submod.__name__ in discovered:
                continue

            discovered.add(submod.__name__)
            submodules.append(submod)
            if hasattr(submod, "__path__"):
                pending_packages.append(submod)

        # Discover namespace package directories not exposed by pkgutil.iter_modules.
        for path_str in current.__path__:
            package_path = Path(path_str)
            if not package_path.is_dir():
                continue

            for child in package_path.iterdir():
                if (
                    not child.is_dir()
                    or child.name == "__pycache__"
                    or not child.name.isidentifier()
                    or (child / "__init__.py").exists()
                ):
                    continue

                module_name = f"{current_name}.{child.name}"
                if module_name in discovered:
                    continue

                try:
                    namespace_mod = importlib.import_module(module_name)
                except Exception:
                    continue

                discovered.add(namespace_mod.__name__)
                submodules.append(namespace_mod)
                if hasattr(namespace_mod, "__path__"):
                    pending_packages.append(namespace_mod)

    return submodules


def scan_package(
    package_name: str, include_private: bool = False, recursive: bool = True
) -> ScannedModule:
    """Scan an installed package and return scanned information."""
    try:
        module = importlib.import_module(package_name)
    except ImportError as e:
        raise ImportError(f"Cannot import package '{package_name}': {e}") from e

    version = _get_package_version(package_name)
    visited: set = set()

    # Scan main module
    symbols = scan_module(module, include_private, visited)

    # Scan submodules if it's a package
    if recursive and hasattr(module, "__path__"):
        for submod in _iter_submodules(module):
            symbols.extend(scan_module(submod, include_private, visited))

    return ScannedModule(name=package_name, version=version, symbols=symbols)
