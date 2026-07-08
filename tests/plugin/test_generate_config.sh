#!/usr/bin/env bash
# Tests for generate-config.sh: generation + idempotent no-clobber + legacy.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/../../plugin/lcp/hooks/generate-config.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

export CLAUDE_PROJECT_DIR="$TMP"
export CLAUDE_PLUGIN_OPTION_LCPCOMMAND="/opt/venv/bin/lcp"
export CLAUDE_PLUGIN_OPTION_REGISTRIES="https://r1,https://r2"

bash "$HOOK"
[ -f "$TMP/.lcp-config.json" ] || { echo "FAIL no file"; exit 1; }
python3 -c "import json;d=json.load(open('$TMP/.lcp-config.json'));assert d['command']=='/opt/venv/bin/lcp';assert d['registries']==['https://r1','https://r2']"
echo "OK generated"

# Idempotent: must NOT clobber an edited file
echo '{"command":"/edited"}' > "$TMP/.lcp-config.json"
bash "$HOOK"
grep -q '/edited' "$TMP/.lcp-config.json" || { echo "FAIL clobbered"; exit 1; }
echo "OK no-clobber"

# Legacy config present: hook must NOT create .lcp-config.json alongside it
LEG="$(mktemp -d)"
echo '{"command":"/x"}' > "$LEG/.lcp.json"
CLAUDE_PROJECT_DIR="$LEG" bash "$HOOK"
[ ! -f "$LEG/.lcp-config.json" ] || { echo "FAIL seeded next to legacy"; exit 1; }
echo "OK legacy blocks seeding"
rm -rf "$LEG"
