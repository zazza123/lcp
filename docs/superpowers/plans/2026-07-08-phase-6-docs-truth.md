# Phase 6 — Documentation Truth + Positioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Docs that validate against the shipped schema, one consistent `docgen` story, an honest positioning page (LCP vs Context7 vs llms.txt vs reading site-packages), and the `.lcp.json` config→`.lcp-config.json` rename with a deprecation fallback.

**Architecture:** Pure docs + plugin-shell + doc-guard-test work; no manifest format or MCP surface changes. A new pytest module extracts fenced JSON from `docs/**/*.md` and validates it through `lcp.validator`, so examples can never silently drift again. The plugin config rename lands in `serve.sh`/`generate-config.sh` with legacy fallback, rippling mechanically through plugin metadata, skills, src error hints, and docs.

**Tech Stack:** pytest, jsonschema (via `lcp.validator.validate_dict`), bash (plugin tests), MkDocs (`mkdocs build --strict`), ruff.

## Settled Open Decisions

1. **Config rename → `.lcp-config.json`** (roadmap recommendation adopted). `.lcp.json` collides with the manifest extension (`pkg.lcp.json`, cache `*.lcp.json.gz`): a config named like a manifest confuses users and tooling. Canonical per-project config becomes `${CLAUDE_PROJECT_DIR}/.lcp-config.json`; legacy `.lcp.json` remains a silent read-fallback in `serve.sh` (with a one-line stderr deprecation notice emitted once at server startup) and blocks re-seeding in `generate-config.sh`. `~/.lcp/config.json` (global) is unchanged — no collision there. Doing it now while plugin adoption is small; plugin version bumps 0.2.0 → 0.3.0.
2. **`docgen` source of truth = `src/lcp/cli.py`**: `lcp docgen COVERAGE_JSON` exists, hierarchical-only, flags `--provider {openai,anthropic}` (default openai), `--model`, `--api-key`, `--kinds`, `--description`, `--reasoning`, `--dry-run`, `--workers` (default 4), `--failure-threshold` (default 0.5). README and `docs/architecture/ai_docgen/architecture.md` already agree with this; `docs/guides/ai-docgen.md` falsely says the CLI is "planned" (fix), `docs/cli.md` omits the command (add a section).
3. **Positioning placement**: rewrite the existing "LCP vs. alternatives" section in `docs/introduction.md` (no new nav entry, no duplicate page) and add a compact "When to choose LCP" section to the README so a newcomer reading only the README can state the one-sentence discriminator (exit criterion). Perimeter: LCP vs Context7 vs llms.txt vs "agent reads site-packages"; defensible claims only (introspected ground truth of the installed version, offline, private packages, token-dense structured responses); explicitly NOT claiming narrative-docs superiority over Context7.

## Verified Facts (recon 2026-07-08)

- Baseline: `.venv/bin/python -m pytest -q` → **566 passed** on `roadmap/phase-6-docs-truth` (base 829d397).
- Symbol schema: `required: [kind, semantics]`, `additionalProperties: false`, allowed props `kind, module, aliases, signatures, semantics, effects, stability, requires` + `^x-`. **`members` is NOT allowed** — `docs/spec/index.md` "Members and nesting" prose contradicts the schema and must be fixed too (generator flattens members to top-level `Class#method` IDs; `_convert_symbol` never emits a `members` array).
- `symbols` map keys are unconstrained (`additionalProperties: {$ref: symbol}`).
- The three replacement JSON fragments below were validated with `validate_dict` — all pass.
- No pytest asserts the `.lcp.json` hint strings in `src/lcp/subprocess_scan.py:147,152` / `src/lcp/mcp_server.py:635,640,664` — safe to reword.
- `docs/guides/mcp-server.md` and `docs/architecture/{mcp_server,manifest}/architecture.md` are already current for phases 2–5; `docs/architecture/plugin/architecture.md` has real drift (startup-flow diagram shows the pre-launcher-resolution "lcp on PATH?" model; claims `serve.sh` reads `CLAUDE_PLUGIN_OPTION_registries`/`CLAUDE_PLUGIN_CONFIG_REGISTRIES` env vars at serve time — it reads the config *file*; missing `lcp-configure` skill, `/lcp:configure` command, `generate-config.sh`, `verify_reminder.py`).
- Plugin shell tests: `bash tests/plugin/run_all.sh` runs 5 scripts; config filename appears in `test_config_reader.sh` (1×), `test_generate_config.sh` (4×), `test_scan_args.sh` (3×), `test_resolution.sh` (1×).

## Global Constraints

- Main suite green start AND end: 566+ passed, 0 failed (`.venv/bin/python -m pytest -q`).
- Plugin shell tests green: `bash tests/plugin/run_all.sh`.
- `mkdocs build --strict` clean (`.venv/bin/mkdocs build --strict`).
- Lint before push: `.venv/bin/ruff check src/lcp` and `.venv/bin/ruff check tests`.
- NO eval-harness run this phase; NO pip installs in `evals/.venv`.
- Docs follow `lcp-writing-documentation` skill: architecture = no code snippets, snake_case, Last-Updated footer; guides/spec/getting-started = kebab-case, code expected, no footer.
- Commits follow `git-commit-convention` (3-letter code; no co-author/session links — public repo). `docs/superpowers/` commits via `git add -f`.
- LCP schema stays `"1.0"`; this phase changes no schema/manifest/tool surface.
- PR title `MRG: ...` → base `roadmap/agentic-improvements`; after opening, `gh pr checks --watch` + resolve review/CodeQL findings in-session.

---

### Task 1: Rot-guard test + rewrite invalid JSON examples

**Files:**
- Create: `tests/test_docs_examples.py`
- Modify: `docs/introduction.md:9-18` (JSON fragment), `docs/spec/examples.md` (both fragments + member prose)

**Interfaces:**
- Produces: `tests/test_docs_examples.py::test_docs_json_examples_validate` (parametrized over doc blocks) and `test_minimum_validatable_examples` (floor ≥ 3). Later tasks must keep any new docs JSON either valid or non-parseable-fragment.

- [ ] **Step 1: Write the failing guard test**

`tests/test_docs_examples.py`:

```python
"""Rot guard: fenced JSON examples in docs/ must validate against the LCP schema.

Blocks that are not standalone JSON (illustrative fragments like
``"symbols": { ... }``) are skipped; blocks that parse are validated when
they are a full LCP document (top-level ``manifest``) or a symbols map
(every value is an object carrying ``kind``). Other parseable JSON (MCP
client configs, error-shape examples) is out of scope and skipped.
"""

import json
import re
from pathlib import Path

import pytest

from lcp.validator import validate_dict

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
EXCLUDED_TOP_DIRS = {"api", "superpowers"}
FENCE_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)

MINIMAL_MANIFEST = {
    "schema_version": "1.0",
    "library": {"name": "docs-example", "version": "1.0.0", "language": "python"},
}


def _iter_json_blocks():
    for path in sorted(DOCS_DIR.rglob("*.md")):
        rel = path.relative_to(DOCS_DIR)
        if rel.parts[0] in EXCLUDED_TOP_DIRS:
            continue
        for i, match in enumerate(FENCE_RE.finditer(path.read_text())):
            yield f"{rel}#{i}", match.group(1)


def _as_lcp_document(block: str):
    """Return a full LCP document dict for validatable blocks, else None."""
    try:
        data = json.loads(block)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data:
        return None
    if "manifest" in data:
        return data
    if all(isinstance(v, dict) and "kind" in v for v in data.values()):
        return {"manifest": MINIMAL_MANIFEST, "symbols": data}
    return None


BLOCKS = list(_iter_json_blocks())
VALIDATABLE = [
    (block_id, doc)
    for block_id, block in BLOCKS
    if (doc := _as_lcp_document(block)) is not None
]


@pytest.mark.parametrize(
    ("block_id", "document"),
    VALIDATABLE,
    ids=[block_id for block_id, _ in VALIDATABLE],
)
def test_docs_json_examples_validate(block_id, document):
    errors = validate_dict(document)
    assert not errors, f"{block_id} does not validate: {errors}"


def test_minimum_validatable_examples():
    """The guard must keep matching real examples; if this drops below the
    floor, the extraction heuristic broke or examples were removed."""
    assert len(VALIDATABLE) >= 3, [b for b, _ in VALIDATABLE]
```

- [ ] **Step 2: Run it to verify it fails on today's docs**

Run: `.venv/bin/python -m pytest tests/test_docs_examples.py -v`
Expected: FAIL — `introduction.md#0`, `spec/examples.md#0`, `spec/examples.md#1` all carry `kind` and get validated, and each fails (`summary`/`signature`/`stability`-string/`members` not allowed by the symbol schema).

- [ ] **Step 3: Rewrite `docs/introduction.md` fragment (lines 9–18)**

Replace the fenced JSON with (pre-validated):

```json
{
  "json:loads": {
    "kind": "function",
    "module": "json",
    "signatures": [
      {
        "params": [{ "name": "s", "type": "str", "required": true }],
        "returns": "Any"
      }
    ],
    "semantics": {
      "summary": "Deserialize a JSON document to a Python object."
    },
    "stability": { "level": "stable" }
  }
}
```

Adjust the sentence after it: "A full manifest contains a `manifest` header plus many such entries in the `symbols` map, keyed by stable symbol IDs."

- [ ] **Step 4: Rewrite `docs/spec/examples.md` fragments**

Function example (pre-validated):

```json
{
  "mymath:add": {
    "kind": "function",
    "module": "mymath",
    "signatures": [
      {
        "params": [
          { "name": "a", "type": "int", "required": true },
          { "name": "b", "type": "int", "required": true }
        ],
        "returns": "int"
      }
    ],
    "semantics": { "summary": "Add two integers." },
    "stability": { "level": "stable" }
  }
}
```

Class example (pre-validated) — class and method are **two top-level entries**; update the intro sentence ("LCP fragment — the class and its method are separate top-level entries in the `symbols` map") and keep the `#`-separator paragraph:

```json
{
  "mymath:Counter": {
    "kind": "class",
    "module": "mymath",
    "signatures": [
      {
        "params": [
          { "name": "start", "type": "int", "required": false, "default": 0 }
        ]
      }
    ],
    "semantics": { "summary": "Monotonically increasing counter." }
  },
  "mymath:Counter#increment": {
    "kind": "method",
    "module": "mymath",
    "signatures": [{ "params": [], "returns": "int" }],
    "semantics": { "summary": "Bump the counter and return the new value." }
  }
}
```

Also reword the "(truncated to the class and one method)" caption accordingly; note the class signature is the `__init__` signature.

- [ ] **Step 5: Run the guard again**

Run: `.venv/bin/python -m pytest tests/test_docs_examples.py -v`
Expected: PASS (≥ 3 validated blocks, all green).

- [ ] **Step 6: Full suite + commit**

Run: `.venv/bin/python -m pytest -q` → 567+ passed (566 + new params), 0 failed.

```bash
git add tests/test_docs_examples.py docs/introduction.md docs/spec/examples.md
git commit  # FIX: Validate embedded docs JSON examples against the schema
```

---

### Task 2: Quickstart jq fix, spec `members` prose, language-agnostic softening

**Files:**
- Modify: `docs/quickstart.md:48-54`, `docs/spec/index.md:124,192-200,387`, `docs/introduction.md` (scanner-scope note)

- [ ] **Step 1: Fix `docs/quickstart.md` "Inspect the output"**

`symbols` is a map, not an array. Replace the `jq '.symbols[0]'` block and the following sentence with:

````markdown
```bash
jq '.symbols | keys | .[:5]' requests.lcp.json          # first few symbol IDs
jq '.symbols["requests.api:get"]' requests.lcp.json     # one full entry
```

The `symbols` object is a map keyed by stable symbol IDs (`module:symbol`; class members use `#`, e.g. `requests.sessions:Session#get`). Each entry has a `kind` (`function`, `class`, `method`, `module`...), a `semantics.summary`, and optional `signatures`, `stability`, `effects`, and `aliases` fields.
````

- [ ] **Step 2: Fix `docs/spec/index.md` members prose to match the schema**

- Line 124: `All other fields (\`signatures\`, \`stability\`, \`effects\`, \`members\`, etc.) are optional.` → `All other fields (\`signatures\`, \`stability\`, \`effects\`, \`aliases\`, etc.) are optional.`
- "Members and nesting" section (lines ~192–200): remove the `members` array option. Replacement content:

```markdown
### Members and nesting

Class members appear as top-level symbols using the `#` separator; the symbol schema does not define a nested member array, so a class entry never embeds its members. Nested types use the dot separator in the entity path:

- Class member: `module:Class#method`
- Nested type: `module:Outer.Inner`
- Nested member: `module:Outer.Inner#method`

Consumers reconstruct class membership from the ID grammar: every key containing `#` belongs to the class named by its prefix.
```

- "Summary" section (line ~387): `optional fields within symbols (\`signatures\`, \`effects\`, \`stability\`, \`members\`)` → `optional fields within symbols (\`signatures\`, \`effects\`, \`stability\`, \`aliases\`)`.

- [ ] **Step 3: Soften language-agnostic claims in `docs/introduction.md`**

After the "What does an LCP fragment look like?" paragraph (or at the end of the opening section), add one clarifying sentence: `The LCP *format* is language-agnostic JSON; the scanner shipped in this SDK introspects **Python** packages. Other languages need their own producers.` Check line 34 ("Because the format is language-agnostic JSON...") stays as a *format* claim — keep, it is accurate. No changes to `docs/spec/index.md:7,24` (format claims).

- [ ] **Step 4: Verify + commit**

Run: `.venv/bin/python -m pytest tests/test_docs_examples.py -q` → PASS (guard unaffected: new blocks are bash/prose).
Run: `.venv/bin/mkdocs build --strict` → clean.

```bash
git add docs/quickstart.md docs/spec/index.md docs/introduction.md
git commit  # DOC: Fix quickstart map access, spec members prose and scanner-scope claim
```

---

### Task 3: One `docgen` story (cli.md + guide)

**Files:**
- Modify: `docs/cli.md` (new section after `lcp coverage`, before `lcp publish`), `docs/guides/ai-docgen.md:19-50`

- [ ] **Step 1: Add `lcp docgen` section to `docs/cli.md`** (after the `lcp coverage` section)

````markdown
## `lcp docgen`

Generate missing docstrings for the symbols listed in a coverage report, using an LLM provider. Requires the optional AI extra (`pip install "lcp[ai]"`). Processing is hierarchical bottom-up (methods → classes → modules) with parallel LLM calls; generated docstrings are injected into the package's source files in place.

```bash
lcp docgen COVERAGE_JSON [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `COVERAGE_JSON` | — | Path to a coverage report produced by [`lcp coverage`](#lcp-coverage). |
| `--provider [openai\|anthropic]` | `openai` | LLM provider. |
| `--model TEXT` | provider default | Model name. |
| `--api-key TEXT` | env var | API key; defaults to `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`. |
| `--kinds TEXT` | all | Filter by symbol kind, comma-separated (e.g. `class,function,method`). |
| `--description TEXT` | — | Package description used to guide the model. |
| `--reasoning` | off | Enable reasoning mode for OpenAI models (o1, o3, ...). |
| `--dry-run` | off | Show what would be modified without writing files. |
| `--workers INTEGER` | `4` | Max concurrent LLM calls. |
| `--failure-threshold FLOAT` | `0.5` | Ratio (0.0–1.0) of failed children that skips the parent symbol. |

**Example:**

```bash
lcp coverage mypackage -o coverage.json
lcp docgen coverage.json --provider openai --dry-run
lcp docgen coverage.json --provider anthropic --workers 8
```

See the [AI DocGen guide](guides/ai-docgen.md) for how hierarchical processing works and the Python API.
````

Also add `- [AI DocGen guide](guides/ai-docgen.md) — generating missing docstrings with \`lcp docgen\`.` to the "See also" list.

- [ ] **Step 2: Fix `docs/guides/ai-docgen.md` Quick start**

Delete the `!!! note "CLI status"` admonition (lines 49–50) — the CLI shipped. Rework "Quick start" (lines 19–47) to be CLI-first:

````markdown
## Quick start

```bash
pip install "lcp[ai]"
export OPENAI_API_KEY=sk-...
```

Generate a coverage report, preview with `--dry-run`, then run for real:

```bash
lcp coverage mypackage -o coverage.json
lcp docgen coverage.json --dry-run
lcp docgen coverage.json --workers 8
```

The writer modifies the package's source files in place. Review the diff with `git diff` before committing. All flags are listed in the [CLI reference](../cli.md#lcp-docgen); the same run is available from Python:

```python
from lcp.ai import DocGenAgent, HierarchicalConfig, OpenAIProvider

provider = OpenAIProvider(model="gpt-4o-mini")
agent = DocGenAgent(provider=provider, config=HierarchicalConfig(max_workers=8))
result = agent.run_sync("coverage.json")

print(f"Updated: {result.symbols_updated}/{result.symbols_processed}")
```
````

Add `- [\`lcp docgen\`](../cli.md#lcp-docgen) — CLI reference for the command.` to "See also". README (`lcp docgen` examples, lines 216–237) already matches `cli.py` — verify, change nothing.

- [ ] **Step 3: Verify + commit**

Run: `.venv/bin/mkdocs build --strict` → clean (anchors `#lcp-docgen`, `#lcp-coverage` resolve).
Run: `.venv/bin/python -m pytest tests/test_docs_examples.py -q` → PASS.

```bash
git add docs/cli.md docs/guides/ai-docgen.md
git commit  # DOC: Document the shipped lcp docgen CLI in cli.md and the AI guide
```

---

### Task 4: Config rename — shell implementation + tests (TDD)

**Files:**
- Modify: `plugin/lcp/bin/serve.sh:23,31-40,120-131`, `plugin/lcp/hooks/generate-config.sh`, `tests/plugin/test_config_reader.sh`, `tests/plugin/test_generate_config.sh`, `tests/plugin/test_scan_args.sh`, `tests/plugin/test_resolution.sh`

**Interfaces:**
- Produces: `lcp_config_file()` resolution order `${CLAUDE_PROJECT_DIR}/.lcp-config.json` → `${CLAUDE_PROJECT_DIR}/.lcp.json` (legacy) → `~/.lcp/config.json`. Task 5 renames every doc/skill reference to `.lcp-config.json`.

- [ ] **Step 1: Update shell tests to the new name + add fallback/precedence cases**

In `tests/plugin/test_config_reader.sh`, `test_scan_args.sh`, `test_resolution.sh`: replace every `"$TMP/.lcp.json"`-style config path with `.lcp-config.json` (manifest paths like `*.lcp.json.gz` untouched — only config files named exactly `.lcp.json`). Append to `test_config_reader.sh`:

```bash
# Legacy fallback: .lcp.json still read when .lcp-config.json is absent
LEGACY="$(mktemp -d)"
echo '{"command":"/legacy/lcp"}' > "$LEGACY/.lcp.json"
CLAUDE_PROJECT_DIR="$LEGACY" run_get command
[ "$OUT" = "/legacy/lcp" ] || { echo "FAIL legacy fallback: $OUT"; exit 1; }
echo "OK legacy fallback"

# Precedence: .lcp-config.json wins over legacy .lcp.json
echo '{"command":"/new/lcp"}' > "$LEGACY/.lcp-config.json"
CLAUDE_PROJECT_DIR="$LEGACY" run_get command
[ "$OUT" = "/new/lcp" ] || { echo "FAIL precedence: $OUT"; exit 1; }
echo "OK precedence"
rm -rf "$LEGACY"
```

(Adapt to the file's existing helper names — read the script first; if it calls `lcp_config_get` directly after sourcing with `LCP_SERVE_LIB=1`, follow that pattern instead of a `run_get` helper.)

In `tests/plugin/test_generate_config.sh`: expect `.lcp-config.json` as the generated file in the existing cases, and append:

```bash
# Legacy config present: hook must NOT create .lcp-config.json alongside it
LEG="$(mktemp -d)"
echo '{"command":"/x"}' > "$LEG/.lcp.json"
CLAUDE_PROJECT_DIR="$LEG" CLAUDE_PLUGIN_OPTION_LCPCOMMAND="/opt/venv/bin/lcp" bash "$HOOK"
[ ! -f "$LEG/.lcp-config.json" ] || { echo "FAIL seeded next to legacy"; exit 1; }
echo "OK legacy blocks seeding"
rm -rf "$LEG"
```

- [ ] **Step 2: Run plugin tests to verify they fail**

Run: `bash tests/plugin/run_all.sh`
Expected: FAIL (hooks/wrapper still use `.lcp.json`).

- [ ] **Step 3: Implement in `serve.sh`**

Replace `lcp_config_file()`:

```bash
# Resolve config file: project .lcp-config.json, legacy project .lcp.json
# (deprecated), then global.
lcp_config_file() {
  if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
    if [ -f "${CLAUDE_PROJECT_DIR}/.lcp-config.json" ]; then
      printf '%s\n' "${CLAUDE_PROJECT_DIR}/.lcp-config.json"; return 0
    fi
    if [ -f "${CLAUDE_PROJECT_DIR}/.lcp.json" ]; then
      printf '%s\n' "${CLAUDE_PROJECT_DIR}/.lcp.json"; return 0
    fi
  fi
  if [ -f "${HOME}/.lcp/config.json" ]; then
    printf '%s\n' "${HOME}/.lcp/config.json"; return 0
  fi
  return 1
}
```

After the lib-mode guard (`if [ -n "${LCP_SERVE_LIB:-}" ]...`, so sourcing tests stay silent), add the one-shot deprecation notice:

```bash
if [ -n "${CLAUDE_PROJECT_DIR:-}" ] \
     && [ ! -f "${CLAUDE_PROJECT_DIR}/.lcp-config.json" ] \
     && [ -f "${CLAUDE_PROJECT_DIR}/.lcp.json" ]; then
  echo "lcp plugin: reading deprecated config .lcp.json — rename it to .lcp-config.json" >&2
fi
```

Update the header comment (line 23: `Config is read from $CLAUDE_PROJECT_DIR/.lcp-config.json (legacy fallback: .lcp.json, deprecated) or ~/.lcp/config.json.`; lines 5–6 and 25 `.lcp.json` mentions → `.lcp-config.json`) and the error heredoc (line 127: `3. Point .lcp-config.json at it:        {"command": "/path/to/lcp"}`).

- [ ] **Step 4: Implement in `generate-config.sh`**

```bash
#!/bin/bash
# SessionStart: generate .lcp-config.json from userConfig when absent.
# Never blocks. A legacy project .lcp.json counts as present (deprecated name).
set -uo pipefail

if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
  target="${CLAUDE_PROJECT_DIR}/.lcp-config.json"
  [ -f "${CLAUDE_PROJECT_DIR}/.lcp.json" ] && exit 0   # legacy config present
else
  target="$HOME/.lcp/config.json"
fi

[ -f "$target" ] && exit 0           # generate-if-absent
```

(rest of the script — python3 guard, mkdir, seeding heredoc — unchanged; keep the "empty project config would shadow the global one" comment, updating the filename it mentions.)

- [ ] **Step 5: Run plugin tests to verify they pass**

Run: `bash tests/plugin/run_all.sh`
Expected: `ALL PLUGIN TESTS PASSED`.

- [ ] **Step 6: Commit**

```bash
git add plugin/lcp/bin/serve.sh plugin/lcp/hooks/generate-config.sh tests/plugin/
git commit  # UPD: Rename plugin config to .lcp-config.json with legacy fallback
```

---

### Task 5: Config rename — ripple through metadata, skills, src hints, docs

**Files:**
- Modify: `plugin/lcp/.claude-plugin/plugin.json` (3 descriptions + version bump 0.2.0→0.3.0), `plugin/lcp/README.md`, `plugin/lcp/commands/configure.md`, `plugin/lcp/skills/lcp-configure/SKILL.md`, `src/lcp/subprocess_scan.py:147,152`, `src/lcp/mcp_server.py:635,640,664`, `docs/guides/claude-code-plugin.md`, `docs/guides/mcp-server.md:68`, `README.md:302-324`, `docs/architecture/mcp_server/architecture.md:48`

- [ ] **Step 1: Mechanical rename of config references**

In every file above, replace `.lcp.json` **used as the config filename** with `.lcp-config.json`. Do NOT touch manifest usages (`pkg.lcp.json`, `*.lcp.json.gz`, `requests.lcp.json`, cache paths) — in `src/lcp/mcp_server.py` only lines 635, 640, 664 change (config hints); lines 292, 329, 1410, 1435 are manifests and stay. Update section headings too (`README.md:302` `### \`.lcp-config.json\` — per-project configuration`; `docs/guides/claude-code-plugin.md` `## Configuration: \`.lcp-config.json\``). In `plugin.json` bump `"version": "0.3.0"`.

- [ ] **Step 2: Document the deprecation for existing users**

- `docs/guides/claude-code-plugin.md`, inside the Configuration section, add:

```markdown
!!! note "Renamed from `.lcp.json`"
    Earlier plugin versions named this file `.lcp.json`, which collided with
    the manifest extension (`<package>.lcp.json`). A legacy `.lcp.json` is
    still read (with a deprecation notice on the server's stderr) when no
    `.lcp-config.json` exists — rename the file to silence it.
```

- `README.md` config section: one sentence — `Earlier versions named this file \`.lcp.json\`; the old name still works as a deprecated fallback — rename it to \`.lcp-config.json\`.`
- `plugin/lcp/skills/lcp-configure/SKILL.md`: besides the rename, add a repair-mode bullet (near the existing "Malformed" bullet, ~line 149): `**Legacy \`.lcp.json\` config found:** offer to rename it to \`.lcp-config.json\` (same content); the old name is a deprecated fallback.`

- [ ] **Step 3: Verify no stragglers, run everything**

Run: `grep -rn '\.lcp\.json' plugin/ docs/guides docs/architecture README.md src/lcp | grep -v '\.gz\|<package>\|pkg\.lcp\|requests\.lcp\|sample\.lcp\|mylib\|numpy\|json\.lcp\|v1\.lcp\|v2\.lcp\|version}\.lcp\|output\|collections'` — every remaining hit must be a manifest usage or an intentional legacy-fallback mention; fix any config straggler.
Run: `.venv/bin/python -m pytest -q` → all passed; `bash tests/plugin/run_all.sh` → pass; `.venv/bin/mkdocs build --strict` → clean; `.venv/bin/ruff check src/lcp` → clean.

- [ ] **Step 4: Commit**

```bash
git add plugin/ src/lcp/subprocess_scan.py src/lcp/mcp_server.py docs/ README.md
git commit  # UPD: Point config hints, skills and docs at .lcp-config.json
```

---

### Task 6: Positioning — introduction rewrite + README section

**Files:**
- Modify: `docs/introduction.md:36-52` ("LCP vs. alternatives" section), `README.md` (new section after "Features")

- [ ] **Step 1: Rewrite "LCP vs. alternatives" in `docs/introduction.md`**

Replace the current section (training data / source parsing / type stubs prose + table) with the honest, evaluator-facing comparison. Content requirements — write these as flowing prose, one short paragraph per alternative, then the table:

- **Context7 (and similar remote docs services):** serves curated, narrative documentation for popular public libraries, fetched from a remote service. Strongest when you want prose: tutorials, guides, upgrade notes. LCP does not compete on narrative quality — it answers a different question: *what exactly does the version installed in this environment expose?* LCP introspects the installed package, so it covers private/internal packages, works fully offline, and returns token-dense structured records (signatures, params, raises, examples) rather than prose pages.
- **llms.txt:** a hand-maintained, site-level summary aimed at crawlers/LLMs. Coarse-grained (library level, not symbol level), only exists if the maintainer publishes one, and says nothing about the version you actually installed.
- **Agent reads site-packages:** always available and version-accurate, but token-expensive — the agent navigates raw source to answer one signature question, with no ranked search and no pre-digested structure. LCP is that same ground truth, pre-indexed: one `search` call returns ranked hits with import lines.
- Closing one-liner (the discriminator, reused in the README): **Choose LCP when the agent needs exact, offline ground truth about the library versions installed in your environment — including private packages. Choose Context7 when you want curated narrative documentation for popular public libraries.**

Table (honest cells — note the deliberate "no" for narrative docs):

```markdown
| | LCP | Context7 | llms.txt | Reading site-packages |
|---|:---:|:---:|:---:|:---:|
| Matches the *installed* version | yes | no — upstream docs | no | yes |
| Works offline | yes | no | no | yes |
| Private / internal packages | yes | no | only self-published | yes |
| Token-dense structured answers | yes | narrative text | coarse summary | raw source (expensive) |
| Symbol-level signatures | yes | partial | no | yes (manual digging) |
| Narrative guides & tutorials | no | yes | partial | no |
```

- [ ] **Step 2: Add "When to choose LCP" to `README.md`** (after "Features", before "Usage")

```markdown
## When to choose LCP

Choose LCP when your AI agent needs **exact, offline ground truth about the library versions installed in your environment** — including private packages that no documentation service has ever seen. Choose a service like Context7 when you want curated narrative documentation (tutorials, guides) for popular public libraries; LCP does not compete on prose, it competes on being *provably right about your environment*.

|  | LCP | Context7 | llms.txt | Reading site-packages |
|---|:---:|:---:|:---:|:---:|
| Matches the *installed* version | yes | no | no | yes |
| Works offline | yes | no | no | yes |
| Private / internal packages | yes | no | no | yes |
| Token-dense structured answers | yes | narrative text | coarse summary | raw source (expensive) |

See the [full comparison](https://zazza123.github.io/lcp/introduction/#lcp-vs-alternatives) in the docs.
```

- [ ] **Step 3: Verify + commit**

Run: `.venv/bin/mkdocs build --strict` → clean; `.venv/bin/python -m pytest tests/test_docs_examples.py -q` → PASS (new tables are markdown, not fenced JSON). Check the anchor slug for "LCP vs. alternatives" in the built site (`site/introduction/index.html`) and match the README link to it.

```bash
git add docs/introduction.md README.md
git commit  # DOC: Position LCP honestly against Context7, llms.txt and raw source
```

---

### Task 7: Plugin architecture doc refresh (phases 2–5 drift)

**Files:**
- Modify: `docs/architecture/plugin/architecture.md`, `docs/architecture/plugin/index.md` (components table check)

Follow the `lcp-writing-documentation` architecture rules: no code snippets, refer to objects by name, Mermaid for flows, update the footer.

- [ ] **Step 1: Fix the factual drift in `architecture.md`**

- **Repository Structure** tree: add `commands/configure.md`, `skills/lcp-configure/SKILL.md`, `hooks/generate-config.sh`, `hooks/verify_reminder.py`; note shell tests live in `tests/plugin/` at the repo root.
- **MCP Server Startup Flow**: replace the obsolete "lcp on PATH?" diagram with the real flow: Claude Code reads `.mcp.json` → `bin/serve.sh` → `lcp_resolve_launcher()` probes 12 candidates (config `command`/`python`, project venvs, `$VIRTUAL_ENV`, `uv run`, PATH/`uvx`/`pipx`) each with `--version` → `lcp_build_args()` assembles `serve-all` flags from `.lcp-config.json` (registries, expose, preload, scan_python/scan_timeout) → exec. On failure: actionable stderr guidance, never a bare `-32000`.
- **userConfig section**: correct the mechanism — `userConfig` values reach the plugin as `CLAUDE_PLUGIN_OPTION_LCPCOMMAND` / `CLAUDE_PLUGIN_OPTION_PYTHONPATH` / `CLAUDE_PLUGIN_OPTION_REGISTRIES` env vars **to the SessionStart hook only**; `generate-config.sh` seeds them into `.lcp-config.json` when absent; `serve.sh` reads the config **file**, never those env vars. Delete the `CLAUDE_PLUGIN_CONFIG_REGISTRIES` claim.
- **Hooks**: describe both hooks from `hooks/hooks.json`: SessionStart → `generate-config.sh` (seed-if-absent, legacy `.lcp.json` blocks seeding); PreToolUse (`Write|Edit`) → `verify_reminder.py` (holds the first Python-file write once per session until an lcp tool was consulted).
- **Skills Design** table: add `lcp-configure` (auto-triggers on server-start/resolve failures; guided `.lcp-config.json` setup + repair). **Commands Design** table: add `/lcp:configure`.
- **Launcher vs scan interpreter** section: update config filename mentions to `.lcp-config.json`.
- Footer: `**Last Updated:** July 2026 (config rename, startup flow, hooks)`.

- [ ] **Step 2: Check `docs/architecture/plugin/index.md`**

Read it; update its key-components table and feature bullets to include the configure skill/command, both hooks, and the `.lcp-config.json` name. Keep the required index structure (overview, ToC, components, related docs).

- [ ] **Step 3: Verify + commit**

Run: `.venv/bin/mkdocs build --strict` → clean.

```bash
git add docs/architecture/plugin/
git commit  # DOC: Refresh plugin architecture doc for launcher, hooks and config rename
```

---

### Task 8: Final verification, roadmap status, PR

- [ ] **Step 1: Full gate**

```bash
.venv/bin/python -m pytest -q                 # expect: 570+ passed, 0 failed
bash tests/plugin/run_all.sh                  # expect: ALL PLUGIN TESTS PASSED
.venv/bin/mkdocs build --strict               # expect: clean
.venv/bin/ruff check src/lcp && .venv/bin/ruff check tests   # expect: clean
```

- [ ] **Step 2: Update roadmap Phase 6 Status** (`docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md:788`)

`**Status:** done (2026-07-08) — 6a + 6b landed; plan: docs/superpowers/plans/2026-07-08-phase-6-docs-truth.md. Docs examples guarded by tests/test_docs_examples.py; config renamed to .lcp-config.json (legacy fallback); positioning in introduction + README.` No eval-log line (not required for Phase 6).

```bash
git add -f docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md docs/superpowers/plans/2026-07-08-phase-6-docs-truth.md
git commit  # UPD: Phase 6 status in the roadmap
```

- [ ] **Step 3: Push + PR**

```bash
git push -u origin roadmap/phase-6-docs-truth
gh pr create --base roadmap/agentic-improvements \
  --title "MRG: Phase 6 — documentation truth and positioning" \
  --body "<summary of 6a fixes, rot guard, docgen story, config rename with fallback, positioning, plugin arch refresh — no session links>"
gh pr checks --watch
```

- [ ] **Step 4: Handle CI + review comments in-session**

Watch checks to completion; read PR comments including CodeQL/advanced-security bots (`gh pr view --comments`, `gh api repos/{owner}/{repo}/pulls/{n}/comments`); fix findings, re-push, re-watch until green.

## Self-Review Notes

- Exit criteria mapping: `mkdocs build --strict` green → Tasks 2–8 gates; every embedded example validates → Task 1 guard + floor test; README one-sentence Context7 discriminator → Task 6 Step 2.
- Roadmap 6a items all covered: introduction/examples shape (T1), quickstart jq (T2), docgen story (T3), language-agnostic softening (T2), rot guard (T1).
- Roadmap 6b items: MCP+plugin guides already consolidated (verified in recon; only rename touches in T5), positioning (T6), config rename (T4–5), architecture refresh for 2–5 (mcp_server/manifest verified current; plugin drift fixed in T7).
- Type/name consistency: `.lcp-config.json` spelled identically across T4–T7; `tests/test_docs_examples.py` names used in later task gates match T1.
