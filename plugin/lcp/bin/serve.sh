#!/bin/bash
# LCP plugin wrapper — starts the lcp serve-all MCP server.
#
# Resolution order for the launcher (first one that actually runs wins):
#   1. ${CLAUDE_PLUGIN_OPTION_lcpCommand}     — explicit path to an `lcp` binary
#   2. ${CLAUDE_PLUGIN_OPTION_pythonPath}     — a python interpreter; runs `python -m lcp`
#   3. `lcp` on PATH
#   4. `python3 -m lcp` / `python -m lcp` on PATH
#
# Each candidate is *probed* (`--version`) before use, so a non-resolvable
# pyenv/conda shim no longer passes a bare `command -v` check and then fails at
# runtime with a cryptic MCP `-32000`. If nothing works we emit actionable
# guidance instead.
#
# Uses ${CLAUDE_PLUGIN_OPTION_registries} if set by userConfig.

set -euo pipefail

# Resolve config file: project first, then global.
lcp_config_file() {
  if [ -n "${CLAUDE_PROJECT_DIR:-}" ] && [ -f "${CLAUDE_PROJECT_DIR}/.lcp.json" ]; then
    printf '%s\n' "${CLAUDE_PROJECT_DIR}/.lcp.json"; return 0
  fi
  if [ -f "${HOME}/.lcp/config.json" ]; then
    printf '%s\n' "${HOME}/.lcp/config.json"; return 0
  fi
  return 1
}

# lcp_config_get <field> — print value (arrays space-joined), or empty.
lcp_config_get() {
  local field="$1" file
  file="$(lcp_config_file)" || return 0
  command -v python3 >/dev/null 2>&1 || return 0
  python3 - "$file" "$field" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
v = data.get(sys.argv[2])
if v is None:
    sys.exit(0)
if isinstance(v, list):
    print(" ".join(str(x) for x in v))
else:
    print(v)
PY
}

# When sourced for tests, stop here.
if [ -n "${LCP_SERVE_LIB:-}" ]; then return 0 2>/dev/null || true; fi

# LAUNCHER is the argv prefix used to invoke the lcp CLI, e.g. ("lcp") or
# ("/path/to/python" "-m" "lcp").
LAUNCHER=()

# probe <argv...> — returns 0 if the given launcher can actually run `lcp`.
probe() {
  "$@" --version >/dev/null 2>&1
}

# Try a configured binary first.
if [[ -n "${CLAUDE_PLUGIN_OPTION_lcpCommand:-}" ]]; then
  if probe "${CLAUDE_PLUGIN_OPTION_lcpCommand}"; then
    LAUNCHER=("${CLAUDE_PLUGIN_OPTION_lcpCommand}")
  else
    echo "Error: configured lcpCommand '${CLAUDE_PLUGIN_OPTION_lcpCommand}' did not run ('--version' failed)." >&2
    exit 1
  fi
fi

# Then a configured python interpreter via `python -m lcp`.
if [[ ${#LAUNCHER[@]} -eq 0 && -n "${CLAUDE_PLUGIN_OPTION_pythonPath:-}" ]]; then
  if probe "${CLAUDE_PLUGIN_OPTION_pythonPath}" -m lcp; then
    LAUNCHER=("${CLAUDE_PLUGIN_OPTION_pythonPath}" "-m" "lcp")
  else
    echo "Error: configured pythonPath '${CLAUDE_PLUGIN_OPTION_pythonPath}' cannot run 'python -m lcp' (is lcp installed in that interpreter?)." >&2
    exit 1
  fi
fi

# Then a bare `lcp` on PATH — but only if it really executes.
if [[ ${#LAUNCHER[@]} -eq 0 ]] && command -v lcp >/dev/null 2>&1 && probe lcp; then
  LAUNCHER=("lcp")
fi

# Finally, fall back to `python -m lcp` on PATH.
if [[ ${#LAUNCHER[@]} -eq 0 ]]; then
  for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1 && probe "$py" -m lcp; then
      LAUNCHER=("$py" "-m" "lcp")
      break
    fi
  done
fi

if [[ ${#LAUNCHER[@]} -eq 0 ]]; then
  cat >&2 <<'EOF'
Error: could not find a runnable 'lcp'.

The plugin needs the `lcp` package importable by the interpreter that launches
this MCP server. A pyenv/conda/venv install that is not the active environment
will NOT be found automatically.

Fix it one of these ways:

  1. Install lcp on a stable global PATH (recommended):
         pipx install lcp        # or:  uv tool install lcp

  2. Point the plugin at your existing install:
         claude plugin config lcp lcpCommand /full/path/to/lcp
         # or, to use a specific interpreter:
         claude plugin config lcp pythonPath /full/path/to/python

Verify with:  <that path> --version
EOF
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

exec "${LAUNCHER[@]}" "${ARGS[@]}"
