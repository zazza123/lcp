#!/usr/bin/env bash
# Tests for lcp_config_get shell function in serve.sh.
# Sources serve.sh in "lib mode" (LCP_SERVE_LIB=1) to prevent server launch.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SERVE="$HERE/../../plugin/lcp/bin/serve.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/.lcp.json" <<JSON
{ "command": "/x/lcp", "registries": ["https://a", "https://b"], "expose": ["json","os"] }
JSON

# source serve.sh in "lib mode" (no auto-run) and call the function
export LCP_SERVE_LIB=1
export CLAUDE_PROJECT_DIR="$TMP"
# shellcheck disable=SC1090
source "$SERVE"

[ "$(lcp_config_get command)" = "/x/lcp" ] || { echo "FAIL command"; exit 1; }
[ "$(lcp_config_get registries)" = "https://a https://b" ] || { echo "FAIL registries"; exit 1; }
[ "$(lcp_config_get expose)" = "json os" ] || { echo "FAIL expose"; exit 1; }
[ -z "$(lcp_config_get python)" ] || { echo "FAIL python empty"; exit 1; }
echo "OK config_reader"
