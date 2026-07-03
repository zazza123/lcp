# Phase 2b Exp1 — skill arm (lcp-universal SKILL.md via --append-system-prompt)

24 runs: 8 F1-sensitive cases (4 fastmcp + 4 cyhole) x 3 reps, arm
`lcp-skill`, model `claude-haiku-4-5-20251001`, claude CLI 2.1.200 (same as
the Phase 2 reference), lcp at the Phase 2 V2 surface. Reference (Phase 2
`lcp` arm, same cases): fastmcp 0.0 calls/run, 1/12 pass; cyhole 2.3–3.6
calls/run, 2–4/12 pass.

## Gate metric

Counting only `mcp__lcp__*` calls (the CLI's built-in ToolSearch is excluded
via `tool_call_details`; the raw `tool_calls` metric counts it too):

| library | lcp calls/run | all tools/run | pass  |
|---------|---------------|---------------|-------|
| cyhole  | 7.6           | 9.8           | 7/12  |
| fastmcp | **1.42**      | 2.5           | 3/12  |

**Gate (fastmcp mean voluntary lcp calls >= 1.0/run): PASSED — outcome A.**

The skill moves fastmcp from 0.0 (two Phase 2 instruction iterations, both
flat zero) to 1.42 lcp calls/run. Engagement is bimodal per run — a run
either ignores the tools (7/12 runs at 0, including all 3
fastmcp-server-tool runs, which hallucinated `fastmcp.Server` every time)
or commits to a full ToolSearch → resolve_library → search → get_symbol
chain (7–11 calls). The skill doesn't make every run verify, but it is the
first shipped channel that produces *any* voluntary verification on a
false-confidence library. Pass rate follows engagement: fastmcp 3/12 vs
1/12 reference (all 3 passes on the resource case), cyhole 7/12 vs 2–4/12.

## Adoption-quality analysis (tool_call_details, cyhole runs)

10 of 12 cyhole runs called `get_symbol` at least once; 7 passed. Across
ALL engaged runs `forbidden_used` and `unresolved_usages` are empty — zero
hallucinated symbols; every import and dotted usage in engaged-run code
resolves at runtime. The two non-engaged runs (rugcheck r1, r3) both
hallucinated package-root symbols (`cyhole.Rugcheck`, `cyhole.Cyhole`) —
the F2 failure pattern appears exclusively where verification was skipped.

All 3 engaged failures are the same single pattern (jupiter-swap r1–r3):
the model fetches the canonical id (`cyhole.jupiter.interaction:Jupiter`,
present in every run's get_symbol ids) and then writes the import the way
users do — `from cyhole.jupiter import Jupiter`, a valid package-level
re-export. The harness's `symbol_used` matcher accepts only the canonical
dotted path, so the required symbol counts as missing. Functionally these
are correct programs: 10/10 engaged runs used real API through valid import
paths. "Verify A, write B" in the hallucination sense did not occur on the
V2 surface; what remains is "verify canonical, write alias".

## Feed-forward to Phase 3

- The dominant residual failure on engaged runs IS the Phase 3 re-export
  alias gap, now measured end-to-end: agents verify the canonical id and
  still import via the package root.
- `evals/harness/verify.py::symbol_used` has the same canonical-only blind
  spot; Phase 3 must teach the verifier aliases in the same phase or the
  eval will under-count the improvement it ships (jupiter-swap alone is
  +3/12 cyhole passes here).
- Binding consequence of outcome A: Phase 8's harness MUST include an
  `lcp-skill` arm — the plugin skill is part of the measured product.
