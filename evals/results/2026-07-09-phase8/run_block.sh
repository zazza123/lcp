#!/usr/bin/env bash
# Phase 8 publication grid — one (model, arm) block.
# Resumable: the runner skips existing run files, so re-invoking after a
# quota reset simply continues. Usage: run_block.sh <haiku|sonnet> <arm>
set -euo pipefail
cd /Users/andreazanini/Projects/lcp/lcp

MODEL_KEY="$1"; ARM="$2"
case "$MODEL_KEY" in
  haiku)  MODEL="claude-haiku-4-5-20251001"; REPS=5; OUT="evals/results/2026-07-09-phase8/pub-haiku" ;;
  sonnet) MODEL="claude-sonnet-5";           REPS=3; OUT="evals/results/2026-07-09-phase8/pub-sonnet" ;;
  *) echo "model must be haiku|sonnet" >&2; exit 2 ;;
esac

# The registry arm skips pixeltable (excluded per PREREGISTRATION.md).
if [ "$ARM" = "registry" ]; then IDS=$(cat /tmp/nonpx_ids.txt); else IDS=$(cat /tmp/all_ids.txt); fi

# shellcheck disable=SC2086
evals/.venv-bench/bin/python evals/run.py run \
  --out "$OUT" --cases evals/cases-v2 --reps "$REPS" --workers 3 \
  --model "$MODEL" --arms "$ARM" $IDS
