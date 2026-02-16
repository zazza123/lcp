# AI Documentation Generation

## Overview

The AI DocGen module (`lcp[ai]`) generates missing docstrings for Python symbols using LLM providers. It processes a coverage report produced by `lcp coverage`, calls an LLM to generate each docstring, and injects the results into source files via AST-based writing.

## Key Features

- Hierarchical bottom-up processing: methods first, then classes (using method docs as context), then modules (using class/function summaries as context)
- Async parallel LLM calls with configurable concurrency
- Failure propagation: if too many children fail, the parent is skipped
- Support for OpenAI and Anthropic providers
- Flat (legacy sequential) mode available via `--flat` flag
- Dry-run mode to preview changes without writing

## Documents

- [Architecture](architecture.md) - Hierarchical processing pipeline, level-based context strategy, and async engine design

## Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| DocGenAgent | `src/lcp/ai/agent.py` | Orchestrator: loads coverage, dispatches processing, writes results |
| HierarchicalConfig | `src/lcp/ai/models.py` | Configuration for parallelism, flat mode, failure threshold |
| Hierarchy Builder | `src/lcp/ai/hierarchy.py` | Builds symbol trees from flat coverage data, assembles level-adaptive context |
| LLMProvider | `src/lcp/ai/provider.py` | Abstract base class with sync `generate()` and async `agenerate()` |
| OpenAIProvider | `src/lcp/ai/connectors/openai.py` | OpenAI connector with standard and reasoning mode |
| AnthropicProvider | `src/lcp/ai/connectors/anthropic.py` | Anthropic connector with cache token tracking |
| Prompt Templates | `src/lcp/ai/prompts.py` | System prompt and level-specific user prompts |
| Writer | `src/lcp/ai/writer.py` | AST-based docstring injection into source files |

## Related Documentation

- [Design Document](../plans/2026-02-16-hierarchical-docgen-design.md) - Original design decisions and trade-offs

---
**Last Updated:** February 2026
**Status:** Implemented
