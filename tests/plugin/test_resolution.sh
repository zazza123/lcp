#!/usr/bin/env bash
# tests/plugin/test_resolution.sh — Task 4: launcher resolution smoke tests.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SERVE="$HERE/../../plugin/lcp/bin/serve.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# Fake working lcp that answers --version
mkdir -p "$TMP/bin"
cat > "$TMP/bin/lcp" <<'SH'
#!/bin/bash
[ "$1" = "--version" ] && { echo "lcp, version 9.9.9"; exit 0; }
echo "serving"; sleep 1
SH
chmod +x "$TMP/bin/lcp"

cat > "$TMP/.lcp.json" <<JSON
{ "command": "$TMP/bin/lcp" }
JSON

export LCP_SERVE_LIB=1 CLAUDE_PROJECT_DIR="$TMP"
# shellcheck disable=SC1090
source "$SERVE"

got="$(lcp_resolve_launcher)"
[ "$got" = "$TMP/bin/lcp" ] || { echo "FAIL resolve: got [$got]"; exit 1; }
echo "OK resolution"

# Negative test — no launcher resolvable in a bare PATH
TMP2="$(mktemp -d)"; export CLAUDE_PROJECT_DIR="$TMP2"
( PATH="/usr/bin:/bin" bash -c '
   unset VIRTUAL_ENV
   export LCP_SERVE_LIB=1
   source "'"$SERVE"'"
   lcp_resolve_launcher && echo "UNEXPECTED" || echo "OK no-launcher"
' )
