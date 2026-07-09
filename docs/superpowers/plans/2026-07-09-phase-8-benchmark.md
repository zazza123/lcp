# Phase 8 — Full Benchmark + Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the pre-registered publication benchmark (84 new tasks × 6 arms × 2 models) on the finished product, publish the results as a docs page + README headline, and leave behind a frozen publication profile plus a cheap reusable regression profile.

**Architecture:** The Phase 0–4b harness (`evals/`) is extended, not replaced: a new self-contained benchmark venv (`evals/.venv-bench`, lcp editable + 11 pinned target libraries, fastmcp resolves to 3.x) runs the runner/verifier for the new case set (`evals/cases-v2/`), while the legacy `evals/.venv` (fastmcp 2.14.4) stays untouched so the phase 0–4b results remain reproducible. Three new arms (`sitepkg`, `registry`, `context7`) differ from existing arms only by CLI flags/config per the established single-flag-difference discipline. The registry-only arm runs `lcp serve-all` from a bare venv (`evals/.venv-registry`, lcp only, no targets) so resolution can only succeed via the public registry — which requires publishing the 9 missing target libraries to `zazza123/lcp-registry` first. The skill screening (B vs A vs A+B) happens before the grid; its winner ships in the plugin and the grid measures the shipped artifact.

**Tech Stack:** Python 3.12 (3 evals venvs + main `.venv`), `claude` CLI headless (subscription-billed, multi-day pacing), pytest, `npx @upstash/context7-mcp`, lcp-registry populate machinery (`~/Projects/lcp/lcp-registry` clone), MkDocs.

## Global Constraints

- **FREEZE: no `src/lcp/` changes.** Manifest format and MCP surface are frozen since Phase 4. If the grid exposes a server bug, record it and decide with the user — never hot-fix mid-benchmark (it would invalidate pre-registration).
- Settled decisions (2026-07-09, with the user — binding):
  - Arms (6): `baseline`, `lcp`, `lcp-skill`, `sitepkg`, `registry`, `context7`.
  - Models/reps: `claude-haiku-4-5-20251001` × 5 reps, `claude-sonnet-5` × 3 reps.
  - Libraries (11): cyhole, hamana (reuse, NEW tasks) + pocket-coffea, narwhals, griffe, cyclopts, pixeltable (new niche) + fastmcp 3.x, polars (churned) + requests, flask (ceiling controls).
  - Skill: screening B vs A vs A+B → ship winner → grid measures shipped skill.
  - Billing: user's Claude subscription (Max 5x), paced over multiple days; runner is resumable; rate-limit error records are deleted and relaunched.
  - Two profiles: publication (frozen, pre-registered) + regression (16 tasks, baseline+lcp-skill, haiku, 3 reps, refresh policy).
- Pre-registered metrics (primary): API-misuse rate, task pass rate, tokens/task. Secondary: tool-adoption (engagement) rate, cost-overhead-when-unused, per-cell variance. `tool_calls` counts attempts including denied ones — say so wherever reported.
- **All grid/screening runs happen AFTER the pre-registration commit (Task 9) and are never re-run to cherry-pick outcomes.** Only harness-error records (timeout, CLI crash, rate-limit) are deleted and relaunched (memory: eval-runner case filter).
- Main suite (`.venv`) green at start and end: **593 passed, 0 failed** at start (2026-07-09). Plugin shell tests (`bash tests/plugin/run_all.sh`) green at start.
- Eval venv rules: never `pip install` into `evals/.venv` (fastmcp 2.14.4 pin). New-case commands use `evals/.venv-bench/bin/python`; legacy dirs keep using `evals/.venv`.
- Before every push: `.venv/bin/ruff check src/lcp tests evals`.
- Commits via `git-commit-convention` skill; NO co-author lines / session links (public repo). `docs/superpowers/` committed with `git add -f`.
- Docs via `lcp-writing-documentation` skill; `mkdocs build --strict` clean at end.
- PR: `MRG: ...` → `roadmap/agentic-improvements`; watch CI, resolve findings in-session.
- Post-roadmap cleanup (docs/superpowers removal) is OUT of scope for this session.

## Cost & pacing budget (notional — subscription-billed)

| Block | Runs | Est. notional |
|---|---|---|
| Screening: 3 variants × 8 cases × 5 reps (haiku) | 120 | ~$8 |
| Grid haiku: 84 × 6 arms × 5 reps | 2520 | ~$150 |
| Grid sonnet: 84 × 6 arms × 3 reps | 1512 | ~$250 |
| Smokes/setup | ~50 | ~$5 |
| **Total** | **~4200** | **~$410** |

Pacing: launch per-(model, arm) blocks with `--workers 3`; expect 5-hour-window rate limits — when runs start erroring, stop, wait for the window reset, delete error records, relaunch (runner skips existing files). Expect 2–3 calendar days for the grid.

---

### Task 1: Preflight gates + environment records

**Files:** none created/modified.

**Interfaces:**
- Produces: recorded values used verbatim in every `meta.json` and in `PREREGISTRATION.md`: `claude --version`, `git rev-parse --short HEAD`, main-suite count.

- [ ] **Step 1: Branch and base sanity**

```bash
git branch --show-current        # expect: roadmap/phase-8-benchmark
git log roadmap/agentic-improvements -1 --oneline   # expect: f5ab62c ...
git status --porcelain           # expect: empty (plan file may be untracked)
```

- [ ] **Step 2: Start gates (already run at session start — re-verify if stale)**

```bash
.venv/bin/python -m pytest -q          # expect: 593 passed, 0 failed
bash tests/plugin/run_all.sh           # expect: ALL PLUGIN TESTS PASSED
evals/.venv/bin/python -m pytest evals/tests -q   # legacy harness tests green
```

- [ ] **Step 3: Record environment**

```bash
claude --version && git rev-parse --short HEAD && npx --version
```

Write the three values down; they go into every `meta.json` and the pre-registration doc.

---

### Task 2: Benchmark venv + pinned targets

**Files:**
- Create: `evals/bench-requirements.txt` (input pins)
- Create: `evals/bench-requirements.lock.txt` (full freeze, committed)
- Modify: `evals/README.md` (new venv section — final text in Task 14)

**Interfaces:**
- Produces: `evals/.venv-bench/` (NOT committed; `.venv*` already effectively ignored — verify with `git status`) with lcp editable, pyyaml, pytest and the 11 targets. All later tasks run the runner via `evals/.venv-bench/bin/python`.

- [ ] **Step 1: Write `evals/bench-requirements.txt`**

```
# Phase 8 benchmark targets — resolved+frozen 2026-07-09 into
# bench-requirements.lock.txt (the authoritative pin set).
# lcp itself is installed editable: pip install -e . plus this file.
pocket-coffea
narwhals
griffe
cyclopts
pixeltable
polars
requests
flask
cyhole
hamana
# fastmcp comes in via lcp's own pin (>=3.0,<4) and is ALSO a target.
pyyaml
pytest
```

- [ ] **Step 2: Create the venv and install**

```bash
python3 -m venv evals/.venv-bench
evals/.venv-bench/bin/pip install -e . -r evals/bench-requirements.txt
evals/.venv-bench/bin/pip freeze --exclude-editable > evals/bench-requirements.lock.txt
```

Expected: resolution succeeds (verified 2026-07-09 via dry-run: numpy 1.26.4 satisfies the whole set; pocket-coffea pins coffea 0.7.29).

- [ ] **Step 3: Smoke-import all 11 targets and record pinned versions**

```bash
evals/.venv-bench/bin/python - <<'EOF'
import importlib, importlib.metadata as md
targets = ["cyhole", "hamana", "pocket_coffea", "narwhals", "griffe",
           "cyclopts", "pixeltable", "fastmcp", "polars", "requests", "flask"]
dists = {"pocket_coffea": "pocket-coffea"}
for t in targets:
    importlib.import_module(t)
    print(f"{t:15s} {md.version(dists.get(t, t))}")
import fastmcp
assert fastmcp.__version__.startswith("3."), fastmcp.__version__
EOF
```

Expected: every import succeeds; fastmcp is 3.x. **Write the 11 versions down** — they are the case pins (Task 6–8) and the registry publication versions (Task 5). If pixeltable or pocket-coffea fail at import (side effects), STOP and discuss substitution with the user before authoring cases.

- [ ] **Step 4: Harness tests pass from the bench venv**

```bash
evals/.venv-bench/bin/python -m pytest evals/tests -q
```

Expected: all pass (harness modules are stdlib+pyyaml; nothing fastmcp-2-specific).

- [ ] **Step 5: Bare registry venv**

```bash
python3 -m venv evals/.venv-registry
evals/.venv-registry/bin/pip install -e .
evals/.venv-registry/bin/python -c "import pocket_coffea" 2>&1 | grep -q ModuleNotFoundError && echo BARE-OK
evals/.venv-registry/bin/lcp --version
```

Expected: `BARE-OK` (no targets leak in) and a working `lcp` bin.

- [ ] **Step 6: Commit**

```bash
git add evals/bench-requirements.txt evals/bench-requirements.lock.txt
git commit   # git-commit-convention: "ADD: Phase 8 benchmark venv requirements (11 pinned targets)"
```

---

### Task 3: Harness — new arms in `agent.py`

**Files:**
- Modify: `evals/harness/agent.py` (`build_command`, new constants, `parse_stream` tool-result capture)
- Test: `evals/tests/test_agent_arms.py` (new)

**Interfaces:**
- Consumes: existing `build_command(prompt, arm, mcp_config, model, append_system)` and `BUILTIN_TOOLS`.
- Produces: `build_command` accepting arms `baseline|lcp|lcp-skill|sitepkg|registry|context7`; constants `MCP_ARMS = {"lcp", "lcp-skill", "registry", "context7"}`, `SITEPKG_KEEP = ("Read", "Glob", "Grep")`, `CONTEXT7_RULE` (str); `parse_stream` result gains `"tool_results": list[dict]` and `AgentRun.tool_results`. Task 4 (run.py) relies on these names exactly.

- [ ] **Step 1: Write the failing tests**

Create `evals/tests/test_agent_arms.py`:

```python
"""Arm-matrix tests for build_command: arms differ ONLY by flags."""

import pytest

from harness import agent


def cmd(arm, mcp_config="cfg.json", append_system=None):
    return agent.build_command(
        "P", arm, mcp_config, model="m", append_system=append_system
    )


class TestMcpArms:
    @pytest.mark.parametrize("arm", ["lcp", "lcp-skill", "registry"])
    def test_lcp_server_arms_use_config_and_allow_lcp(self, arm):
        c = cmd(arm, append_system="skill" if arm == "lcp-skill" else None)
        assert "--mcp-config" in c and "cfg.json" in c
        assert c[c.index("--allowedTools") + 1] == "mcp__lcp"

    def test_context7_allows_context7_tools_only(self):
        c = cmd("context7", append_system=agent.CONTEXT7_RULE)
        assert "--mcp-config" in c
        assert c[c.index("--allowedTools") + 1] == "mcp__context7"
        assert "mcp__lcp" not in c

    @pytest.mark.parametrize("arm", sorted(agent.MCP_ARMS))
    def test_mcp_arms_require_config(self, arm):
        with pytest.raises(ValueError):
            cmd(arm, mcp_config=None)


class TestSitepkgArm:
    def test_keeps_read_glob_grep_denies_the_rest(self):
        c = cmd("sitepkg", mcp_config=None, append_system="site-packages: /x")
        i = c.index("--disallowedTools")
        j = c.index("--allowedTools") if "--allowedTools" in c else len(c)
        denied = c[i + 1:j]
        for keep in agent.SITEPKG_KEEP:
            assert keep not in denied
        assert "Bash" in denied and "WebFetch" in denied and "Write" in denied

    def test_no_mcp_and_no_allowed_tools(self):
        c = cmd("sitepkg", mcp_config=None, append_system="x")
        assert "--mcp-config" not in c and "--allowedTools" not in c


class TestBaselineUnchanged:
    def test_baseline_denies_all_builtins_no_mcp(self):
        c = cmd("baseline", mcp_config=None)
        assert "--mcp-config" not in c
        i = c.index("--disallowedTools")
        denied = c[i + 1:i + 1 + len(agent.BUILTIN_TOOLS)]
        assert denied == agent.BUILTIN_TOOLS


class TestAppendSystem:
    def test_any_arm_gets_append_system_when_given(self):
        c = cmd("context7", append_system="RULE")
        assert c[c.index("--append-system-prompt") + 1] == "RULE"

    def test_lcp_skill_still_requires_it(self):
        with pytest.raises(ValueError):
            cmd("lcp-skill", append_system=None)


class TestToolResultCapture:
    def test_parse_stream_records_mcp_tool_results(self):
        lines = [
            '{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "mcp__lcp__search", "input": {"query": "q"}}]}}',
            '{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "RESULT-TEXT"}]}]}}',
            '{"type": "result", "result": "done", "subtype": "success", "usage": {}}',
        ]
        parsed = agent.parse_stream(lines)
        assert parsed["tool_results"] == [
            {"tool_use_id": "t1", "content": "RESULT-TEXT"}
        ]
```

- [ ] **Step 2: Run to verify failure**

```bash
evals/.venv-bench/bin/python -m pytest evals/tests/test_agent_arms.py -q
```

Expected: FAIL (`AttributeError: ... MCP_ARMS`, ValueError not raised for `registry`, etc.).

- [ ] **Step 3: Implement in `evals/harness/agent.py`**

After `BUILTIN_TOOLS`, add:

```python
# Arms that talk to an MCP server (each needs an --mcp-config).
MCP_ARMS = {"lcp", "lcp-skill", "registry", "context7"}
# Built-ins the sitepkg arm keeps: read-only source inspection.
SITEPKG_KEEP = ("Read", "Glob", "Grep")
# Steelman nudge for the context7 arm — the vendor's own recommended
# always-use rule, so the competitor arm gets the same treatment class
# as lcp-skill (a task-side instruction), not a handicapped server.
CONTEXT7_RULE = (
    "Use the context7 MCP tools to look up current library documentation "
    "and code examples before writing code that uses a third-party "
    "library. Resolve the library id first, then fetch the docs for the "
    "APIs you are about to use."
)
```

Replace the body of `build_command` (keep the docstring, extend it with one line per new arm):

```python
    allowed = None
    if arm in ("lcp", "lcp-skill", "registry"):
        allowed = "mcp__lcp"
    elif arm == "context7":
        allowed = "mcp__context7"
    denied = list(BUILTIN_TOOLS)
    if arm == "sitepkg":
        denied = [t for t in BUILTIN_TOOLS if t not in SITEPKG_KEEP]
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "stream-json", "--verbose",
        "--strict-mcp-config",
        "--disallowedTools", *denied,
    ]
    if allowed:
        cmd += ["--allowedTools", allowed]
    if arm in MCP_ARMS:
        if mcp_config is None:
            raise ValueError(f"{arm} arm requires an mcp_config path")
        cmd += ["--mcp-config", str(mcp_config)]
    if arm == "lcp-skill" and append_system is None:
        raise ValueError("lcp-skill arm requires append_system text")
    if append_system is not None:
        cmd += ["--append-system-prompt", append_system]
    return cmd
```

NOTE: baseline/lcp/lcp-skill produce the same flags as before except flag
order (`--allowedTools` after `--disallowedTools` — it already was). Do not
change `BUILTIN_TOOLS` order (a test asserts it).

In `parse_stream`, capture MCP tool results (Context7 content is not
pinnable, so responses must be recorded for reproducibility; lcp responses
are useful evidence too). Track ids of MCP tool_use blocks, then:

```python
    tool_calls = 0
    tool_call_details: list[dict] = []
    tool_results: list[dict] = []
    mcp_ids: set[str] = set()
```

inside the `type == "assistant"` branch, after appending to
`tool_call_details`:

```python
                    if b.get("name", "").startswith("mcp__"):
                        mcp_ids.add(b.get("id", ""))
```

add a new branch before `elif event.get("type") == "result":`:

```python
        elif event.get("type") == "user":
            for b in event.get("message", {}).get("content", []):
                if (
                    isinstance(b, dict)
                    and b.get("type") == "tool_result"
                    and b.get("tool_use_id") in mcp_ids
                ):
                    parts = b.get("content") or []
                    text = " ".join(
                        p.get("text", "") for p in parts
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                    tool_results.append({
                        "tool_use_id": b.get("tool_use_id"),
                        "content": text[:2000],
                    })
```

and add `"tool_results": tool_results,` to the returned dict. Add
`tool_results: list = field(default_factory=list)` to `AgentRun`, thread it
through `run_agent` (both the timeout return — `tool_results=[]` — and the
success return — `tool_results=parsed["tool_results"]`).

- [ ] **Step 4: Run the new tests + full harness suite**

```bash
evals/.venv-bench/bin/python -m pytest evals/tests -q
```

Expected: all pass (existing `build_command`/`parse_stream` tests included).

- [ ] **Step 5: Commit**

```bash
git add evals/harness/agent.py evals/tests/test_agent_arms.py
git commit   # "ADD: sitepkg/registry/context7 arms to the eval agent command builder"
```

---

### Task 4: Harness — runner arm matrix, per-arm configs, models

**Files:**
- Modify: `evals/run.py` (`_write_mcp_config` → per-arm configs, `cmd_run`, `_run_one`, `build_parser`)
- Test: extend `evals/tests/test_run_args.py`

**Interfaces:**
- Consumes: Task 3 names (`MCP_ARMS`, `CONTEXT7_RULE`, `SITEPKG_KEEP`).
- Produces: `run` subcommand with repeatable `--arms` (choices: the 6 arms; default `["baseline", "lcp"]`; the old `both` alias removed), `--registry-lcp-bin` (default `EVALS_DIR / ".venv-registry/bin/lcp"`); `_write_arm_configs(out_dir, libraries, arms, registry_lcp_bin) -> dict[str, Path | None]`; `_sitepkg_note() -> str`; run records gain `"tool_results"`. Tasks 10–12 launch blocks via these flags.

- [ ] **Step 1: Extend `evals/tests/test_run_args.py` (failing tests)**

```python
class TestArmsMatrix:
    def test_arms_repeatable(self):
        args = build_parser().parse_args(
            ["run", "--out", "x", "--arms", "baseline", "--arms", "registry"]
        )
        assert args.arms == ["baseline", "registry"]

    def test_default_arms(self):
        args = build_parser().parse_args(["run", "--out", "x"])
        assert args.arms == ["baseline", "lcp"]

    def test_registry_lcp_bin_default(self):
        args = build_parser().parse_args(["run", "--out", "x"])
        assert str(args.registry_lcp_bin).endswith(".venv-registry/bin/lcp")


class TestArmConfigs:
    def test_writes_one_config_per_mcp_arm_family(self, tmp_path):
        from run import _write_arm_configs

        configs = _write_arm_configs(
            tmp_path, ["polars"],
            ["baseline", "lcp", "lcp-skill", "sitepkg", "registry", "context7"],
            registry_lcp_bin="/reg/bin/lcp",
        )
        assert configs["baseline"] is None and configs["sitepkg"] is None
        assert configs["lcp"] == configs["lcp-skill"]
        import json

        lcp_cfg = json.loads(configs["lcp"].read_text())
        assert "--expose" in lcp_cfg["mcpServers"]["lcp"]["args"]
        reg_cfg = json.loads(configs["registry"].read_text())
        assert reg_cfg["mcpServers"]["lcp"]["command"] == "/reg/bin/lcp"
        assert "--expose" not in reg_cfg["mcpServers"]["lcp"]["args"]
        assert ".lcp-registry-cache" in " ".join(
            reg_cfg["mcpServers"]["lcp"]["args"]
        )
        c7 = json.loads(configs["context7"].read_text())
        assert c7["mcpServers"]["context7"]["command"] == "npx"
```

- [ ] **Step 2: Run to verify failure**

```bash
evals/.venv-bench/bin/python -m pytest evals/tests/test_run_args.py -q
```

Expected: FAIL (argparse rejects repeated `--arms`, `_write_arm_configs` missing).

- [ ] **Step 3: Implement in `evals/run.py`**

Replace `_write_mcp_config` with:

```python
def _write_arm_configs(
    out_dir: Path, libraries: list[str], arms: list[str],
    registry_lcp_bin: str,
) -> dict:
    """One MCP config per arm family; non-MCP arms map to None.

    lcp / lcp-skill : this venv's lcp, scans the bench venv, --expose all.
    registry        : the BARE venv's lcp (no targets installed) with an
                      isolated cache — resolution can only succeed via the
                      public registry, which is the point of the arm.
    context7        : the vendor's server via npx; CONTEXT7_API_KEY is
                      forwarded when set so rate limits don't bite mid-grid.
    """
    import os

    configs: dict = {arm: None for arm in arms}
    if {"lcp", "lcp-skill"} & set(arms):
        lcp_bin = Path(sys.executable).with_name("lcp")
        expose = list(chain.from_iterable(("--expose", lib) for lib in libraries))
        path = out_dir / "mcp-config.json"
        path.write_text(json.dumps({"mcpServers": {"lcp": {
            "command": str(lcp_bin),
            "args": ["serve-all", "--cache-dir",
                     str(EVALS_DIR / ".lcp-cache-bench"), *expose],
        }}}, indent=2))
        for arm in ("lcp", "lcp-skill"):
            if arm in configs:
                configs[arm] = path
    if "registry" in arms:
        path = out_dir / "mcp-config-registry.json"
        path.write_text(json.dumps({"mcpServers": {"lcp": {
            "command": str(registry_lcp_bin),
            "args": ["serve-all", "--cache-dir",
                     str(EVALS_DIR / ".lcp-registry-cache")],
        }}}, indent=2))
        configs["registry"] = path
    if "context7" in arms:
        server: dict = {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]}
        if os.environ.get("CONTEXT7_API_KEY"):
            server["env"] = {"CONTEXT7_API_KEY": os.environ["CONTEXT7_API_KEY"]}
        path = out_dir / "mcp-config-context7.json"
        path.write_text(json.dumps({"mcpServers": {"context7": server}}, indent=2))
        configs["context7"] = path
    return configs


def _sitepkg_note() -> str:
    site = next(Path(sys.executable).parents[1].glob("lib/python*/site-packages"))
    return (
        f"All required libraries are installed under: {site}\n"
        "You may inspect installed package source with the Read, Glob and "
        "Grep tools to verify APIs before using them."
    )
```

In `_run_one`, change the signature and body to take per-arm maps:

```python
def _run_one(
    case, arm: str, rep: int, mcp_configs: dict, runs_dir: Path,
    model: str, append_by_arm: dict,
) -> str:
    out_path = runs_dir / f"{case.id}_{arm}_r{rep}.json"
    if out_path.exists():
        return f"SKIP     {out_path.name} (exists)"
    result = agent.run_agent(
        case, arm,
        mcp_configs.get(arm),
        model=model,
        append_system=append_by_arm.get(arm),
    )
```

and add `"tool_results": result.tool_results,` to `record` right after
`"tool_call_details"`.

In `cmd_run`, replace the arms/append/mcp wiring:

```python
    arms = args.arms
    mcp_configs = _write_arm_configs(
        out_dir, libraries, arms, str(args.registry_lcp_bin)
    )
    append_by_arm: dict = {}
    if "lcp-skill" in arms:
        append_by_arm["lcp-skill"] = agent.load_skill_text(args.skill_file)
    if "sitepkg" in arms:
        append_by_arm["sitepkg"] = _sitepkg_note()
    if "context7" in arms:
        append_by_arm["context7"] = agent.CONTEXT7_RULE
```

(and thread `mcp_configs` / `append_by_arm` through the `pool.submit` call
in place of `mcp_config` / `append_system`). NOTE: `out_dir`/`runs_dir`
creation must move ABOVE `_write_arm_configs` (it writes into `out_dir`) —
it already is; verify.

In `build_parser`, replace the `--arms` argument with:

```python
    p_run.add_argument(
        "--arms", action="append",
        choices=["baseline", "lcp", "lcp-skill", "sitepkg", "registry",
                 "context7"],
        help="repeatable; default: baseline + lcp",
    )
    p_run.add_argument(
        "--registry-lcp-bin", type=Path,
        default=EVALS_DIR / ".venv-registry/bin/lcp",
        help="lcp binary of the BARE venv used by the registry arm",
    )
```

and in `cmd_run` start: `if not args.arms: args.arms = ["baseline", "lcp"]`.

- [ ] **Step 4: Run all harness tests**

```bash
evals/.venv-bench/bin/python -m pytest evals/tests -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add evals/run.py evals/tests/test_run_args.py
git commit   # "ADD: per-arm MCP configs and 6-arm matrix to the eval runner"
```

---

### Task 5: Registry publication of the 11 targets

**Files (in `~/Projects/lcp/lcp-registry` — separate repo, separate commits/PRs):**
- Modify: `packages.yaml` (single source of truth after issue #25)

**Interfaces:**
- Consumes: pinned versions from Task 2 Step 3.
- Produces: all 11 targets resolvable from the public registry at the pinned versions (needed by the `registry` arm, Tasks 10–12). Missing today: cyhole, hamana, pocket-coffea, narwhals, griffe, cyclopts, pixeltable, fastmcp, flask. Present at other versions: polars (1.42.1), requests (2.34.2) — republish at the bench pins if newer.

- [ ] **Step 1: Inspect the registry machinery state** — read `~/Projects/lcp/lcp-registry/packages.yaml` and the populate/update script (`populate.py` or successor after PR #25-unification) to confirm the add-a-package workflow and the per-package minimal-venv scan (host-leak lesson from Phase 7: population MUST use a minimal requirements venv).

- [ ] **Step 2: Add the 9 missing packages** (plus polars/requests version bumps if the bench pins are newer) to `packages.yaml` following the existing entry format, commit on a branch in that repo.

- [ ] **Step 3: Run the population flow** for the new packages per that repo's README (isolated venv per package, lcp pinned per the CI workflow). Expected: one PR per package with a CI-verified manifest.

- [ ] **Step 4: Watch CI on each PR** (`gh pr checks --watch` in that repo). pocket-coffea and pixeltable are the crash-risk candidates (heavy import graphs) — if CI regeneration fails for a package: first try a documented `verify-overrides.yaml` tolerance; if genuinely unresolvable, record it in `PREREGISTRATION.md` (the `registry` arm then covers 10/11 libs and the page says so — do NOT silently shrink).

- [ ] **Step 5: Merge the PRs** (user's repo — merge after green CI), then verify end-to-end from the bare venv:

```bash
rm -rf evals/.lcp-registry-cache
evals/.venv-registry/bin/python - <<'EOF'
from lcp.mcp_server import resolve_library_document
for lib in ["cyhole", "hamana", "pocket-coffea", "narwhals", "griffe",
            "cyclopts", "pixeltable", "fastmcp", "polars", "requests", "flask"]:
    doc, meta = None, None
    try:
        result = resolve_library_document(lib, cache_dir="evals/.lcp-registry-cache")
        print("OK ", lib)
    except Exception as exc:
        print("FAIL", lib, exc)
EOF
```

(adapt the call to the actual `resolve_library_document` signature — read it first; the point is: every lib resolves from the bare venv via registry fetch).

- [ ] **Step 6: Freeze the registry for the benchmark window** — disable the weekly-update workflow in lcp-registry (`gh workflow disable <name>`) so `latest.json` cannot drift mid-grid; record the disable (and the re-enable after Task 12) in `PREREGISTRATION.md`.

---

### Task 6: Author cases — churned + controls (fastmcp, polars, requests, flask)

**Files:**
- Create: `evals/cases-v2/fastmcp.yaml` (8 cases), `evals/cases-v2/polars.yaml` (8), `evals/cases-v2/requests.yaml` (6), `evals/cases-v2/flask.yaml` (6)

**Interfaces:**
- Consumes: bench venv (Task 2); case format from `evals/harness/cases.py` (`id`, `library`, `version`, `prompt`, `checks.required_symbols`, `checks.forbidden_symbols`).
- Produces: 28 validated cases. Case ids are `<library>-<slug>` (the `by_prefix` engagement split keys on the first dash-segment).

**Authoring methodology (applies to Tasks 6–8):**

1. Introspect the REAL pinned API first — never author from memory:
   ```bash
   evals/.venv-bench/bin/lcp scan <pkg> -o /tmp/<pkg>.lcp.json
   evals/.venv-bench/bin/python -c "import json; d=json.load(open('/tmp/<pkg>.lcp.json')); print('\n'.join(sorted(d['symbols'])[:200]))"
   ```
2. Per case: a realistic small task (self-contained: inline data, no
   internet, no files unless the prompt supplies content), 1–3
   `required_symbols` (the correct current API), 1–3 `forbidden_symbols`
   (plausible hallucinations: the OLD name of a renamed API, the
   sibling-library idiom, an invented convenience method).
3. Every forbidden symbol must NOT resolve; every required one must —
   `validate` enforces both. Iterate until clean.
4. **Overfitting guard (roadmap risk #4):** no case id, prompt, or
   (required, forbidden) pair may duplicate anything in `evals/cases/`
   (the phases 0–4 set). For reused libraries target DIFFERENT API areas.
5. Version field = the bench pin recorded in Task 2 Step 3.

- [ ] **Step 1: fastmcp 8 cases** — the churn trap is 2.x→3.x: mine the installed 3.x for renames/removals (compare against the legacy `evals/cases/fastmcp.yaml` 2.14.4 symbols and the fastmcp changelog via introspection: any 2.x symbol that no longer resolves is a candidate forbidden symbol). Target areas DIFFERENT from the legacy 4 cases (which covered server-tool, resource, client, context basics). Example of the required shape (validate against the real 3.x API before committing — do not trust this example's symbol ids blindly):

```yaml
- id: fastmcp-tool-annotations
  library: fastmcp
  version: "<bench pin>"
  prompt: >
    Create a FastMCP server exposing one tool `add(a: int, b: int) -> int`
    with a human-readable title and a read-only annotation, then run it
    with the stdio transport.
  checks:
    required_symbols: ["fastmcp:FastMCP", "fastmcp:FastMCP#tool"]
    forbidden_symbols: ["fastmcp:Server"]
```

- [ ] **Step 2: polars 8 cases** — renamed-API traps beyond the legacy set (legacy used `groupby`/`apply`/`with_column`/`frame_equal`): candidates from introspection diff (e.g. old eager/lazy idioms, renamed IO or expression methods that no longer resolve). New API areas: lazy frames, expressions, joins, IO other than CSV.

- [ ] **Step 3: requests 6 + flask 6 ceiling controls** — straightforward tasks the models pass from parametric knowledge (sessions, timeouts, blueprints, error handlers). Forbidden symbols still required (e.g. invented helpers like `requests:Session#get_json`) so misuse is measurable, but EXPECT ~100% baseline pass — that is the point of the control class (F4).

- [ ] **Step 4: Validate**

```bash
evals/.venv-bench/bin/python evals/run.py validate --cases evals/cases-v2
```

Expected: `28 cases, 0 problems`.

- [ ] **Step 5: Commit**

```bash
git add evals/cases-v2/
git commit   # "ADD: Phase 8 churned+control benchmark cases (fastmcp3, polars, requests, flask)"
```

---

### Task 7: Author cases — niche reuse (cyhole, hamana)

**Files:**
- Create: `evals/cases-v2/cyhole.yaml` (8 cases), `evals/cases-v2/hamana.yaml` (8)

Same methodology as Task 6. The legacy set covered: cyhole birdeye-price, jupiter-swap, rugcheck-report, missing-api-key; hamana connect/query basics. New cases MUST target different connectors/endpoints/parameters (introspect the pinned versions for what exists — both libraries grew since the phase-0 pins; the bench venv has the LATEST versions, not the legacy pins, so re-derive every symbol id).

- [ ] **Step 1: cyhole 8 cases** (different connectors than the legacy 4; traps: invented method names mirroring the real F2 failures, e.g. plausible `get_<thing>` variants that don't resolve).
- [ ] **Step 2: hamana 8 cases** (beyond connect/query: introspect for the actual surface).
- [ ] **Step 3: Validate** — `evals/.venv-bench/bin/python evals/run.py validate --cases evals/cases-v2` → `44 cases, 0 problems`.
- [ ] **Step 4: Commit** — `"ADD: Phase 8 niche-reuse benchmark cases (cyhole, hamana)"`.

---

### Task 8: Author cases — new niche (pocket-coffea, narwhals, griffe, cyclopts, pixeltable)

**Files:**
- Create: `evals/cases-v2/pocket-coffea.yaml` (8), `evals/cases-v2/narwhals.yaml` (8), `evals/cases-v2/griffe.yaml` (8), `evals/cases-v2/cyclopts.yaml` (8), `evals/cases-v2/pixeltable.yaml` (8)

Same methodology. Class-specific trap guidance:
- **pocket-coffea**: models know coffea-0.7-era tutorials and generic coffea idioms — traps = writing raw-coffea patterns where pocket-coffea has its own config/API layer. NOTE `library: pocket-coffea` (dist name) needs `_IMPORT_NAMES["pocket-coffea"] = "pocket_coffea"` in `evals/harness/cases.py` — add it in this task (one-line change + it is exercised by `validate`).
- **narwhals**: traps = pandas/polars methods that don't exist on narwhals frames (the whole library is "almost-polars", maximally confusable).
- **griffe**: traps = mkdocstrings/inspect-style invented loaders.
- **cyclopts**: traps = typer idioms (`typer.Option`-style patterns) that don't resolve on cyclopts.
- **pixeltable**: traps = pandas-style mutation methods on pixeltable tables.

- [ ] **Step 1: pocket-coffea 8 cases** (+ the `_IMPORT_NAMES` line).
- [ ] **Step 2: narwhals 8 cases.**
- [ ] **Step 3: griffe 8 cases.**
- [ ] **Step 4: cyclopts 8 cases.**
- [ ] **Step 5: pixeltable 8 cases.**
- [ ] **Step 6: Validate all** — `evals/.venv-bench/bin/python evals/run.py validate --cases evals/cases-v2` → `84 cases, 0 problems`.
- [ ] **Step 7: Commit** — `"ADD: Phase 8 new-niche benchmark cases (5 libraries)"` (include `evals/harness/cases.py`).

---

### Task 9: USER CHECKPOINT — case review + pre-registration freeze

**Files:**
- Create: `evals/results/2026-07-09-phase8/PREREGISTRATION.md`

**Interfaces:**
- Consumes: the 84 validated cases; environment records (Task 1); registry state (Task 5).
- Produces: the frozen, committed pre-registration that Tasks 10–13 execute verbatim. **No grid run starts before this commit.**

- [ ] **Step 1: Present the case set to the user** — a per-library table (case id, one-line prompt gist, the trap) via AskUserQuestion/summary; the user is the domain expert for pocket-coffea/cyhole/hamana. Apply requested edits, re-validate, commit amendments.

- [ ] **Step 2: Write `PREREGISTRATION.md`** with exactly these sections (fill every ⟨⟩ from the session records — no placeholders may survive):
  - **Design**: 84 cases (11 libraries: 7 niche / 2 churned / 2 control), 6 arms (baseline, lcp, lcp-skill, sitepkg, registry, context7 — with the one-flag difference of each spelled out), haiku `claude-haiku-4-5-20251001` × 5 reps, sonnet `claude-sonnet-5` × 3 reps; harness commit ⟨hash⟩; `claude --version` ⟨v⟩; bench pins = `evals/bench-requirements.lock.txt`; registry state ⟨packages/manifests count + which of the 11 are served, weekly updater disabled on ⟨date⟩⟩; CONTEXT7_API_KEY ⟨set/unset⟩.
  - **Primary metrics**: API-misuse rate (misuse_count/run), task pass rate, tokens/task (input+output). **Secondary**: engagement rate (≥1 `mcp__lcp__*` call; `mcp__context7__*` for the context7 arm), cost-overhead-when-unused (notional cost delta on runs with 0 MCP calls vs baseline), per-cell variance. `tool_calls` counts attempts including permission-denied ones.
  - **Interpretation rules (pre-registered)**: effects <20% relative = noise (Phase 0 rule); the headline number comes from the niche-class cells (the target use case), control cells reported as ceiling context; if lcp-skill does not beat sitepkg on accuracy, the token/latency delta is the story; if it loses both, that is a product finding and gets published anyway.
  - **Error-handling rule**: harness-error records (timeout / CLI crash / rate-limit) are deleted and relaunched; model outputs are never re-rolled.
  - **Screening protocol** (Task 10's rules, verbatim — written BEFORE screening runs).

- [ ] **Step 3: Commit** — `git add evals/results/2026-07-09-phase8/PREREGISTRATION.md evals/cases-v2/ && git commit` — `"ADD: Phase 8 pre-registration (design, metrics, decision rules)"`.

---

### Task 10: Skill screening — B vs A vs A+B, ship the winner

**Files:**
- Create: `evals/results/2026-07-09-phase8/screening/variant-b/SKILL.md` (copy of shipped), `variant-a/SKILL.md` (copy of `evals/results/2026-07-07-phase4b/variant-a/SKILL.md`), `variant-ab/SKILL.md` (new)
- Create: `evals/results/2026-07-09-phase8/screening/{variant-b,variant-a,variant-ab}/` run outputs + `meta.json` each
- Create: `evals/results/2026-07-09-phase8/screening/analysis.md`
- Modify (conditional): `plugin/lcp/skills/lcp-universal/SKILL.md`

**Interfaces:**
- Consumes: `--skill-file` flag; the 84-case set (subset via `--case-id`).
- Produces: the shipped skill text the grid measures.

**Pre-registered screening protocol (goes into PREREGISTRATION.md, Task 9):**
- Subset: the 8 false-confidence cases — 4 fastmcp + 4 pocket-coffea case ids (chosen at Task 9 freeze, listed in the doc): the two classes where the model wrongly trusts stale knowledge (fastmcp 2.x, coffea 0.7 era).
- 5 reps × 8 cases × 3 variants = 120 runs, haiku, arm `lcp-skill`.
- Disqualification: engaged-run misuse ≥2 → variant out. Exactly 1 → rerun THAT case ×5 more reps for that variant; any further engaged misuse → out, else the variant stays (incident recorded). (This fixes the Phase 4b n=1 disqualification the roadmap flags for re-measurement.)
- Winner: highest engaged-run count among qualified variants; ties → higher overall pass → lower misuse/run.
- Ship rule: the winner replaces the shipped B text ONLY if it is not B and beats B's engaged count by ≥4/40 (+10pp). Otherwise B stays.

- [ ] **Step 1: Author `variant-ab/SKILL.md`** — start from the SHIPPED skill (which contains B's "Before you write ANY import statement…" paragraph) and insert variant A's paragraph immediately after it, byte-identical to Phase 4b's A-insertion:

```markdown
**Loading tools is not verifying.** If the lcp tools are deferred (their
names are listed but their schemas are not loaded), load them with
ToolSearch and then IMMEDIATELY make the first real call:
`resolve_library("<package>")`. ToolSearch retrieves no documentation —
if your last tool call was ToolSearch, you have verified nothing yet.
```

Copy variant-b (shipped file verbatim) and variant-a (the Phase 4b file verbatim). Sanity: the three files are pairwise different (`md5 -q` on each).

- [ ] **Step 2: Launch the three screening runs** (sequentially, ~40 min each):

```bash
for v in b a ab; do
  evals/.venv-bench/bin/python evals/run.py run \
    --out evals/results/2026-07-09-phase8/screening/variant-$v \
    --cases evals/cases-v2 --arms lcp-skill --reps 5 --workers 2 \
    --model claude-haiku-4-5-20251001 \
    --skill-file evals/results/2026-07-09-phase8/screening/variant-$v/SKILL.md \
    --case-id <fastmcp-id-1> --case-id <fastmcp-id-2> \
    --case-id <fastmcp-id-3> --case-id <fastmcp-id-4> \
    --case-id <pocket-coffea-id-1> --case-id <pocket-coffea-id-2> \
    --case-id <pocket-coffea-id-3> --case-id <pocket-coffea-id-4>
done
```

Expected first line each: `40 runs (8 cases x ['lcp-skill'] x 5 reps)`. After each: check `grep -l '"error": "' runs/*.json` — delete genuine harness-error files and relaunch (runner skips existing).

- [ ] **Step 3: Decide per the protocol**

```bash
evals/.venv-bench/bin/python evals/run.py engagement \
  --out evals/results/2026-07-09-phase8/screening/variant-b \
  --out evals/results/2026-07-09-phase8/screening/variant-a \
  --out evals/results/2026-07-09-phase8/screening/variant-ab
```

Apply the pre-registered rules mechanically; write `screening/analysis.md` (per-variant table, DQ evaluation, winner, ship decision) + `meta.json` per variant dir (same fields as Phase 4b metas).

- [ ] **Step 4: Ship (conditional)** — if the winner ≠ B: `cp` the winning file over `plugin/lcp/skills/lcp-universal/SKILL.md`, and run the main-suite + plugin tests (`.venv/bin/python -m pytest -q && bash tests/plugin/run_all.sh`). The plugin skill is shipped docs (docs-alignment rule) — no other page quotes the body (re-verify with `grep -r "resolve_library(" docs/guides/claude-code-plugin.md`).

- [ ] **Step 5: Commit** — screening dirs + analysis (+ plugin file if shipped): `"ADD: Phase 8 skill screening (B vs A vs A+B)"` / `"UPD: Ship the Phase 8 screening winner in the plugin skill"`.

---

### Task 11: Grid smoke — one case through all 6 arms

**Files:**
- Scratch outputs only (scratchpad dir), NOT committed.

Before burning quota on 4000 runs, prove every arm works end-to-end.

- [ ] **Step 1: Smoke run** — pick one cheap case (a requests one) and run:

```bash
evals/.venv-bench/bin/python evals/run.py run \
  --out /private/tmp/claude-501/-Users-andreazanini-Projects-lcp-lcp/fe1f9c7b-8c25-4ff2-bb5c-3595705ecfa3/scratchpad/phase8-smoke \
  --cases evals/cases-v2 --reps 1 --workers 1 \
  --model claude-haiku-4-5-20251001 \
  --arms baseline --arms lcp --arms lcp-skill --arms sitepkg \
  --arms registry --arms context7 \
  --case-id <requests-case-id>
```

- [ ] **Step 2: Verify each arm's mechanics** in the 6 run JSONs:
  - `lcp`/`lcp-skill`: any `mcp__lcp__*` in `tool_call_details` (or none — engagement is the model's choice; what MUST hold is no `error`).
  - `registry`: server came up from the bare venv; if the model called `resolve_library`, the response came from the registry (check `tool_results` for the registry-sourced document / `version_mismatch` absence).
  - `context7`: server startup OK (npx fetch), `tool_results` captured if called.
  - `sitepkg`: no MCP config, Read/Glob/Grep not denied.
  - All: `code` extracted, `verification` present.
- [ ] **Step 3: Fix anything broken** (harness-side only), re-smoke until clean. Delete the smoke dir.

---

### Task 12: Publication grid — paced execution

**Files:**
- Create: `evals/results/2026-07-09-phase8/pub-haiku/` (2520 runs + summary/report/meta.json)
- Create: `evals/results/2026-07-09-phase8/pub-sonnet/` (1512 runs + summary/report/meta.json)

**Execution discipline (multi-day, quota-paced):**
- One results dir per model (cross-model runs never share a dir — README rule).
- Launch per-arm blocks so a rate-limit stop never leaves a half-run arm ambiguous; the runner resumes anyway.
- After EVERY block: `grep -l '"error": "' <out>/runs/*.json` → inspect; delete harness-error files (timeout/crash/rate-limit) and relaunch the same command; NEVER delete a completed run.
- Track notional spend: `evals/run.py report --out <dir>` shows cumulative cost.

- [ ] **Step 1: haiku blocks** (5 reps; ~420 runs/arm; repeat per arm):

```bash
for ARM in baseline lcp lcp-skill sitepkg registry context7; do
  evals/.venv-bench/bin/python evals/run.py run \
    --out evals/results/2026-07-09-phase8/pub-haiku \
    --cases evals/cases-v2 --reps 5 --workers 3 \
    --model claude-haiku-4-5-20251001 --arms $ARM
done
```

(one `--arms` per invocation = the block structure; on rate-limit stop, rerun the same loop — SKIP lines confirm resumption).

- [ ] **Step 2: Completeness gate haiku** — `ls evals/results/2026-07-09-phase8/pub-haiku/runs | wc -l` → `2520`, zero files with a non-null `"error"`.
- [ ] **Step 3: sonnet blocks** — same loop with `--reps 3 --model claude-sonnet-5 --out .../pub-sonnet` → `1512` files, zero errors.
- [ ] **Step 4: `meta.json` per dir** (experiment description, dates spanned, claude/CLI version, lcp commit, skill file = the SHIPPED one post-Task 10, arms, reps, model, cases dir, PREREGISTRATION.md reference).
- [ ] **Step 5: Re-enable the registry weekly updater** (`gh workflow enable` in lcp-registry) and note the timestamp in the metas.
- [ ] **Step 6: Commit in batches** (runs dirs are large; one commit per model dir): `"ADD: Phase 8 publication grid results (haiku)"` / `"... (sonnet)"`.

---

### Task 13: Analysis + headline

**Files:**
- Create: `evals/harness/stats.py` + `evals/tests/test_stats.py`
- Create: `evals/results/2026-07-09-phase8/analysis.md`

- [ ] **Step 1: TDD `stats.py`** — a seeded bootstrap CI helper the analysis quotes:

```python
# evals/tests/test_stats.py
from harness.stats import bootstrap_ci


def test_ci_brackets_the_mean_and_is_deterministic():
    values = [0, 0, 1, 1, 1, 1, 0, 1, 1, 1]
    lo1, hi1 = bootstrap_ci(values, seed=42)
    lo2, hi2 = bootstrap_ci(values, seed=42)
    assert (lo1, hi1) == (lo2, hi2)
    assert lo1 <= sum(values) / len(values) <= hi1
    assert 0.0 <= lo1 < hi1 <= 1.0
```

```python
# evals/harness/stats.py
"""Seeded bootstrap confidence intervals for the Phase 8 analysis."""

import random


def bootstrap_ci(values, n_boot: int = 10_000, alpha: float = 0.05,
                 seed: int = 42) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of `values` (deterministic)."""
    rng = random.Random(seed)
    k = len(values)
    means = sorted(
        sum(rng.choices(values, k=k)) / k for _ in range(n_boot)
    )
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot) - 1]
    return lo, hi
```

Run `evals/.venv-bench/bin/python -m pytest evals/tests/test_stats.py -q` (fail → implement → pass). Commit: `"ADD: bootstrap CI helper for the benchmark analysis"`.

- [ ] **Step 2: Write `analysis.md`** — computed strictly per PREREGISTRATION.md:
  - per-(model, arm) table: pass rate [CI], misuse/run [CI], tokens/task, engagement rate, cost;
  - per-class breakdown (niche / churned / control) — the headline comes from the niche cells;
  - lcp-skill vs sitepkg accuracy + token comparison (the honest-arm test);
  - registry arm: resolution success + deltas vs lcp arm;
  - context7 arm: coverage on niche libs (found/not-found from `tool_results`) + quality where covered;
  - screening cross-reference; cost-overhead-when-unused; the per-phase delta story (baseline 45%→ Phase 8 numbers, from the roadmap Eval results log);
  - **the headline number**, stated exactly as the README will quote it;
  - honest caveats: static verification, single-vendor models (no non-Claude arm — decided 2026-07-09), `tool_calls` counts attempts, subscription-notional costs, Context7 content not pinnable (responses recorded in runs).
- [ ] **Step 3: Commit** — `"ADD: Phase 8 benchmark analysis"`.

---

### Task 14: Regression profile + evals README

**Files:**
- Create: `evals/profiles/regression.yaml`
- Modify: `evals/README.md`

- [ ] **Step 1: Select the 16 regression cases** per the settled criteria, FROM the haiku publication cells: rank by discriminative power (lcp-skill pass − baseline pass, then lower baseline pass); exclude ceiling cases (baseline ≥4/5); cover ≥5 libraries. Write:

```yaml
# evals/profiles/regression.yaml — cheap release-monitoring profile.
# Publication profile (frozen): see evals/results/2026-07-09-phase8/PREREGISTRATION.md
profile: regression
model: claude-haiku-4-5-20251001
arms: [baseline, lcp-skill]
reps: 3
cases_dir: evals/cases-v2
case_ids: [<16 ids>]
# Refresh policy (settled 2026-07-09): replace a case's library when the
# BASELINE arm passes >=90% of its runs across 2 consecutive checks (the
# model has absorbed it — it no longer discriminates). Version bumps of a
# kept library require re-running `run.py validate` and re-pinning
# bench-requirements.lock.txt.
# Cost: 16 x 2 x 3 = 96 runs, ~$8 notional per check.
```

- [ ] **Step 2: Update `evals/README.md`**: the three-venv layout (legacy `.venv` / `.venv-bench` / `.venv-registry` and which commands use which), the 6 arms with their one-flag differences, `cases-v2` vs legacy `cases`, the profiles section (publication = frozen + pointer to PREREGISTRATION.md; regression = how to run it verbatim:

```bash
evals/.venv-bench/bin/python evals/run.py run \
  --out evals/results/<date>-regression \
  --cases evals/cases-v2 --reps 3 --workers 2 \
  --model claude-haiku-4-5-20251001 \
  --arms baseline --arms lcp-skill \
  $(evals/.venv-bench/bin/python -c "import yaml;print(' '.join('--case-id '+c for c in yaml.safe_load(open('evals/profiles/regression.yaml'))['case_ids']))")
```

), and the tool_results field.
- [ ] **Step 3: Commit** — `"ADD: regression benchmark profile and evals README refresh"`.

---

### Task 15: Publication docs + README headline

**Files:**
- Create: `docs/benchmark.md`
- Modify: `mkdocs.yml` (nav), `README.md`, possibly `docs/introduction.md` (one cross-link)

**Use the `lcp-writing-documentation` skill** (user-facing area: kebab-case, task-oriented, examples allowed).

- [ ] **Step 1: Write `docs/benchmark.md`** — user-facing, reproducible-methodology page:
  - What was measured (plain-language: an agent writes code against 11 libraries, 84 tasks; misuse verified by live introspection);
  - The arms table (what each configuration is, incl. Context7 and the honest sitepkg arm);
  - Results: headline + the per-class table + tokens/cost table (from analysis.md — numbers copied, not re-derived);
  - Reproducibility: pinned harness commit, `evals/` pointers, pre-registration statement, exact rerun commands, model ids, dates;
  - Caveats section (verbatim honesty from analysis.md).
- [ ] **Step 2: nav entry in `mkdocs.yml`** (top level, after Quickstart or with the guides — follow the skill's nav conventions).
- [ ] **Step 3: README** — headline number in the opening section (exact sentence from analysis.md) + link to the docs page.
- [ ] **Step 4: Build strict**

```bash
.venv/bin/python -m mkdocs build --strict
```

Expected: zero warnings.
- [ ] **Step 5: Commit** — `"DOC: Publish the LCP benchmark results page and README headline"`.

---

### Task 16: Roadmap update, end gates, PR

**Files:**
- Modify: `docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md` (Phase 8 Status + Eval results log rows)

- [ ] **Step 1: End gates**

```bash
.venv/bin/python -m pytest -q                       # 593 passed (+ any new), 0 failed
bash tests/plugin/run_all.sh                        # green
evals/.venv-bench/bin/python -m pytest evals/tests -q   # green
evals/.venv/bin/python -m pytest evals/tests -q     # legacy venv still green
.venv/bin/ruff check src/lcp tests evals            # clean
.venv/bin/python -m mkdocs build --strict           # clean
```

- [ ] **Step 2: Roadmap** — Phase 8 **Status** line → `done (2026-07-⟨D⟩) — ...` (headline, arms, screening outcome, profiles, plan link); Eval results log: one row per screening variant + one row per (model × key arm summary) for the publication grid, same column format. Commit with `git add -f docs/superpowers/plans/...` — `"UPD: Phase 8 status and eval results log in the roadmap"`.

- [ ] **Step 3: Push + PR** (public repo: no session links/co-authors)

```bash
git push -u origin roadmap/phase-8-benchmark
gh pr create --base roadmap/agentic-improvements \
  --title "MRG: Phase 8 — full benchmark + publication" \
  --body "<summary: pre-registration, screening outcome, grid results headline, docs page, regression profile; links to PREREGISTRATION.md and analysis.md>"
```

- [ ] **Step 4: Watch CI + resolve** — `gh pr checks --watch`; fix lint/CodeQL findings and address review comments (bots included) in-session.

---

## Self-review notes

- Spec coverage: two profiles (Tasks 9/14), package/task selection with user (Tasks 6–9, settled list in constraints), arms incl. binding lcp-skill + new registry axis + Context7 (Tasks 3–5, 11–12), skill strategy re-measurement with adequate reps + pre-registered DQ rules (Task 10), models+reps+cost-before-launch (constraints table + Task 9), pre-registered metrics incl. tool-adoption and cost-overhead-when-unused and the tool_calls caveat (Tasks 9/13), publication page + README headline (Task 15), roadmap status+log (Task 16), suites green start/end incl. plugin tests (Tasks 1/16), fastmcp pin untouched via bench venv (Task 2), registry freeze during the window (Tasks 5/12).
- Type consistency: `_write_arm_configs`/`_sitepkg_note` (Tasks 4, 11–12), `MCP_ARMS`/`SITEPKG_KEEP`/`CONTEXT7_RULE`/`tool_results` (Tasks 3–4, 11–13), `bootstrap_ci` (Task 13), case-id prefix convention (Tasks 6–8 ↔ engagement by_prefix).
- Known deliberate gaps: exact case prompts/symbols are authored against live introspection (Tasks 6–8 methodology) because authoring from memory is precisely the failure mode this benchmark measures; exact fastmcp/pocket-coffea screening case ids fixed at the Task 9 freeze.
