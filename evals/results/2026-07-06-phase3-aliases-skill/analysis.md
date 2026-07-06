# Phase 3 — alias-aware server, lcp-skill re-run (8 F1 cases)

24 runs: 8 F1-sensitive cases (4 fastmcp + 4 cyhole) x 3 reps, arm
`lcp-skill`, model `claude-haiku-4-5-20251001`, claude CLI 2.1.201 (Phase 2b
used 2.1.200 — patch drift, noted), lcp at the Phase 3 alias surface
(commit 252ee4d), `evals/.lcp-cache` cleared so manifests carry aliases.

**Baseline for every comparison below:**
`evals/results/2026-07-06-phase2b-skill-rescored` — the Phase 2b Exp1 runs
re-verified with the same alias-aware verifier this phase ships. Comparing
against the raw 2026-07-03 numbers would double-count the verifier fix.

## Headline

| library | rescored 2b (fair baseline) | Phase 3 run | lcp calls/run (2b → 3) |
|---------|-----------------------------|-------------|------------------------|
| cyhole  | 10/12, misuse 3             | **11/12, misuse 2** | 7.6 → 9.0 |
| fastmcp | 5/12, misuse 10             | 5/12, **misuse 6**  | 1.42 → 2.08 |
| total   | 15/24 (62%), 0.54 misuse/run | **16/24 (67%), 0.33 misuse/run** | — |

Two effects stack for the phase total: the verifier fairness fix alone moved
10/24 → 15/24 on frozen Phase 2b code (see the rescored dir's meta), and the
alias-aware server adds 15/24 → 16/24 on fresh runs, with misuse down ~40%.
Both deltas are within noise individually (n=3/case); the mechanism evidence
below is the stronger signal.

## 1. Do agents copy the alias ids they now see? Yes — directly measured

`tool_call_details` on the cyhole runs shows `get_symbol` being called with
**alias ids** taken from search hits: `cyhole.jupiter:Jupiter`,
`cyhole.birdeye:Birdeye` (3/3 missing-api-key runs, 2/3 birdeye-price runs)
alongside canonical ids — every one resolved (`not_found` empty everywhere).
On the V1/V2 surface these exact ids were the "verify canonical, write
alias" mismatch; now both forms resolve and the `import` line shown is the
documented path. jupiter-swap, the Phase 2b flagship failure (0/3 engaged
passes there), is **3/3** here, and rugcheck-report went 1/3 → 3/3 with all
runs engaged (previously 2/3 of its failures were non-engaged
hallucinations).

## 2. Residual failure patterns (8 failing runs)

- **Non-engagement, the known F1 bimodality (unchanged mechanism):**
  birdeye-price r2 made zero lcp calls and hallucinated root-level
  `cyhole.Birdeye` (the forbidden trap) — the only cyhole failure.
  fastmcp-client r1/r2 and fastmcp-server-tool r2 similarly invented
  `fastmcp.ClientSession`, `fastmcp.client.AsyncClient`,
  `fastmcp.server.Server` without verifying.
- **Task-compliance, not API misuse:** fastmcp-context r2/r3 wrote valid
  code that simply never used the required `fastmcp:Context` (missing, but
  zero unresolved usages) — context regressed 1/3 → 0/3 on this pattern.
- **Engaged-but-wrong residue is nearly gone:** across all engaged runs the
  only unresolved usage is `fastmcp.Context.current` (context r1) — one
  invented classmethod. Zero forbidden symbols on engaged runs.

## 3. fastmcp engagement moved (secondary, treat as tentative)

Voluntary lcp calls on fastmcp rose 1.42 → 2.08/run and the flagship
false-confidence case, fastmcp-server-tool, went **0/3 (all-time zero
before) → 2/3 with full resolve→search→get_symbol chains**. Aliases don't
touch adoption mechanics, so this is either engagement noise (bimodal, n=3)
or a side effect of alias-first hits making the first search response more
obviously useful. Do not claim it as a Phase 3 effect; re-measure in
Phase 8's larger sample. Net fastmcp pass rate stayed 5/12 because the two
context runs traded places with it.

## Verdict for the roadmap log

The alias gap measured in Phase 2b is closed at both ends: the verifier no
longer under-counts valid re-export imports (10/24 → 15/24 on frozen code)
and the server now serves the documented import path as the primary id,
which agents demonstrably copy into their `get_symbol` calls and imports
(15/24 → 16/24, misuse/run 0.54 → 0.33, engaged-run hallucinations ~zero).
Remaining failures are adoption (F1 non-engagement) and task compliance —
not import-path resolution. F2 is done.
