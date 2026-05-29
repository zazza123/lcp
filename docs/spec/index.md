# LCP v1 Specification

This is the normative specification for the Library Context Protocol (LCP) v1.0. It defines the format, semantics, and constraints that all conforming LCP documents MUST satisfy. For the machine-readable schema used by validators and tooling, see the companion [JSON Schema](schema.md) page.

## Overview

The **Library Context Protocol (LCP)** is a language-agnostic, machine-readable format for describing software libraries in a way that is optimized for **AI systems, tooling, and documentation generators**.

An LCP document captures:

- What a library is (metadata)
- What symbols it exposes (functions, classes, modules, etc.)
- How those symbols behave (semantics, signatures, effects, stability)
- How symbols are identified in a stable, canonical way

The primary design goal is to provide **high-fidelity context** about libraries so that LLMs, IDEs, and analysis tools can reason about APIs accurately without relying on source code parsing at runtime.

## Design principles

LCP is built around a few core principles:

- **Symbol-centric** — Everything revolves around well-defined symbols.
- **Stable identifiers** — Symbol IDs SHOULD NOT change across refactors; they form the stable public address of an API element.
- **Language-agnostic** — Works across Python, JS/TS, Java, C#, Rust, and other languages.
- **Tool-friendly** — Easy to diff, index, validate, and generate.
- **Extensible** — Vendor or ecosystem-specific data MAY be attached via `x-*` fields without violating the schema.

## Document structure

An LCP file is a single JSON document with up to four top-level keys:

```json
{
  "manifest": { ... },
  "symbols": { ... },
  "deprecations": { ... },
  "detailed_index": { ... }
}
```

Only `manifest` and `symbols` are required. `deprecations` and `detailed_index` are optional sections that extend the document with historical and traceability information.

## Manifest

The `manifest` section describes the **library as a whole**. It MUST appear in every valid LCP document.

### Required fields

```json
"manifest": {
  "schema_version": "1.0",
  "library": {
    "name": "example-lib",
    "version": "1.2.3",
    "language": "python"
  }
}
```

| Field | Description |
|---|---|
| `schema_version` | LCP schema version. MUST be `"1.0"` for documents conforming to this specification. |
| `library.name` | Canonical library name. |
| `library.version` | Semantic version string in `MAJOR.MINOR.PATCH` form. |
| `library.language` | Primary implementation language (e.g., `"python"`, `"typescript"`, `"rust"`). |

### Optional metadata

The manifest MAY also include the following fields:

| Field | Description |
|---|---|
| `runtime_language` | Runtime language if different from the implementation language (e.g., Python bindings over a C++ core). |
| `bindings` | Binding type or target ecosystem. |
| `compatibility` | Runtime or platform compatibility constraints. |
| `distribution` | Package registry identifier (`"pypi"`, `"npm"`, `"cargo"`, etc.). |
| `license` | SPDX-compatible identifier or free-text license description. |
| `changelog` | URL and format of the library changelog. |
| `generation` | Tooling metadata: generator name, version, and generation date. |

### Symbol resolution

```json
"symbol_resolution": "fully-qualified"
```

The `symbol_resolution` field controls how symbols in the document are identified. The recommended and default mode is **`fully-qualified`**, meaning every symbol key is a complete, unambiguous identifier. Producers SHOULD set this field explicitly.

## Symbols

The `symbols` object is the **core of LCP**. Each key is a Symbol ID and each value is a symbol description object.

```json
"symbols": {
  "math:sin": { ... },
  "pathlib:Path": { ... }
}
```

### Symbol kinds

Each symbol object MUST include a `kind` field. The defined kinds are:

- `module` — A package or module namespace.
- `function` — A standalone callable (free function, static function, or module-level function).
- `class` — A class or type definition.
- `method` — A callable that is a member of a class.
- `attribute` — A data member of a class or module.
- `constant` — A module-level value that is not expected to change.

### Minimal symbol shape

Only `kind` and `semantics.summary` are required in a symbol object. The smallest valid symbol is:

```json
"math:sin": {
  "kind": "function",
  "semantics": {
    "summary": "Return the sine of x (measured in radians)."
  }
}
```

All other fields (`signatures`, `stability`, `effects`, `members`, etc.) are optional.

### Symbol identification

LCP uses **stable, fully-qualified Symbol IDs** as object keys in the `symbols` map. The canonical format is:

```
<module_path>:<entity_path>
```

The `<module_path>` is the dotted import path to the module. The `<entity_path>` is the dotted path to the entity within that module. Class members use a `#` separator between the class path and the member name.

Examples:

| Symbol ID | What it identifies |
|---|---|
| `json:loads` | The `loads` function in the `json` module |
| `collections:Counter` | The `Counter` class in `collections` |
| `collections:Counter#update` | The `update` method of `Counter` |
| `System.IO:File#ReadAllText` | A member in a .NET-style namespace |

Symbol IDs MUST be stable across patch releases and SHOULD be stable across minor releases. Renaming a symbol constitutes a breaking change and SHOULD be recorded in the `deprecations` section.

### Modules as symbols

Modules are represented using an empty entity path:

```
collections:
```

This convention allows a module itself to carry a symbol entry with `"kind": "module"`, providing module-level documentation and a grouping point for its members.

### Members and nesting

Class members appear in two places: as top-level symbols (using the `#` separator) and optionally as entries in a `members` array on the parent class symbol. Nested types use the dot separator in the entity path:

- Class member: `module:Class#method`
- Nested type: `module:Outer.Inner`
- Nested member: `module:Outer.Inner#method`

Producers MAY choose to emit members only at the top level, only nested under their parent's `members` array, or both. Consumers MUST be prepared to handle all three forms.

### Overloads

Overloaded functions or methods MUST NOT use different Symbol IDs. When a callable has multiple valid call signatures (e.g., due to Python `@overload` decorators or language-level method overloading), all signatures are placed in the `signatures` array under the **same** symbol. Each entry in `signatures` describes one calling form.

## Signatures

`signatures` describes the callable forms of a function or method symbol. It is an array; a symbol with no overloads typically has exactly one entry.

```json
"signatures": [
  {
    "params": [
      { "name": "path", "type": "string", "required": true }
    ],
    "returns": "string"
  }
]
```

Each signature object MAY define:

- `when` — A string describing the condition under which this signature applies (for overloads).
- `async` — Boolean; whether the call is asynchronous.
- `params` — Ordered array of parameter objects (see below).
- `returns` — Return type as a `type_ref` (see [Types](#types)).
- `raises` — Array of exception/error objects that the callable MAY raise.

### Parameter properties

Each entry in `params` is a parameter object with the following fields:

| Property | Type | Description |
|---|---|---|
| `name` | string | Parameter name. Required. |
| `type` | type_ref | Type annotation. Required. |
| `required` | boolean | Whether the parameter is required. Defaults to `true`. |
| `default` | any | Default value when `required` is `false`. |
| `variadic` | boolean | Whether this is a variadic parameter (`*args` / rest). |
| `kind` | string | One of `positional`, `keyword`, `positional_only`, `keyword_only`, `rest`. |
| `description` | string | Human-readable parameter documentation. |

## Types

Types are represented using `type_ref`. A `type_ref` value is either a simple string or a structured object.

### Simple types

A simple type is a plain JSON string naming the type. Primitive names (`"string"`, `"int"`, `"bool"`, `"float"`, `"bytes"`, `"null"`) and named references (`"pathlib.Path"`, `"datetime.datetime"`) are all valid simple types.

```json
"returns": "string"
```

### Structured types

When a type cannot be expressed as a plain string, use an object with a `kind` discriminator:

```json
{
  "kind": "array",
  "items": "string"
}
```

The supported structured type kinds are:

- `named` — A named type reference, equivalent to a plain string but written as an object (`{ "kind": "named", "name": "Path" }`).
- `array` — An ordered, homogeneous collection. Requires `"items"` (a `type_ref`).
- `map` — A key-value mapping. Requires `"key"` and `"value"` (both `type_ref`).
- `tuple` — A fixed-length, ordered, heterogeneous sequence. Requires `"elements"` (array of `type_ref`).
- `union` — A type that can be any one of several alternatives. Requires `"types"` (array of `type_ref`).

Structured types MAY be nested arbitrarily, allowing lossless representation of complex generic type systems from any language.

## Semantics

The `semantics` object describes **what a symbol does**, independent of how it is implemented. It is required on every symbol and MUST contain at least `summary`.

```json
"semantics": {
  "summary": "Reads a file and returns its contents.",
  "description": "The file must exist and be readable.",
  "examples": [
    { "code": "read_file('a.txt')" }
  ]
}
```

- `summary` is required. It SHOULD be a single concise sentence suitable for use in autocomplete tooltips or hover documentation.
- `description` is optional but SHOULD be provided for non-trivial symbols. It MAY use Markdown.
- `examples` is optional. Each example object MUST include `"code"` and MAY include `"description"`.

### Effects

The optional `effects` object describes the observable side-effects of calling a symbol. It is intended to support AI reasoning, sandboxing decisions, and static analysis.

```json
"effects": {
  "categories": ["filesystem"],
  "idempotent": true,
  "deterministic": true
}
```

Supported effect category values:

| Category | Meaning |
|---|---|
| `io` | General I/O operations. |
| `network` | Network calls (HTTP, sockets, DNS, etc.). |
| `filesystem` | File system reads or writes. |
| `cpu` | CPU-intensive operations (significant compute). |
| `memory` | Memory-intensive operations (large allocations). |
| `gpu` | GPU operations. |

`idempotent` and `deterministic` are boolean flags. `idempotent` means calling the function multiple times with the same inputs produces the same observable result. `deterministic` means the output is fully determined by the inputs (no randomness or time-dependence).

### Stability

Symbols MAY declare a stability level to communicate API guarantees:

```json
"stability": {
  "level": "stable",
  "since": "1.0.0"
}
```

The defined levels are:

- `experimental` — The symbol MAY change or be removed without notice. Consumers SHOULD NOT depend on it in production code.
- `stable` — The symbol follows semver guarantees. Breaking changes require a major version bump.
- `deprecated` — The symbol is scheduled for removal. Consumers SHOULD migrate to the replacement indicated in the `deprecations` section.

`since` is an optional version string recording when the current stability level was assigned.

### Deprecations

A symbol with `"stability.level": "deprecated"` SHOULD have a corresponding entry in the top-level `deprecations` object:

```json
"deprecations": {
  "old.module:func": {
    "deprecated_in": "2.0.0",
    "replaced_by": "new.module:func"
  }
}
```

The `deprecations` map uses Symbol IDs as keys. Each entry records:

- `deprecated_in` — The version in which the symbol was deprecated.
- `replaced_by` — The Symbol ID of the recommended replacement (optional if there is no direct replacement).

This section allows tooling to track removals even **after** a symbol has been deleted from `symbols`, preserving migration information across library versions.

### Detailed index

The optional `detailed_index` object links Symbol IDs back to their source artifacts. This is useful for IDEs, documentation generators, and traceability tooling.

```json
"detailed_index": {
  "math:sin": {
    "implementation": {
      "path": "math.py",
      "lines": [10, 42]
    }
  }
}
```

Each entry uses the Symbol ID as the key. The `implementation` object MAY include `path` (relative file path) and `lines` (a two-element array `[start, end]` of 1-based line numbers). Additional fields such as source URLs or commit SHAs MAY be added using `x-*` extension fields.

## Extensibility

Any object in an LCP document MAY include vendor or ecosystem-specific data using keys prefixed with `x-`:

```json
"x-internal-id": "abc123"
```

Extension keys MUST begin with `x-` followed by at least one character. The core schema ignores extension fields; conforming tooling MUST preserve them when reading and re-serialising LCP documents. Extension authors SHOULD use a namespace prefix after `x-` to avoid collisions (e.g., `x-myorg-priority`).

## Summary

LCP provides a **compact, precise, and extensible** way to describe libraries at the semantic level. The two required sections — `manifest` and `symbols` — are sufficient to produce a useful document. Optional sections (`deprecations`, `detailed_index`) and optional fields within symbols (`signatures`, `effects`, `stability`, `members`) add progressively more information without breaking basic consumers. By standardising symbol identity and behaviour, LCP enables tools — and AI systems in particular — to understand APIs by intent, contract, and effect, not just syntax.
