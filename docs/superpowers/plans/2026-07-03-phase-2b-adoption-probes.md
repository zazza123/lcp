# Phase 2b — Adoption Probes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run two cheap, targeted experiments that determine which lever closes the F1 adoption gap — the shipped plugin skill or model class — and record an explicit A/B/C decision in the roadmap, adding a "forcing functions" phase only if both levers fail.

**Architecture:** Extend the existing eval harness (`evals/`) minimally, keeping its "arms differ by flags only" discipline: a third arm `lcp-skill` (= the `lcp` arm plus `--append-system-prompt` carrying the `lcp-universal` SKILL.md body verbatim), a `--model` override for the sonnet probe, and per-run `tool_call_details` capture for adoption-quality analysis. No `src/lcp/` changes.

**Tech Stack:** Python ≥3.10 (evals venv, fastmcp 2.14.4 runtime), `claude` CLI headless, pytest for harness unit tests.

## Global Constraints

- Read first: roadmap section **"Phase 2b — Adoption probes"** in `docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md` — it holds the evidence (E1–E4), the experiment definitions, and the A/B/C decision rule this plan implements. Do not re-derive or re-litigate them.
- Everything runs from the **evals venv**: `evals/.venv/bin/python`. Do NOT `pip install -e ".[dev]"` there (fastmcp==2.14.4 is a pinned eval target; see the note in `evals/README.md`).
- Harness unit tests: `evals/.venv/bin/python -m pytest evals/tests -q` (they import via `sys.path` trickery — run from repo root; if imports fail, run as `cd evals && .venv/bin/python -m pytest tests -q`).
- The main package suite is untouched by this phase, but run it once at the end from the project venv as a no-regression check: `.venv/bin/python -m pytest tests/ -q` (ignore the known env-dependent `test_publish_no_token` failure when `LCP_GITHUB_TOKEN` is set; prefix with `env -u LCP_GITHUB_TOKEN -u GITHUB_PERSONAL_ACCESS_TOKEN`).
- Skill text must be injected **verbatim** from `plugin/lcp/skills/lcp-universal/SKILL.md` (frontmatter stripped) — we are measuring the shipped artifact, not a paraphrase.
- Pinned model stays `claude-haiku-4-5-20251001` for Exp1; Exp2 uses `claude-sonnet-5`. Record `claude --version` in each results dir's `meta.json`.
- Commits follow the `git-commit-convention` skill (`CODE: Title` + body); **no Co-Authored-By / session links** (public repo).
- Branch: start from updated `roadmap/agentic-improvements`, branch `roadmap/phase-2b-adoption-probes`, PR back with title `CODE: ...`.
- `docs/superpowers/` is gitignored — roadmap/plan commits need `git add -f`.
- The 8 F1-sensitive case ids: `fastmcp-server-tool fastmcp-resource fastmcp-client fastmcp-context cyhole-birdeye-price cyhole-jupiter-swap cyhole-rugcheck-report cyhole-missing-api-key`.

---

### Task 1: Capture `tool_call_details` in the stream parser

**Files:**
- Modify: `evals/harness/agent.py` (`parse_stream`, `AgentRun`, `run_agent`)
- Modify: `evals/run.py` (`_run_one` record)
- Test: `evals/tests/test_agent.py`

**Interfaces:**
- Produces: `parse_stream(lines)["tool_call_details"]: list[dict]` — one `{"name": str, "input": dict}` per tool_use block, in stream order, `input` truncated to 500 chars of JSON per call.
- Produces: `AgentRun.tool_call_details: list` field; run JSON gains `"tool_call_details"` at the top level (next to `metrics`).

- [ ] **Step 1: Write the failing test**

Add to `evals/tests/test_agent.py` inside `TestParseStream` (the module-level `STREAM_LINES` fixture already contains one `tool_use` block named `mcp__lcp__resolve_library`):

```python
    def test_collects_tool_call_details(self):
        details = parse_stream(STREAM_LINES)["tool_call_details"]
        assert details == [
            {"name": "mcp__lcp__resolve_library", "input": {}}
        ]

    def test_tool_call_input_is_truncated(self):
        lines = [
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "mcp__lcp__search",
                 "input": {"query": "x" * 2000}}]}}),
            STREAM_LINES[-1],
        ]
        details = parse_stream(lines)["tool_call_details"]
        assert details[0]["name"] == "mcp__lcp__search"
        assert len(json.dumps(details[0]["input"])) <= 520
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `evals/.venv/bin/python -m pytest evals/tests/test_agent.py -q`
Expected: FAIL with `KeyError: 'tool_call_details'`.

- [ ] **Step 3: Implement**

In `evals/harness/agent.py`, replace the tool-counting hunk of `parse_stream` and thread the field through:

```python
def _truncate_input(value: dict, limit: int = 500) -> dict:
    """Keep tool inputs analyzable without bloating run files."""
    encoded = json.dumps(value)
    if len(encoded) <= limit:
        return value
    return {"_truncated": encoded[:limit]}
```

In `parse_stream`, replace `tool_calls = 0` / the assistant branch with:

```python
    tool_calls = 0
    tool_call_details: list[dict] = []
    result: dict = {}
    for line in lines:
        ...
        if event.get("type") == "assistant":
            content = event.get("message", {}).get("content", [])
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tool_calls += 1
                    tool_call_details.append(
                        {
                            "name": b.get("name", ""),
                            "input": _truncate_input(b.get("input") or {}),
                        }
                    )
```

and add `"tool_call_details": tool_call_details,` to the returned dict.

In `AgentRun`, add the field `tool_call_details: list = None  # type: ignore[assignment]` — actually use a proper default: add `from dataclasses import field` and declare `tool_call_details: list = field(default_factory=list)` **after** the non-default fields but before `error` (dataclass ordering: fields with defaults must come last — place it right before `error: str | None = None`). Populate it in both `AgentRun(...)` constructions in `run_agent` (empty list in the timeout branch, `parsed["tool_call_details"]` in the normal branch).

In `evals/run.py` `_run_one`, add to the record dict (top level, after `"metrics"`):

```python
        "tool_call_details": result.tool_call_details,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `evals/.venv/bin/python -m pytest evals/tests -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/harness/agent.py evals/run.py evals/tests/test_agent.py
git commit
# ADD: Capture per-run tool-call names and inputs in the eval harness
```

---

### Task 2: `lcp-skill` arm and `--model` override

**Files:**
- Modify: `evals/harness/agent.py` (`build_command`, `run_agent`, new `load_skill_text`)
- Modify: `evals/run.py` (`--arms` choices, `--model` option, `_run_one` threading)
- Test: `evals/tests/test_agent.py`

**Interfaces:**
- Produces: `build_command(prompt, arm, mcp_config, model=MODEL, append_system=None)` — arm `"lcp-skill"` requires both `mcp_config` and `append_system`, adds `--append-system-prompt <text>`; any arm honors `model`.
- Produces: `load_skill_text(path) -> str` — reads a SKILL.md, strips the YAML frontmatter block, returns the body.
- Produces: `run_agent(case, arm, mcp_config=None, timeout=TIMEOUT_S, model=MODEL, append_system=None)`.
- Produces: `run.py` CLI — `--arms {both,baseline,lcp,lcp-skill}`, `--model TEXT` (default: `agent.MODEL`); the run record's `"model"` field reflects the override.

- [ ] **Step 1: Write the failing tests**

Add to `evals/tests/test_agent.py`:

```python
from pathlib import Path

from harness.agent import load_skill_text


class TestBuildCommandArms:
    def test_lcp_skill_arm_appends_system_prompt(self):
        cmd = build_command(
            "do things", "lcp-skill", "/tmp/mcp.json",
            append_system="SKILL BODY",
        )
        assert "--mcp-config" in cmd
        i = cmd.index("--append-system-prompt")
        assert cmd[i + 1] == "SKILL BODY"

    def test_lcp_skill_arm_requires_append_system(self):
        import pytest

        with pytest.raises(ValueError):
            build_command("p", "lcp-skill", "/tmp/mcp.json")

    def test_model_override(self):
        cmd = build_command("p", "baseline", None, model="claude-sonnet-5")
        i = cmd.index("--model")
        assert cmd[i + 1] == "claude-sonnet-5"

    def test_default_model_unchanged(self):
        cmd = build_command("p", "baseline", None)
        assert cmd[cmd.index("--model") + 1] == MODEL


class TestLoadSkillText:
    def test_strips_frontmatter(self, tmp_path: Path):
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: x\ndescription: y\n---\n\n# Body\n\ntext\n")
        body = load_skill_text(skill)
        assert body.startswith("# Body")
        assert "name: x" not in body

    def test_real_skill_loads(self):
        real = Path(__file__).parents[2] / "plugin/lcp/skills/lcp-universal/SKILL.md"
        body = load_skill_text(real)
        assert "resolve_library" in body
        assert not body.startswith("---")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `evals/.venv/bin/python -m pytest evals/tests/test_agent.py -q`
Expected: FAIL (ImportError on `load_skill_text`, TypeError on new kwargs).

- [ ] **Step 3: Implement**

In `evals/harness/agent.py`:

```python
def load_skill_text(path) -> str:
    """Return a SKILL.md body with the YAML frontmatter stripped.

    Injected verbatim via --append-system-prompt: the experiment measures
    the shipped skill artifact, not a paraphrase of it.
    """
    text = Path(path).read_text()
    if text.startswith("---"):
        end = text.index("---", 3)
        text = text[end + 3:]
    return text.strip() + "\n"
```

(add `from pathlib import Path` to the imports.)

Update `build_command`:

```python
def build_command(
    prompt: str,
    arm: str,
    mcp_config: str | None,
    model: str = MODEL,
    append_system: str | None = None,
) -> list[str]:
    """Build the claude CLI command; arms differ ONLY by flags.

    baseline    : no MCP config.
    lcp         : + --mcp-config (the server's instructions are the only nudge).
    lcp-skill   : lcp + --append-system-prompt with the lcp-universal skill
                  body — approximates what a developer with the plugin
                  installed experiences (the skill fires task-side).

    (keep the existing docstring paragraphs about --disallowedTools and
    --allowedTools verbatim below this)
    """
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "stream-json", "--verbose",
        "--strict-mcp-config",
        "--disallowedTools", *BUILTIN_TOOLS,
        "--allowedTools", "mcp__lcp",
    ]
    if arm in ("lcp", "lcp-skill"):
        if mcp_config is None:
            raise ValueError(f"{arm} arm requires an mcp_config path")
        cmd += ["--mcp-config", str(mcp_config)]
    if arm == "lcp-skill":
        if append_system is None:
            raise ValueError("lcp-skill arm requires append_system text")
        cmd += ["--append-system-prompt", append_system]
    return cmd
```

Update `run_agent` signature to `(case, arm, mcp_config=None, timeout=TIMEOUT_S, model=MODEL, append_system=None)` and pass both through to `build_command`.

In `evals/run.py`:

- `--arms` choices become `["both", "baseline", "lcp", "lcp-skill"]` (`both` still means `["baseline", "lcp"]` — the skill arm is always explicit).
- Add `p_run.add_argument("--model", default=agent.MODEL)`.
- In `cmd_run`, load the skill body once when needed:

```python
    append_system = None
    if "lcp-skill" in arms:
        skill_path = (
            EVALS_DIR.parent / "plugin/lcp/skills/lcp-universal/SKILL.md"
        )
        append_system = agent.load_skill_text(skill_path)
```

- Thread `args.model` and `append_system` into `_run_one` (extend its signature: `_run_one(case, arm, rep, mcp_config, runs_dir, model, append_system)`), which calls:

```python
    result = agent.run_agent(
        case, arm,
        mcp_config if arm in ("lcp", "lcp-skill") else None,
        model=model,
        append_system=append_system if arm == "lcp-skill" else None,
    )
```

and records `"model": model` (replacing `agent.MODEL`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `evals/.venv/bin/python -m pytest evals/tests -q`
Expected: all PASS. Also smoke the CLI plumbing without spending money: `evals/.venv/bin/python evals/run.py run --help` shows the new flags.

- [ ] **Step 5: Update `evals/README.md`**

Document the third arm and the model flag in the **Commands** section: `--arms both|baseline|lcp|lcp-skill` (lcp-skill = lcp + the lcp-universal skill body via `--append-system-prompt`, always explicit, never part of `both`) and `--model` (default pinned haiku; used by the Phase 2b sonnet probe — cross-model comparability caveat applies). One paragraph, matching the file's existing tone.

- [ ] **Step 6: Commit**

```bash
git add evals/harness/agent.py evals/run.py evals/tests/test_agent.py evals/README.md
git commit
# ADD: Add lcp-skill arm and model override to the eval harness
```

---

### Task 3: Exp1 — the skill arm on the 8 F1-sensitive cases

**Files:**
- Create: `evals/results/<today>-phase2b-skill/` (committed)

- [ ] **Step 1: Run (background; ~24 runs, resumable)**

```bash
claude --version   # record below
evals/.venv/bin/python evals/run.py run \
  --out evals/results/$(date +%F)-phase2b-skill \
  --arms lcp-skill \
  --case-id fastmcp-server-tool --case-id fastmcp-resource \
  --case-id fastmcp-client --case-id fastmcp-context \
  --case-id cyhole-birdeye-price --case-id cyhole-jupiter-swap \
  --case-id cyhole-rugcheck-report --case-id cyhole-missing-api-key
```

Write a `meta.json` in the results dir: `claude_version`, `model`, `lcp_commit` (`git rev-parse --short HEAD`), and `"arm": "lcp-skill (lcp-universal SKILL.md via --append-system-prompt)"`.

- [ ] **Step 2: Analyze the gate metric**

Per-library mean tool calls, passes, misuse (same one-liner used at Phase 2 close):

```bash
evals/.venv/bin/python - <<'EOF'
import json, glob
from collections import defaultdict
lib = defaultdict(lambda: {"tools": 0, "passes": 0, "runs": 0, "misuse": 0})
for f in glob.glob("evals/results/*-phase2b-skill/runs/*.json"):
    d = json.load(open(f))
    L = lib[d["case_id"].split("-")[0]]
    L["tools"] += d["metrics"]["tool_calls"]
    L["runs"] += 1
    L["passes"] += 1 if d["verification"]["passed"] else 0
    L["misuse"] += d["verification"]["misuse_count"]
for k, v in sorted(lib.items()):
    print(f"{k:10} tools/run={v['tools']/max(v['runs'],1):.1f} "
          f"pass={v['passes']}/{v['runs']} misuse={v['misuse']}")
EOF
```

Reference numbers (Phase 2, `lcp` arm, same cases): fastmcp **0.0** calls, 1/12 pass; cyhole 2.3–3.6 calls, 2–4/12 pass. **Gate: fastmcp mean calls ≥1.0/run → outcome A.**

- [ ] **Step 3: Adoption-quality analysis (feeds Phase 3)**

Using `tool_call_details` on the engaged cyhole runs: for each run with ≥1 `mcp__lcp__get_symbol` call, list the requested ids next to `verification.forbidden_used`/`unresolved_usages` — does the model verify symbol A and still write symbol B? Summarize in 3–5 sentences; this goes into the results commit message and the Phase 3 session notes (roadmap Phase 3 **Code notes** if actionable).

- [ ] **Step 4: Commit**

```bash
git add evals/results/*-phase2b-skill
git commit
# UPD: Record Phase 2b Exp1 (skill-arm adoption probe)
```

---

### Task 4: Exp2 — sonnet model probe on the fastmcp cases

**Files:**
- Create: `evals/results/<today>-phase2b-sonnet/` (committed)

- [ ] **Step 1: Run (both arms so pass-rate has context; 24 runs)**

```bash
evals/.venv/bin/python evals/run.py run \
  --out evals/results/$(date +%F)-phase2b-sonnet \
  --arms both --model claude-sonnet-5 \
  --case-id fastmcp-server-tool --case-id fastmcp-resource \
  --case-id fastmcp-client --case-id fastmcp-context
```

Write `meta.json` as in Task 3 (`model: claude-sonnet-5`). Note: sonnet runs cost more per token but n=24 keeps this a few dollars.

- [ ] **Step 2: Analyze**

Same per-library script against `*-phase2b-sonnet/runs/*_lcp_*.json` plus the baseline arm for pass context. **Gate: fastmcp mean voluntary calls in the `lcp` arm ≥1.0/run → outcome B (if Exp1 was ~0).** Also worth recording: does sonnet's *baseline* arm already avoid the `fastmcp.Server` hallucination? If yes, the fastmcp cases may be at ceiling for capable models — note it for the Phase 8 task mix (E4-style calibration).

- [ ] **Step 3: Commit**

```bash
git add evals/results/*-phase2b-sonnet
git commit
# UPD: Record Phase 2b Exp2 (sonnet adoption probe)
```

---

### Task 5: Decision, roadmap update, PR

**Files:**
- Modify: `docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md` (Phase 2b **Status**, Eval results log, conditionally a new Phase 2c section)

- [ ] **Step 1: Apply the decision rule**

Take the A/B/C rule verbatim from the roadmap's Phase 2b section and apply it to the Exp1/Exp2 gate numbers:

- **A** (skill closes it): write into Phase 2b Status: outcome A, one-paragraph rationale with numbers, and the binding consequence: *Phase 8's harness MUST include an `lcp-skill` arm.* Add that line to Phase 8's section too. No new phase.
- **B** (model-bound): outcome B in Status; consequence: product guidance (small models need the skill; capable models self-serve) recorded in Phase 8's model-mix notes. No new phase.
- **C** (both dead): outcome C in Status; append a new roadmap section **"Phase 2c — Adoption forcing functions"** modeled on the other phase sections (Status: not started; Objective: mechanical adoption via plugin hook intercepting unverified third-party imports at Write/Edit time + `/lcp:resolve` promotion; Scope in/out; Code notes pointing at `plugin/lcp/hooks/hooks.json` and the eval evidence; Exit criteria gated on the same 8 cases). Position it between Phase 2b and Phase 3.

- [ ] **Step 2: Update the Eval results log**

Two rows (Exp1, Exp2) following the existing table format: config, gate metric front and center in Notes, pass/misuse for context.

- [ ] **Step 3: Final verification**

```bash
evals/.venv/bin/python -m pytest evals/tests -q          # harness green
env -u LCP_GITHUB_TOKEN -u GITHUB_PERSONAL_ACCESS_TOKEN .venv/bin/python -m pytest tests/ -q   # package unaffected
```

Docs site is untouched by this phase (evals/ and docs/superpowers/ are not part of the MkDocs tree) — no `mkdocs build` needed unless you touched `docs/`.

- [ ] **Step 4: Commit roadmap + PR**

```bash
git add -f docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md
git commit
# UPD: Record Phase 2b decision and close the phase in the roadmap
git push -u origin roadmap/phase-2b-adoption-probes
gh pr create --base roadmap/agentic-improvements \
  --title "CODE: Phase 2b adoption probes (skill arm + model probe)" \
  --body "<summary with the A/B/C outcome and gate numbers; NO session links>"
```

---

## Self-Review notes (done at plan time)

- **Coverage vs the roadmap section:** harness scope (arm/model/details) → Tasks 1–2; Exp1 → Task 3; Exp2 → Task 4; decision rule + exit criteria (results committed, log updated, A/B/C written, conditional 2c drafted) → Task 5. Secondary cyhole analysis → Task 3 Step 3.
- **Type consistency:** `build_command(..., model, append_system)` matches `run_agent(..., model, append_system)` and `_run_one(..., model, append_system)`; `tool_call_details` name identical in `parse_stream` dict, `AgentRun` field, and run JSON key.
- **Known risks:** (1) dataclass field ordering in `AgentRun` — the new list field must sit with the defaulted fields or instantiation breaks; the timeout branch must pass an explicit empty list. (2) `--append-system-prompt` length: the skill body is ~70 lines, well within CLI arg limits on darwin. (3) If `claude --version` differs from 2.1.200 (Phase 2 runs), note it in `meta.json` — cross-run comparison caveat, not a blocker.
