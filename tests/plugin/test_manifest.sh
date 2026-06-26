#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HERE/../../plugin/lcp"
python3 - "$ROOT" <<'PY'
import json, sys, os
root = sys.argv[1]
pj = json.load(open(os.path.join(root, ".claude-plugin", "plugin.json")))
uc = pj.get("userConfig", {})
assert set(["lcpCommand","pythonPath","registries"]).issubset(uc), "missing userConfig keys"
assert "expose" not in uc and "preload" not in uc, "expose/preload must not be userConfig"
mj = json.load(open(os.path.join(root, ".mcp.json")))
cmd = mj["mcpServers"]["lcp"]["command"]
assert cmd == "${CLAUDE_PLUGIN_ROOT}/bin/serve.sh", cmd
assert "env" not in mj["mcpServers"]["lcp"], "no env block needed"
print("OK manifest")
PY
