# Phase 8 skill screening — B vs A vs A+B

Protocol: `../PREREGISTRATION.md` (§ Screening protocol). 8 false-confidence
cases (4 fastmcp 3.4.4 + 4 pocket-coffea 0.9.13) × 5 reps × 3 variants,
`claude-haiku-4-5-20251001`, arm `lcp-skill`, CLI 2.1.205, lcp commit
86a1914, cases frozen at fc0fd11. 120/120 runs, 0 harness errors, no
deletions/re-rolls.

## Decision table

| Variant | Engaged /40 | Engaged pass | Engaged misuse (rate) | Non-eng pass | Overall pass /40 | fastmcp eng | pocket-coffea eng |
|---|---|---|---|---|---|---|---|
| B (shipped) | 33 | 7/33 (21%) | 27 (0.82/run) | 0/7 | 7 | 13/20 | 20/20 |
| A | 30 | 9/30 (30%) | 27 (0.90/run) | 0/10 | 9 | 11/20 | 19/20 |
| **A+B** | **36** | 10/36 (28%) | **25 (0.69/run)** | 0/4 | **10** | **17/20** | 19/20 |

## Pre-registration deviation (reported, not silently patched)

The disqualification rule ("engaged-run misuse ≥ 2 → variant out") was
calibrated on the Phase 4b case set, where engaged misuse was ≈0. On this
new, much harder screening subset every variant — including the shipped
control B — shows engaged misuse in the dozens: agents engage the server
and still hallucinate module paths (`pocket_coffea.lib.hist_tools.*`,
`fastmcp.Server`, `Hist.new.Regular`; verified genuine hallucinations,
not verifier artifacts). Applied literally the rule disqualifies all
three variants, control included — a reductio that shows the threshold,
not the variants, is wrong. Applied per its documented intent (a
*relative* guard: a variant that raises engagement must not degrade
engaged quality vs the control), no variant is disqualified: A+B has
*better* engaged quality than B on both pass rate and misuse rate; A is
marginally worse on misuse rate (0.90 vs 0.82) but loses on engagement
count anyway.

**The ship decision is identical under any reading of the DQ rule**, so
the deviation does not affect the outcome.

## Outcome (per the pre-registered winner + ship rules)

- **Winner:** A+B — highest engaged count (36/40), and incidentally best
  on overall pass (10/40) and engaged misuse rate (0.69/run). The A
  mechanism works as designed: the lone-ToolSearch stall drops from 7
  (B) to 4 (A+B) non-engaged runs, with fastmcp engagement 13/20 → 17/20.
- **Ship rule:** winner ≠ B requires engaged ≥ B + 4/40. A+B is +3
  (36 vs 33) → **threshold not met → B stays shipped.** The publication
  grid's `lcp-skill` arm measures the unchanged shipped skill
  (`plugin/lcp/skills/lcp-universal/SKILL.md`, byte-identical to
  `variant-b/SKILL.md`).
- A+B's +3 engagement / −0.13 misuse-rate improvement on n=40 is recorded
  as a post-launch candidate; re-evaluate with grid-scale data.

## Notes for the grid analysis

- These 8 cases are the hardest false-confidence subset; overall pass
  7–10/40 here is NOT representative of the full 84-case set.
- Engaged-but-hallucinating (tool calls followed by invented module
  paths) is a failure mode the Phase 0–4 case set never surfaced —
  track it as its own bucket in the Task 13 analysis.
