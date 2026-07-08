#!/bin/bash
# LCP plugin wrapper — starts the lcp serve-all MCP server.
#
# Resolution order for the launcher (first one whose --version probe succeeds):
#   1.  .lcp-config.json `command`                  — explicit path to an `lcp` binary
#   2.  .lcp-config.json `python` -m lcp            — a python interpreter + lcp
#   3.  $CLAUDE_PROJECT_DIR/.venv/bin/lcp            — project venv (.venv) lcp
#   4.  $CLAUDE_PROJECT_DIR/.venv/bin/python -m lcp  — project venv (.venv) python -m lcp
#   5.  $CLAUDE_PROJECT_DIR/venv/bin/lcp             — project venv (venv) lcp
#   6.  $CLAUDE_PROJECT_DIR/venv/bin/python -m lcp   — project venv (venv) python -m lcp
#   7.  $VIRTUAL_ENV/bin/lcp                         — active venv lcp
#   8.  $VIRTUAL_ENV/bin/python -m lcp               — active venv python -m lcp
#   9.  uv run --project <dir> --with lcp lcp        — ephemeral uv run
#  10.  lcp on PATH
#  11.  uvx lcp
#  12.  pipx run lcp
#
# Each candidate is probed (`--version`) before use, so a non-resolvable
# pyenv/conda shim no longer passes a bare `command -v` check and then fails at
# runtime with a cryptic MCP `-32000`. If nothing works we emit actionable
# guidance instead.
#
# Config is read from $CLAUDE_PROJECT_DIR/.lcp-config.json (legacy fallback:
# .lcp.json, deprecated) or ~/.lcp/config.json.
#
# Scan interpreter: the config's `scan_python` (fallback: `python`) is passed
# to the server as --scan-python — that is the environment resolve_library
# scans; `scan_timeout` is passed as --scan-timeout.

set -euo pipefail

# Resolve config file: project .lcp-config.json, legacy project .lcp.json
# (deprecated), then global.
lcp_config_file() {
  if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
    if [ -f "${CLAUDE_PROJECT_DIR}/.lcp-config.json" ]; then
      printf '%s\n' "${CLAUDE_PROJECT_DIR}/.lcp-config.json"; return 0
    fi
    if [ -f "${CLAUDE_PROJECT_DIR}/.lcp.json" ]; then
      printf '%s\n' "${CLAUDE_PROJECT_DIR}/.lcp.json"; return 0
    fi
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

# _probe <argv...> — returns 0 if the given command can run `lcp --version`.
_probe() { "$@" --version >/dev/null 2>&1; }

# lcp_resolve_launcher — echo the argv prefix (space-separated string) for the
# first candidate whose --version probe succeeds, or return 1.
lcp_resolve_launcher() {
  local cmd py proj="${CLAUDE_PROJECT_DIR:-}"
  cmd="$(lcp_config_get command)"; py="$(lcp_config_get python)"

  if [ -n "$cmd" ] && _probe "$cmd"; then printf '%s' "$cmd"; return 0; fi
  if [ -n "$py" ] && _probe "$py" -m lcp; then printf '%s -m lcp' "$py"; return 0; fi

  if [ -n "$proj" ]; then
    if [ -x "$proj/.venv/bin/lcp" ] && _probe "$proj/.venv/bin/lcp"; then
      printf '%s' "$proj/.venv/bin/lcp"; return 0; fi
    if [ -x "$proj/.venv/bin/python" ] && _probe "$proj/.venv/bin/python" -m lcp; then
      printf '%s -m lcp' "$proj/.venv/bin/python"; return 0; fi
    if [ -x "$proj/venv/bin/lcp" ] && _probe "$proj/venv/bin/lcp"; then
      printf '%s' "$proj/venv/bin/lcp"; return 0; fi
    if [ -x "$proj/venv/bin/python" ] && _probe "$proj/venv/bin/python" -m lcp; then
      printf '%s -m lcp' "$proj/venv/bin/python"; return 0; fi
  fi
  if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/lcp" ] && _probe "$VIRTUAL_ENV/bin/lcp"; then
    printf '%s' "$VIRTUAL_ENV/bin/lcp"; return 0; fi
  if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ] && _probe "$VIRTUAL_ENV/bin/python" -m lcp; then
    printf '%s -m lcp' "$VIRTUAL_ENV/bin/python"; return 0; fi
  if [ -n "$proj" ] && command -v uv >/dev/null 2>&1 \
       && _probe uv run --project "$proj" --with lcp lcp; then
    printf 'uv run --project %s --with lcp lcp' "$proj"; return 0; fi
  if command -v lcp >/dev/null 2>&1 && _probe lcp; then printf 'lcp'; return 0; fi
  if command -v uvx >/dev/null 2>&1 && _probe uvx lcp; then printf 'uvx lcp'; return 0; fi
  if command -v pipx >/dev/null 2>&1 && _probe pipx run lcp; then printf 'pipx run lcp'; return 0; fi
  return 1
}

# lcp_build_args — echo the `lcp serve-all` argv, one element per line.
# The scan interpreter resolution implements the documented double duty:
# `scan_python` wins; else `python` (the user's "my project env" intent —
# even when the launcher probe rejected it for *running* the server, it is
# still the environment the user wants scanned); else the server scans its
# own environment.
lcp_build_args() {
  local out=(serve-all) r e p sp st
  for r in $(lcp_config_get registries); do out+=(--registry "$r"); break; done
  for e in $(lcp_config_get expose);  do out+=(--expose "$e");  done
  for p in $(lcp_config_get preload); do out+=(--preload "$p"); done
  sp="$(lcp_config_get scan_python)"
  if [ -z "$sp" ]; then sp="$(lcp_config_get python)"; fi
  if [ -n "$sp" ]; then out+=(--scan-python "$sp"); fi
  st="$(lcp_config_get scan_timeout)"
  if [ -n "$st" ]; then out+=(--scan-timeout "$st"); fi
  printf '%s\n' "${out[@]}"
}

# When sourced for tests, stop here.
if [ -n "${LCP_SERVE_LIB:-}" ]; then return 0 2>/dev/null || true; fi

# One-shot deprecation notice when only the legacy config name is present.
if [ -n "${CLAUDE_PROJECT_DIR:-}" ] \
     && [ ! -f "${CLAUDE_PROJECT_DIR}/.lcp-config.json" ] \
     && [ -f "${CLAUDE_PROJECT_DIR}/.lcp.json" ]; then
  echo "lcp plugin: reading deprecated config .lcp.json — rename it to .lcp-config.json" >&2
fi

LAUNCHER="$(lcp_resolve_launcher)" || {
  cat >&2 <<'EOF'
Error: could not resolve a runnable `lcp` for this project.

Fix it one of these ways:
  1. Install lcp in your project venv:   uv pip install lcp   (or: pip install lcp)
  2. Install a global lcp:                pipx install lcp     (or: uv tool install lcp)
  3. Point .lcp-config.json at it:        {"command": "/path/to/lcp"}

Verify with:  <that path> --version
EOF
  exit 1
}

ARGS=()
while IFS= read -r a; do ARGS+=("$a"); done < <(lcp_build_args)

# shellcheck disable=SC2086
exec $LAUNCHER "${ARGS[@]}"
