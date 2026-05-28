# Introduction

The **Library Context Protocol (LCP)** is a machine-readable format for describing software libraries: their public symbols, signatures, types, and semantics — designed to be consumed by AI systems, IDEs, and documentation generators.

AI code assistants are trained on large datasets, but libraries evolve constantly. New versions ship, APIs change, and functions get deprecated. Without accurate, up-to-date context, AI assistants are left guessing from training data — leading to fabricated method names, wrong parameter names, and suggestions that worked in an older version but break at runtime. LCP addresses this by providing a structured, version-specific description of a library's public API that tools can consume directly, rather than inferring from source code or stale training snapshots.

## What does an LCP fragment look like?

```json
{
  "id": "json:loads",
  "kind": "function",
  "module": "json",
  "signature": "loads(s, *, cls=None, object_hook=None) -> Any",
  "summary": "Deserialize a JSON document to a Python object.",
  "stability": "stable"
}
```

A full manifest contains many such symbols, plus module-level metadata. See [Examples](spec/examples.md) for more.

## Who benefits from LCP?

### AI code assistants

AI assistants can use an LCP manifest as ground truth about what a library actually exports. Instead of guessing from training data, the model receives exact function signatures, parameter names, types, and behavioral notes for the specific version installed in the user's environment. This eliminates a class of runtime errors caused by invented methods, renamed parameters, or deprecated call patterns.

### Documentation generators

Documentation tools can consume an LCP manifest as a single authoritative source of record for a library's public API. Because LCP captures not just signatures but also summaries and stability markers, a generator can produce human-readable docs without re-parsing source files or maintaining a separate extraction pipeline per language.

### IDEs and language tooling

An IDE plugin can load an LCP manifest to provide autocomplete, inline documentation, and deprecation warnings for any library, regardless of whether type stubs or source code are available locally. Because the format is language-agnostic JSON, the same manifest can serve tooling written in any language.

## LCP vs. alternatives

Several existing approaches give AI systems and tools some information about library APIs, but each has gaps that LCP is designed to fill.

**Training data** is the default for LLMs: the model has seen API usage in its training corpus. This is not reliable for version-specific accuracy — the model may know `requests.get` but not which keyword arguments are valid in the version the user has installed — and it cannot be updated without retraining.

**Source parsing and AST analysis** can extract accurate signatures, but the output is not portable. Each consuming tool must implement its own parser, the result is typically language-specific, and semantic information (summaries, deprecation notices, stability) is not captured unless docstrings happen to follow a parseable format.

**Type stubs** (`.pyi` files) provide accurate signatures and are versioned, but they carry no semantic content — no summaries, no deprecation text, no examples. They are also not designed for consumption by LLMs directly.

| Approach | Accurate | Portable | Semantic | Versioned |
|---|:---:|:---:|:---:|:---:|
| **LCP** | yes | yes | yes | yes |
| Training data | no | yes | partial | no |
| Source parsing | yes | no | no | yes |
| Type stubs | yes | no | no | yes |
| Inline docs | yes | no | yes | partial |

## Next steps

- [Quickstart](quickstart.md) — generate your first LCP manifest.
- [LCP v1 spec](spec/index.md) — the full specification.
- [MCP server](guides/mcp-server.md) — expose an LCP manifest to AI agents.
