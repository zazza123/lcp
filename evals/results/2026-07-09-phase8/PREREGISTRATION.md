# Phase 8 publication benchmark — pre-registration

Frozen 2026-07-09, before any screening or grid run. Case set approved by
the maintainer (domain expert for cyhole/hamana/pocket-coffea) on
2026-07-09. Any change to cases, arms, metrics, or decision rules after
this commit invalidates the pre-registration and must be reported in the
published page.

## Design

- **Cases:** 84, in `evals/cases-v2/` (frozen at commit `fc0fd11`), across
  11 libraries in three classes:
  - *niche* (7): cyhole 0.3.0, hamana 1.0.1, pocket-coffea 0.9.13,
    narwhals 2.23.0, griffe 2.1.0, cyclopts 4.20.0, pixeltable 0.6.6 —
    8 cases each (56)
  - *churned* (2): fastmcp 3.4.4 (2.x→3.x rewrite), polars 1.42.1
    (renamed pre-1.0 API) — 8 cases each (16)
  - *control/ceiling* (2): requests 2.34.2, flask 3.1.3 — 6 cases each (12)
  - All 84 prompts are NEW (never used in phases 0–4b); every
    required/forbidden symbol was derived by live introspection of the
    pinned environment and validated bidirectionally
    (`run.py validate` = 84 cases, 0 problems).
- **Environment:** bench venv `evals/.venv-bench` (Python 3.12, pins in
  `evals/bench-requirements.lock.txt`); harness at commit `fc0fd11`;
  `claude` CLI 2.1.205; runs billed to the maintainer's subscription
  (costs reported are the CLI's notional `cost_usd`).
- **Models × reps:** `claude-haiku-4-5-20251001` × 5 reps;
  `claude-sonnet-5` × 3 reps. One results dir per model
  (`pub-haiku/`, `pub-sonnet/`).
- **Arms (6)** — same prompt everywhere; arms differ only by CLI
  flags/config:

  | Arm | Difference vs baseline |
  |---|---|
  | `baseline` | headless `claude -p`, all built-in tools denied, no MCP |
  | `lcp` | + `--mcp-config` → `lcp serve-all` (bench venv, `--expose` per library, cache `.lcp-cache-bench`), `--allowedTools mcp__lcp` |
  | `lcp-skill` | `lcp` + `--append-system-prompt` = the SHIPPED plugin skill body (post-screening) |
  | `sitepkg` | no MCP; Read/Glob/Grep re-enabled + system-prompt note naming the site-packages path (the "agent reads the source" honest arm) |
  | `registry` | `lcp` config but the server runs from a BARE venv (no targets installed) — resolution via the public registry |
  | `context7` | + `--mcp-config` → `npx @upstash/context7-mcp`, `--allowedTools mcp__context7`, + the vendor's recommended always-use rule as system prompt (steelman) |

- **Registry-arm coverage (pre-registered exceptions):**
  - 7/11 libraries resolve from the public registry
    (zazza123/lcp-registry, main @ `8483cfd`).
  - fastmcp, cyclopts, griffe are dependencies of lcp itself, so they are
    importable in the bare server venv and resolve via LOCAL SCAN at the
    same pinned versions (3.4.4 / 4.20.0 / 2.1.0). This is inherent to any
    real deployment of the registry server and is reported as such.
  - pixeltable is EXCLUDED from this arm: the registry cannot build its
    manifest (pgvector 0.5.0 upstream breakage; lcp-registry issue #168).
    Its registry-arm cells are recorded as structurally-missing, not as
    failures.
  - The registry's weekly-update workflow was disabled on 2026-07-09 for
    the measurement window (manifest freeze); it is re-enabled when the
    grid completes.
- **Context7 arm:** CONTEXT7_API_KEY unset at freeze (anonymous tier). If
  Context7 rate-limits mid-grid, a key may be added and recorded in
  `meta.json` — it changes quota, not served content. All MCP tool
  RESPONSES (lcp and context7) are recorded in the run files
  (`tool_results`, truncated at 2000 chars) for reproducibility, since
  Context7 content is not pinnable.

## Metrics

**Primary (pre-registered):**
1. **API-misuse rate** — mean `misuse_count`/run (forbidden symbols used +
   unresolved library-rooted attribute chains, via live introspection)
2. **Task pass rate** — share of runs passing all checks
3. **Tokens/task** — mean input+output tokens

**Secondary:** engagement rate (runs with ≥1 `mcp__lcp__*` call;
`mcp__context7__*` in the context7 arm); cost-overhead-when-unused
(notional cost delta of tool-arm runs with 0 MCP calls vs baseline);
per-cell variance with seeded-bootstrap 95% CIs.

**Caveat (pre-registered):** `tool_calls` counts ATTEMPTS, including
permission-denied ones; static verification only (no code execution).

## Interpretation rules

- Effects < 20% relative are noise (Phase 0 rule); per-cell CIs reported.
- The headline number comes from the NICHE-class cells (the target use
  case). Control cells are ceiling context, expected ≈100% pass in every
  arm; churned cells measure stale-training traps.
- If lcp-skill does not beat sitepkg on accuracy, the token/latency delta
  is the story; if it loses both, that is a product finding and gets
  published anyway.
- Registry-arm comparisons for fastmcp/cyclopts/griffe are labeled
  local-scan (see coverage notes) and never counted as registry evidence.

## Error handling

Harness-error records (subprocess timeout, CLI crash, subscription
rate-limit) are deleted and relaunched — the runner skips existing files.
Model outputs are NEVER re-rolled: a completed run is final, regardless of
outcome.

## Screening protocol (runs BEFORE the grid; ships the skill the grid measures)

- **Variants:** B = shipped skill (control; Phase 4b winner),
  A = Phase 4b variant-a file (deferred-tools paragraph on the pre-B
  body), A+B = new file: shipped body + A's paragraph inserted after B's
  unconditional-first-action paragraph.
- **Subset (false-confidence classes — the model wrongly trusts stale
  knowledge):** fastmcp (knows 2.x): `fastmcp-http-transport`,
  `fastmcp-proxy`, `fastmcp-mount`, `fastmcp-openapi`; pocket-coffea
  (knows coffea-0.7 era): `pocket-coffea-configurator`,
  `pocket-coffea-custom-cut`, `pocket-coffea-histograms`,
  `pocket-coffea-custom-workflow`.
- **Runs:** 8 cases × 5 reps × 3 variants = 120, haiku, arm `lcp-skill`,
  one results dir per variant under
  `evals/results/2026-07-09-phase8/screening/`.
- **Disqualification:** engaged-run misuse ≥ 2 → variant out. Exactly 1 →
  that case is re-run ×5 additional reps for that variant; any further
  engaged misuse → out, else the variant stays (incident recorded). (This
  replaces Phase 4b's n=1 disqualification, per the roadmap's Phase 8
  re-measurement note.)
- **Winner:** highest engaged-run count among qualified variants; ties →
  higher overall pass → lower misuse/run.
- **Ship rule:** the winner replaces the shipped B text ONLY if it is not
  B and beats B's engaged count by ≥ 4/40 (+10pp). Otherwise B stays.
  The grid's lcp-skill arm uses whatever is shipped after this rule.
