# Phase 4b — Engagement Iteration (skill + hooks) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise lcp-skill engagement on the 8 F1 cases from 13–15/24 to ≥18/24 by A/B-testing three variants of the plugin skill text (measured with the existing eval harness) and adding a deterministic PreToolUse reminder hook to the plugin — with engaged-run misuse staying 0.

**Architecture:** Skill variants live as complete `SKILL.md` files under `evals/results/2026-07-07-phase4b/variant-{a,b,c}/`; a new `--skill-file` flag on `evals/run.py` injects each one into the lcp-skill arm, so the shipped plugin file only changes once, when the winner is copied over. A new `engagement` harness module/subcommand computes the decision metric (runs with ≥1 `mcp__lcp__*` call). The hook experiment is a stdlib-only `verify_reminder.py` PreToolUse script wired into `plugin/lcp/hooks/hooks.json`; because the eval harness disallows Write/Edit, the hook **cannot fire in F1 runs** — it is verified by unit tests plus a headless smoke run, not by the F1 eval.

**Tech Stack:** Python 3.12 (two venvs: `.venv` for the main suite, `evals/.venv` for the harness), `claude` CLI headless (`-p`, stream-json), pytest, Claude Code plugin hooks.

## Global Constraints

- **FREEZE:** no changes to manifest format, MCP server, or `schema.json` (frozen at end of Phase 4). Only skill text, plugin hooks, eval harness, and docs.
- Eval runs use `evals/.venv/bin/python evals/run.py` — **never** `pip install -e ".[dev]"` into `evals/.venv` (fastmcp pinned at 2.14.4; `docstring_parser` already installed there manually).
- Model pinned: `claude-haiku-4-5-20251001`. Arm: `lcp-skill`. Reps: 3.
- **Mandatory `--case-id` filters** on every run (8 F1 cases): `fastmcp-server-tool`, `fastmcp-resource`, `fastmcp-client`, `fastmcp-context`, `cyhole-birdeye-price`, `cyhole-jupiter-swap`, `cyhole-rugcheck-report`, `cyhole-missing-api-key`. Without them the runner starts all 28 cases (Phase 4 mistake).
- Separate `--out` per variant; every variant gets a `meta.json` recording `claude --version` (stall pattern is CLI-version-sensitive; Phase 4 was 2.1.202).
- Comparison baselines (same verifier, no rescore needed): `evals/results/2026-07-07-phase4-docstrings-skill` (13/24 engaged) and `evals/results/2026-07-06-phase3-aliases-skill` (15/24 engaged).
- Keep `evals/.lcp-cache/` as-is (server code unchanged on this branch since the Phase 4 run).
- Main suite (`.venv`) must be fully green at phase start and end: **532 passed, 0 failed** at start (plus the new tests at end).
- Single source of truth for the *shipped* skill: `plugin/lcp/skills/lcp-universal/SKILL.md`. Variant files are experiment artifacts; only the winner is copied into the plugin.
- Commits follow the `git-commit-convention` skill; **no co-author lines or session links** (public repo). `docs/superpowers/` is gitignored — commit plan/roadmap changes with `git add -f`.
- Docs follow the `lcp-writing-documentation` skill; `mkdocs build --strict` must pass at the end.
- PR title starts with `MRG:` (not `CODE:`), target branch `roadmap/agentic-improvements`.

## Decision Rule (settled up front)

1. **Disqualified:** any variant with engaged-run misuse > 0 (a variant that raises engagement but degrades engaged quality loses).
2. **Winner:** among qualified variants, highest engaged-run count (of 24); ties broken by higher overall pass rate, then lower misuse/run.
3. **Ship the winner's text** into the plugin iff its engaged count ≥ 16/24 (beats the Phase 3 best of 15). Record explicitly whether the ≥18/24 exit target was met.
4. If **no** variant reaches ≥16/24: keep the current shipped skill text unchanged, record the result honestly in the roadmap, and move the engagement problem to Phase 8's task-mix design (this is the roadmap's foreseen exit path).
5. **Hook ships independently of the skill outcome** iff: all unit tests pass AND the headless smoke run shows it (a) blocks the first `.py` write with the reminder when no lcp call has happened, (b) fires at most once (no deny loop), and (c) the agent proceeds afterwards (either calls the server or repeats the write). The hook is eval-neutral for F1 by construction.

---

### Task 1: Preflight sanity gates

**Files:** none created/modified.

**Interfaces:**
- Consumes: nothing.
- Produces: recorded `claude --version` string and HEAD short hash used verbatim in every `meta.json` later (Tasks 5–7).

- [ ] **Step 1: Verify branch and base**

Run:
```bash
git branch --show-current
git log roadmap/agentic-improvements -1 --oneline
git status --porcelain
```
Expected: `roadmap/phase-4b-engagement`; base log shows `7cee88c Merge pull request #46 ...`; status empty.

- [ ] **Step 2: Main suite green (start gate)**

Run: `.venv/bin/python -m pytest -q`
Expected: `532 passed` — 0 failures. If anything fails, STOP: the gate is 0 failures (historical env failures were fixed before Phase 4).

- [ ] **Step 3: Evals venv + harness tests green**

Run:
```bash
evals/.venv/bin/python -c "import fastmcp, docstring_parser, lcp; print(fastmcp.__version__, lcp.__file__)"
evals/.venv/bin/python -m pytest evals/tests -q
```
Expected: `2.14.4` and an `lcp` path inside `src/lcp/` (editable install of this branch); all harness tests pass.

- [ ] **Step 4: Record environment for meta.json**

Run: `claude --version && git rev-parse --short HEAD`
Expected: a version like `2.1.202 (Claude Code)` — write both values down; they go verbatim into every `meta.json` (Tasks 5–7) and into the analysis (Task 8).

---

### Task 2: `--skill-file` flag on the eval runner

**Files:**
- Modify: `evals/run.py` (parser construction + `cmd_run` skill loading, lines ~114–120 and ~186–222)
- Test: `evals/tests/test_run_args.py` (new)

**Interfaces:**
- Consumes: `agent.load_skill_text(path)` (exists, `evals/harness/agent.py:30`).
- Produces: `build_parser() -> argparse.ArgumentParser` (module-level in `run.py`); `run` subcommand gains `--skill-file` (type `Path`, default = the shipped plugin skill `plugin/lcp/skills/lcp-universal/SKILL.md`). Tasks 5–7 pass `--skill-file` per variant.

- [ ] **Step 1: Write the failing test**

Create `evals/tests/test_run_args.py`:

```python
"""Argument-plumbing tests for evals/run.py (no agents are run)."""

from pathlib import Path

from run import build_parser

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestSkillFileFlag:
    def test_default_is_the_shipped_plugin_skill(self):
        args = build_parser().parse_args(["run", "--out", "x"])
        assert args.skill_file == (
            REPO_ROOT / "plugin/lcp/skills/lcp-universal/SKILL.md"
        )

    def test_override(self, tmp_path):
        skill = tmp_path / "SKILL.md"
        args = build_parser().parse_args(
            ["run", "--out", "x", "--skill-file", str(skill)]
        )
        assert args.skill_file == skill
```

- [ ] **Step 2: Run it to verify it fails**

Run: `evals/.venv/bin/python -m pytest evals/tests/test_run_args.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_parser'`.

- [ ] **Step 3: Implement**

In `evals/run.py`:

(a) In `cmd_run`, replace the skill-path block

```python
    arms = ["baseline", "lcp"] if args.arms == "both" else [args.arms]
    append_system = None
    if "lcp-skill" in arms:
        skill_path = (
            EVALS_DIR.parent / "plugin/lcp/skills/lcp-universal/SKILL.md"
        )
        append_system = agent.load_skill_text(skill_path)
```

with

```python
    arms = ["baseline", "lcp"] if args.arms == "both" else [args.arms]
    append_system = None
    if "lcp-skill" in arms:
        append_system = agent.load_skill_text(args.skill_file)
```

(b) Rename `main()`'s parser construction into a module-level `build_parser()` and add the flag. Replace

```python
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
```

with

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
```

add inside the `p_run` block (after the `--case-id` line):

```python
    p_run.add_argument(
        "--skill-file", type=Path,
        default=EVALS_DIR.parent / "plugin/lcp/skills/lcp-universal/SKILL.md",
        help="SKILL.md injected in the lcp-skill arm "
             "(default: the shipped plugin skill)",
    )
```

and close the function / re-create `main()`: replace

```python
    args = parser.parse_args()
    return args.func(args)
```

with

```python
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)
```

(the `p_rescore.set_defaults(...)` line stays the last statement before `return parser`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `evals/.venv/bin/python -m pytest evals/tests -q`
Expected: all pass (new file green, no regressions).

- [ ] **Step 5: Commit**

```bash
git add evals/run.py evals/tests/test_run_args.py
git commit  # via git-commit-convention skill: "ADD: --skill-file option to the eval runner"
```

---

### Task 3: Engagement-conditioned stats in the harness

**Files:**
- Create: `evals/harness/engagement.py`
- Modify: `evals/run.py` (new `engagement` subcommand in `build_parser()` + `cmd_engagement`)
- Test: `evals/tests/test_engagement.py` (new), extend `evals/tests/test_run_args.py`

**Interfaces:**
- Consumes: `report.load_runs(results_dir: Path) -> list[dict]` (`evals/harness/report.py:8`); run records carry `tool_call_details: [{"name": ..., "input": ...}]`, `verification: {"passed", "misuse_count", ...}`, `case_id`.
- Produces: `is_engaged(run: dict) -> bool`; `engagement_stats(runs: list[dict]) -> dict` with keys `total`/`engaged`/`non_engaged` (each `{"runs", "passed", "misuse"}`) and `by_prefix` (`{prefix: {"runs", "engaged"}}`); CLI `evals/run.py engagement --out DIR [--out DIR ...]`. Task 8 uses the CLI for the decision table.

- [ ] **Step 1: Write the failing tests**

Create `evals/tests/test_engagement.py`:

```python
from harness.engagement import engagement_stats, is_engaged


def make_run(case_id="cyhole-birdeye-price", passed=True, misuse=0, tools=()):
    return {
        "case_id": case_id,
        "verification": {"passed": passed, "misuse_count": misuse},
        "tool_call_details": [{"name": n, "input": {}} for n in tools],
    }


class TestIsEngaged:
    def test_lcp_call_counts(self):
        assert is_engaged(make_run(tools=("mcp__lcp__resolve_library",)))

    def test_toolsearch_alone_is_not_engaged(self):
        # The Phase 4 stall pattern: deferred-tool load with no lcp call after.
        assert not is_engaged(make_run(tools=("ToolSearch",)))

    def test_no_tool_calls(self):
        assert not is_engaged(make_run())


class TestEngagementStats:
    def test_buckets_and_prefixes(self):
        runs = [
            make_run(tools=("mcp__lcp__resolve_library",), passed=True),
            make_run(passed=False, misuse=2),
            make_run(case_id="fastmcp-client", tools=("ToolSearch",),
                     passed=False, misuse=1),
        ]
        stats = engagement_stats(runs)
        assert stats["total"] == {"runs": 3, "passed": 1, "misuse": 3}
        assert stats["engaged"] == {"runs": 1, "passed": 1, "misuse": 0}
        assert stats["non_engaged"] == {"runs": 2, "passed": 0, "misuse": 3}
        assert stats["by_prefix"]["cyhole"] == {"runs": 2, "engaged": 1}
        assert stats["by_prefix"]["fastmcp"] == {"runs": 1, "engaged": 0}
```

Append to `evals/tests/test_run_args.py`:

```python
class TestEngagementSubcommand:
    def test_accepts_multiple_out_dirs(self):
        args = build_parser().parse_args(
            ["engagement", "--out", "a", "--out", "b"]
        )
        assert args.out == ["a", "b"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `evals/.venv/bin/python -m pytest evals/tests/test_engagement.py evals/tests/test_run_args.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.engagement` and argparse error for the unknown subcommand.

- [ ] **Step 3: Implement**

Create `evals/harness/engagement.py`:

```python
"""Engagement-conditioned stats (Phase 4b).

A run is *engaged* when it makes >=1 mcp__lcp__* tool call — the metric the
Phase 3/4 analyses condition on (evals/results/2026-07-07-phase4-docstrings-
skill/analysis.md). A lone deferred-tool ToolSearch call is NOT engagement.
"""


def is_engaged(run: dict) -> bool:
    return any(
        d.get("name", "").startswith("mcp__lcp__")
        for d in run.get("tool_call_details", [])
    )


def _bucket(runs: list[dict]) -> dict:
    return {
        "runs": len(runs),
        "passed": sum(1 for r in runs if r["verification"]["passed"]),
        "misuse": sum(r["verification"]["misuse_count"] for r in runs),
    }


def engagement_stats(runs: list[dict]) -> dict:
    engaged = [r for r in runs if is_engaged(r)]
    non_engaged = [r for r in runs if not is_engaged(r)]
    by_prefix: dict[str, dict] = {}
    for prefix in sorted({r["case_id"].split("-")[0] for r in runs}):
        prefix_runs = [
            r for r in runs if r["case_id"].split("-")[0] == prefix
        ]
        by_prefix[prefix] = {
            "runs": len(prefix_runs),
            "engaged": sum(1 for r in prefix_runs if is_engaged(r)),
        }
    return {
        "total": _bucket(runs),
        "engaged": _bucket(engaged),
        "non_engaged": _bucket(non_engaged),
        "by_prefix": by_prefix,
    }
```

In `evals/run.py`: change the harness import line to

```python
from harness import agent, cases, engagement, report, verify  # noqa: E402
```

add after `cmd_report`:

```python
def cmd_engagement(args) -> int:
    for out in args.out:
        runs = report.load_runs(Path(out))
        if not runs:
            print(f"{out}: no runs found", file=sys.stderr)
            return 1
        print(f"== {out}")
        print(json.dumps(engagement.engagement_stats(runs), indent=2))
    return 0
```

and register it in `build_parser()` (after the `p_report` block):

```python
    p_eng = sub.add_parser(
        "engagement",
        help="engagement-conditioned stats for one or more results dirs",
    )
    p_eng.add_argument("--out", action="append", required=True)
    p_eng.set_defaults(func=cmd_engagement)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `evals/.venv/bin/python -m pytest evals/tests -q`
Expected: all pass.

- [ ] **Step 5: Sanity-check against real Phase 3/4 data**

Run:
```bash
evals/.venv/bin/python evals/run.py engagement \
  --out evals/results/2026-07-06-phase3-aliases-skill \
  --out evals/results/2026-07-07-phase4-docstrings-skill
```
Expected: engaged runs **15** (Phase 3) and **13** (Phase 4), engaged misuse 0 in both, non-engaged misuse 8 and 17 — matching analysis.md exactly. If not, STOP and debug before any new run (the metric would be wrong).

- [ ] **Step 6: Commit**

```bash
git add evals/harness/engagement.py evals/run.py evals/tests/test_engagement.py evals/tests/test_run_args.py
git commit  # "ADD: engagement-conditioned stats to the eval harness"
```

---

### Task 4: Author the three skill variants

**Files:**
- Create: `evals/results/2026-07-07-phase4b/variant-a/SKILL.md`
- Create: `evals/results/2026-07-07-phase4b/variant-b/SKILL.md`
- Create: `evals/results/2026-07-07-phase4b/variant-c/SKILL.md`

**Interfaces:**
- Consumes: current `plugin/lcp/skills/lcp-universal/SKILL.md` (base text; frontmatter identical in all variants — the harness strips it, the plugin trigger needs it unchanged).
- Produces: three complete SKILL.md files; Tasks 5–7 pass them via `--skill-file`; Task 11 copies the winner over the plugin file byte-for-byte.

- [ ] **Step 1: Variant A — explicit deferred-tools step (targets the ToolSearch stall)**

Copy the base file, then insert ONE new paragraph immediately after the "Verify before you write." paragraph (i.e., between "…The whole workflow is 3 calls." and "If a library name is provided via arguments…"):

```markdown
**Loading tools is not verifying.** If the lcp tools are deferred (their
names are listed but their schemas are not loaded), load them with
ToolSearch and then IMMEDIATELY make the first real call:
`resolve_library("<package>")`. ToolSearch retrieves no documentation —
if your last tool call was ToolSearch, you have verified nothing yet.
```

Everything else stays byte-identical to the base. Create it with:
```bash
mkdir -p evals/results/2026-07-07-phase4b/variant-{a,b,c}
cp plugin/lcp/skills/lcp-universal/SKILL.md evals/results/2026-07-07-phase4b/variant-a/SKILL.md
# then apply the single-paragraph insertion with the Edit tool
```

- [ ] **Step 2: Variant B — unconditional first action (targets bimodality: the failure is step one)**

Copy the base file, then REPLACE the paragraph

```markdown
**Verify before you write.** If you are not certain a symbol exists with
the exact signature you are about to write — especially for niche, new, or
fast-moving libraries — check it first. The whole workflow is 3 calls.
```

with

```markdown
**Before you write ANY import statement, your FIRST tool call is
`resolve_library("<package>")`.** This is unconditional — do it even when
you feel certain, because memory of library APIs is stale and unreliable.
Code written before `resolve_library` returns is guessed code. The whole
workflow is 3 calls.
```

Everything else stays byte-identical to the base.

- [ ] **Step 3: Variant C — short body (tests the haiku prompt-length compliance hypothesis)**

Write this complete file (frontmatter identical to the base):

````markdown
---
name: lcp-universal
description: This skill should be used when the user writes code that imports or uses a Python library, asks to "look up the X API", "check how to use X", "what's the signature of X.Y", "resolve library X", or encounters import errors or API misuse. Activates the lcp MCP server's resolve → search → get_symbol workflow for on-demand introspection of any pip-installed package.
---

# LCP — Verified Python Library APIs

The `lcp` MCP server serves ground-truth API documentation for any
pip-installed Python library, introspected from the installed version —
never stale, unlike memory.

**Verify before you write.** If you are not certain a symbol exists with
the exact signature you are about to write, check it first — the whole
workflow is 3 calls:

```
resolve_library("polars")                  # 1. load the library (always first)
search("read csv", library="polars")       # 2. find symbols, ranked
get_symbol(ids=["polars:read_csv"])        # 3. exact signature + import line
```

Rules:

- **Never assume** a parameter name, type, or default — `get_symbol` first.
- **Never invent** methods on returned objects — follow
  `usage_hints.returns_classes`.
- Copy the `import` line from responses as-is; batch related ids into ONE
  `get_symbol(ids=[...])` call.
- With two or more libraries loaded, pass `library=<name>` on every call.
- Error responses are structured and carry a `hint` — follow it (e.g.
  "call resolve_library first").
````

- [ ] **Step 4: Verify the variants load and differ**

Run:
```bash
evals/.venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, "evals")
from harness.agent import load_skill_text
texts = {v: load_skill_text(f"evals/results/2026-07-07-phase4b/variant-{v}/SKILL.md") for v in "abc"}
base = load_skill_text("plugin/lcp/skills/lcp-universal/SKILL.md")
assert "ToolSearch" in texts["a"] and "ToolSearch" not in base
assert "unconditional" in texts["b"]
assert len(texts["c"]) < 0.5 * len(base), (len(texts["c"]), len(base))
assert len({t for t in texts.values()}) == 3
print("ok:", {v: len(t) for v, t in texts.items()}, "base", len(base))
EOF
```
Expected: `ok: ...` with variant C < 50% of base length.

- [ ] **Step 5: Commit**

```bash
git add evals/results/2026-07-07-phase4b
git commit  # "ADD: Phase 4b skill variants A/B/C for the engagement experiment"
```

---

### Task 5: Run variant A eval (8 F1 cases × 3 reps)

**Files:**
- Create: `evals/results/2026-07-07-phase4b/variant-a/{runs/,summary.json,report.md,mcp-config.json,meta.json}` (runner output + hand-written meta)

**Interfaces:**
- Consumes: `--skill-file` (Task 2), variant A file (Task 4), env values recorded in Task 1.
- Produces: 24 run JSONs consumed by Task 8.

- [ ] **Step 1: Launch the run (~30 min, ~$1.30 — run in background, then monitor)**

```bash
evals/.venv/bin/python evals/run.py run \
  --out evals/results/2026-07-07-phase4b/variant-a \
  --arms lcp-skill --reps 3 --workers 2 \
  --model claude-haiku-4-5-20251001 \
  --skill-file evals/results/2026-07-07-phase4b/variant-a/SKILL.md \
  --case-id fastmcp-server-tool --case-id fastmcp-resource \
  --case-id fastmcp-client --case-id fastmcp-context \
  --case-id cyhole-birdeye-price --case-id cyhole-jupiter-swap \
  --case-id cyhole-rugcheck-report --case-id cyhole-missing-api-key
```
Expected first line: `24 runs (8 cases x ['lcp-skill'] x 3 reps)` — if it says 28 cases, kill it immediately (missing filters).

- [ ] **Step 2: Verify completeness**

Run: `ls evals/results/2026-07-07-phase4b/variant-a/runs | wc -l`
Expected: `24`. `summary.json` and `report.md` exist. Any run with `"error"` set → inspect; rerun a rep only if it's a harness error (timeout/CLI crash), never to cherry-pick outcomes (delete the failed file first — the runner skips existing files).

- [ ] **Step 3: Write meta.json**

Create `evals/results/2026-07-07-phase4b/variant-a/meta.json` (fill ⟨⟩ from Task 1):

```json
{
  "experiment": "Phase 4b variant A — deferred-tools step (ToolSearch, then CALL resolve_library), lcp-skill arm, 8 F1 cases",
  "date": "2026-07-07",
  "claude_version": "⟨claude --version⟩",
  "model": "claude-haiku-4-5-20251001",
  "lcp_commit": "⟨git rev-parse --short HEAD⟩ (server code unchanged since Phase 4 — skill text experiment only)",
  "arm": "lcp-skill (variant SKILL.md via --skill-file / --append-system-prompt)",
  "skill_file": "evals/results/2026-07-07-phase4b/variant-a/SKILL.md",
  "cases": ["fastmcp-server-tool", "fastmcp-resource", "fastmcp-client", "fastmcp-context", "cyhole-birdeye-price", "cyhole-jupiter-swap", "cyhole-rugcheck-report", "cyhole-missing-api-key"],
  "reps": 3,
  "reference": "evals/results/2026-07-07-phase4-docstrings-skill and evals/results/2026-07-06-phase3-aliases-skill (same verifier — direct comparison)",
  "note": "evals/.lcp-cache retained from the Phase 4 run (same server code on this branch). Decision metric: engaged runs (>=1 mcp__lcp__* call), engaged misuse must stay 0."
}
```

- [ ] **Step 4: Commit**

```bash
git add evals/results/2026-07-07-phase4b/variant-a
git commit  # "ADD: Phase 4b variant A eval results (8 F1 cases, 3 reps)"
```

---

### Task 6: Run variant B eval

Identical to Task 5 with `variant-a` → `variant-b` everywhere and meta `experiment` = `"Phase 4b variant B — unconditional first action (resolve_library before any import), lcp-skill arm, 8 F1 cases"`, `skill_file` = `evals/results/2026-07-07-phase4b/variant-b/SKILL.md`.

- [ ] **Step 1: Launch** — same command with `--out .../variant-b --skill-file .../variant-b/SKILL.md`; expect `24 runs (8 cases ...)`.
- [ ] **Step 2: Verify completeness** — 24 files in `variant-b/runs/`.
- [ ] **Step 3: Write meta.json** (template above, B values).
- [ ] **Step 4: Commit** — `git add evals/results/2026-07-07-phase4b/variant-b` — `"ADD: Phase 4b variant B eval results (8 F1 cases, 3 reps)"`.

---

### Task 7: Run variant C eval

Identical to Task 5 with `variant-c` and meta `experiment` = `"Phase 4b variant C — compressed skill body (haiku prompt-length compliance test), lcp-skill arm, 8 F1 cases"`, `skill_file` = `evals/results/2026-07-07-phase4b/variant-c/SKILL.md`.

- [ ] **Step 1: Launch** — same command with `variant-c`; expect `24 runs (8 cases ...)`.
- [ ] **Step 2: Verify completeness** — 24 files in `variant-c/runs/`.
- [ ] **Step 3: Write meta.json** (C values).
- [ ] **Step 4: Commit** — `"ADD: Phase 4b variant C eval results (8 F1 cases, 3 reps)"`.

---

### Task 8: Comparative analysis + winner decision

**Files:**
- Create: `evals/results/2026-07-07-phase4b/analysis.md`

**Interfaces:**
- Consumes: `run.py engagement` CLI (Task 3), the three variant dirs (Tasks 5–7), Phase 3/4 reference dirs.
- Produces: the winner decision (per the Decision Rule) consumed by Task 11 and the roadmap update (Task 12).

- [ ] **Step 1: Compute the decision table**

```bash
evals/.venv/bin/python evals/run.py engagement \
  --out evals/results/2026-07-07-phase4b/variant-a \
  --out evals/results/2026-07-07-phase4b/variant-b \
  --out evals/results/2026-07-07-phase4b/variant-c \
  --out evals/results/2026-07-06-phase3-aliases-skill \
  --out evals/results/2026-07-07-phase4-docstrings-skill
```

- [ ] **Step 2: Write `analysis.md`** following the structure of `evals/results/2026-07-07-phase4-docstrings-skill/analysis.md`: comparison base line (both references, CLI versions), a per-variant table with columns — engaged/24, engaged pass, **engaged misuse (must be 0)**, non-engaged pass/misuse, pass rate/24, cyhole vs fastmcp engagement split — plus Phase 3/4 baseline rows; a "Reading" section (did the targeted mechanism move? e.g. did variant A reduce lone-ToolSearch stalls — check `tool_call_details` of non-engaged runs for the pattern); the explicit winner per the Decision Rule with the rule quoted; a placeholder-free honest statement of whether ≥18/24 was met. Leave a `## Hook experiment` section stub to be filled by Task 10.

- [ ] **Step 3: Commit**

```bash
git add evals/results/2026-07-07-phase4b/analysis.md
git commit  # "ADD: Phase 4b comparative engagement analysis"
```

---

### Task 9: PreToolUse verify-reminder hook (TDD)

**Files:**
- Create: `plugin/lcp/hooks/verify_reminder.py`
- Modify: `plugin/lcp/hooks/hooks.json`
- Test: `tests/test_plugin_hooks.py` (new, runs in the MAIN venv)

**Interfaces:**
- Consumes: Claude Code hook contract — stdin JSON with `tool_name`, `tool_input`, `transcript_path`; exit 0 = allow, exit 2 + stderr = block with model-visible feedback.
- Produces: `verify_reminder.py` (stdlib-only, python3) used by Task 10's smoke test and shipped in the plugin.

Note: this task is independent of Tasks 5–8 and may be done while eval runs execute.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugin_hooks.py`:

```python
"""Tests for the plugin's PreToolUse verify-reminder hook.

The hook is exercised exactly as Claude Code runs it: a subprocess with the
hook payload on stdin. Exit 0 = allow the tool call; exit 2 = block it and
feed stderr back to the model. The hook must fail OPEN on every anomaly.
"""

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "plugin/lcp/hooks/verify_reminder.py"
HOOKS_JSON = Path(__file__).parent.parent / "plugin/lcp/hooks/hooks.json"


def run_hook(payload):
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=data, capture_output=True, text=True, timeout=10,
    )


def payload(tmp_path, transcript_text, file_path="script.py"):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(transcript_text)
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": "import x"},
        "transcript_path": str(transcript),
    }


class TestVerifyReminderHook:
    def test_blocks_py_write_without_lcp_call(self, tmp_path):
        result = run_hook(payload(tmp_path, '{"type": "user"}\n'))
        assert result.returncode == 2
        assert "lcp-verify-reminder" in result.stderr
        assert "resolve_library" in result.stderr

    def test_allows_after_lcp_call(self, tmp_path):
        transcript = json.dumps({
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "name": "mcp__lcp__resolve_library",
                "input": {"name": "cyhole"},
            }]},
        }) + "\n"
        assert run_hook(payload(tmp_path, transcript)).returncode == 0

    def test_reminds_only_once(self, tmp_path):
        # After one block, the marker is in the transcript: never nag again.
        transcript = '{"type": "user", "content": "[lcp-verify-reminder] ..."}\n'
        assert run_hook(payload(tmp_path, transcript)).returncode == 0

    def test_mention_of_tool_name_in_prose_does_not_count_as_a_call(self, tmp_path):
        # e.g. a deferred-tools listing that cites mcp__lcp__resolve_library
        # as plain text is NOT an lcp call.
        result = run_hook(payload(
            tmp_path, '{"type": "user", "content": "tools: mcp__lcp__resolve_library"}\n'
        ))
        assert result.returncode == 2

    def test_ignores_non_python_files(self, tmp_path):
        assert run_hook(payload(tmp_path, "{}", file_path="notes.md")).returncode == 0

    def test_fails_open_on_missing_transcript(self):
        p = {"tool_name": "Write", "tool_input": {"file_path": "a.py"},
             "transcript_path": "/nonexistent/transcript.jsonl"}
        assert run_hook(p).returncode == 0

    def test_fails_open_on_malformed_stdin(self):
        assert run_hook("not json").returncode == 0


class TestHooksJson:
    def test_wires_pretooluse_to_hook_script(self):
        config = json.loads(HOOKS_JSON.read_text())
        pre = config["hooks"]["PreToolUse"]
        assert pre[0]["matcher"] == "Write|Edit"
        assert "verify_reminder.py" in pre[0]["hooks"][0]["command"]
        assert "${CLAUDE_PLUGIN_ROOT}" in pre[0]["hooks"][0]["command"]

    def test_keeps_sessionstart_hook(self):
        config = json.loads(HOOKS_JSON.read_text())
        assert "SessionStart" in config["hooks"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_plugin_hooks.py -v`
Expected: FAIL — hook script missing (FileNotFoundError/exit != expected) and `KeyError: 'PreToolUse'`.

- [ ] **Step 3: Implement the hook script**

Create `plugin/lcp/hooks/verify_reminder.py`:

```python
#!/usr/bin/env python3
"""PreToolUse hook (Write|Edit): once per session, block the first .py write
that happens before any lcp verification call and remind the agent to verify.

Claude Code hook contract:
- stdin: JSON payload with tool_name, tool_input, transcript_path.
- exit 0          -> allow the tool call.
- exit 2 + stderr -> block the call; stderr is fed back to the model.

Fail-open everywhere: a broken hook must never block real work.
"""

import json
import re
import sys
from pathlib import Path

MARKER = "lcp-verify-reminder"
# A real lcp tool call appears in the transcript as a tool_use block whose
# "name" field starts with mcp__lcp__ — prose mentions of tool names don't.
LCP_CALL = re.compile(r'"name"\s*:\s*"mcp__lcp__')
REMINDER = (
    f"[{MARKER}] You are writing a Python file but have made no lcp "
    'verification call this session. If this code imports a third-party '
    'library, verify the APIs first: call resolve_library("<package>"), '
    "then get_symbol on the symbols you use. If the lcp server is "
    "unavailable or no third-party library is involved, repeat this "
    "Write/Edit unchanged and it will go through."
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    tool_input = payload.get("tool_input") or {}
    if not str(tool_input.get("file_path", "")).endswith(".py"):
        return 0
    try:
        transcript = Path(str(payload.get("transcript_path", ""))).read_text()
    except OSError:
        return 0
    if MARKER in transcript or LCP_CALL.search(transcript):
        return 0
    print(REMINDER, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

Overwrite `plugin/lcp/hooks/hooks.json` with:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/generate-config.sh\"",
            "timeout": 10 }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          { "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/verify_reminder.py\"",
            "timeout": 10 }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_plugin_hooks.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add plugin/lcp/hooks/verify_reminder.py plugin/lcp/hooks/hooks.json tests/test_plugin_hooks.py
git commit  # "ADD: PreToolUse verify-reminder hook to the Claude Code plugin"
```

---

### Task 10: Hook headless smoke test

**Files:**
- Modify: `evals/results/2026-07-07-phase4b/analysis.md` (fill the `## Hook experiment` section)
- Scratch: settings + outputs under the session scratchpad (NOT committed)

**Interfaces:**
- Consumes: `verify_reminder.py` (Task 9), any variant dir's `mcp-config.json` (written by the runner in Tasks 5–7).
- Produces: the hook ship/no-ship decision per Decision Rule item 5.

Rationale (recorded in the analysis): the F1 eval denies Write/Edit (`--disallowedTools` in `evals/harness/agent.py`) and asks for a fenced code block, so this hook **cannot fire in F1 runs** — it is eval-neutral by construction and must be judged on deterministic behavior instead.

- [ ] **Step 1: Prepare scratch settings**

In the scratchpad directory, create `hook-smoke/settings.json` (absolute path — `${CLAUDE_PLUGIN_ROOT}` doesn't resolve outside the plugin):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          { "type": "command",
            "command": "python3 /Users/andreazanini/Projects/lcp/lcp/plugin/lcp/hooks/verify_reminder.py",
            "timeout": 10 }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Run the smoke (3 reps)**

From the `hook-smoke` directory:

```bash
claude -p "Using the cyhole Python library (already installed), create a file price.py IN THE CURRENT DIRECTORY with the Write tool. It should fetch the current price of a token via Birdeye. You must actually write the file." \
  --model claude-haiku-4-5-20251001 \
  --settings settings.json \
  --mcp-config /Users/andreazanini/Projects/lcp/lcp/evals/results/2026-07-07-phase4b/variant-a/mcp-config.json \
  --strict-mcp-config \
  --allowedTools Write --allowedTools mcp__lcp \
  --output-format stream-json --verbose > smoke-r1.jsonl
```

(repeat with `smoke-r2.jsonl`, `smoke-r3.jsonl`; delete any `price.py` between reps).

- [ ] **Step 3: Evaluate against Decision Rule item 5**

For each rep, grep the jsonl: count occurrences of `lcp-verify-reminder` (expect ≥1 block event, and the reminder text delivered at most once as feedback), check whether `mcp__lcp__resolve_library` appears BEFORE the successful Write, and confirm `price.py` was ultimately written. Record per-rep outcomes in the `## Hook experiment` section of `analysis.md`: fired?, once-only?, agent redirected to the server?, write completed?, ship decision. If the model called the server before writing (hook never fires, exit 0 path) that is a PASS for non-interference — note it and verify the firing path is still covered by the unit tests.

- [ ] **Step 4: Commit**

```bash
git add evals/results/2026-07-07-phase4b/analysis.md
git commit  # "UPD: Record hook smoke-test results in the Phase 4b analysis"
```

---

### Task 11: Ship the winner + docs alignment

**Files:**
- Modify: `plugin/lcp/skills/lcp-universal/SKILL.md` (only if a variant qualified per Decision Rule 3)
- Modify: `docs/guides/claude-code-plugin.md` (only if the hook ships per Decision Rule 5)

**Interfaces:**
- Consumes: winner decision (Task 8), hook decision (Task 10).
- Produces: shipped plugin artifacts; docs consistent with them.

- [ ] **Step 1: Ship the winning skill text (conditional)**

If a variant qualified (engaged ≥16/24, engaged misuse 0):
```bash
cp evals/results/2026-07-07-phase4b/variant-⟨x⟩/SKILL.md plugin/lcp/skills/lcp-universal/SKILL.md
git diff --stat plugin/lcp/skills/lcp-universal/SKILL.md
```
If NO variant qualified: skip (shipped skill stays as-is) and say so in the commit body of Task 12.

- [ ] **Step 2: Docs alignment (use the `lcp-writing-documentation` skill)**

If the hook ships, in `docs/guides/claude-code-plugin.md`:

(a) Replace the "What's included" table row

```markdown
| **Session hook** | Auto-generates `.lcp.json` for the active project when absent, seeding it from `settings.json` `pluginConfigs` values |
```

with

```markdown
| **Session hook** | Auto-generates `.lcp.json` for the active project when absent, seeding it from `settings.json` `pluginConfigs` values |
| **Verification reminder hook** | If Claude reaches its first Python file write without having consulted `lcp`, a `PreToolUse` hook holds that one write and reminds it to verify the library APIs first — at most once per session, Python files only |
```

(b) Append one sentence to the paragraph ending "…they change how Claude uses it." (line ~125):

```markdown
A `PreToolUse` hook backs the skill deterministically: the first time a session writes a `.py` file without any prior `lcp` call, the write is held once with a reminder to verify — repeating the write (or calling `resolve_library`) proceeds normally.
```

The skill file itself is shipped docs; no other page quotes its body (verified via grep), so no further doc edits for the skill change.

- [ ] **Step 3: Build docs strictly**

Run: `.venv/bin/python -m mkdocs build --strict` (install `.[docs]` extras into `.venv` first if `mkdocs` is missing).
Expected: build succeeds, zero warnings.

- [ ] **Step 4: Full main suite (end gate)**

Run: `.venv/bin/python -m pytest -q`
Expected: `540 passed` (532 + 8 hook tests), 0 failed. Also rerun `evals/.venv/bin/python -m pytest evals/tests -q` — all green.

- [ ] **Step 5: Commit**

```bash
git add plugin/lcp/skills/lcp-universal/SKILL.md docs/guides/claude-code-plugin.md
git commit  # "UPD: Ship Phase 4b winning skill variant and document the reminder hook"
```

---

### Task 12: Roadmap update

**Files:**
- Modify: `docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md` — Phase 4b **Status** line (line ~632) and **Eval results log** table (line ~957)

- [ ] **Step 1: Update the Phase 4b Status line** to `done (2026-07-07) — <one-line outcome: winner variant + engaged count vs baseline, hook shipped or not, plan link docs/superpowers/plans/2026-07-07-phase-4b-engagement.md>`. If no variant qualified, status records that honestly and notes the hand-off to Phase 8 task-mix design (the roadmap's foreseen exit path).

- [ ] **Step 2: Append one Eval results log row per variant** (3 rows), following the existing column format, each noting: engaged x/24 (cyhole a/12, fastmcp b/12), engaged pass, engaged misuse (must read 0), pass rate, CLI version, and for the winner the ship decision; plus the hook smoke outcome in the winner row's notes.

- [ ] **Step 3: Commit (gitignored path — force add)**

```bash
git add -f docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md docs/superpowers/plans/2026-07-07-phase-4b-engagement.md
git commit  # "UPD: Phase 4b status and eval results log in the roadmap"
```

---

### Task 13: PR

- [ ] **Step 1: Push**

```bash
git push -u origin roadmap/phase-4b-engagement
```

- [ ] **Step 2: Open the PR** (public repo: NO session links, no co-author lines)

```bash
gh pr create --base roadmap/agentic-improvements \
  --title "MRG: Phase 4b — engagement iteration (skill variants + reminder hook)" \
  --body "<summary: per-variant engagement table, winner + ship decision, hook decision, references to evals/results/2026-07-07-phase4b/analysis.md; note the freeze was respected (no server/manifest changes)>"
```

- [ ] **Step 3: Verify CI green** on the PR (CodeQL + tests), fix trivial breakage if any.

---

## Self-review notes

- Spec coverage: variants A/B/C (Tasks 4–7), hook experiment (9–10), engagement methodology + `claude --version` in meta (Tasks 1, 3, 5–7), comparison vs Phase 3/4 (Tasks 3 step 5, 8), ship winner + docs-alignment (11), roadmap status + per-variant log (12), MRG PR (13), honest-failure exit path (Decision Rule 4, Tasks 11–12 conditionals).
- The eval-can't-measure-the-hook constraint is stated in Task 10 and recorded in the analysis, satisfying "record honestly".
- Type consistency: `build_parser` (Tasks 2, 3), `engagement_stats`/`is_engaged` (Tasks 3, 8), `verify_reminder.py` path (Tasks 9, 10), variant paths (Tasks 4–8, 11) all match.
