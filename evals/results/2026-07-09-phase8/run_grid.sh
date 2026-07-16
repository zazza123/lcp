#!/usr/bin/env bash
# Phase 8 publication grid — chained driver.
# Runs the arms of one model in priority order (most informative first, so a
# partial grid still yields the headline comparison). After each block it
# checks for error records (non-null "error" = rate-limit/crash); on any it
# HALTS so the controller can clean + relaunch after a quota reset. Fully
# resumable: re-invoking skips completed runs.
# Usage: run_grid.sh <haiku|sonnet>
set -uo pipefail
cd /Users/andreazanini/Projects/lcp/lcp

MODEL_KEY="$1"
case "$MODEL_KEY" in
  haiku)  OUT="evals/results/2026-07-09-phase8/pub-haiku";  EXPECT=420 ;;
  sonnet) OUT="evals/results/2026-07-09-phase8/pub-sonnet"; EXPECT=252 ;;
  *) echo "model must be haiku|sonnet" >&2; exit 2 ;;
esac
ARMS=(baseline lcp-skill sitepkg lcp registry context7)

for ARM in "${ARMS[@]}"; do
  expect=$EXPECT
  [ "$ARM" = "registry" ] && expect=$(( EXPECT / 84 * 76 ))  # pixeltable excluded
  echo "=== $MODEL_KEY/$ARM (target $expect) ==="
  bash evals/results/2026-07-09-phase8/run_block.sh "$MODEL_KEY" "$ARM"
  # Count genuine errors by parsing the top-level "error" field — a naive
  # grep also matches the string "error": " inside the model's generated
  # code, producing phantom HALTs.
  errs=$(evals/.venv-bench/bin/python - "$OUT" "$ARM" <<'PY'
import json, glob, sys
out, arm = sys.argv[1], sys.argv[2]
print(sum(1 for f in glob.glob(f"{out}/runs/*_{arm}_*.json")
          if json.load(open(f)).get("error")))
PY
)
  done=$(ls "$OUT"/runs/*_"$ARM"_*.json 2>/dev/null | wc -l | tr -d ' ')
  echo "--- $MODEL_KEY/$ARM: $done/$expect written, $errs error-records ---"
  if [ "$errs" -gt 0 ] || [ "$done" -lt "$expect" ]; then
    echo "HALT: $MODEL_KEY/$ARM incomplete or errored — clean error files and re-run this driver after quota reset."
    exit 1
  fi
done
echo "ALL $MODEL_KEY ARMS COMPLETE"
