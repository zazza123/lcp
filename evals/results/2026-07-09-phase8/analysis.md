# Phase 8 publication benchmark — analysis

Computed strictly per `PREREGISTRATION.md` over the frozen grid: **3968 runs**
(haiku 2480 + sonnet 1488), 6 arms, 84 cases, integrity clean (0 error
records, every (case, rep) pair distinct). Pass-rate and misuse CIs are
seeded percentile bootstraps (`harness/stats.py`, n=10 000, seed=42).

## Headline

**On niche and post-cutoff Python libraries — the case LCP is built for — the
shipped LCP plugin lifts a small model's task success rate from 28% to 66%
and cuts its API-misuse rate in half, outperforming an agent that reads the
installed package source.** For a frontier model the same libraries rise from
68% to 92%.

## Per-(model, arm) results

Primary metrics; pass% with bootstrap 95% CI, misuse per run, mean tokens/task,
engagement (share of runs with ≥1 MCP tool call), mean notional cost.

### haiku (`claude-haiku-4-5-20251001`, 5 reps)

| Arm | n | Pass% [95% CI] | Misuse/run | Tokens | Engage% | $ |
|---|---|---|---|---|---|---|
| baseline | 420 | 41.0 [36–45] | 0.70 | 2079 | 0 | 0.016 |
| **lcp-skill** | 420 | **69.0 [65–73]** | **0.35** | 2113 | 70 | 0.056 |
| sitepkg | 420 | 61.4 [57–66] | 0.34 | 2128 | 0 | 0.030 |
| lcp | 420 | 47.1 [42–52] | 0.56 | 1991 | 19 | 0.025 |
| registry | 380 | 41.8 [37–47] | 0.64 | 1960 | 12 | 0.020 |
| context7 | 420 | 41.7 [37–46] | 0.64 | 1985 | 17 | 0.019 |

### sonnet (`claude-sonnet-5`, 3 reps)

| Arm | n | Pass% [95% CI] | Misuse/run | Tokens | Engage% | $ |
|---|---|---|---|---|---|---|
| baseline | 252 | 75.8 [70–81] | 0.22 | 1496 | 0 | 0.069 |
| lcp-skill | 252 | 91.7 [88–95] | 0.04 | 2312 | 100 | 0.228 |
| **sitepkg** | 252 | **92.9 [90–96]** | 0.02 | 1320 | 0 | 0.120 |
| lcp | 252 | 87.7 [83–92] | 0.09 | 1919 | 43 | 0.134 |
| registry | 228 | 74.6 [69–80] | 0.15 | 2588 | 73 | 0.200 |
| context7 | 252 | 75.0 [69–80] | 0.15 | 2112 | 52 | 0.139 |

## Pass rate by library class × arm (the headline lives in *niche*)

Per the pre-registration, the headline comes from the niche cells; control
cells are ceiling context; churned cells measure stale-training traps.

### haiku
| Class | baseline | lcp-skill | sitepkg | lcp | registry | context7 |
|---|---|---|---|---|---|---|
| **niche** | 28.2 | **65.7** | 55.4 | 34.3 | 26.2 | 26.1 |
| churned | 47.5 | 62.5 | 61.3 | 60.0 | 52.5 | 58.8 |
| control | 91.7 | 93.3 | 90.0 | 90.0 | 90.0 | 91.7 |

### sonnet
| Class | baseline | lcp-skill | sitepkg | lcp | registry | context7 |
|---|---|---|---|---|---|---|
| **niche** | 68.5 | 91.7 | **96.4** | 85.1 | 66.7 | 69.0 |
| churned | 95.8 | 91.7 | 87.5 | 100.0 | 87.5 | 89.6 |
| control | 83.3 | 91.7 | 83.3 | 83.3 | 88.9 | 83.3 |

## Reading the result

1. **The shipped product (lcp-skill) is the strongest verified configuration
   on the target workload for a small model.** Haiku niche pass 28.2 → 65.7
   (+37.5pp, +133% relative; CIs disjoint), niche misuse 0.91 → 0.42 (−54%;
   overall-arm misuse 0.70 → 0.35). This is the headline and it clears the
   >20%-relative bar by a wide margin.

2. **The client-side skill is what closes the F1 adoption gap.** Only the
   `lcp-skill` arm carries the plugin skill; the bare `lcp`, `registry` and
   `context7` arms get the server but no task-side nudge. Their engagement is
   low on haiku (12–19%) and their niche pass rate sits at baseline. The
   server's content is not the bottleneck — adoption is, exactly as Phases
   0–2b found, and the skill is the lever (haiku lcp 19% → lcp-skill 70%
   engagement).

3. **Against the honest arm (read the installed source), LCP wins for the
   small model and ties-to-loses for the frontier model — reported plainly
   per the pre-registration.** Haiku: lcp-skill 65.7 beats sitepkg 55.4 on
   niche. Sonnet: sitepkg 96.4 edges lcp-skill 91.7 on niche AND uses fewer
   tokens (1320 vs 2312). For a capable model that can read source
   effectively, reading source is competitive. **But sitepkg only exists when
   the package is installed and its source is readable** — the registry arm
   is LCP's answer for uninstalled/private packages, a capability sitepkg
   structurally lacks. LCP's defensible value is (a) large accuracy gains for
   small/cheap models, and (b) working at all when there is no local source.

4. **Context7 did not move niche accuracy.** Given the same always-use nudge,
   the context7 arm lands at baseline on niche (haiku 26.1 vs 28.2; sonnet
   69.0 vs 68.5). Narrative docs for well-known libraries are not what these
   post-cutoff/private libraries need; introspected ground truth of the
   installed version is. (Context7 responses are recorded in the run files;
   the coverage heuristic was too noisy to quote per-library.)

5. **Churned libraries (fastmcp 2→3, polars pre-1.0 renames):** lcp-skill
   helps haiku (47.5 → 62.5) but sonnet already clears them from parametric
   knowledge (95.8 baseline) — the F4 ceiling effect, now measured on churn.

6. **Controls at ceiling in every arm** (~90% haiku, ~83% sonnet), confirming
   they measure little — as designed.

## Secondary metrics

- **Cost-overhead-when-unused** (tool-arm runs with 0 MCP calls vs baseline
  mean cost): haiku `lcp` +2% (negligible — the consolidated surface adds
  almost nothing when the model doesn't call it), haiku `lcp-skill` +26% over
  126 unused runs. Sonnet `lcp-skill` was essentially always engaged (100%),
  so there is no unused population to penalize.
- **Tokens/task:** lcp-skill is within noise of baseline on haiku (2113 vs
  2079) despite the tool round-trips — the ranked, capped responses keep the
  transcript lean. On sonnet the honest arm is the token-cheapest of the
  assisted configurations.
- **`tool_calls` counts attempts, including permission-denied ones**
  (pre-registered caveat); engagement here is computed from actual
  `mcp__*__*` tool_use blocks, not the raw counter.

## Per-phase delta story (from the roadmap eval log)

Phase 0 baseline (no LCP, haiku, original 28-case set) was 45% overall with
the LCP arm within noise at 52% — because the agent rarely called the tools
(F1). Phases 1–4 fixed the surface and content; Phase 4b shipped the skill
that drives adoption. Phase 8, on a fresh 84-case set weighted to niche
libraries, isolates the payoff: **on the niche workload the shipped plugin
takes haiku from 28% to 66% and halves misuse** — the adoption gap that made
the Phase 0 delta "within noise" is closed where it matters.

## Caveats (honest, pre-registered)

- **Static verification only** — symbol usage is checked against live
  introspection, code is not executed. Misuse = forbidden symbols used +
  unresolved library-rooted attribute chains.
- **Single vendor** — both models are Claude. No non-Claude arm was run
  (decided at phase start); the mechanism (MCP + introspected manifests) is
  vendor-neutral but that is not demonstrated here.
- **Subscription-paced, notional costs** — `cost_usd` is the CLI's reported
  figure, not a billed amount; runs spanned 2026-07-09…18 across quota
  windows. Rate-limited runs were deleted and relaunched; completed runs were
  never re-rolled.
- **Context7 content is not pinnable** — its responses are recorded in the
  run files for reproducibility, but a re-run may see different upstream docs.
- **Registry arm** covers 10/11 libraries at manifest level; pixeltable is
  excluded (upstream pgvector break, lcp-registry issue #168), and
  fastmcp/cyclopts/griffe resolve via local scan in the bare server venv
  because they are lcp's own dependencies (labeled, not counted as registry
  evidence). The aggregated registry *niche* cell above is therefore
  local-scan-inclusive; it sits at baseline regardless and is not a headline.
- **Post-freeze harness commits.** The pre-registration froze the harness at
  `fc0fd11`; the grid ran with two later commits — `bd53ee4` (tool_result
  capture fix) and `03e4c4b` (bootstrap-CI helper), recorded in `meta.json`.
  Both are metric-neutral: engagement derives from `tool_call_details`, and
  pass/misuse from the verifier — neither touches an arm definition or a
  scored field.
