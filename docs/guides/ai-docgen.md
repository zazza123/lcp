# AI DocGen

The `lcp.ai` module reads a [coverage report](../cli.md#lcp-coverage), identifies undocumented symbols, and generates docstrings using a Large Language Model. The implementation lives in `src/lcp/ai/` and is gated behind the `[ai]` install extra.

## What is AI DocGen?

The `lcp coverage` command identifies undocumented symbols in a Python package and writes a JSON report listing each gap. AI DocGen takes that report, organizes symbols into a hierarchy, and uses parallel LLM calls to generate Google-style docstrings from the bottom up. The generated docstrings are injected directly into the package's source files via AST analysis.

The ordering matters: methods are documented first, then classes (whose prompts include the already-generated method docstrings as context), then modules (whose prompts include class-level summary lines). This bottom-up flow means each level receives progressively more meaningful context than a flat, order-independent approach would provide.

## How it works

`build_hierarchy()` in `src/lcp/ai/hierarchy.py` reads the undocumented symbol list and groups it into `SymbolNode` trees, one `ModuleTree` per Python module. Nodes are assigned to one of three levels: L0 (functions and methods), L1 (classes), L2 (modules). The engine processes all nodes at a given level concurrently using `asyncio.gather` with a semaphore, then moves to the next level and passes the previously generated docstrings as context.

Prompt selection is handled in `src/lcp/ai/prompts.py`, which produces level-appropriate instructions for each call. Once all levels are processed, `src/lcp/ai/writer.py` injects the generated docstrings into the source files using `inject_docstrings_batch()`. Injections are applied in descending line-number order so that earlier writes do not shift the offsets of lines that follow.

If too many child symbols fail at one level, the parent at the next level is skipped automatically. The ratio is controlled by the `failure_threshold` field of `HierarchicalConfig` (default `0.5`).

## Quick start

```bash
pip install "lcp[ai]"
export OPENAI_API_KEY=sk-...
```

Generate a coverage report first, then run the agent:

```bash
lcp coverage mypackage -o coverage.json
```

Then in Python:

```python
from lcp.ai import DocGenAgent, HierarchicalConfig, OpenAIProvider

provider = OpenAIProvider(model="gpt-4o-mini")
config = HierarchicalConfig(
    max_workers=8,
)
agent = DocGenAgent(provider=provider, config=config)
result = agent.run_sync("coverage.json")

print(f"Updated: {result.symbols_updated}/{result.symbols_processed}")
```

The writer modifies the package's source files in place. Review the diff with `git diff` before committing.

!!! note "CLI status"
    A `lcp docgen` CLI wrapper around this Python API is planned. Until it ships, use the `DocGenAgent` class directly as shown above.

## Providers

=== "OpenAI"

    ```bash
    export OPENAI_API_KEY=sk-...
    ```

    `OpenAIProvider` (in `src/lcp/ai/connectors/openai.py`) defaults to `gpt-4o` and supports reasoning models such as `o1` and `o3` via the `reasoning=True` constructor flag, which switches to the developer-message format those models require. Both `generate()` (sync) and `agenerate()` (async) are implemented.

    ```python
    from lcp.ai import OpenAIProvider

    # Standard model
    provider = OpenAIProvider(model="gpt-4o-mini")

    # Reasoning model (o1, o3, etc.)
    provider = OpenAIProvider(model="o3-mini", reasoning=True)
    ```

=== "Anthropic"

    ```bash
    export ANTHROPIC_API_KEY=sk-ant-...
    ```

    `AnthropicProvider` (in `src/lcp/ai/connectors/anthropic.py`) defaults to `claude-sonnet-4-20250514` and tracks prompt-cache tokens separately in `TokenUsage.cache_tokens`, which aggregates both `cache_creation_input_tokens` and `cache_read_input_tokens`. Both `generate()` and `agenerate()` are implemented.

    ```python
    from lcp.ai import AnthropicProvider

    provider = AnthropicProvider(model="claude-haiku-4-20250514")
    ```

## Python API

```python
from lcp.ai import DocGenAgent, HierarchicalConfig, AnthropicProvider

provider = AnthropicProvider(model="claude-sonnet-4-20250514")

config = HierarchicalConfig(
    max_workers=4,
    failure_threshold=0.5,
    dry_run=False,             # set True to preview without writing
    docstring_style="google",  # inherited from DocGenConfig
)

agent = DocGenAgent(provider=provider, config=config)

# Synchronous — wraps asyncio.run() internally
result = agent.run_sync("coverage.json")

# Async — use when embedding into an existing event loop
# result = await agent.run_async("coverage.json")

print(f"Processed: {result.symbols_processed}")
print(f"Updated:   {result.symbols_updated}")
print(f"Skipped:   {result.symbols_skipped}")
print(f"Failed:    {result.symbols_failed}")
print(f"Tokens:    {result.total_usage.input_tokens} in / "
      f"{result.total_usage.output_tokens} out")

for sym in result.results:
    print(f"  {sym.symbol_id}: {sym.status}")
```

`DocGenResult` (in `src/lcp/ai/models.py`) contains aggregate counts (`symbols_processed`, `symbols_updated`, `symbols_skipped`, `symbols_failed`), a `total_usage: TokenUsage` that sums input, output, cache, and reasoning tokens across all LLM calls, and a `results: list[SymbolResult]` with per-symbol detail including `status`, `docstring`, and any `error` message. `DocGenConfig` is the flat base configuration class; `HierarchicalConfig` extends it with `max_workers` (concurrency limit via asyncio semaphore) and `failure_threshold` (ratio of child failures that causes a parent to be skipped rather than processed with incomplete context).

## See also

- [`lcp coverage`](../cli.md#lcp-coverage) — produces the coverage JSON consumed by `DocGenAgent`.
- [LCP v1 spec](../spec/index.md) — the manifest that documentation is generated for.
