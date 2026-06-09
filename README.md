<p align="center">
  <a href="https://zazza123.github.io/lcp">
    <img src="https://raw.githubusercontent.com/zazza123/lcp/main/docs/assets/logo.png" alt="LCP Logo" width="80">
  </a>
</p>
<h1 align="center">Library Context Protocol</h1>

---

<p class="readme">
    <b>Documentation</b>: <a href="https://zazza123.github.io/lcp">https://zazza123.github.io/lcp</a>
</p>
<hr class="readme">

**lcp** (*Library Context Protocol*) is primarly a protocol designed to solve the problem of AI agents not having access to up-to-date library documentation, which leads to hallucinations and inaccurate code generation. The LCP SDK provides tools to scan Python packages, extract API information, and generate LCP-compliant JSON manifests. It also includes features for analyzing documentation coverage and generating missing docstrings using AI.

## Installation

```bash
pip install lcp
```

## Features

- Scans installed Python packages using `inspect` and `ast` modules
- Generates LCP v1 compliant JSON files
- Extracts functions, classes, methods, attributes, and constants
- Parses docstrings for summaries and descriptions
- Extracts type hints from function signatures
- Validates output against LCP JSON schema
- Documentation coverage analysis with JSON/Markdown reports
- Version diff to detect deprecated symbols across releases
- AI-powered docstring generation via OpenAI and Anthropic (`lcp[ai]`)
- Both CLI and Python API interfaces
- MCP server for AI agent integration

## Usage

### CLI

```bash
# Scan a package and output LCP JSON
lcp scan requests -o requests.lcp.json

# Include private symbols
lcp scan mypackage --include-private

# Skip validation
lcp scan mypackage --no-validate

# Start an MCP server for a library manifest
lcp serve requests.lcp.json
```

### Python API

```python
from lcp import scan

# Scan a package
lcp_doc = scan("requests")

# Save to file
lcp_doc.to_file("requests.lcp.json")

# Get as dict
data = lcp_doc.to_dict()

# Include private symbols
lcp_doc = scan("mypackage", include_private=True)
```

## Documentation Coverage

Analyze documentation completeness of a package to identify missing docstrings.

### CLI

```bash
# Generate coverage report (JSON)
lcp coverage requests -o coverage.json

# Generate coverage report (Markdown)
lcp coverage requests -o coverage.md --format markdown

# Generate both LCP manifest and coverage report in one scan
lcp scan requests -o requests.lcp.json --coverage coverage.json
```

### Python API

```python
from lcp import generate_coverage

# Generate coverage report
report = generate_coverage("requests")

# Check coverage percentage
print(f"Coverage: {report.summary.coverage_percent}%")
print(f"Documented: {report.summary.documented}/{report.summary.total_symbols}")

# List undocumented symbols
for symbol in report.undocumented:
    print(f"  - {symbol.module}:{symbol.entity} ({symbol.kind})")

# Save report
report.to_file("coverage.json")      # JSON format
report.to_file("coverage.md")        # Markdown format
```

## Version Diff

Compare two LCP manifests to detect symbols that were removed between versions and automatically generate deprecation entries.

### CLI

```bash
# Compare two versions and print the diff report
lcp diff v1.lcp.json v2.lcp.json

# Save the diff report to a file
lcp diff v1.lcp.json v2.lcp.json -o diff.json

# Automatically update the new manifest with deprecation entries
lcp diff v1.lcp.json v2.lcp.json --update
```

### Python API

```python
from lcp import diff_documents, load_lcp_document, update_document

# Load two versions
old = load_lcp_document("v1.lcp.json")
new = load_lcp_document("v2.lcp.json")

# Compare
result = diff_documents(old, new)
print(f"Removed: {len(result.removed)}, Added: {len(result.added)}")

for sid, dep in result.deprecated.items():
    print(f"  {sid}: deprecated in {dep.deprecated_in}")

# Merge deprecations into the new document
updated = update_document(new, result)
updated.to_file("v2.lcp.json")
```

## MCP Server

The SDK includes an MCP (Model Context Protocol) server that exposes LCP manifest data to AI agents. This allows agents to explore library APIs and generate accurate code.

### Starting the Server

```bash
# Start MCP server for a library
lcp serve requests.lcp.json

# With custom server name
lcp serve numpy.lcp.json --name numpy-docs
```

### MCP Client Configuration

Add to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "requests-api": {
      "command": "lcp",
      "args": ["serve", "/path/to/requests.lcp.json"]
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `get_manifest` | Get library metadata (name, version, language) |
| `list_modules` | List all modules in the library |
| `list_symbols` | Browse symbols with optional filtering by module or kind |
| `get_symbol` | Get full details for a specific symbol |
| `search_symbols` | Find symbols by text search |
| `get_class_members` | Get all methods and attributes of a class |

### Programmatic Usage

```python
from lcp.mcp_server import create_server, run_server

# Create and customize server
server = create_server("path/to/manifest.lcp.json", name="my-server")

# Or run directly
run_server("path/to/manifest.lcp.json")
```

## AI Documentation Generation

Automatically generate missing docstrings using LLM providers (OpenAI, Anthropic). Requires the optional `ai` extra:

```bash
pip install lcp[ai]
```

### CLI

```bash
# Generate coverage report first
lcp coverage mypackage -o coverage.json

# Generate docstrings (dry-run to preview)
lcp docgen coverage.json --provider openai --dry-run

# Generate docstrings for real
lcp docgen coverage.json --provider openai

# Use Anthropic
lcp docgen coverage.json --provider anthropic --model claude-sonnet-4-20250514

# Filter by symbol kind
lcp docgen coverage.json --kinds class,function,method

# Provide a guiding description
lcp docgen coverage.json --description "A web framework for building REST APIs"

# Use OpenAI reasoning models (o1, o3)
lcp docgen coverage.json --provider openai --model o3 --reasoning
```

### Python API

```python
from lcp.ai import DocGenAgent, DocGenConfig, OpenAIProvider

# Create provider and agent
provider = OpenAIProvider(model="gpt-4o")
config = DocGenConfig(kinds=["class", "function"], dry_run=True)
agent = DocGenAgent(provider=provider, config=config)

# Run on a coverage JSON file
result = agent.run("coverage.json")

# Or pass a dict directly
result = agent.run(coverage_dict)

# Inspect results
print(f"Updated: {result.symbols_updated}")
print(f"Tokens: {result.total_usage.input_tokens} in / {result.total_usage.output_tokens} out")
for r in result.results:
    print(f"  {r.symbol_id}: {r.status}")
```

## Claude Code Plugin

The SDK ships a ready-to-install [Claude Code](https://code.claude.com) plugin in `plugin/lcp/`. It packages `lcp serve-all` as an MCP server so Claude Code can resolve any pip-installed Python library on demand — no per-project configuration required.

### Prerequisites

```bash
pip install lcp
```

### Installation

```bash
claude plugin install plugin/lcp
```

Once installed, Claude Code automatically starts the LCP MCP server on session start. The `lcp-universal` skill instructs the agent to call `resolve_library("package")` before writing code that depends on an external library.

### Optional: configure a registry

During or after installation you can configure one or more registry URLs (comma-separated) for teams that host pre-built manifests for private packages:

```bash
claude plugin config lcp registries https://raw.githubusercontent.com/your-org/lcp-registry/main
```

### Shortcuts

| Shortcut | Action |
|----------|--------|
| `/lcp:resolve <package>` | Resolve a library and summarise its public API |
| `/lcp:scan <package>` | Scan a package and display module/symbol overview |

## License

MIT