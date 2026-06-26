#!/usr/bin/env bash
# Tests for generate-config.sh: generation + idempotent no-clobber.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/../../plugin/lcp/hooks/generate-config.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

export CLAUDE_PROJECT_DIR="$TMP"
export CLAUDE_PLUGIN_OPTION_LCPCOMMAND="/opt/venv/bin/lcp"
export CLAUDE_PLUGIN_OPTION_REGISTRIES="https://r1,https://r2"

bash "$HOOK"
[ -f "$TMP/.lcp.json" ] || { echo "FAIL no file"; exit 1; }
python3 -c "import json;d=json.load(open('$TMP/.lcp.json'));assert d['command']=='/opt/venv/bin/lcp';assert d['registries']==['https://r1','https://r2']"
echo "OK generated"

# Idempotent: must NOT clobber an edited file
echo '{"command":"/edited"}' > "$TMP/.lcp.json"
bash "$HOOK"
grep -q '/edited' "$TMP/.lcp.json" || { echo "FAIL clobbered"; exit 1; }
echo "OK no-clobber"
