# Quickstart

Generate your first LCP manifest in 60 seconds.

## Install

LCP requires **Python 3.10 or newer**.

=== "Standard"

    ```bash
    pip install lcp
    ```

=== "With AI DocGen extras"

    ```bash
    pip install "lcp[ai]"
    ```

=== "Development"

    ```bash
    pip install -e ".[dev]"
    ```

The `[ai]` extra adds OpenAI and Anthropic clients for [AI DocGen](guides/ai-docgen.md).

## Scan a package

Generate an LCP manifest for any installed Python package:

```bash
lcp scan requests -o requests.lcp.json
```

By default this skips private (underscore-prefixed) symbols and scans submodules recursively. To include private symbols:

```bash
lcp scan requests -o requests.lcp.json --include-private
```

!!! tip
    The default JSON indent is 2 spaces. Use `--indent 0` for compact output suitable for diffs.

## Inspect the output

The generated file is a JSON document. You can pipe it through `jq` or open it in any editor.

```bash
jq '.symbols | keys | .[:5]' requests.lcp.json          # first few symbol IDs
jq '.symbols["requests.api:get"]' requests.lcp.json     # one full entry
```

The `symbols` object is a map keyed by stable symbol IDs (`module:symbol`; class members use `#`, e.g. `requests.sessions:Session#get`). Each entry has a `kind` (`function`, `class`, `method`, `module`...), a `semantics.summary`, and optional `signatures`, `stability`, `effects`, and `aliases` fields.

## Validate

Validation runs automatically during `scan`. To validate an existing file:

```bash
lcp validate requests.lcp.json
```

A successful validation prints `OK`. Errors point at the offending JSON Pointer path.

## Next steps

- [CLI reference](cli.md) — all `lcp` commands and flags.
- [MCP Server](guides/mcp-server.md) — serve the manifest to an AI agent.
- [LCP v1 spec](spec/index.md) — what each field means.
