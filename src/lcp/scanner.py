"""Scanner module for introspecting Python packages."""

from __future__ import annotations

import importlib
import importlib.metadata
import inspect
import pkgutil
import re
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
    """Scanned symbol information.

    ``aliases`` holds ``(module_path, name)`` pairs where the symbol is
    re-exported inside its own package (e.g. ``("requests", "get")`` for a
    function defined in ``requests.api``); the definition site stays the
    canonical identity.
    """

    name: str
    qualified_name: str
    module_path: str
    kind: str  # function, class, method, attribute, constant, module
    summary: str | None = None
    description: str | None = None
    docstring: str | None = None
    signature: ScannedSignature | None = None
    members: list[ScannedSymbol] = field(default_factory=list)
    source_file: str | None = None
    source_lines: tuple[int, int] | None = None
    aliases: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ScannedModule:
    """Scanned module information."""

    name: str
    version: str
    symbols: list[ScannedSymbol] = field(default_factory=list)
    unresolved_reexports: list[tuple[str, int, int]] = field(default_factory=list)


class _ComplexDefault:
    """Sentinel for a parameter default that is not a JSON primitive.

    Round-trips ``ScannedParam.default`` across the subprocess boundary: it is
    not ``inspect.Parameter.empty`` (so ``has_default`` stays ``True``) and not
    a primitive, so the generator renders it as ``"..."`` — identical to how it
    would render the original object.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<complex default>"


_COMPLEX_DEFAULT = _ComplexDefault()
_PRIMITIVE_DEFAULT_TYPES = (str, int, float, bool)


def _default_to_dict(default: Any) -> dict:
    """Encode a ``ScannedParam.default`` into a JSON-safe descriptor."""
    if default is inspect.Parameter.empty:
        return {"kind": "empty"}
    if default is None or isinstance(default, _PRIMITIVE_DEFAULT_TYPES):
        return {"kind": "primitive", "value": default}
    return {"kind": "complex"}


def _default_from_dict(d: dict) -> Any:
    """Decode the descriptor produced by :func:`_default_to_dict`."""
    kind = d.get("kind", "empty")
    if kind == "primitive":
        return d.get("value")
    if kind == "complex":
        return _COMPLEX_DEFAULT
    return inspect.Parameter.empty


def _param_to_dict(p: ScannedParam) -> dict:
    return {
        "name": p.name,
        "type_hint": p.type_hint,
        "default": _default_to_dict(p.default),
        "kind": p.kind,
        "description": p.description,
    }


def _param_from_dict(d: dict) -> ScannedParam:
    return ScannedParam(
        name=d["name"],
        type_hint=d.get("type_hint"),
        default=_default_from_dict(d.get("default", {})),
        kind=d.get("kind", "positional"),
        description=d.get("description"),
    )


def _signature_to_dict(s: ScannedSignature) -> dict:
    return {
        "params": [_param_to_dict(p) for p in s.params],
        "return_type": s.return_type,
        "is_async": s.is_async,
        "raises": list(s.raises),
    }


def _signature_from_dict(d: dict) -> ScannedSignature:
    return ScannedSignature(
        params=[_param_from_dict(p) for p in d.get("params", [])],
        return_type=d.get("return_type"),
        is_async=d.get("is_async", False),
        raises=list(d.get("raises", [])),
    )


def _symbol_to_dict(s: ScannedSymbol) -> dict:
    return {
        "name": s.name,
        "qualified_name": s.qualified_name,
        "module_path": s.module_path,
        "kind": s.kind,
        "summary": s.summary,
        "description": s.description,
        "docstring": s.docstring,
        "signature": _signature_to_dict(s.signature) if s.signature else None,
        "members": [_symbol_to_dict(m) for m in s.members],
        "source_file": s.source_file,
        "source_lines": list(s.source_lines) if s.source_lines else None,
        "aliases": [list(a) for a in s.aliases],
    }


def _symbol_from_dict(d: dict) -> ScannedSymbol:
    signature = d.get("signature")
    source_lines = d.get("source_lines")
    return ScannedSymbol(
        name=d["name"],
        qualified_name=d["qualified_name"],
        module_path=d["module_path"],
        kind=d["kind"],
        summary=d.get("summary"),
        description=d.get("description"),
        docstring=d.get("docstring"),
        signature=_signature_from_dict(signature) if signature else None,
        members=[_symbol_from_dict(m) for m in d.get("members", [])],
        source_file=d.get("source_file"),
        source_lines=tuple(source_lines) if source_lines else None,
        aliases=[tuple(a) for a in d.get("aliases", [])],
    )


def scanned_to_dict(module: ScannedModule) -> dict:
    """Serialize a :class:`ScannedModule` tree into a JSON-safe dict.

    Total by construction: complex parameter defaults degrade to a marker
    rather than raising, so the child can always emit a document.
    """
    return {
        "name": module.name,
        "version": module.version,
        "symbols": [_symbol_to_dict(s) for s in module.symbols],
        "unresolved_reexports": [
            [mod, count, module_count]
            for mod, count, module_count in module.unresolved_reexports
        ],
    }


def scanned_from_dict(d: dict) -> ScannedModule:
    """Rebuild a :class:`ScannedModule` tree from :func:`scanned_to_dict` output."""
    return ScannedModule(
        name=d["name"],
        version=d["version"],
        symbols=[_symbol_from_dict(s) for s in d.get("symbols", [])],
        unresolved_reexports=[
            (mod, count, module_count)
            for mod, count, module_count in d.get("unresolved_reexports", [])
        ],
    )


@dataclass
class _AliasRecord:
    """A re-export observed while scanning, before its target is known.

    ``scan_module`` records these when a member's ``__module__`` points at
    another module inside the same package; ``_attach_aliases`` resolves
    them onto the canonical scanned symbols once every module is scanned.
    """

    target_module: str
    target_name: str
    alias_module: str
    alias_name: str


def _attach_aliases(
    symbols: list[ScannedSymbol], records: list[_AliasRecord], target: str
) -> list[tuple[str, int, int]]:
    """Attach re-export aliases to their canonical scanned symbols.

    Records whose target was never scanned are dropped. A drop is *benign*
    when the defining module was itself scanned — the target simply is not a
    scannable kind. A drop means real lost surface when the defining module
    was never visited at all: that happens when the scan root is a facade
    re-exporting from a sibling package (see issue #58).

    A facade re-exports from a SIBLING package, which sits at the same depth
    in the module tree as the scanned package itself. So before reporting,
    each unscanned origin module OUTSIDE the scanned subtree is collapsed to
    its first ``N`` dotted segments, ``N`` being the number of segments in
    *target* — e.g. scanning ``google.cloud.firestore`` (3 segments)
    collapses the origin ``google.cloud.firestore_v1.types.write`` to
    ``google.cloud.firestore_v1``, the sibling package a user should
    actually scan, rather than reporting every defining submodule
    (including private ones such as ``google.cloud.firestore_v1._helpers``)
    as a separate line. An origin with fewer segments than *target* keeps
    its own full name — it is never padded out to *target*'s depth.

    An origin NESTED under *target* (i.e. ``origin == target`` or it starts
    with ``target + "."``) is never collapsed: truncating it to *target*'s
    depth would just return *target* itself, which is nonsensical — the
    package that was just scanned cannot also be the follow-up scan
    suggestion. This case is a submodule of the scanned package that simply
    failed to import during the walk (an optional dependency, a
    ``TYPE_CHECKING``-only import, a platform-specific module); its own full
    module path is the genuinely actionable target, so it is kept as-is.

    Collapsed diagnostics are reported back so callers can warn instead of
    silently shipping an empty manifest.

    Args:
        symbols: Every symbol scanned so far, canonical definitions included.
        records: Re-exports observed during scanning, targets unresolved.
        target: Dotted path of the package or module that was scanned (e.g.
            ``"google.cloud.firestore"``); sets the collapsing depth.

    Returns:
        ``(ancestor_module, distinct_name_count, contributing_module_count)``
        triples for ancestor modules that were never scanned.
        ``distinct_name_count`` is the number of distinct names lost across
        every origin module collapsed into that ancestor (not the number of
        re-export sites — the same name re-exported from both a package's
        ``__init__.py`` and a compat shim counts once).
        ``contributing_module_count`` is the number of distinct origin
        modules that collapsed into the ancestor. Ordered by descending
        ``distinct_name_count`` then ascending ``ancestor_module``.
    """
    by_key = {(s.module_path, s.qualified_name): s for s in symbols}
    scanned_modules = {s.module_path for s in symbols if s.kind == "module"}
    unresolved: dict[str, set[str]] = {}

    for rec in records:
        target_symbol = by_key.get((rec.target_module, rec.target_name))
        if target_symbol is None:
            if rec.target_module not in scanned_modules:
                unresolved.setdefault(rec.target_module, set()).add(rec.target_name)
            continue
        alias = (rec.alias_module, rec.alias_name)
        if alias not in target_symbol.aliases:
            target_symbol.aliases.append(alias)

    depth = len(target.split("."))
    collapsed_names: dict[str, set[str]] = {}
    collapsed_modules: dict[str, set[str]] = {}
    for mod, names in unresolved.items():
        if mod == target or mod.startswith(target + "."):
            # Descendant of the scanned subtree: a submodule that failed to
            # import, not a sibling. Truncating to `depth` would collapse it
            # onto `target` itself, so keep its own full path.
            ancestor = mod
        else:
            ancestor = ".".join(mod.split(".")[:depth])
        collapsed_names.setdefault(ancestor, set()).update(names)
        collapsed_modules.setdefault(ancestor, set()).add(mod)

    return sorted(
        (
            (ancestor, len(names), len(collapsed_modules[ancestor]))
            for ancestor, names in collapsed_names.items()
        ),
        key=lambda kv: (-kv[1], kv[0]),
    )


def _raw_docstring(doc: Any) -> str | None:
    """Return *doc* when it is a plain string docstring, else ``None``.

    Same non-string guard as ``_parse_docstring``: ``__doc__`` can be a
    descriptor (e.g. sympy) and must never be parsed or stored as-is.
    """
    return doc if isinstance(doc, str) and doc else None


def _parse_docstring(docstring: str | None) -> tuple[str | None, str | None]:
    """Parse docstring into summary and description."""
    # ``__doc__`` is not guaranteed to be a string: some classes expose it as a
    # ``property`` or other descriptor (e.g. sympy). Treat any non-string as
    # having no docstring rather than crashing on ``.strip()``.
    if not isinstance(docstring, str) or not docstring:
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


def _is_member_from_package(cls: type, name: str, package_root: str) -> bool:
    """Check if a class member belongs to the scanned package.

    A member belongs to the package if it is defined directly on the class
    (present in cls.__dict__) or if the base class that defines it has a
    __module__ within the package root.
    """
    if name in cls.__dict__:
        return True

    for base in cls.__mro__:
        if name in base.__dict__:
            base_module = getattr(base, "__module__", None)
            # ``__module__`` is usually a str but C-level slots can expose it as
            # a ``member_descriptor`` (e.g. zope.interface); anything non-string
            # cannot be within the package root.
            if not isinstance(base_module, str):
                return False
            return base_module == package_root or base_module.startswith(
                package_root + "."
            )

    return False


def _safe_getmembers(obj: Any) -> list[tuple[str, Any]]:
    """Like ``inspect.getmembers`` but skips members whose access raises.

    Some packages expose lazily-resolved attributes (PEP 562 module
    ``__getattr__`` / metaclass ``__getattr__``) that raise — e.g.
    ``ModuleNotFoundError`` for a moved or removed submodule. Plain
    ``inspect.getmembers`` propagates such errors and aborts the whole scan;
    here we skip the offending member and keep going.
    """
    results: list[tuple[str, Any]] = []
    for name in dir(obj):
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        results.append((name, value))
    results.sort(key=lambda item: item[0])
    return results


def _scan_class(
    cls: type,
    module_path: str,
    include_private: bool = False,
    package_root: str | None = None,
) -> ScannedSymbol:
    """Scan a class and its members."""
    if package_root is None:
        package_root = module_path.split(".")[0]

    summary, description = _parse_docstring(cls.__doc__)
    source_file, source_lines = _get_source_info(cls)

    # Scan __init__ signature as the class signature
    init_sig = None
    if hasattr(cls, "__init__"):
        init_sig = _scan_signature(cls.__init__)

    members: list[ScannedSymbol] = []

    # Scan methods and attributes
    for name, obj in _safe_getmembers(cls):
        if not _is_public(name, include_private):
            continue

        # Skip members inherited from outside the scanned package
        if not _is_member_from_package(cls, name, package_root):
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
                    docstring=_raw_docstring(getattr(obj, "__doc__", None)),
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
                    docstring=_raw_docstring(obj.fget.__doc__ if obj.fget else None),
                )
            )

    return ScannedSymbol(
        name=cls.__name__,
        qualified_name=cls.__name__,
        module_path=module_path,
        kind="class",
        summary=summary,
        description=description,
        docstring=_raw_docstring(cls.__doc__),
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
        docstring=_raw_docstring(func.__doc__),
        signature=sig,
        source_file=source_file,
        source_lines=source_lines,
    )


_PRIMITIVE_TYPES = (int, float, str, bytes, bool, type(None), tuple, frozenset)


def _is_primitive(value: Any) -> bool:
    """Whether *value* is a primitive, without trusting the object.

    ``isinstance`` is not safe here. When its fast ``type()`` check misses it
    falls back to reading ``value.__class__``, and that read goes through a
    hostile ``__getattribute__``: an ``AttributeError`` is swallowed, but a
    proxy raising anything else propagates out of what reads like a pure
    predicate. The identity check settles the common case without touching
    the object at all; the guarded fallback preserves subclass semantics,
    which a bare ``type(value) in`` check would lose.

    A proxy like ``flask.request`` never actually reaches this function
    through ``scan_module``: the member loop's own
    ``getattr(obj, "__module__", None)`` raises first and the member is
    dropped before classification is attempted. Reaching this guarded
    fallback at all is only possible for objects that survive that earlier
    step; it remains as defence-in-depth for callers that classify a value
    directly (as some tests do) or for a future member-loop shape that
    reaches classification sooner.

    Args:
        value: The object to classify.

    Returns:
        ``True`` when *value* is one of the primitive types.
    """
    if type(value) in _PRIMITIVE_TYPES:
        return True
    try:
        return isinstance(value, _PRIMITIVE_TYPES)
    except Exception:
        return False


def _is_constant(name: str, value: Any) -> bool:
    """Decide whether *value* should be recorded as a public constant.

    Three cases, in order:

    * a primitive value is admitted only under an ``UPPER_CASE`` name — the
      historical rule, unchanged;
    * a callable under a non-``UPPER_CASE`` name is rejected;
    * anything else is admitted when its *type* is defined outside the
      standard library.

    That asymmetry on case is what keeps C-implemented functions out.
    Libraries written partly in C ship their functions as instances of a
    library-defined callable type — ``numpy.add`` is a ``ufunc``,
    ``numpy.mean`` an ``_ArrayFunctionDispatcher`` — and those are
    structurally indistinguishable from a legitimate value object such as
    ``click.INT``: ``inspect.isroutine``, the descriptor protocol,
    ``__code__`` and ``__wrapped__`` all fail to separate them. Python's
    naming convention separates what structure cannot. Scanning those
    functions properly is issue #63.

    Only ``type(value)`` is consulted, never the instance's own attributes.
    Attribute access on the value itself is unsafe: a proxy forwards it and
    can raise (``flask.request`` raises ``RuntimeError`` outside a request
    context). Primitive detection goes through ``_is_primitive`` rather than
    a bare ``isinstance`` call for the same reason.

    Args:
        name: Attribute name the object is bound to in its module.
        value: The object bound to that name.

    Returns:
        ``True`` when the symbol should be recorded as a constant.
    """
    if _is_primitive(value):
        return name.isupper()
    if callable(value) and not name.isupper():
        return False
    top_level = str(type(value).__module__ or "").split(".")[0]
    return top_level not in sys.stdlib_module_names


def _normalize_dist(name: str) -> str:
    """Normalise a distribution or top-level name for comparison.

    Collapses runs of ``-``, ``_`` and ``.`` to a single ``-`` and lowercases,
    so ``Fake_Dep.Name`` and ``fake-dep-name`` compare equal (PEP 503-style).

    Args:
        name: A distribution or import name.

    Returns:
        The normalised form.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _followable_top_levels(package_root: str) -> frozenset[str]:
    """Top-level import names provided by ``package_root``'s declared deps.

    Resolves ``package_root`` to its distribution(s), reads their declared
    dependencies, and returns the set of top-level import names those
    dependency distributions provide. A foreign re-export whose origin
    top-level is in this set comes from a declared dependency and may be
    followed (facade support, #67). Any failure yields an empty set, which
    disables following rather than raising.

    Args:
        package_root: First dotted segment of the scanned package's import path.

    Returns:
        The followable top-level import names, or an empty set.
    """
    try:
        pkg_dists = importlib.metadata.packages_distributions()
    except Exception:
        return frozenset()
    dists = pkg_dists.get(package_root, [])
    if not dists:
        return frozenset()
    declared: set[str] = set()
    for dist in dists:
        try:
            reqs = importlib.metadata.requires(dist) or []
        except Exception:
            reqs = []
        for req in reqs:
            dep = re.split(r"[ ;<>=!~\[\(]", req.strip())[0]
            if dep:
                declared.add(_normalize_dist(dep))
    if not declared:
        return frozenset()
    return frozenset(
        top
        for top, tops_dists in pkg_dists.items()
        if any(_normalize_dist(d) in declared for d in tops_dists)
    )


def _is_followable_reexport(
    obj_module: str, followable_tops: frozenset[str] | None
) -> bool:
    """Whether a foreign re-export defined in ``obj_module`` should be followed.

    Args:
        obj_module: The ``__module__`` of the re-exported object.
        followable_tops: Top-levels provided by declared deps, or ``None`` when
            the feature is inert.

    Returns:
        ``True`` when the origin is a declared, non-stdlib dependency.
    """
    if not followable_tops:
        return False
    top = obj_module.split(".")[0]
    if top in sys.stdlib_module_names:
        return False
    return top in followable_tops


def _reexport_kind(name: str, obj: Any) -> str:
    """Classify a followed foreign re-export.

    Returns ``"class"``, ``"function"``, ``"value"`` or ``"defer"``. ``"defer"``
    marks a callable with a recoverable signature — it looks like a
    C-implemented function and is left for #63 rather than mislabelled a
    constant here. A callable whose ``signature()`` raises (e.g. a proxy read
    outside its context) is a value object, not a function.

    Args:
        name: Attribute name the object is bound to at the facade.
        obj: The re-exported object.

    Returns:
        The classification tag.
    """
    if inspect.isclass(obj):
        return "class"
    if inspect.isfunction(obj):
        return "function"
    if _is_constant(name, obj):
        return "value"
    try:
        inspect.signature(obj)
    except Exception:
        return "value"
    return "defer"


def _capture_reexport(
    name: str, obj: Any, module_path: str, include_private: bool
) -> ScannedSymbol | None:
    """Capture a followed foreign re-export as a symbol at ``module_path``.

    A re-exported class is scanned with its *origin* top-level as the package
    root, so its own methods are kept rather than filtered out by the facade's
    root. A deferred callable (see :func:`_reexport_kind`) yields ``None``.

    Args:
        name: Attribute name at the facade.
        obj: The re-exported object.
        module_path: The facade module the symbol is attributed to.
        include_private: Whether to include private members (classes).

    Returns:
        The captured symbol, or ``None`` when deferred to #63.
    """
    kind = _reexport_kind(name, obj)
    if kind == "class":
        origin_root = str(getattr(obj, "__module__", "") or "").split(".")[0]
        return _scan_class(obj, module_path, include_private, package_root=origin_root)
    if kind == "function":
        return _scan_function(obj, module_path, name)
    if kind == "value":
        return ScannedSymbol(
            name=name,
            qualified_name=name,
            module_path=module_path,
            kind="constant",
            summary=_constant_summary(obj),
        )
    return None


_MAX_CONSTANT_REPR = 60


def _constant_summary(value: Any) -> str:
    """Build the summary line for a constant symbol.

    Primitives carry their value; everything else carries only its type name.
    The value is deliberately withheld for non-primitives: ``__repr__`` on an
    arbitrary object can be enormous, expensive, or raise. Primitive
    detection goes through ``_is_primitive`` rather than a bare
    ``isinstance`` call, which is not safe on a hostile object.

    Two of the primitive types, ``tuple`` and ``frozenset``, are containers
    that can hold arbitrary objects, and ``str``/``bytes`` can be subclassed
    with an overridden ``__repr__``. So even a primitive's own ``repr()``
    call is not guaranteed safe: if it raises, the summary degrades to the
    type-only form rather than letting the exception escape (which would
    otherwise drop the whole symbol from the scan).

    Args:
        value: The object bound to the constant's name.

    Returns:
        e.g. ``"int constant: 100"`` or ``"Sentinel constant."``.
    """
    type_name = type(value).__name__
    if not _is_primitive(value):
        return f"{type_name} constant."
    try:
        rendered = repr(value)
    except Exception:
        return f"{type_name} constant."
    if len(rendered) > _MAX_CONSTANT_REPR:
        rendered = rendered[:_MAX_CONSTANT_REPR] + "…"
    return f"{type_name} constant: {rendered}"


def scan_module(
    module: ModuleType,
    include_private: bool = False,
    _visited: set | None = None,
    _package_root: str | None = None,
    _alias_records: list[_AliasRecord] | None = None,
    _followable_tops: frozenset[str] | None = None,
) -> list[ScannedSymbol]:
    """Scan a module for symbols."""
    if _visited is None:
        _visited = set()

    records = _alias_records if _alias_records is not None else []

    if _package_root is None:
        _package_root = module.__name__.split(".")[0]

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
            docstring=_raw_docstring(module.__doc__),
        )
    )

    # Get all public names
    if hasattr(module, "__all__"):
        public_names = set(module.__all__)
    else:
        public_names = None

    for name, obj in _safe_getmembers(module):
        # Skip private symbols
        if not _is_public(name, include_private):
            continue

        # If __all__ is defined, respect it
        if public_names is not None and name not in public_names:
            continue

        try:
            # Classifying/scanning a member can raise even though fetching it
            # did not: objects with hostile ``__getattribute__`` or lazy setup
            # (e.g. ``django.conf.settings`` raising ``ImproperlyConfigured`` on
            # an ``isinstance`` check) blow up here. Skip the member instead of
            # aborting the whole scan.

            # Skip imported modules (they belong to their own package)
            if inspect.ismodule(obj):
                continue

            # Check if this symbol is defined in this module
            obj_module = getattr(obj, "__module__", None)
            if obj_module and obj_module != module_path:
                # Re-exported symbol, documented at its definition site.
                if isinstance(obj_module, str):
                    if obj_module == _package_root or obj_module.startswith(
                        _package_root + "."
                    ):
                        # In-package origin: record the re-export as an alias
                        # on the canonical symbol.
                        target_name = getattr(obj, "__name__", None)
                        if isinstance(target_name, str):
                            records.append(
                                _AliasRecord(
                                    target_module=obj_module,
                                    target_name=target_name,
                                    alias_module=module_path,
                                    alias_name=name,
                                )
                            )
                    elif _is_followable_reexport(obj_module, _followable_tops):
                        # Foreign origin in a declared dependency: capture the
                        # object at the facade (#67). The foreign package is
                        # not scanned.
                        captured = _capture_reexport(
                            name, obj, module_path, include_private
                        )
                        if captured is not None:
                            symbols.append(captured)
                continue

            if inspect.isclass(obj):
                symbols.append(
                    _scan_class(
                        obj, module_path, include_private, package_root=_package_root
                    )
                )
            elif inspect.isfunction(obj):
                symbols.append(_scan_function(obj, module_path, name))
            elif _is_constant(name, obj):
                symbols.append(
                    ScannedSymbol(
                        name=name,
                        qualified_name=name,
                        module_path=module_path,
                        kind="constant",
                        summary=_constant_summary(obj),
                    )
                )
        except KeyboardInterrupt:
            raise
        except Exception:
            continue

    if _alias_records is None:
        _attach_aliases(symbols, records, module_path)

    return symbols


def _get_package_version(package_name: str) -> str:
    """Get the version of an installed package."""
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def _iter_submodules(
    package: ModuleType, include_tests: bool = False
) -> list[ModuleType]:
    """Iterate over all submodules of a package, including namespace packages.

    Args:
        package: The imported package to walk.
        include_tests: When ``False`` (default), subpackages whose leaf name is
            exactly ``tests`` are skipped — they are not public API and pollute
            manifests. Public utilities like ``numpy.testing`` (leaf
            ``testing``) are always included.
    """
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
            leaf = module_info.name.rpartition(".")[2]
            # ``__main__`` modules are entry-point scripts, never public API,
            # and importing them runs arbitrary CLI code (often ``sys.exit()``).
            if leaf == "__main__":
                continue
            # Test subpackages are not public API and pollute manifests; their
            # modules also frequently call ``pytest.importorskip`` at import,
            # raising ``Skipped`` (a ``BaseException``). Skip before importing.
            if not include_tests and leaf == "tests":
                continue
            try:
                submod = importlib.import_module(module_info.name)
            except KeyboardInterrupt:
                raise
            except SystemExit:
                # Skip modules that terminate at import time (for example CLI-style
                # modules that call ``sys.exit()``).
                continue
            except BaseException:
                # Skip modules that fail to import with any exception, including
                # ``BaseException`` subclasses such as ``pytest.Skipped`` raised
                # by ``importorskip`` in test modules.
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
                    or (not include_tests and child.name == "tests")
                ):
                    continue

                module_name = f"{current_name}.{child.name}"
                if module_name in discovered:
                    continue

                try:
                    namespace_mod = importlib.import_module(module_name)
                except KeyboardInterrupt:
                    raise
                except SystemExit:
                    continue
                except BaseException:
                    continue

                discovered.add(namespace_mod.__name__)
                submodules.append(namespace_mod)
                if hasattr(namespace_mod, "__path__"):
                    pending_packages.append(namespace_mod)

    return submodules


def scan_package(
    package_name: str,
    include_private: bool = False,
    recursive: bool = True,
    include_tests: bool = False,
) -> ScannedModule:
    """Scan an installed package and return scanned information.

    Args:
        package_name: Import path of the package to scan.
        include_private: Include private symbols (names starting with ``_``).
        recursive: Walk submodules recursively.
        include_tests: When ``False`` (default), skip ``*.tests`` subpackages —
            they are not public API and pollute manifests. Public utilities like
            ``numpy.testing`` are always included.
    """
    try:
        module = importlib.import_module(package_name)
    except ImportError as e:
        raise ImportError(f"Cannot import package '{package_name}': {e}") from e

    version = _get_package_version(package_name)
    visited: set = set()
    package_root = package_name.split(".")[0]
    followable_tops = _followable_top_levels(package_root)
    alias_records: list[_AliasRecord] = []

    # Scan main module
    symbols = scan_module(
        module,
        include_private,
        visited,
        _package_root=package_root,
        _alias_records=alias_records,
        _followable_tops=followable_tops,
    )

    # Scan submodules if it's a package
    if recursive and hasattr(module, "__path__"):
        for submod in _iter_submodules(module, include_tests=include_tests):
            symbols.extend(
                scan_module(
                    submod,
                    include_private,
                    visited,
                    _package_root=package_root,
                    _alias_records=alias_records,
                    # Facade capture is scoped to the entry module: a package's
                    # public re-export surface is the module the user scans, not
                    # its internal submodules. See #67.
                    _followable_tops=None,
                )
            )

    unresolved = _attach_aliases(symbols, alias_records, package_name)
    return ScannedModule(
        name=package_name,
        version=version,
        symbols=symbols,
        unresolved_reexports=unresolved,
    )
