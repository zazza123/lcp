#!/usr/bin/env bash
# serve.sh must pass the scan interpreter through to `lcp serve-all`:
# scan_python wins, python is the documented fallback, scan_timeout follows.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SERVE="$HERE/../../plugin/lcp/bin/serve.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

export LCP_SERVE_LIB=1
export CLAUDE_PROJECT_DIR="$TMP"
# shellcheck disable=SC1090
source "$SERVE"

# 1. scan_python set → used verbatim; scan_timeout passes through
cat > "$TMP/.lcp-config.json" <<'JSON'
{ "python": "/venv/server/bin/python", "scan_python": "/venv/scan/bin/python", "scan_timeout": 120 }
JSON
args="$(lcp_build_args | tr '\n' ' ')"
case "$args" in *"--scan-python /venv/scan/bin/python "*) ;; *) echo "FAIL scan_python: $args"; exit 1;; esac
case "$args" in *"--scan-timeout 120 "*) ;; *) echo "FAIL scan_timeout: $args"; exit 1;; esac

# 2. no scan_python → python is the fallback scan interpreter
cat > "$TMP/.lcp-config.json" <<'JSON'
{ "python": "/venv/project/bin/python" }
JSON
args="$(lcp_build_args | tr '\n' ' ')"
case "$args" in *"--scan-python /venv/project/bin/python "*) ;; *) echo "FAIL python fallback: $args"; exit 1;; esac

# 3. neither field → no --scan-python at all; existing args still built
cat > "$TMP/.lcp-config.json" <<'JSON'
{ "expose": ["json"] }
JSON
args="$(lcp_build_args | tr '\n' ' ')"
case "$args" in *"--scan-python"*) echo "FAIL unexpected scan_python: $args"; exit 1;; *) ;; esac
case "$args" in *"--expose json "*) ;; *) echo "FAIL expose lost: $args"; exit 1;; esac

echo "OK scan_args"
