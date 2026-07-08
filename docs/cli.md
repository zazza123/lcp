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
| `--include-tests` | off | Include `*.tests` subpackages (excluded by default). |
| `--validate / --no-validate` | on | Validate output against LCP schema. |
| `--indent INTEGER` | `2` | JSON indentation level. |
| `--coverage PATH` | — | Also generate a documentation coverage report to this path. |

By default, `*.tests` subpackages (whose leaf name is exactly `tests`) are skipped: they are not public API and would otherwise pollute the manifest. Public utilities such as `numpy.testing` are unaffected. Pass `--include-tests` to scan them anyway.

**Example:**

```bash
lcp scan requests -o requests.lcp.json
lcp scan numpy --include-private
```

### Machine-mode scanning: `python -m lcp.scanjson`

For programmatic callers, `lcp.scanjson` is a machine-mode scan entry point with a strict output contract. It writes the LCP JSON document to stdout, reports errors as a single JSON object on stderr, and distinguishes failures by exit code:

```bash
python -m lcp.scanjson PACKAGE [--include-private] [--no-recursive] [--include-tests]
```

| Exit code | Meaning | Output |
|-----------|---------|--------|
| `0` | Success | LCP JSON document on stdout |
| `3` | Import failure — the package could not be imported | `{"type": "import_failure", "message": ...}` on stderr |
| `4` | Scan failure — the package imported but scanning or generation failed (including `SystemExit` raised by import-time code) | `{"type": "scan_failure", "message": ...}` on stderr |

Unlike `lcp scan`, this entry point never prints human-readable progress, and it only needs `lcp` and `pydantic` importable in the interpreter that runs it (no `click`) — so it can run inside a project virtualenv that does not have the full CLI installed. Import-time prints from the scanned package are redirected to stderr so they cannot corrupt the stdout document.

`lcp.scanjson` is a **same-venv** entry point: it emits the full LCP document and expects `lcp` installed in the interpreter running it. Cross-venv scans — the MCP server documenting a package in a *different* virtualenv — instead go through [`lcp.subprocess_scan`](guides/mcp-server.md#scanning-environment), which runs an isolated child that loads only the scanner by file path (never importing the host's `lcp`/`pydantic`) and hands the raw scan back to the host for generation, so the host environment can never contaminate the target scan.

```bash
python -m lcp.scanjson requests > requests.lcp.json
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

## `lcp serve` (deprecated)

!!! warning "Deprecated"
    `lcp serve` is deprecated — use [`lcp serve-all`](#lcp-serve-all) with `--expose <package>` instead. The command still works: it starts the same universal server, pre-loaded with the manifest and restricted to that library, and prints a deprecation warning on stderr.

```bash
lcp serve MANIFEST [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `MANIFEST` | — | Path to an LCP JSON file to serve. |
| `--name TEXT` | `lcp-{library-name}` | Server name for MCP identification. |

## `lcp serve-all`

Start a universal MCP server that resolves any installed Python library on the fly. No pre-built manifest is required — AI agents call the `resolve_library` tool to load any pip-installed package, then `search` and `get_symbol` to explore it. Manifests are cached locally and, when local scanning fails, can be fetched from a remote LCP registry.

Resolution order: local cache → live scan → registry fetch.

```bash
lcp serve-all [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--cache-dir PATH` | `~/.lcp/cache/` | Cache directory for LCP manifests. |
| `--name TEXT` | `lcp-universal` | Server name for MCP identification. |
| `--no-cache` | off | Disable reading from and writing to the local cache. |
| `--registry TEXT` | — | Base URL of an LCP registry used as fallback when local scanning fails. Manifests are fetched from `{registry}/manifests/{language}/{first_letter}/{slug}/{version}.lcp.json.gz`, where `{slug}` is the hyphenated package name (`google.adk` → `google-adk`). |
| `--expose TEXT` | all packages | Restrict `resolve_library` to these package names (repeatable). |
| `--preload TEXT` | — | Resolve these packages at startup (repeatable). |
| `--max-response-bytes INT` | `25000` | Byte budget for list-returning tool responses (context blowout guard). |
| `--scan-mode [subprocess\|inprocess]` | `subprocess` | How `resolve_library` scans installed packages. `subprocess` isolates package imports in a disposable child process (crash isolation, cross-venv scanning, no import-lock stalls); `inprocess` imports into the server process, for environments where spawning is restricted. |
| `--scan-python TEXT` | server's interpreter | Python interpreter whose environment `resolve_library` scans. Lets the server document packages installed in a different venv. |
| `--scan-timeout FLOAT` | `60.0` | Seconds before a subprocess scan is killed. |

**Example:**

```bash
lcp serve-all
lcp serve-all --registry https://raw.githubusercontent.com/zazza123/lcp-registry/refs/heads/main
lcp serve-all --expose requests --preload requests
lcp serve-all --scan-python /path/to/project/.venv/bin/python
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
| `--include-tests` | off | Include `*.tests` subpackages (excluded by default). |

**Example:**

```bash
lcp coverage requests -o coverage.json
lcp coverage numpy -o coverage.md --format markdown
```

## `lcp docgen`

Generate missing docstrings for the symbols listed in a coverage report, using an LLM provider. Requires the optional AI extra (`pip install "lcp[ai]"`). Processing is hierarchical bottom-up (methods → classes → modules) with parallel LLM calls; generated docstrings are injected into the package's source files in place.

```bash
lcp docgen COVERAGE_JSON [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `COVERAGE_JSON` | — | Path to a coverage report produced by [`lcp coverage`](#lcp-coverage). |
| `--provider [openai\|anthropic]` | `openai` | LLM provider. |
| `--model TEXT` | provider default | Model name. |
| `--api-key TEXT` | env var | API key; defaults to `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`. |
| `--kinds TEXT` | all | Filter by symbol kind, comma-separated (e.g. `class,function,method`). |
| `--description TEXT` | — | Package description used to guide the model. |
| `--reasoning` | off | Enable reasoning mode for OpenAI models (o1, o3, ...). |
| `--dry-run` | off | Show what would be modified without writing files. |
| `--workers INTEGER` | `4` | Max concurrent LLM calls. |
| `--failure-threshold FLOAT` | `0.5` | Ratio (0.0–1.0) of failed children that skips the parent symbol. |

**Example:**

```bash
lcp coverage mypackage -o coverage.json
lcp docgen coverage.json --provider openai --dry-run
lcp docgen coverage.json --provider anthropic --workers 8
```

See the [AI DocGen guide](guides/ai-docgen.md) for how hierarchical processing works and the Python API.

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
- [MCP Server guide](guides/mcp-server.md) — using `lcp serve` and `lcp serve-all` in depth.
- [AI DocGen guide](guides/ai-docgen.md) — generating missing docstrings with `lcp docgen`.
- [Publishing guide](guides/publishing.md) — using `lcp publish` to submit to the registry.
