# V2 Surface — Design Spec

> **Status:** approved 2026-07-03. Settles every decision that Phases 2–4 of
> the [agentic improvements roadmap](../plans/2026-07-02-agentic-improvements-roadmap.md)
> implement, so the MCP tool surface and the manifest additions are designed as
> one coherent product and the schema is touched once, not three times.
>
> This is an internal working document (a Phase 1 deliverable), not user-facing
> documentation. Each decision below carries a one-line rationale, per the
> phase's exit criteria.

## Context

Phase 0 measured the baseline (`evals/results/2026-07-03-baseline/`). Two
findings drive this design:

- **F1 — Adoption gap (the bottleneck).** The agent does not call the lcp
  tools where it errs most (fastmcp: 11/12 failures, **zero** tool calls). The
  model doesn't know that it doesn't know, so it never asks. Manifest quality
  is irrelevant until the agent queries the server. → tool *adoption* is a
  first-class design goal: the tool set, tool descriptions and the MCP
  `instructions` field must nudge a guessing agent to resolve→search first.
- **F2 — Information→code gap.** On cyhole the agent *does* call tools yet
  still writes `from cyhole import Rugcheck` (root doesn't re-export) and
  invents method names. Tool responses don't make the correct import path
  obvious. → every `search`/`get_symbol` result must carry the importable,
  alias-aware path prominently, not just the definition-site ID.

Everything that changes the manifest format or MCP tool surface happens
**before** the registry is populated (Phase 7), so these decisions are made
together and frozen at the end of Phase 4.

---

## Decision 0 — FastMCP dependency

**Target FastMCP `>=3.0,<4`. The concrete migration happens in Phase 2**, where
the tool surface is rewritten and the `mcp.tool_funcs` attribute-stuffing hack
is removed anyway.

- **Rationale:** the current pin `fastmcp>=2.0` has no upper bound, so a fresh
  install already resolves to 3.4.2 while the code was written/tested on
  2.14.4 — the incompatibility risk exists today. Phase 2 already reworks the
  exact surfaces (tool registration, `tool_funcs`, preload) that a 3.x bump
  would break, so migrating there is a single change onto the maintained major
  instead of a separate migration after the registry is populated.
- **Fact check (2026-07-03):** installed 2.14.4; latest on PyPI 3.4.2;
  `instructions` constructor argument is present in 2.14.4 and retained in 3.x,
  so 3.x is *not* required for the F1 work — this is a timing/alignment
  decision, not a capability one.
- **Correction:** the roadmap's Phase 2 code note (line 274) claiming "the
  project runs FastMCP 3.x" is wrong — it runs 2.14.4. Corrected in the
  roadmap as part of this phase.
- **Risk carried into Phase 2:** the Phase 2 plan must verify on 3.x: (a)
  `@mcp.tool` registration and the replacement for `tool_funcs` (the preload
  loop depends on it), (b) the `instructions` constructor argument, (c)
  in-process tool invocation used by tests. Pin becomes `fastmcp>=3.0,<4` in
  `pyproject.toml`.

---

## MCP surface (feeds Phase 2)

### D1 — Tool set

Four tools, replacing the current nine:

1. `resolve_library(name, version?)` — load a library's manifest into the
   in-memory index.
2. `search(query, library?, kind?, limit?)` — ranked, capped; the primary
   entry point.
3. `get_symbol(ids: list[str], library?)` — batch lookup.
4. `get_overview(library?)` — manifest metadata + module tree with symbol
   counts.

**Rationale:** fewer, sharper tools reduce the choice-paralysis behind F1; the
recommended happy path is ≤3 calls (resolve → search → get_symbol).

### D2 — Removals

- `get_usage_guide` → content moves to the FastMCP `instructions` field and
  tool descriptions. *Rationale:* an always-present server instruction reaches
  the agent even when it never calls a tool (F1); a tool it must choose to call
  does not.
- `get_suggestions` (bag-of-words matcher) → removed. *Rationale:* an LLM with
  a good `search` beats a keyword matcher; the `return_type.startswith(("str",
  "int", ...))` suggestion heuristic must not survive.
- `explore_return_type` → removed; its useful part ("return type X is class
  `mod:X`") folds into `get_symbol`'s `usage_hints`. *Rationale:* its
  `type_part.endswith(class_name)` matching produces false positives (e.g.
  `PurePath` matching a `Path` lookup); resolving `returns` to a class ID from
  the index is exact.

### D3 — `list_symbols` is folded into `search`

`list_symbols` is **removed**. Browsing is served by:

- `get_overview` for structure (module tree + counts), and
- `search("", module=..., kind=...)` for contents — an empty query means
  "browse", ordered deterministically by `(kind, name)` (there is no relevance
  to rank by).

**Rationale:** two near-identical discovery tools (`search` vs `list_symbols`)
are exactly the ambiguity that makes a guessing agent hesitate (F1). One
discovery tool + one structure tool is simpler to describe and to choose
between.

### D4 — Response shape

- **`search`** returns a ranked list of hits. Each hit is compact:
  `{id, kind, summary, import, resolved_via_alias?}`. Ranking (implemented in
  Phase 2, no new deps): exact name match > name prefix > name substring >
  summary substring > description substring; stable tie-break by ID. Default
  `limit=20`; when results are capped, `"truncated": true` is set.
- **`get_symbol`** returns, per requested ID:
  - the **importable path** prominently as `"import"` (alias-aware, F2) —
    e.g. `"from requests import get"`;
  - for **functions/methods**: full signature(s) + structured docs
    (`params` with descriptions, `returns`, `raises`, `examples`);
  - for **classes**: members inline as **summaries** (name + kind + one-line
    summary + `import`), not full member bodies — full member docs are fetched
    by a follow-up `get_symbol` on the member ID;
  - `usage_hints`: return-type-to-class-ID resolution (the salvaged part of
    `explore_return_type`), e.g. `"returns Response → get_symbol('requests:Response')"`.
- **`get_overview`** returns manifest metadata (name, version, source,
  version-mismatch flags if any) + a module tree with per-module symbol counts.

**Rationale:** F2 requires the import path to be the most visible field in both
discovery and detail responses; inlining class members as summaries (not full
bodies) keeps responses under the byte cap (D6) on heavy classes like pandas
`DataFrame`.

### D5 — Error convention

Every tool returns a **structured error dict with a stable shape** on failure:

```json
{"error": {"code": "ambiguous_library",
           "message": "...",
           "hint": "...",
           "loaded_libraries": ["requests", "httpx"]}}
```

Applied everywhere, replacing today's inconsistent shapes (dict-returning tools
emit `{"error": ...}`, list-returning tools emit `[{"error": ...}]`). FastMCP
`ToolError` is **not** used for recoverable conditions.

**Rationale:** agents recover from structured data better than from protocol
errors, which tend to abort the flow rather than prompt a correction. Reserve
exceptions for genuine protocol faults, not "you need to pass `library`".

### D6 — Caps

A configurable **max-bytes guard on every list-returning tool**, with a
sensible default (target: keep any single response comfortably within a small
fraction of the context window; concrete number set in the Phase 2 plan against
a heavy real library). `search` additionally caps by `limit` (default 20) and
signals `"truncated": true`.

**Rationale:** today `search_symbols` is an unbounded O(n) substring scan and
`list_symbols()` with no filters returns every symbol — a real context blowout,
not a theoretical one.

### D7 — `library` disambiguation

When **≥2 libraries** are loaded, tools that act on a single library **require**
`library`. If it is missing/ambiguous, they return a structured error (D5,
`code: "ambiguous_library"`) listing the loaded libraries. With exactly one
library loaded, `library` may be omitted.

**Rationale:** the implicit default (`MultiLibraryIndex._default`) is silently
reassigned by every `add()`, a race that makes multi-library answers
non-deterministic. An explicit error that names the choices is recoverable;
a silent wrong-library answer is not.

### D8 — `lcp serve` (single-library mode)

`lcp serve` is **deprecated in favor of `serve-all --expose`**. `lcp serve X`
becomes a thin alias for `serve-all --expose X` that emits a deprecation
warning. Both are backed by **one tool-registration function parameterized by
an index provider**, eliminating the ~450 lines duplicated between the two
servers today.

**Rationale:** one surface to maintain, document, and test. The plugin's
adoption is still small, so the mildly-breaking change is cheap now and
expensive later.

### D9 — Adoption levers (F1)

The FastMCP `instructions` field and every tool description are written to nudge
a *guessing* agent toward resolve→search **before** it writes an import. The
plugin skills, commands, and the `library-explorer` agent (updated in Phase 2)
teach the same ≤3-call path. This is the primary F1 lever; the Phase 2 eval
re-run gates on voluntary tool-call rate rising on the fastmcp/cyhole-class
cases, not only on pass rate.

---

## Manifest additions (feeds Phases 3–4)

### D10 — Alias representation

Add an **additive `Symbol.aliases: list[str]`** field holding full alternative
IDs (e.g. `["requests:get"]`). The canonical ID (definition site) remains the
map key. `LCPIndex` indexes every alias ID, and for a re-exported **class** it
computes alias-member IDs at build time (`requests:Session#get` →
`requests.sessions:Session#get`) — **without** duplicating member entries in
the manifest. Alias hits are marked in responses with
`"resolved_via_alias": "requests.api:get"`.

**Rationale:** keeps the manifest lean and additive (respects the D6 caps and
the Phase 4 size budget), keeps IDs stable at the definition site (avoids the
rejected "rewrite IDs to re-export site" option, which breaks the
`module_path:entity_path` grammar and ID stability), and serves member lookups
by index computation rather than manifest bloat. Materializing member entries
was rejected: it trades duplication for marginally simpler lookup.

### D11 — Structured docstring fields

Populate the already-existing model fields `Param.description`,
`Signature.raises` (`RaisesEntry.type` + `condition`), `Signature.returns`
description, and `Semantics.examples` (`Example.code` + `description`) by
parsing docstrings with the **`docstring_parser`** dependency.

- **Styles:** Google + NumPy (minimum). reST/Sphinx field-lists are out of
  scope (Phase 4 scope line).
- **Dependency sign-off:** `docstring_parser` is a mature, small, pure-python
  (MIT) library. This spec is the explicit sign-off required by the roadmap's
  global constraints. It is a **core** dependency of the scan/generate path
  (`lcp scan` → generator), **not** part of the `ai` extra, and is **not**
  needed at MCP-server runtime (the server consumes pre-built manifests).
- **Fail-open:** any parser exception falls back to today's behavior (summary +
  raw description). Parse at the **generator** level, not during scanner member
  iteration, so the scanner's hostile-package resilience does not regress.
- **No information loss:** `description` keeps the unparsed remainder; docstring
  params are merged with introspected params **by name**, introspection wins on
  existence and type, and an unmatched docstring entry never invents a `Param`.

**Rationale:** these fields are what differentiate LCP from "type stubs in
JSON"; reinventing a docstring parser is a maintenance and correctness sink,
and `docstring_parser` is Phase 4's named candidate.

### D12 — Version bump policy

All changes above are **additive under schema `"1.0"`**. `extra="allow"` already
guarantees old consumers tolerate the new fields. No `"1.1"` bump.

**Rationale:** every addition (an optional `aliases` list, filling
already-declared docstring fields) is backward-compatible; nothing removes or
reshapes an existing field.

---

## Roadmap deltas (contradictions this spec resolves)

Applied to `docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md`
as part of this phase:

1. **Phase 2 code note (line 274):** "the project runs FastMCP 3.x" → corrected
   to 2.14.4; add the Decision 0 target (`>=3.0,<4`, migrate here) and the
   3.x verification risk list.
2. **Phase 1 working proposal:** `list_symbols` "decide whether it survives" →
   resolved to **folded into `search`** (D3).
3. **Phase 1 open items** (library-required, error convention, serve mode,
   alias representation, parser dependency) → all now have written answers
   above; mark them settled.
4. Phases 3–4 sections remain consistent with D10/D11 (they already anticipate
   the recommended options); no content change needed beyond noting the spec
   as the authority.

## Exit criteria (Phase 1)

- [x] Spec merged with a written answer + one-line rationale per open decision.
- [ ] Phases 2–4 sections of the roadmap updated where this spec contradicts
      them (deltas above).
- [ ] Phase 1 Status line updated.
