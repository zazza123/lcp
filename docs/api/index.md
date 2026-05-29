# API Reference

Auto-generated reference for the public Python API of the LCP SDK, extracted directly from the source docstrings. For conceptual explanations of how each component works, see the [Architecture](../architecture/index.md) section.

## Modules

| Module | Description |
|--------|-------------|
| [Scanner](scanner.md) | Introspects an installed Python package into `ScannedModule` |
| [Generator](generator.md) | Converts scanned data into an `LCPDocument` |
| [Validator](validator.md) | Validates documents against the LCP JSON Schema |
| [Models](models.md) | Pydantic models matching the LCP v1 specification |
| [Coverage](coverage.md) | Measures documentation completeness across a package |
| [Diff](diff.md) | Compares two LCP manifests and detects deprecations |
| [Publish](publish.md) | Submits manifests to the registry via GitHub Pull Request |
| [MCP Server](mcp-server.md) | Serves LCP manifests to AI agents over the Model Context Protocol |
| [AI DocGen](ai.md) | Optional LLM-based docstring generation (`lcp[ai]`) |

!!! tip "Top-level entry point"
    Most workflows start from the package-level `scan()` function, re-exported from `lcp`. See [Scanner](scanner.md) for the full pipeline.
