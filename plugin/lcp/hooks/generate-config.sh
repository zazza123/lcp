#!/bin/bash
# SessionStart: generate .lcp.json from userConfig when absent. Never blocks.
set -uo pipefail

target="${CLAUDE_PROJECT_DIR:+${CLAUDE_PROJECT_DIR}/.lcp.json}"
target="${target:-$HOME/.lcp/config.json}"

[ -f "$target" ] && exit 0           # generate-if-absent
command -v python3 >/dev/null 2>&1 || exit 0

mkdir -p "$(dirname "$target")" 2>/dev/null || exit 0

LCMD="${CLAUDE_PLUGIN_OPTION_LCPCOMMAND:-}" \
LPY="${CLAUDE_PLUGIN_OPTION_PYTHONPATH:-}" \
LREG="${CLAUDE_PLUGIN_OPTION_REGISTRIES:-}" \
python3 - "$target" <<'PY' || exit 0
import json, os, sys
out = {}
if os.environ.get("LCMD"): out["command"] = os.environ["LCMD"]
if os.environ.get("LPY"):  out["python"]  = os.environ["LPY"]
reg = [r.strip() for r in os.environ.get("LREG","").split(",") if r.strip()]
if reg: out["registries"] = reg
# Only write the file when there is something to write; an empty project
# .lcp.json would silently shadow a populated ~/.lcp/config.json.
if out: json.dump(out, open(sys.argv[1], "w"), indent=2)
PY
exit 0
