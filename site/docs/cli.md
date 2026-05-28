# CLI reference

The `lcp` command-line tool is installed by `pip install lcp`. All subcommands accept `--help` for inline documentation.

```bash
lcp --version
lcp <command> --help
```

## `lcp scan`

Introspect an installed Python package and emit an LCP manifest.

```bash
lcp scan PACKAGE [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `PACKAGE` | — | Importable package name (e.g. `requests`). |
| `-o, --output PATH` | stdout | Output file path. |
| `--include-private` | off | Include private symbols (starting with `_`). |
| `--no-recursive` | off | Don't scan submodules recursively. |
| `--validate / --no-validate` | on | Validate output against LCP schema. |
| `--indent INTEGER` | `2` | JSON indentation level. |
| `--coverage PATH` | — | Also generate a documentation coverage report to this path. |

**Example:**

```bash
lcp scan requests -o requests.lcp.json
lcp scan numpy --include-private
```

## `lcp validate`

Validate an LCP JSON file against the LCP schema.

```bash
lcp validate FILE
```

| Flag | Default | Description |
|------|---------|-------------|
| `FILE` | — | Path to an LCP JSON file to validate. |

**Example:**

```bash
lcp validate requests.lcp.json
```

## `lcp serve`

Start an MCP server (stdio transport) for a single LCP manifest file, exposing tools for exploring and querying the library's API.

```bash
lcp serve MANIFEST [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `MANIFEST` | — | Path to an LCP JSON file to serve. |
| `--name TEXT` | `lcp-{library-name}` | Server name for MCP identification. |

**Example:**

```bash
lcp serve requests.lcp.json
lcp serve numpy.lcp.json --name numpy-docs
```

## `lcp serve-all`

Start a universal MCP server that resolves any installed Python library on the fly. Unlike `lcp serve`, no pre-built manifest is required — AI agents call the `resolve_library` tool to load any pip-installed package. Manifests are cached locally and, when local scanning fails, can be fetched from a remote LCP registry.

Resolution order: local cache → live scan → registry fetch.

```bash
lcp serve-all [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--cache-dir PATH` | `~/.lcp/cache/` | Cache directory for LCP manifests. |
| `--name TEXT` | `lcp-universal` | Server name for MCP identification. |
| `--no-cache` | off | Disable reading from and writing to the local cache. |
| `--registry TEXT` | — | Base URL of an LCP registry used as fallback when local scanning fails. Manifests are fetched from `{registry}/manifests/{language}/{name}/{version}.lcp.json`. |

**Example:**

```bash
lcp serve-all
lcp serve-all --registry https://raw.githubusercontent.com/zazza123/lcp-registry/refs/heads/main
```

## `lcp coverage`

Generate a documentation coverage report for a Python package, showing which symbols are missing docstrings.

```bash
lcp coverage PACKAGE [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `PACKAGE` | — | Importable package name to analyze. |
| `-o, --output PATH` | stdout | Output file path. |
| `--format [json\|markdown]` | `json` | Output format. |
| `--include-private` | off | Include private symbols (starting with `_`). |
| `--no-recursive` | off | Don't scan submodules recursively. |

**Example:**

```bash
lcp coverage requests -o coverage.json
lcp coverage numpy -o coverage.md --format markdown
```

## `lcp publish`

Publish an LCP manifest to the registry by opening a GitHub Pull Request. The command scans the package (or uses an existing manifest via `--file`), validates it, then submits the PR to the registry repository.

```bash
lcp publish PACKAGE [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `PACKAGE` | — | Importable package name to publish. |
| `--token TEXT` | — | GitHub personal access token with `repo` or `public_repo` scope. Can also be set via `LCP_GITHUB_TOKEN` or `GITHUB_TOKEN` env var. |
| `--registry-repo TEXT` | `zazza123/lcp-registry` | Target registry repository in `owner/name` format. |
| `--file PATH` | — | Use an existing LCP JSON file instead of scanning the package. |
| `--include-private` | off | Include private symbols when scanning (starting with `_`). |
| `--no-recursive` | off | Don't scan submodules recursively. |
| `--dry-run` | off | Generate the manifest and show what would be submitted without creating a PR. |

**Example:**

```bash
lcp publish requests --token ghp_xxxx
lcp publish numpy --dry-run
lcp publish mylib --file mylib.lcp.json --token ghp_xxxx
```

## `lcp diff`

Compare two LCP files and detect deprecated symbols. Symbols present in the older file but missing in the newer file are reported as removed. The output includes generated deprecation entries that can be merged into the new manifest.

```bash
lcp diff OLD NEW [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `OLD` | — | Path to the earlier LCP JSON file. |
| `NEW` | — | Path to the later LCP JSON file. |
| `-o, --output PATH` | stdout | Output file path. |
| `--indent INTEGER` | `2` | JSON indentation level. |
| `--update` | off | Write detected deprecations back into the `NEW` LCP file. |

**Example:**

```bash
lcp diff v1.lcp.json v2.lcp.json
lcp diff v1.lcp.json v2.lcp.json -o diff.json --update
```

## See also

- [Quickstart](quickstart.md) — first-time usage.
- [MCP server guide](guides/mcp-server.md) — using `lcp serve` and `lcp serve-all` in depth.
- [Publishing guide](guides/publishing.md) — using `lcp publish` to submit to the registry.
