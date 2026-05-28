# Claude Code plugin

The LCP Claude Code plugin packages [`lcp serve-all`](mcp-server.md#universal-mode-registry-backed) plus a set of skills, commands, and a subagent for proactive library exploration. Install it once and Claude Code starts the MCP server automatically on every session — no manual setup needed.

## What's included

- **MCP server** — `.mcp.json` declares `lcp serve-all`; Claude Code starts it automatically via `bin/serve.sh`.
- **Startup wrapper** — `bin/serve.sh` validates that `lcp` is on PATH, injects the `--registry` flag if configured, then execs `lcp serve-all`.
- **Session hook** — `hooks/hooks.json` registers a `SessionStart` hook that warns immediately if the `lcp` binary is not found, before the server starts.
- **Skills** — `skills/lcp-universal/` and `skills/lcp-usage/` are auto-invoked skills that teach Claude the library-resolution workflow and general LCP guidance.
- **Commands** — `commands/resolve.md` and `commands/scan.md` expose `/lcp:resolve <pkg>` and `/lcp:scan <pkg>` as Claude Code slash commands.
- **Library explorer subagent** — `agents/library-explorer.md` is a read-only Claude Haiku subagent for deep API research without consuming the parent context window.
- **Registry support** — `plugin.json` exposes a `userConfig.registries` field for configuring private or team registries with pre-built manifests.

## Installation

### 1. Prerequisites

- [Claude Code](https://claude.com/claude-code) installed.
- `lcp` installed and on your `PATH` (see [Quickstart](../quickstart.md)):

```bash
pip install lcp
lcp --version
```

### 2. Install the plugin

Install directly from the GitHub repository or from a local clone:

```bash
# From the repository (no local clone needed)
claude plugin install https://github.com/zazza123/lcp/tree/main/plugin/lcp

# Or from a local clone
git clone https://github.com/zazza123/lcp.git
claude plugin install lcp/plugin/lcp
```

### 3. Verify

Open a new Claude Code session. The LCP MCP server starts automatically. You should see it listed under active MCP servers. Ask Claude about any pip-installed Python library to confirm resolution is working.

## How it works

The plugin manifest lives in `.claude-plugin/plugin.json`. It declares the plugin name, version, author, and the `userConfig.registries` schema used by the registry feature. Claude Code reads this file to register the plugin.

The actual server is declared in `.mcp.json`, which points to `bin/serve.sh` as the MCP server command. When a session opens, Claude Code executes `serve.sh`, which first checks that `lcp` is available on `PATH` and exits with an error if it is not. It then builds the argument list — always starting with `serve-all` — and conditionally appends `--registry <url>` if `CLAUDE_PLUGIN_OPTION_registries` is set (populated from `userConfig.registries`). Finally, it execs `lcp serve-all`, handing control over to the MCP server process.

The `hooks/hooks.json` `SessionStart` hook runs in parallel with server startup. If `lcp` is not on `PATH`, it prints a warning to stderr immediately, so you get a visible signal rather than a silent failure. The two skills (`lcp-universal`, `lcp-usage`) are loaded automatically and guide Claude toward the correct tool-calling workflow when it detects a library-related request.

## Configuring registries

By default, `lcp serve-all` resolves libraries on demand by scanning the local Python environment. If your team hosts pre-built LCP manifests in a private registry, you can configure the plugin to use it.

Set the `registries` option via the plugin config command:

```bash
# Single registry
claude plugin config lcp registries "https://your-registry.example.com"

# Multiple registries (comma-separated; only the first is passed to --registry)
claude plugin config lcp registries "https://internal.example.com,https://public.example.com"
```

The `userConfig.registries` field in `plugin.json` defines this option's schema — type `string`, comma-separated URLs. The `bin/serve.sh` wrapper reads the value from `CLAUDE_PLUGIN_OPTION_registries`, splits on commas, trims whitespace, and passes the first URL to `lcp serve-all --registry`. Subsequent URLs in the list are currently ignored by the wrapper but recorded for future multi-registry support.

A minimal `plugin.json` `userConfig` block looks like this:

```json
{
  "userConfig": {
    "registries": {
      "type": "string",
      "title": "LCP Registries",
      "description": "Comma-separated list of LCP registry URLs. The first URL is used as the primary registry.",
      "sensitive": false
    }
  }
}
```

## Troubleshooting

!!! warning "`lcp` command not found"
    The `SessionStart` hook and `bin/serve.sh` both check for `lcp` on `PATH`. If you see this warning, install `lcp` with `pip install lcp` and confirm `lcp --version` works in the same shell environment Claude Code uses.

!!! warning "MCP server not starting"
    Run `lcp serve-all` manually in your terminal to check for errors. On Unix systems, `bin/serve.sh` must be executable — run `chmod +x plugin/lcp/bin/serve.sh` if needed. Confirm Claude Code shows `lcp` in its MCP server list.

!!! warning "Library not resolving"
    The package must be pip-installed in the Python environment that `lcp` uses. Run `lcp scan <package>` manually to verify the library can be introspected. If the scan succeeds but the MCP tool still fails, restart the Claude Code session to reload the server.

## See also

- [MCP server](mcp-server.md) — the underlying server the plugin wraps.
- [CLI reference](../cli.md) — `serve-all` flags and all other commands.
