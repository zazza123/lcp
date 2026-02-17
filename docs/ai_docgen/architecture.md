# AI DocGen - Architecture

## Overview

The AI DocGen module uses a hierarchical bottom-up approach to generate missing docstrings. Instead of processing symbols in isolation, it builds a three-level hierarchy (methods, classes, modules) and generates documentation from the bottom up, passing context from lower levels to higher ones.

## Processing Pipeline

```
Coverage JSON (flat list of undocumented symbols)
        │
        ▼
┌──────────────────┐
│ Hierarchy Builder │  Groups by module, builds parent-child trees,
│                   │  assigns levels (0=leaf, 1=class, 2=module)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Level 0: Leaves  │  Functions and methods
│ asyncio.gather() │  Context: source code of the symbol (max 50 lines)
└────────┬─────────┘
         │ barrier + failure propagation
         ▼
┌──────────────────┐
│ Level 1: Classes │  Context: class signature + __init__ + full
│ asyncio.gather() │  docstrings of child methods
└────────┬─────────┘
         │ barrier + failure propagation
         ▼
┌──────────────────┐
│ Level 2: Modules │  Context: top 30 lines of file + summary lines
│ asyncio.gather() │  of child classes/functions
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Batch Writer    │  Groups by file, injects docstrings bottom-up
│                  │  via AST to avoid line offset issues
└──────────────────┘
```

Each level is processed fully before the next begins. This ensures that when generating a class docstring, all method docstrings are already available as context.

## Hierarchy Builder

`build_hierarchy()` in `src/lcp/ai/hierarchy.py` transforms the flat list of undocumented symbols from the coverage report into a dict of `ModuleTree` objects, one per module.

The builder groups symbols by module, identifies parent-child relationships using the `#` separator in entity names (e.g., `MyClass#method`), and assigns each symbol a level:

| Kind | Level | Role |
|------|-------|------|
| function | 0 | Leaf - processed first |
| method | 0 | Leaf - processed first |
| class | 1 | Parent of methods - processed after leaves |
| module | 2 | Root - processed last |

When a method references a class that is already documented (not in the undocumented list), the builder creates a placeholder `SymbolNode` with `status="skipped"`. This preserves the tree structure without re-generating existing documentation.

Each `ModuleTree` contains a `levels` dict that pre-groups nodes by level, so the processing engine can iterate directly without tree traversal.

## Context Strategy

The context builder `build_context()` in `src/lcp/ai/hierarchy.py` assembles different context depending on the symbol's level.

**Level 0 (functions/methods):** The raw source code of the symbol, capped at 50 lines.

**Level 1 (classes):** A composite view including:
- The class signature and decorators
- Class-level attribute annotations and assignments
- The `__init__` method source (up to 30 lines)
- For each child method: its full docstring if available (generated at Level 0 or pre-existing), or just its signature if generation failed

**Level 2 (modules):** A high-level overview including:
- The first 30 lines of the file (imports, constants)
- For each child class/function: only the summary line (first line) of its docstring, or just its signature if unavailable

This adaptive strategy gives the LLM progressively more summarized context at higher levels, keeping token usage efficient while providing enough information to write accurate documentation.

Pre-existing docstrings (symbols not in the undocumented list) are included in the context only when they are direct children of the node being documented.

## Async Processing Engine

`DocGenAgent` in `src/lcp/ai/agent.py` orchestrates the hierarchical processing.

The entry point `run_sync()` calls `asyncio.run()` on the async engine `run_async()` when using `HierarchicalConfig`.

The async engine creates an `asyncio.Semaphore` with the configured `max_workers` to limit concurrent LLM calls. For each level (0, 1, 2), it collects all pending nodes and processes them in parallel using `asyncio.gather()`. Each node is handled by `_process_node()`, which acquires the semaphore, builds context, constructs the prompt, and calls `agenerate()` on the provider.

After each level completes, `_propagate_failures()` checks whether parent nodes at the next level should be skipped. If the ratio of failed children meets or exceeds `failure_threshold` (default 0.5), the parent is marked as skipped and will not be processed.

## Provider Interface

`LLMProvider` in `src/lcp/ai/provider.py` defines two abstract methods: `generate()` (synchronous) and `agenerate()` (async, used by the hierarchical engine). Both accept a system prompt and user prompt, returning an `LLMResponse` with content and token usage.

`OpenAIProvider` and `AnthropicProvider` each maintain both a sync and an async client (lazy-initialized). The async clients (`AsyncOpenAI`, `AsyncAnthropic`) enable true concurrent I/O without threading.

## Prompt Templates

`build_user_prompt_hierarchical()` in `src/lcp/ai/prompts.py` selects the appropriate prompt template based on the node's level:

- **Level 0:** Delegates to the standard `build_user_prompt()`, which presents the source code and asks for a docstring
- **Level 1 (classes):** Presents the class structure with child documentation and asks the LLM to describe the class purpose, key attributes, and role in the module
- **Level 2 (modules):** Presents the module overview with component summaries and asks for a module-level description

The system prompt is shared across all levels and configures the docstring style (default: Google), output format rules, and optional user-provided description.

## CLI Integration

The `lcp docgen` command in `src/lcp/cli.py` uses `HierarchicalConfig` with two additional flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--workers` | 4 | Maximum concurrent LLM calls |
| `--failure-threshold` | 0.5 | Ratio of child failures to skip parent |

## Failure Propagation

When a Level 0 symbol fails (LLM error, empty response, missing source), it is marked as `"failed"`. After Level 0 completes, the engine checks each Level 1 (class) node: if 50% or more of its children failed, the class is marked `"skipped"` and will not be sent to the LLM. The same check runs after Level 1 for Level 2 (module) nodes.

This prevents wasting LLM calls on parent symbols that lack sufficient context from their children.

## Related Documentation

- [AI DocGen Overview](index.md)
- [Hierarchical DocGen Design](../plans/2026-02-16-hierarchical-docgen-design.md) - Original design decisions

---
**Last Updated:** February 2026
**Status:** Implemented
