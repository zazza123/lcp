# Agentic Improvements Roadmap

> **How to use this document:** This is the master roadmap, not an executable
> implementation plan. Each phase below is a self-contained work package that
> will be executed in its own session. At the start of each phase session:
> read this document, settle the phase's **Open decisions**, then use
> `superpowers:writing-plans` to produce the detailed TDD implementation plan
> (`docs/superpowers/plans/YYYY-MM-DD-phase-N-<name>.md`) from the phase
> section. After a phase lands, update its **Status** line and the
> **Eval results log** at the bottom.

**Goal:** Make LCP the most token-efficient, verifiably accurate way for AI
coding agents to consume Python library APIs — and prove it with a benchmark.

**Strategy (agreed 2026-07-02):** Build the measurement harness first
(private, cheap), then change interface and manifest content (phases 1–4),
then infrastructure and distribution (phases 5–7), and only then run and
publish the full benchmark (phase 8). Everything that changes the manifest
format or the MCP tool surface happens **before** the registry is populated.

**Ordering rationale:**

1. Without a baseline measurement, improvement claims are guesses (Phase 0).
2. The MCP tool surface defines what everything else is measured and
   documented against — change it first (Phases 1–2).
3. Manifest content changes (aliases, structured docs) must be frozen before
   mass-publishing manifests, or the registry gets regenerated twice
   (Phases 3–4 before Phase 7).
4. Docs describe interface + format, so a full docs pass only pays off once
   those stop moving (Phase 6). Exception: docs that are *factually wrong
   today* get fixed immediately (Phase 6a is unblocked from day one).
5. The published benchmark is the launch asset; it runs on the finished
   product (Phase 8).

**De-scoping rule (if the timeline slips):** cut from Phase 4 (doctest
extraction) and Phase 7 (population breadth: 100 libraries instead of 500),
never from Phases 2–3. A correct interface with less content beats the
opposite.

## Global constraints

- Python `>=3.10`; core deps stay minimal (`pydantic>=2`, `click>=8`,
  `jsonschema>=4`, `fastmcp>=2`). New runtime deps need explicit sign-off in
  the phase's design decision.
- LCP schema version stays `"1.0"`; all manifest additions must be
  backward-compatible (additive fields only — `extra="allow"` already
  guarantees old consumers tolerate them). If a change cannot be additive, it
  blocks on a `"1.1"` schema decision — flag it, don't improvise.
- Commits follow the `git-commit-convention` skill; docs follow the
  `lcp-writing-documentation` skill (architecture vs guides vs API-reference
  conventions).
- Every phase ends with: full test suite green (`pytest`), docs updated,
  `mkdocs build --strict` clean, and (for phases 2–4) an eval-harness run
  recorded in the results log.
- **Docs-alignment rule:** from Phase 2 onward, any phase that changes
  behavior, the MCP surface, or the manifest format MUST update the
  user-facing docs (`docs/guides`, `docs/spec`, `docs/cli.md`, plugin skills)
  via the `lcp-writing-documentation` skill *in the same phase* — that is the
  shipped documentation; keep it aligned as you go, don't defer it all to
  Phase 6. (Design-only phases like Phase 1 have no user docs to touch.)
- **Internal-docs handling:** `docs/superpowers/` is gitignored; phase
  deliverables there (this roadmap, design specs) are force-added
  (`git add -f`) onto `roadmap/agentic-improvements`. Before that branch
  merges into `main`, strip `docs/superpowers/` (see post-roadmap cleanup) so
  `main` never carries internal working docs.

---

## Phase 0 — Eval harness (baseline measurement)

**Status:** done (2026-07-03) — harness in `evals/`, baseline in
`evals/results/2026-07-03-baseline/`, plan:
`docs/superpowers/plans/2026-07-02-phase-0-eval-harness.md`. Key finding:
haiku rarely calls the lcp tools voluntarily (mean 1.7 calls/run), so the
LCP-arm delta (+7pp pass rate) is within noise — closing that adoption gap
is what phases 1–2 must move.

**Objective:** A small, private, repeatable benchmark that measures how often
a coding agent misuses library APIs, with and without the LCP MCP server —
run it once now to record the baseline before any change.

**Why first:** every subsequent phase claims to reduce hallucination or token
cost; without a baseline those claims are unfalsifiable, and effort keeps
flowing to features that don't move the metric.

**Scope (in):**
- `evals/` top-level directory (not part of the `lcp` package, not shipped in
  the wheel).
- 20–30 task cases as YAML/JSON files:
  `{library, version, prompt, checks}` where checks are
  `forbidden_symbols` (APIs that don't exist — the hallucination trap),
  `required_symbols` (the correct API), and optionally a `run` smoke command.
- Target libraries: lesser-known and/or recently-churned APIs where training
  data is stale (candidates: `polars`, `httpx`, `textual`, `pydantic` v2
  migration surface, `fastmcp` itself, one or two niche libs). Avoid
  requests/numpy-class libraries the model already knows cold.
- Runner script (`evals/run.py`): invokes `claude -p` (headless) per task,
  in two configurations (with / without the lcp MCP server configured),
  captures the generated code, verifies symbol usage **against live
  introspection** (reuse `lcp.scanner`), and emits a JSON + Markdown report.
- Metrics: API-misuse count per task, task pass rate, tokens + tool-call
  count per task (from the transcript).
- Baseline run: 3 repetitions per configuration, results committed to
  `evals/results/` and summarized in the log at the bottom of this file.

**Scope (out):** CI integration, dashboards, publishing anything, task-count
beyond ~30, non-Claude agents (defer to Phase 8).

**Code notes (2026-07-02 review):**
- LCP arm vs baseline arm: same `claude -p` invocation, the only difference
  being `--mcp-config` pointing at a config that launches `lcp serve-all`.
  Disable web tools in both arms, otherwise you measure internet access, not
  LCP.
- Use `--output-format json` to get token usage and tool-call counts from
  the transcript without parsing text.
- Symbol verification should reuse `lcp.scanner.scan_package` (or plain
  `importlib` + `getattr` walks) against the *pinned* library version — a
  regex-only check misses `obj.method()` misuse on returned objects, which
  is exactly the hallucination class LCP claims to fix.

**Critical caveat (measurement noise):** agents are stochastic; with ~30
tasks, a single run cannot distinguish a 5% delta from noise. Mitigation:
3 repetitions minimum, report per-task misuse *counts* (not just pass/fail),
and treat only large effects (>20% relative) as signal during phases 2–4.
The gate between phases is "no regression + plausible improvement", not
statistical proof — that's what Phase 8 is for.

**Open decisions (settle at phase start):**
- Exact task list and library set.
- Whether checks run as static verification only (grep generated code for
  symbol usage, verify via introspection) or also execute the code. Static
  only is acceptable for the baseline.
- Which model/agent config to pin for comparability across phases.

**Exit criteria:** `evals/run.py` produces a report end-to-end; baseline
recorded in the results log; a `evals/README.md` documents how to re-run.

---

### Phase 0 baseline findings (2026-07-03) — evidence for later phases

Per-library numbers behind the aggregate 45%→52%; referenced below as F1–F4.
Full data: `evals/results/2026-07-03-baseline/` (per-run JSON incl. generated
code and verification detail).

- **F1 — Adoption gap (the bottleneck).** The agent does not call the lcp
  tools precisely where it errs most: fastmcp scored 1–2/12 with 12/24 runs
  hallucinating `fastmcp.Server` (confusion with the official `mcp` SDK), yet
  made **zero** lcp tool calls in the LCP arm. The model doesn't know that it
  doesn't know, so it never asks. Manifest quality is irrelevant until the
  agent queries the server. → attacked by Phases 1–2 (tool naming,
  descriptions, MCP `instructions`, plugin skills).
- **F2 — Information→code gap.** On cyhole (unknown lib) the agent *does*
  call tools (4.3/run) but still scored 0/12: it writes
  `from cyhole import Rugcheck` (root doesn't re-export) and invents method
  names (`get_risk_report` vs the real `get_token_report`). Tool responses
  don't currently make the correct import path obvious. → attacked by
  Phase 3 (aliases) and the Phase 1 response-shape decisions (`get_symbol`
  should state how to import the thing).
- **F3 — Proof of concept.** hamana: 7.6 tool calls/run → pass rate doubled
  (2/12→4/12), misuse halved (6→3). Where the agent engages, the mechanism
  delivers.
- **F4 — Ceiling + noise calibration.** pydantic/httpx/polars are at ceiling
  (30/36 baseline) with 0 tool calls even in the LCP arm — they measure
  little. textual "improved" 5/12→7/12 with zero tool calls in both arms:
  pure stochasticity, validating the >20%-relative-effect rule. LCP arm cost
  overhead when tools go unused: +48% cost, +9% tokens/task. → informs the
  Phase 8 task mix and metrics.

---

## Phase 1 — "V2 surface" design spec (interface + manifest additions)

**Status:** done (2026-07-03) — spec at
`docs/superpowers/specs/2026-07-03-v2-surface-design.md`; every open decision
below has a written answer with rationale (D0–D12). Key settlements:
FastMCP target `>=3.0,<4` (migrate in Phase 2, not a new phase); `list_symbols`
folded into `search`; structured error dicts everywhere; `library` required
when ≥2 libs loaded; `lcp serve` deprecated → `serve-all --expose`; alias =
additive `Symbol.aliases: list[str]` with index-time member expansion;
docstrings parsed via `docstring_parser` (core dep, generate-time only);
all additive under schema `"1.0"`.

**Baseline evidence (2026-07-03):** F1 makes tool *adoption* the design's
first-class goal — tool names, descriptions and the MCP `instructions` field
must be written so an agent that is guessing gets nudged to resolve+search
first (fastmcp: 11/12 failures, zero calls). F2 binds the response-shape
decisions: `search`/`get_symbol` results must carry the importable path
(alias-aware) prominently, not just the definition-site ID.

**Objective:** One short design document
(`docs/superpowers/specs/YYYY-MM-DD-v2-surface-design.md`) that settles,
*together*, every decision phases 2–4 implement — so the tool surface and the
manifest additions are designed as a coherent whole and the schema is touched
once, not three times.

**Why a separate phase:** phases 2, 3 and 4 are one product decision wearing
three implementation hats. Designing them independently risks e.g. an alias
representation that the consolidated `get_symbol` can't serve efficiently.

**Decisions the spec must settle:**

*MCP surface (feeds Phase 2):*
- Final tool set — working proposal, to be confirmed:
  1. `resolve_library(name, version?)`
  2. `search(query, library?, kind?, limit?)` — ranked, capped, the primary
     entry point
  3. `get_symbol(ids: list[str], library?)` — batch; classes include members
     inline (summaries), functions include full signature + structured docs
  4. `get_overview(library?)` — manifest metadata + module tree with symbol
     counts (replaces `get_manifest` + `list_modules`). **Settled (spec D3):**
     `list_symbols` is removed — browse is `search("", module=…, kind=…)` with
     deterministic `(kind, name)` order, structure is `get_overview`.
- Removals: `get_usage_guide` (content moves to the MCP `instructions` field
  and tool descriptions), `get_suggestions` (bag-of-words matcher; an LLM
  with good `search` beats it), `explore_return_type` (its useful part —
  "return type X is class `mod:X`" — folds into `get_symbol`'s
  `usage_hints`).
- Whether `library` becomes required when ≥2 libraries are loaded (recommended:
  yes, return a structured error listing loaded libraries) vs keeping the
  implicit last-resolved default.
- Response shape and hard caps: search default `limit=20` with
  `"truncated": true` signal; a max-bytes guard on every list-returning tool.
- Error convention: FastMCP `ToolError` vs `{"error": ...}` dicts — pick one,
  apply everywhere (recommended: structured error dicts with a stable shape,
  since agents recover from data better than from protocol errors — but
  decide and document).
- Single-library `lcp serve` mode: keep in sync with the same surface
  (thin wrapper), or deprecate in favor of `serve-all --expose`? (Recommended:
  the latter; one surface to maintain and document.)

*Manifest additions (feeds Phases 3–4):*
- Alias representation (recommended: additive `aliases: list[str]` field on
  `Symbol`, IDs stay at definition site, `LCPIndex` indexes aliases too;
  alternative: canonical-ID-at-reexport-site — rejected unless the spec
  review finds ID stability problems with aliases).
- Structured docstring fields: `Param.description`, `Signature.raises`,
  `semantics.examples` populated from parsed docstrings; which docstring
  styles (Google, NumPy, reST) and which parser dependency (see Phase 4).
- Version bump policy: confirm all changes are additive under schema `"1.0"`,
  or explicitly open the `"1.1"` question.

**Exit criteria:** spec merged; each open decision above has a written
answer with a one-line rationale; phases 2–4 sections of this roadmap
updated if the spec contradicts them.

---

## Phase 2 — MCP consolidation

**Status:** done (2026-07-03) — plan:
`docs/superpowers/plans/2026-07-03-phase-2-mcp-consolidation.md`. Shipped: the
four-tool V2 surface (resolve_library/search/get_symbol/get_overview) behind a
single `_register_tools()` path, `LCPServer` replacing `tool_funcs`, D5 error
dicts + D7 disambiguation, byte caps (25k default, `--max-response-bytes`),
`fastmcp>=3.0,<4`, `lcp serve` deprecated (D8), plugin + docs aligned. Eval
re-run recorded below; exit-criteria delta: LCP-arm cost overhead 48%→7% with
output tokens below the baseline arm, plugin smoke test answered a signature
question in exactly 3 calls. **F1 residual (recorded per the gate rule):**
fastmcp-class adoption stayed at 0 voluntary calls across two instruction
iterations even though a probe confirmed the server `instructions` reach the
model verbatim and cyhole/hamana (known-unknown libs) do get calls — with
haiku headless this is a model-compliance limit, not a discovery failure. The
remaining F1 levers are client-side (the plugin skills, which this harness
deliberately excludes) and the Phase 8 task mix/model choice — **probed with
data in Phase 2b below before any new phase is added.**

**Baseline evidence (2026-07-03):** this phase carries F1 — the skills/
`instructions` rewrite is where "the agent never asks" gets fixed. The
phase-end eval re-run has a concrete target beyond pass rate: mean voluntary
tool calls on the fastmcp/cyhole-class cases must rise from ~0/4.3 per run
(if adoption doesn't move, iterate on descriptions before closing the phase).

**Objective:** Implement the tool surface decided in Phase 1 in
`src/lcp/mcp_server.py`; update the plugin skills to match.

**Scope (in):**
- Rework `create_universal_server` (and `create_server` per the Phase 1
  decision) to the new tool set: ranked+capped `search`, batch `get_symbol`
  with inline class members, `get_overview`, `instructions` field on the
  FastMCP server.
- Search ranking (no new deps): exact name match > name prefix > name
  substring > summary substring > description substring; stable
  tie-break by ID. Cap + truncation flag.
- Consistent error shape everywhere; explicit error when `library` is
  ambiguous (per Phase 1 decision).
- Remove `mcp.tool_funcs` attribute-stuffing: expose tool callables through a
  proper return type or module-level registry that tests import.
- Update `plugin/lcp/skills/lcp-universal/SKILL.md`,
  `plugin/lcp/skills/lcp-usage/SKILL.md`, `plugin/lcp/commands/*.md`, and
  `plugin/lcp/agents/library-explorer.md` to the new workflow (the
  recommended path should be ≤3 calls: resolve → search → get_symbol).
- Tests: rewrite `tests/test_mcp_server.py` around the new surface; add
  ranking, cap/truncation, batch, ambiguous-library, and error-shape cases.

**Scope (out):** manifest format changes (Phase 3–4), subprocess scanning
(Phase 5), docs site pages (Phase 6 — but keep docstrings accurate, they
feed the API reference).

**Code notes (2026-07-02 review):**
- `search_symbols` is an unbounded O(n) substring scan, and `list_symbols()`
  with no filters returns every symbol in the library
  (`src/lcp/mcp_server.py:636`, `:1223`, `:549`, `:1124`) — the caps fix a
  real context-blowout, not a theoretical one.
- `get_usage_guide` is duplicated verbatim in both servers (`:461`, `:1005`);
  its content maps 1:1 onto the `FastMCP(name, instructions=...)` constructor
  argument, confirmed present in the installed 2.14.4 and retained in 3.x.
  (The comment at `:1472` claiming FastMCP 3.x is wrong — the project runs
  2.14.4.) **Spec D0:** this phase migrates the pin to `fastmcp>=3.0,<4`
  while it rewrites the surface; verify on 3.x: tool registration + the
  `tool_funcs` replacement (preload depends on it), the `instructions`
  argument, and in-process tool invocation used by tests.
- The implicit default library is `MultiLibraryIndex._default`, silently
  reassigned by every `add()` (`:65-68`) — that is the race behind the
  ambiguous-`library` decision.
- `explore_return_type` matches classes via `type_part.endswith(class_name)`
  (`:766`, `:1372`) → false positives (e.g. `PurePath` matching a `Path`
  lookup). The salvageable behavior is resolving `returns` to a class ID
  inside `get_symbol`'s `usage_hints`; the
  `return_type.startswith(("str", "int", ...))` suggestion heuristic
  (`:630`) should not survive the fold.
- The single-library server duplicates ~450 lines of the universal one —
  whatever the `lcp serve` keep/deprecate decision, deduplicate the
  implementations (one tool-registration function parameterized by an index
  provider).
- Today's error shapes are inconsistent: dict-returning tools emit
  `{"error": ...}`, list-returning tools emit `[{"error": ...}]`.
- `mcp.tool_funcs` (`:1474-1484`) is also load-bearing for `preload` —
  replacing it changes the preload loop too.

**Files:** `src/lcp/mcp_server.py`, `src/lcp/cli.py` (serve/serve-all
options), `tests/test_mcp_server.py`, `tests/test_serve_all_expose.py`,
`plugin/lcp/skills/*`, `plugin/lcp/commands/*`, `plugin/lcp/agents/*`.

**Exit criteria:** tests green; eval harness re-run recorded (expect: fewer
tool calls and tokens per task at equal or better accuracy); plugin smoke
test — `lcp serve-all` under Claude Code resolves a library and answers a
signature question through the new surface in ≤3 tool calls.

---

## Phase 2b — Adoption probes (decide the F1 lever with data)

**Status:** done (2026-07-04) — **outcome A: the shipped plugin skill closes
F1.** Exp1 (arm `lcp-skill` = `lcp` + the `lcp-universal` SKILL.md body
verbatim, pinned haiku, V2 surface) moved fastmcp from 0.0 voluntary lcp
calls/run (both Phase 2 instruction iterations) to **1.42/run** — gate
(≥1.0) passed; pass rates followed (fastmcp 3/12 vs 1/12 ref, cyhole 7/12 vs
2–4/12, cyhole engagement 2.3–3.6 → 7.6 lcp calls/run). Engagement is
bimodal: a run either ignores the tools or commits to a full
resolve→search→get_symbol chain. Exp2 (sonnet, both arms, no skill):
0.00 lcp calls in both arms but baseline at ceiling (12/12, zero misuse) —
the F1 false-confidence failure is haiku-class-bound; for capable models
these cases can't differentiate (Phase 8 task-mix note). **Binding
consequence: Phase 8's harness MUST include an `lcp-skill` arm** — without
it the benchmark measures a product configuration nobody installs. No new
phase needed. Results: `evals/results/2026-07-03-phase2b-{skill,sonnet}/`
(each with `analysis.md`); plan:
`docs/superpowers/plans/2026-07-03-phase-2b-adoption-probes.md`. Secondary
finding for Phase 3: on engaged cyhole runs the only residual failure
pattern is "verify canonical id, write the package-root re-export import"
(all 3 jupiter-swap failures) — zero hallucinated symbols on engaged runs.

**Objective:** Phase 2 falsified the server-side persuasion lever (D9) for
haiku-class agents; before adding any new phase, run two cheap, targeted
experiments that determine *which* remaining lever closes the F1 adoption
gap — the plugin skill (client-side, shipped but never measured) or model
class — and only add a "forcing functions" phase if both fail.

**Evidence this phase rests on (2026-07-03, Phase 2 close — do not re-derive):**
- **E1 — Instructions reach the model and are ignored.** A probe run quoted
  the server `instructions` back verbatim (they ARE in context), yet fastmcp
  cases stayed at **0 voluntary tool calls across two instruction
  iterations** (conditional wording, then unconditional "verify EVERY
  library"). Persuasion-by-server-text is exhausted for haiku headless.
- **E2 — Adoption exists where the model knows it doesn't know.** cyhole
  2.3–4.3 calls/run (pass 0/12 → 4/12 across baseline → phase2 → iter2,
  the F2 import-line fix working), hamana engaged at 1.0 calls/run. The
  failure is confined to libraries the model *wrongly thinks it knows*
  (fastmcp ↔ official `mcp` SDK confusion).
- **E3 — The shipped F1 lever was never measured.** The harness deliberately
  denies skills/built-ins; real developers install the plugin whose
  `lcp-universal` skill fires task-side. The Phase 2 smoke test showed the
  3-call path works perfectly *when the workflow is in the prompt* — which
  is what a skill does.
- **E4 — Instructed-agent efficiency is solved.** Cost overhead 48%→7%,
  output tokens below the no-LCP arm; whatever 2b finds, the consolidated
  surface is not the bottleneck.

**Scope (in):**
- Harness: third arm `lcp-skill` (= `lcp` + `--append-system-prompt` with the
  `lcp-universal` SKILL.md body — approximates plugin-skill activation),
  `--model` override, and per-run `tool_call_details` capture (names + key
  args) so adoption *quality* (did it get_symbol what it used?) becomes
  analyzable. Unit tests in `evals/tests/`.
- **Exp1 (skill arm):** 8 F1-sensitive cases (4 fastmcp + 4 cyhole) × 3 reps,
  arm `lcp-skill`, pinned haiku. Gate metric: mean voluntary calls on the
  fastmcp cases.
- **Exp2 (model probe):** 4 fastmcp cases × 3 reps × both arms with
  `--model claude-sonnet-5`, no skill. Does a stronger model adopt
  spontaneously from instructions alone?
- **Decision rule (record the outcome, then stop):**
  - **A.** Exp1 fastmcp ≥1.0 calls/run → the shipped plugin closes F1: no new
    phase; Phase 8 MUST include an `lcp-skill` arm or it benchmarks a product
    nobody installs.
  - **B.** Exp1 ~0 but Exp2 ≥1.0 → F1 is model-bound: no new phase; record as
    product guidance (small models need the skill/forcing, capable models
    self-serve) and fold into the Phase 8 model mix.
  - **C.** Both ~0 → persuasion is dead in all shipped channels: add a
    "Phase 2c — adoption forcing functions" section (plugin hook that
    intercepts unverified third-party imports at Write/Edit time and
    suggests `resolve_library`; `/lcp:resolve` promotion) — 2b's last task
    drafts that section from the collected data.
- Secondary analysis from `tool_call_details` (feeds Phase 3): on engaged
  cyhole runs, are the symbols used in the generated code the ones actually
  fetched via `get_symbol`, or does the model verify A and write B?

**Scope (out):** implementing forcing functions (that is the conditional
Phase 2c), any `src/lcp/` change, non-Claude agents, statistical claims
(n stays small; this phase picks a lever, Phase 8 proves it).

**Code notes (2026-07-03):**
- `evals/harness/agent.py:29` `build_command(prompt, arm, mcp_config)` — arms
  differ only by flags; extend with `model` and `append_system` params, keep
  the single-flag-difference discipline. `MODEL` pin at `:11`.
- `evals/run.py:105` arms list, `:151` `--arms` choices, `:50` `_run_one`
  (records `model` per run at `:60` — thread the override through).
- Skill body: `plugin/lcp/skills/lcp-universal/SKILL.md` minus the YAML
  frontmatter; inject verbatim, do not paraphrase (we are measuring the
  shipped artifact).
- `parse_stream` (`agent.py:59`) already walks assistant tool_use blocks —
  collect `{"name", "input"}` there for `tool_call_details`.
- Model id for Exp2: `claude-sonnet-5`.
- Run from `evals/.venv` (fastmcp 2.14.4 runtime constraint — see
  `evals/README.md` note).

**Exit criteria:** both experiments run and committed under `evals/results/`;
eval log updated; the A/B/C decision written into this file (either "no new
phase — rationale" or a drafted Phase 2c section); harness changes merged
with tests green.

---

## Phase 3 — Re-export aliases

**Status:** done (2026-07-06) — plan:
`docs/superpowers/plans/2026-07-06-phase-3-reexport-aliases.md`. Shipped: the
scanner records intra-package re-exports as aliases on the canonical symbol
(external re-exports stay skipped; `__all__`, star and `as`-renamed
re-exports covered via the `tests/sample_package` fixture); additive
`Symbol.aliases` under schema `"1.0"` (both schema.json copies, old
manifests still validate); `LCPIndex` maps alias ids — including
build-time-derived class-member ids — to canonicals, and `search`/
`get_symbol` are **alias-first** (preferred importable id presented,
`resolved_via_alias` names the definition site, `import` line always the
documented path; decisions settled with the user 2026-07-06). Harness
co-fix landed in the same phase: `symbol_used` matches by live
object-identity plus a new `rescore` subcommand. Eval: rescoring frozen
Phase 2b runs with the fair verifier moved 10/24 → 15/24 (all 3
jupiter-swap flips — the exact predicted blind spot); the fresh
alias-server run adds 15/24 → 16/24 with misuse/run 0.54 → 0.33 and
`tool_call_details` showing agents copying alias ids into `get_symbol`
calls. Residual failures are F1 non-engagement and task compliance — F2
(information→code gap) is considered closed. Secondary, tentative:
fastmcp-server-tool engaged for the first time ever (0/3 all-time → 2/3,
calls 1.42 → 2.08/run) — re-measure in Phase 8, do not attribute.

**Baseline evidence (2026-07-03):** F2 is this phase's live repro: cyhole LCP
runs called the tools yet wrote `from cyhole import Rugcheck` (0/12 passes) —
"agents think in documented import paths" is now measured, not asserted. The
eval harness has 8 cyhole/hamana cases specifically sensitive to this fix.

**Objective:** A symbol re-exported at package level is findable under the
name users actually import: `requests.get` resolves even though it is defined
in `requests.api`.

**Why:** today `scan_module` skips any object whose `__module__` differs from
the scanning module (scanner.py, re-export check), so the most user-visible
names — package-root re-exports listed in `__all__` — are reachable only
under their definition path. Agents think in documented import paths; this is
the single most expensive usability bug.

**Scope (in):**
- Scanner: when a module (especially a package `__init__`) re-exports an
  object (`__module__` differs but the name is in `__all__`, or the module is
  the package root), record an alias `(module_path, name)` on the scanned
  symbol instead of dropping it silently. Definition site remains canonical.
- Generator: emit the additive `aliases` field per the Phase 1 decision.
- `LCPIndex._build_indexes`: index aliases so `get_symbol("requests:get")`
  and `search("get")` both hit; alias hits marked in responses
  (`"resolved_via_alias": "requests.api:get"`-style, exact shape per Phase 1).
- Edge cases that must have tests: `__all__` re-export, star re-export
  without `__all__`, aliased name (`from x import y as z`), class re-export
  whose members must be reachable via both IDs, name collisions (two modules
  re-exporting different objects under the same name), and the existing
  skip-external-modules behavior must not regress.
- Regenerate `tests/sample_module.py` fixtures / add a re-exporting fixture
  package under `tests/`.

**Scope (out):** rewriting IDs to re-export sites; alias support in the
registry `latest.json` (nothing changes there — aliases live inside the
manifest).

**Code notes (2026-07-02 review):**
- The exact skip is `src/lcp/scanner.py:453-457`: any object with
  `obj.__module__ != module_path` → `continue`. The `__all__` allowlist
  computed at `:428-431` is only used to *filter*, never to record the
  re-export — that is the hook point.
- Concrete repro: `requests.get.__module__ == "requests.api"`, so a scan of
  `requests` yields only `requests.api:get`.
- IDs are assembled in `generator._build_symbol_id`
  (`src/lcp/generator.py:51-63`) as `module_path:qualified_name`; modules use
  an empty entity path (`"pkg:"`) — alias IDs must follow the same grammar.
- Class-member lookups key on the `#`-prefix (`LCPIndex._build_indexes`,
  `src/lcp/mcp_server.py:43-46`): if `requests:Session` becomes an alias,
  members must be reachable as `requests:Session#get` too — decide whether
  the index maps alias-prefixed member IDs to canonical ones or materializes
  alias entries per member.
- Aliasing must not defeat the id-based `_visited` module dedup nor trigger
  re-scans — record aliases during the existing pass, don't add a second one.
- **Phase 2b evidence (2026-07-04):** the alias gap is now measured
  end-to-end on engaged agents, not just asserted: in the Exp1 skill-arm
  runs all 3 cyhole-jupiter-swap failures fetched the canonical
  `cyhole.jupiter.interaction:Jupiter` via `get_symbol` and still wrote
  `from cyhole.jupiter import Jupiter` (valid re-export) — agents write the
  package-root import even *after* verifying the canonical id. See
  `evals/results/2026-07-03-phase2b-skill/analysis.md`.
- **Harness co-fix required:** `evals/harness/verify.py::symbol_used` has
  the same canonical-only blind spot — it must accept alias paths in this
  phase, or the eval re-run will under-count the improvement this phase
  ships (jupiter-swap alone is +3/12 cyhole passes in the Phase 2b data).

**Files:** `src/lcp/scanner.py`, `src/lcp/generator.py`,
`src/lcp/models.py` (additive `Symbol.aliases`), `src/lcp/mcp_server.py`
(index + lookup), `src/lcp/schema.json` + `docs/assets/schema.json`,
`tests/test_scanner.py`, `tests/test_generator.py`,
`tests/test_mcp_server.py`, new fixture package.

**Exit criteria:** `get_symbol("requests:get")` (or equivalent fixture)
resolves; eval harness re-run recorded — this phase is the one expected to
show the clearest accuracy delta; schema files updated and `lcp validate`
accepts both old and new manifests.

---

## Phase 4 — Structured docstrings + examples

**Status:** done (2026-07-07) — plan:
`docs/superpowers/plans/2026-07-07-phase-4-structured-docstrings.md`. Shipped:
`docstring_parser` as a core dep (D11 sign-off); new `src/lcp/docstrings.py`
with fail-open `extract_structured()` (Google + NumPy; params, raises,
returns, doctest/verbatim examples); scanner captures the raw docstring
(capture only — resilience untouched); generator merges docstring params by
name (introspection wins, unmatched entries never invent a `Param`),
`semantics.description` keeps the full raw remainder (the parser drops
mid-docstring `Note:`-style sections, so rebuilding it would lose prose);
additive `Signature.returns_description` under schema `"1.0"` (settled with
the user — `type_ref` has no description slot; both schema copies updated);
`get_symbol` drops trailing examples before the description under the 25k cap
(`examples_truncated`). Exit criteria (measured): documented params with
description 98.9–99.6 % on fastmcp/polars/click (threshold ≥90 %); manifest
gzip growth ×1.09–1.28 (≤2×, inline-vs-lazy not reopened); polars
`DataFrame` entry 24 791 B under the cap. Doctest extraction was NOT
de-scoped. Eval re-run recorded (see log + analysis.md: engaged-run quality
unchanged, topline delta is F1 engagement variance). **The manifest format
is now FROZEN for Phase 7 registry population** — additive ideas discovered
from here on are post-launch.

**Objective:** Populate the fields that differentiate LCP from "type stubs in
JSON": per-parameter descriptions, `raises`, and usage examples extracted
from docstrings and doctests.

**Scope (in):**
- Docstring parsing (Google + NumPy styles minimum) → `Param.description`,
  `Signature.raises` (`RaisesEntry.type` + `condition`), `returns`
  description. Dependency decision from Phase 1: `docstring_parser` is the
  obvious candidate (~pure-python, small); if rejected, a minimal in-house
  Google-style parser is acceptable but must be scoped to sections
  (`Args/Returns/Raises/Examples`) only — no attempt at full reST.
- Doctest / `Examples:` section extraction → `semantics.examples`
  (`Example.code` + `description`). Use the stdlib `doctest` parser for
  `>>>` blocks; fenced/indented code in `Examples:` sections taken verbatim.
- Generator wires parsed structures into the models; `description` keeps the
  *unparsed remainder* so no information is lost when parsing fails.
- Parsing must be fail-open: any parser exception falls back to today's
  behavior (summary + raw description). The scanner's resilience guarantees
  (hostile packages) must not regress — parse at generator level, not during
  member iteration.
- `get_symbol` response includes the structured fields; check response size
  on a heavy real library (e.g. pandas `DataFrame`) against the Phase 2 caps.
- Tests: parametrized docstring fixtures (Google, NumPy, malformed, empty,
  non-string `__doc__`), doctest extraction, generator integration, MCP
  response shape.

**Scope (out):** AI-generated docs (the `ai/` module is a separate product
surface and stays untouched), reST/Sphinx field lists, cross-reference
resolution inside docstrings, `effects`/`stability` inference (revisit after
Phase 8 with data).

**De-scope line (pre-agreed):** if the phase runs long, ship docstring
parsing without doctest extraction and move examples to a follow-up.

**Code notes (2026-07-02 review):**
- No model changes needed: `Param.description`, `RaisesEntry`, `Example`,
  `Semantics.examples` all already exist in `src/lcp/models.py` — the
  generator just never fills them (`src/lcp/generator.py:98` hardcodes
  `raises=None`, `:110` hardcodes `examples=None`).
- `scanner._parse_docstring` (`src/lcp/scanner.py:70-100`) keeps the entire
  post-summary remainder as `description` and guards non-string `__doc__`
  (sympy exposes it as a property) — preserve both behaviors.
- Merge docstring params with introspected params *by name*; introspection
  wins on existence and type. Docstrings routinely document renamed or
  removed params — an unmatched docstring entry must never invent a `Param`.
- Complex defaults are serialized as the placeholder `"..."`
  (`src/lcp/generator.py:77`); the docstring often states the real default in
  prose — keeping that prose in `Param.description` is the cheap fix.

**Files:** `src/lcp/generator.py` (or a new `src/lcp/docstrings.py` —
decide in the phase plan), `src/lcp/models.py` (nothing new expected —
fields exist), `pyproject.toml` (dependency, if approved),
`tests/test_generator.py`, new `tests/test_docstrings.py`.

**Exit criteria:** on a real library scan, ≥X% of documented params carry
descriptions (set X from a quick pre-measurement, don't guess); eval re-run
recorded; manifest size growth measured and reported (gzip) — if manifests
balloon >2×, revisit what `get_symbol` inlines vs. lazy-loads.

---

## Phase 4b — Engagement iteration (skill + hooks)

**Status:** not started — unblocked (added 2026-07-07 after the Phase 4
retrospective; uses only the existing harness, no manifest/server changes)

**Objective:** Raise lcp-skill engagement on the 8 F1 cases from the current
13–15/24 to **≥18/24** without degrading engaged-run quality, by iterating on
the plugin skill text and the plugin hooks — not on the server.

**Why:** Phases 3–4 proved the product claim: engaged runs pass 27/28 with
**zero** misuse, and every measured hallucination sits in a non-engaged run.
Content work is frozen (Phase 4); engagement (F1) is now the binding
constraint, and it is also the cheapest thing to iterate — a full F1
comparison run costs ~$1.30 and ~30 minutes, so several variants fit in one
session. Strategic framing confirmed 2026-07-07: the target user is agents
working on code LLMs *don't* know (niche, churned, private packages), where
the model cannot fall back on parametric knowledge — engagement is the whole
game there.

**Scope (in):**
- A/B variants of `plugin/lcp/skills/lcp-universal/SKILL.md`, measured
  independently with the existing harness (lcp-skill arm, 8 F1 cases,
  3 reps, haiku pinned, `--case-id` filters — see the eval-runner memory):
  - **Variant A — deferred-tools step:** the observed stall is a lone
    `ToolSearch` call and nothing after it (the model loads the deferred MCP
    tools and behaves as if it verified something). Add an explicit
    instruction: load the lcp tools via ToolSearch, then **call**
    `resolve_library` — loading is not verifying.
  - **Variant B — unconditional first action:** engagement is bimodal
    (0-or-full-chain), so the failure is the first step, not workflow
    comprehension. Reframe: "before writing ANY import statement, your first
    tool call is `resolve_library(<package>)`".
  - **Variant C — shorter body:** haiku compliance may degrade with prompt
    length; a compressed skill body tests that hypothesis. Optional few-shot
    example if length allows.
- **Hook experiment:** a `PreToolUse` hook on Write/Edit in
  `plugin/lcp/hooks/hooks.json` that reminds the agent when no
  `mcp__lcp__*` call has happened in the session — deterministic where
  prose is probabilistic, and robust to CLI-version drift (the ToolSearch
  stall pattern is harness-version-sensitive; 2.1.201→2.1.202 already
  showed variance).
- Every run records `claude --version` in meta.json; compare variants on
  (1) engagement rate (runs with ≥1 `mcp__lcp__*` call in
  `tool_call_details`), (2) pass rate, (3) engaged-run misuse — which MUST
  stay 0 (a variant that raises engagement but degrades engaged quality
  loses).
- Ship the winning variant (skill + hook if it earns its keep) in the
  plugin; docs-alignment rule applies (plugin skill files are shipped docs).

**Scope (out):** manifest/server changes (format frozen at Phase 4), new
eval cases or task-mix changes (Phase 8), non-Claude harnesses, statistical
proof (3 reps per variant is a screening filter — Phase 8 confirms).

**Code notes (2026-07-07):**
- Engagement counting and the stall pattern are documented in
  `evals/results/2026-07-07-phase4-docstrings-skill/analysis.md`; baselines:
  Phase 3 engaged 15/24, Phase 4 engaged 13/24, fastmcp stuck at 4/12 in
  both, cyhole 9–11/12.
- The skill reaches the model via `--append-system-prompt` in the harness
  (`evals/run.py`), but real users get it through the plugin's skill
  auto-trigger — keep the two texts identical (single source of truth in
  `plugin/lcp/skills/`).
- `hooks/hooks.json` currently has only a `SessionStart` PATH check; hook
  output conventions are documented in the Claude Code plugin docs.

**Exit criteria:** best variant reaches ≥18/24 engaged with engaged-run
misuse = 0 across the standard 24-run comparison; shipped in the plugin;
results + per-variant table recorded in the eval log; if NO variant beats
15/24 meaningfully, record that honestly and move the engagement problem to
Phase 8's task-mix design (harder tasks on unknown code may engage
naturally).

---

## Phase 5 — Subprocess scanning

**Status:** not started — independent (can run any time after Phase 2)

**Objective:** `resolve_library` no longer imports arbitrary package code
into the MCP server process, and can scan packages installed in a *different*
interpreter/venv.

**Why:** import-based scanning executes package code at import time inside
the agent-facing server (side effects, crashes take the server down, heavy
imports block the tool call), and today the server can only see its own
environment — the #1 real-world friction (project venv ≠ lcp venv).

**Scope (in):**
- A machine-mode scan entry point: `lcp scan <pkg> --json -` (or
  `python -m lcp.scanjson <pkg>`) that writes the LCP document to stdout,
  errors as structured JSON to stderr, exit codes distinguishing
  import-failure / scan-failure.
- `resolve_library_document` gains a subprocess path: configurable
  interpreter (from `.lcp.json` `python` field, already plumbed through the
  plugin's `serve.sh`), timeout (default ~60s, configurable), captured
  stderr surfaced in the error message.
- In-process scanning remains available as a fallback/option
  (`--scan-mode inprocess|subprocess`, default subprocess) — needed for
  environments where spawning is restricted, and for tests.
- The error message for "installed in a different environment" now has a
  real remedy: the server *uses* the configured interpreter instead of just
  mentioning it.
- Tests: subprocess happy path, timeout, crashing package (fixture that
  `sys.exit`s or segfault-simulates via exception), interpreter-not-found,
  fallback mode.

**Scope (out):** sandboxing beyond process isolation (no seccomp/containers —
document the residual trust model honestly instead), Windows-specific
launcher work beyond `sys.executable` defaults.

**Critical note:** this phase adds a second code path for the same operation.
Keep the subprocess protocol *identical* to the public document format (an
LCP JSON on stdout) so there is no private IPC format to version.

**Code notes (2026-07-02 review):**
- `resolve_library_document` (`src/lcp/mcp_server.py:310-414`) is the single
  choke point: cache read/write, the three-step resolution order, and the
  error wording all live there. The subprocess path must preserve the cache
  side effect.
- `.lcp.json`'s `python` field is currently consumed by the plugin's
  `serve.sh` (`plugin/lcp/bin/serve.sh:39-69`) to pick the interpreter that
  *runs the server*. Phase 5 needs the interpreter whose environment *gets
  scanned* — usually the same, but decide explicitly whether `python` does
  double duty or a `scan_python` field is added; conflating them silently is
  how someone ends up scanning the wrong venv.
- FastMCP runs sync tools on a worker thread, but the CPython import lock +
  GIL still stall concurrent tool calls during a heavy in-process import —
  the subprocess is about responsiveness as much as crash isolation.
- Suggested exit-code contract: 0 = ok, 3 = import failure, 4 = scan
  failure; stderr carries one JSON object `{"type": ..., "message": ...}`.

**Files:** `src/lcp/cli.py`, `src/lcp/mcp_server.py`
(`resolve_library_document`), `plugin/lcp/bin/serve.sh` (pass-through of the
interpreter config — mostly already there), `tests/test_mcp_server.py`, new
`tests/test_subprocess_scan.py`.

**Exit criteria:** a package installed only in a second venv resolves via
`.lcp.json` `python` config; a package whose import raises `SystemExit`
degrades to a clean error without killing the server; scan of a heavy
library doesn't freeze concurrent tool calls.

---

## Phase 6 — Documentation truth + positioning

**Status:** 6a unblocked now; 6b unblocked (Phases 2–4 done as of 2026-07-07)

**Objective:** Docs that validate, one consistent story, and explicit
positioning against the alternatives every evaluator has in mind.

**Phase 6a — factual fixes (do immediately, ~1 hour, any session):**
- `docs/introduction.md` + `docs/spec/examples.md`: examples use a flat
  symbol shape (`summary`, `signature` string, `stability: "stable"`,
  `members[]`) that does **not** validate against the normative spec
  (map keyed by ID, `semantics.summary`, `signatures[]`, stability object).
  Rewrite the examples to validate; add a CI-adjacent test that runs
  `lcp validate` on every JSON example embedded in docs.
- `docs/quickstart.md`: `jq '.symbols[0]'` is wrong for a map — fix.
- `docgen` story: README documents a CLI with certain flags, the
  architecture doc documents different flags, the guide says "planned",
  `docs/cli.md` omits it. Establish the truth from `src/lcp/cli.py` and make
  all four agree.
- README/introduction: soften "language-agnostic" claims to "the *format* is
  language-agnostic; the shipped scanner is Python" wherever capability is
  implied.
- Rot guard: add `tests/test_docs_examples.py` that extracts fenced JSON
  blocks from `docs/**/*.md` and runs them through `lcp.validator`, so
  examples cannot silently drift from the schema again.

**Phase 6b — the positioning + refresh pass (after 2–4):**
- Rewrite MCP guide + plugin guide around the consolidated surface.
- New short page (or README section): **LCP vs Context7 vs llms.txt vs
  "agent reads site-packages"** — honest table. LCP's defensible claims:
  introspected ground truth of the *installed* version, offline, private
  packages, token-dense structured responses. Do not claim narrative-docs
  superiority over Context7; that's not what LCP is.
- Rename decision for the `.lcp.json` config-vs-manifest collision
  (recommendation: config becomes `.lcp-config.json`, with a deprecation
  fallback in `serve.sh` and the plugin userConfig seeding). This is a
  breaking-ish plugin change — do it here, while plugin adoption is small.
- Architecture docs updated for phases 2–5 per `lcp-writing-documentation`.

**Exit criteria:** `mkdocs build --strict` green; every embedded example
validates; a newcomer reading only the README can state in one sentence when
to choose LCP over Context7.

---

## Phase 7 — Registry: CI verification + pre-population

**Status:** not started — unblocked: manifest format frozen at end of Phase 4 (2026-07-07)

**Objective:** The registry verifies submissions automatically and ships
pre-built manifests for the top PyPI libraries, so `serve-all --registry`
has answers on day one.

**Important:** most of this work lands in the **registry repo**
(`zazza123/lcp-registry`), not this SDK repo. Plan sessions accordingly.

**Scope (in):**
- Registry CI (GitHub Action on PR): for each added manifest, install the
  claimed `(package, version)` from PyPI in an isolated env, regenerate the
  manifest with pinned lcp version, and compare (symbol-ID set equality +
  spot-check of signatures; allow a documented tolerance for
  environment-dependent symbols). Green check replaces manual review as the
  trust mechanism.
- `lcp validate` + schema check + path-layout check (`manifests/{lang}/
  {letter}/{slug}/{version}.lcp.json.gz` + `latest.json` update) in the same
  action.
- Pre-population: batch script (this repo, `scripts/populate_registry.py` or
  in the registry repo) that takes a list of top-PyPI packages, scans each in
  an isolated venv (Phase 5 machinery), and opens batched PRs via the
  existing `publish.py` flow. Target: top 100 by download count that aren't
  stdlib-trivial; 500 only if the pipeline proves cheap.
- Regenerate the 10 pre-freeze manifests already published (6 libraries as
  of 2026-07-07: azure-ai-contentunderstanding, firebase-admin, google-adk,
  google-cloud-aiplatform, google-cloud-firestore, google-genai): they
  validate fine under the frozen `"1.0"` schema but lack the Phase 4
  structured fields (param descriptions, raises, returns_description,
  examples). Fold them into the population batch.
- Idempotent publish: `publish.py` currently fails on re-run for the same
  `(package, version)` (branch/file already exist) — make it upsert or
  cleanly no-op; needed for batch operation.
- Version-mismatch honesty in the server: when the cache/registry serves a
  version different from the installed one (`_find_any_cached`, `latest.json`
  fallback), the response carries `"version_mismatch": true` + both versions.

**Scope (out):** registry hosting beyond raw.githubusercontent (CDN, API
service — revisit only if adoption demands it), signing/attestation
(document as known limitation), non-Python languages.

**Critical caveat:** CI that installs arbitrary PyPI packages executes
arbitrary code — the Action must run with no secrets exposed, on isolated
runners, with network egress documented. Don't hand-wave this in the phase
plan.

**Code notes (2026-07-02 review):**
- Non-idempotence, concretely: `_create_branch` POSTs a git ref and fails if
  the branch already exists (`src/lcp/publish.py:196-233`);
  `_upload_manifest` PUTs contents without a `sha`, which GitHub rejects for
  pre-existing files (`:236-274`). Upsert = GET the file's sha first +
  tolerate an existing branch.
- The current publish flow uploads only the manifest file — it does **not**
  update the package's `latest.json` pointer (shape:
  `{"version": ..., "manifest": "X.lcp.json.gz"}`, validated by
  `_fetch_from_registry` at `src/lcp/mcp_server.py:280-286`). Check how the
  registry repo maintains `latest.json` (bot? CI?); the batch publisher must
  handle it, or population produces packages the server cannot resolve
  without an exact version.
- Version-mismatch sources to flag in responses: `_find_any_cached`
  (`src/lcp/mcp_server.py:147-159`, returns *any* cached version) and the
  registry-`latest` fallback taken when `_installed_version` returns None.
- The batch script must use `lcp.naming.normalize_package_name` for
  slug/sharding — the same helper `publish.py` and `_fetch_from_registry`
  already share; do not reimplement it.

**Exit criteria:** a manually-submitted wrong manifest (e.g. a function
signature edited to not match the real package) is rejected by CI; top-100 manifests published; a fresh machine with *no*
local package installed gets a useful `resolve_library("polars")` answer via
registry in <2s.

---

## Phase 8 — Full benchmark + publication

**Status:** not started — blocked by all previous phases

**Objective:** Run the grown-up version of the Phase 0 harness on the
finished product and publish results as the launch asset.

**Baseline evidence (2026-07-03):** F4 shapes the task mix — pydantic/httpx/
polars-class libraries are at ceiling for current models and mostly measure
noise; weight the expanded set toward niche/recently-churned libraries
(cyhole/hamana-class), where both failure modes (F1, F2) actually show.
Report tool-adoption rate and cost-overhead-when-unused (+48% cost at
baseline) alongside the pre-registered metrics; note that `tool_calls`
counts attempts including permission-denied ones.

**Scope (in):**
- Expand task set (target 75–100 tasks), add at least one non-Claude agent
  configuration if cheap (e.g. an OpenAI-tool-use harness) to preempt "works
  only with Claude" objections.
- Enough repetitions for defensible numbers (pin models; report variance;
  pre-register the metric: API-misuse rate + task pass rate + tokens/task).
- Comparison arms: (a) no assistance, (b) LCP MCP, (c) agent free to read
  site-packages, and — decide at phase start — (d) Context7 if reproducible.
  **Binding (Phase 2b outcome A): the arm set MUST also include
  `lcp-skill` (b + the plugin skill body)** — it is the shipped developer
  experience and the only configuration where haiku-class models verify
  false-confidence libraries at all (fastmcp 0.0 → 1.42 lcp calls/run).
- Model mix (Phase 2b Exp2): pair a haiku-class and a sonnet-class model;
  capable models pass well-known-library cases from parametric knowledge
  (sonnet baseline 12/12 on fastmcp, zero calls), so the LCP delta for them
  only shows on post-cutoff/niche cases — weight the task set accordingly.
  Arm (c) is the intellectually honest one and the most likely to be
  uncomfortable; run it anyway. If LCP doesn't beat (c) on accuracy, the
  token/latency delta is the story; if it loses both, that's a product
  finding, not a marketing problem.
- Publication: `docs/` page + README summary + the per-phase delta story
  from the results log ("baseline → final").

**Exit criteria:** published page with reproducible methodology (harness
committed, config pinned); README leads with the headline number.

---

## Post-roadmap cleanup (after Phase 8)

Once the roadmap is complete, remove the scaffolding it needed. **This cleanup
happens on `roadmap/agentic-improvements` before it merges into `main`** — the
internal docs live on the roadmap branch during development but must not reach
`main`:

- Remove the **Active Roadmap** section from `CLAUDE.md` (it exists only to
  route sessions to this file while the work is in flight).
- Clean up `docs/superpowers/` (plans + specs): these are internal working
  documents, not user documentation. Archive or delete them — decide then
  whether anything (e.g. the v2 surface design spec) deserves promotion into
  `docs/architecture/` per the `lcp-writing-documentation` conventions
  before deletion.
- Verify `mkdocs.yml` never referenced them (they are outside the nav today;
  keep it that way).

---

## Eval results log

| Date | Phase | Config | Misuse rate | Pass rate | Tokens/task | Tool calls/task | Notes |
|------|-------|--------|-------------|-----------|-------------|-----------------|-------|
| 2026-07-03 | 0 baseline (no LCP) | haiku-4.5, 28 cases, 3 reps | 0.46/run | 45% | ~1501 (13 in + 1488 out) | 0.5 | static checks only; tool calls count attempts (residual built-ins denied) |
| 2026-07-03 | 0 baseline (LCP current) | haiku-4.5, 28 cases, 3 reps | 0.43/run | 52% | ~1643 (21 in + 1622 out) | 1.7 | serve-all, --expose 7 libs; delta within noise; low voluntary tool use |
| 2026-07-03 | 2 (no LCP) | haiku-4.5, 28 cases, 3 reps | 0.31/run | 45% | ~1664 (11 in + 1653 out) | 0.3 | fresh baseline arm, same pass rate as Phase 0 |
| 2026-07-03 | 2 (LCP V2 surface) | haiku-4.5, 28 cases, 3 reps | 0.32/run | 52% | ~1418 (13 in + 1405 out) | 0.65 | 4-tool surface: LCP-arm cost overhead 48%→7%, output tokens now BELOW baseline arm; cyhole 0/12→2/12 pass, misuse 13→8 (F2 import lines working); hamana same outcome at 7.6→1.0 calls/run; fastmcp still 0 voluntary calls |
| 2026-07-03 | 2 iter2 (LCP arm, fastmcp+cyhole) | haiku-4.5, 8 cases, 3 reps | — | cyhole 4/12, fastmcp 1/12 | — | cyhole 2.3 | after unconditional-verification instructions rewrite: cyhole pass trend 0→2→4/12; fastmcp adoption stays 0 despite instructions verifiably reaching the model (quoted verbatim on probe) — model-compliance limit, see Phase 2 status |
| 2026-07-04 | 2b Exp1 (lcp-skill arm) | haiku-4.5, 8 F1 cases, 3 reps | cyhole 3, fastmcp 10 | cyhole 7/12, fastmcp 3/12 | — | **fastmcp 1.42 lcp calls/run (gate ≥1.0 PASSED)**, cyhole 7.6 | skill body via --append-system-prompt on the V2 surface → outcome A; engagement bimodal (0 or full chain); engaged runs: zero hallucinated symbols, all 3 engaged failures are canonical-vs-alias import mismatches (Phase 3 evidence) |
| 2026-07-04 | 2b Exp2 (sonnet, both arms) | sonnet-5, 4 fastmcp cases, 3 reps | 0 | 24/24 (both arms) | — | 0.00 lcp calls/run both arms | sonnet baseline at ceiling: correct fastmcp 2.x from parametric knowledge, nothing to verify → F1 is haiku-class-bound; fastmcp cases can't differentiate for capable models (Phase 8 task-mix note) |
| 2026-07-06 | 3 rescore (2b Exp1 runs, alias-aware verifier) | haiku-4.5, 8 F1 cases, 3 reps (frozen code) | cyhole 3, fastmcp 10 | **15/24** (cyhole 10/12, fastmcp 5/12) | — | unchanged (no agent runs) | verifier-fairness effect isolated: 10/24 → 15/24 on identical generated code; all 3 jupiter-swap flips (predicted in 2b analysis) + 2 symmetric fastmcp flips (root-required, deep-written). THE baseline for Phase 3 comparisons |
| 2026-07-06 | 3 (lcp-skill, alias server) | haiku-4.5, 8 F1 cases, 3 reps, CLI 2.1.201 | cyhole 2, fastmcp 6 (0.33/run) | **16/24** (cyhole 11/12, fastmcp 5/12) | — | cyhole 9.0, fastmcp 2.08 lcp calls/run | vs rescored baseline: +1 pass, misuse/run 0.54→0.33; jupiter-swap & rugcheck 3/3; agents copy alias ids into get_symbol (tool_call_details); engaged-run hallucinations ≈0 (one invented classmethod); residual failures = non-engagement (F1) + task compliance. fastmcp-server-tool first-ever engagement 0/3→2/3 — tentative, re-measure in Phase 8 |
| 2026-07-07 | 4 (lcp-skill, structured-docstrings server) | haiku-4.5, 8 F1 cases, 3 reps, CLI 2.1.202 | 0.71/run (all 17 in non-engaged runs) | 13/24 (cyhole 8/12, fastmcp 5/12) | — | cyhole 8.67, fastmcp 2.08 lcp calls/run | topline down vs Phase 3 but NOT a server regression: engaged runs 12/13 pass with ZERO misuse (Phase 3: 15/15, 0) — agents consumed param descriptions/raises/returns_description/examples without confusion; the whole delta is engagement variance (engaged 15→13/24, cyhole draw 11→9/12; fastmcp stable 4/12) = the F1 bimodality with 3 reps. Exit criteria: param descriptions 98.9–99.6 %, gzip ×1.09–1.28, DataFrame under cap. See analysis.md |

---

## Cross-phase risks (standing)

1. **Schema churn:** any manifest field added after Phase 7 population means
   mass-regeneration. The freeze point is the end of Phase 4 — treat additive
   ideas discovered later as post-launch.
2. **Moving target:** agents keep getting better at reading site-packages
   directly. The moat is token efficiency + ranked search + structured
   examples + registry for uninstalled/private packages — if a phase doesn't
   serve one of those, question it.
3. **Solo-maintainer bandwidth:** phases are sized to be individually
   shippable; never start a phase that can't be merged in that session's
   horizon. De-scope per the rule in the header, don't stall mid-phase.
4. **Eval overfitting:** phases 2–4 are tuned against the Phase 0 task set.
   Phase 8 must add fresh tasks the earlier phases never saw, or the final
   number is meaningless.
