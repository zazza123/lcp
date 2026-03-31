#!/bin/bash
# LCP plugin wrapper — starts the lcp serve-all MCP server.
# Uses ${CLAUDE_PLUGIN_OPTION_registries} if set by userConfig.

set -euo pipefail

if ! command -v lcp >/dev/null 2>&1; then
  echo "Error: 'lcp' command not found. Install with: pip install lcp" >&2
  exit 1
fi

ARGS=("serve-all")

# If the user configured registries via userConfig, use the first one.
if [[ -n "${CLAUDE_PLUGIN_OPTION_registries:-}" ]]; then
  FIRST_REGISTRY=$(echo "$CLAUDE_PLUGIN_OPTION_registries" | cut -d',' -f1 | xargs)
  if [[ -n "$FIRST_REGISTRY" ]]; then
    ARGS+=("--registry" "$FIRST_REGISTRY")
  fi
fi

exec lcp "${ARGS[@]}"
