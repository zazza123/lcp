# Phase 4 eval analysis — structured docstrings, lcp-skill arm

**Comparison base:** `evals/results/2026-07-06-phase3-aliases-skill`
(same verifier, same 8 F1 cases, same model pin, same arm; CLI 2.1.201 → 2.1.202).

## Topline

| Metric | Phase 3 | Phase 4 |
|---|---|---|
| Pass rate | 16/24 (cyhole 11/12, fastmcp 5/12) | 13/24 (cyhole 8/12, fastmcp 5/12) |
| Misuse/run | 0.33 | 0.71 |
| lcp calls/run | cyhole 9.00, fastmcp 2.08 | cyhole 8.67, fastmcp 2.08 |

## Engagement-conditioned view (the one that matters)

A run is *engaged* when it makes ≥1 `mcp__lcp__*` call.

| | Phase 3 | Phase 4 |
|---|---|---|
| Engaged runs | 15/24 | 13/24 |
| Engaged pass rate | 15/15 | 12/13 |
| Engaged misuse | 0 | **0** |
| Non-engaged pass rate | 1/9 | 1/11 |
| Non-engaged misuse | 8 | 17 |

Every one of the 17 misuses sits in a non-engaged run (symbols invented
without consulting the server, e.g. `fastmcp.ClientSession`,
`StdioServerTransport`). The single engaged failure (jupiter-swap r2,
23 lcp calls, 0 misuse) is the known task-compliance residual class, not
an API-accuracy failure.

## Reading

1. **No Phase-4-induced regression.** Engaged runs consumed the enriched
   `get_symbol` responses (param descriptions, `raises`,
   `returns_description`, docstring examples) with zero hallucinated
   symbols and an unchanged call pattern (cyhole 8.67 vs 9.00 calls/run;
   fastmcp identical at 2.08). Nothing suggests the larger responses
   confused the model.
2. **The topline delta is engagement variance.** cyhole engagement drew
   11/12 in Phase 3 and 9/12 here; fastmcp is stable at 4/12. Non-engaged
   runs stall right after the deferred-tool `ToolSearch` step (a pattern
   already present in the Phase 3 runs) or skip the server entirely — the
   F1 bimodality documented since Phase 2b. With 3 reps per case the
   engagement coin-flip dominates the topline.
3. **Structured-fields exit criteria** (measured on this branch, dev venv):
   documented params carrying `Param.description`: fastmcp 99.4 %,
   polars 99.6 %, click 98.9 % (threshold ≥90 %); manifest gzip growth
   ×1.13 / ×1.28 / ×1.09 (threshold ≤2×); `polars.dataframe.frame:DataFrame`
   `get_symbol` entry 24 791 B under the 25 000 B cap (members truncated by
   the pre-existing budget, examples intact).

## Follow-ups

- Engagement (F1), not answer quality, remains the binding constraint on
  the skill arm — Phase 8 should measure it with more reps and fresh tasks
  before reading any single-digit pass-rate delta as signal.
- The deferred-tool `ToolSearch` stall pattern is harness-version-sensitive;
  record `claude --version` in every future meta.json (2.1.202 here).
