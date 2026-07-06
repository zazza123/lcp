# LCP Eval Harness (Phase 0)

Private benchmark measuring API misuse by a coding agent with and without
the LCP MCP server. Not part of the `lcp` package; nothing here ships.

## Setup

Run from the repo root:

```bash
python3 -m venv evals/.venv
evals/.venv/bin/pip install -e ".[dev]" -r evals/requirements.txt
```

> **Note:** the evals venv pins `fastmcp==2.14.4` because fastmcp is one of
> the seven *target* libraries and the cases were validated against that
> version. The `lcp` package itself now pins `fastmcp>=3.0,<4`, so do NOT
> re-run `pip install -e ".[dev]"` in this venv (it would bump fastmcp and
> invalidate the case pins) — lcp is installed editable and picks up code
> changes automatically. The server code happens to run on both majors; the
> supported pin is 3.x. Run the MAIN test suite (`tests/`) from the project
> `.venv` (fastmcp 3.x), never from `evals/.venv`.
> When recording a new results directory, note the `claude --version` in
> `meta.json` — the harness denies a snapshot of the CLI's built-in tools, so
> CLI drift between runs must stay detectable.

The `-e ".[dev]"` install puts the `lcp` package (and the `lcp` console
script) on the venv's PATH — the harness shells out to `lcp serve-all` for
the LCP arm. `evals/requirements.txt` pins the seven target libraries
(`polars`, `httpx`, `textual`, `pydantic`, `fastmcp`, `cyhole`, `hamana`) at
the exact versions the cases were written against, plus `pyyaml` for case
loading.

You also need the `claude` CLI installed and authenticated (`claude auth
login` or equivalent) — the harness invokes it as a subprocess (`claude -p
...`) and does not talk to any API directly.

## Layout

- `run.py` — CLI entry point (`validate` / `run` / `report`).
- `harness/agent.py` — builds and runs the `claude -p` command for one case
  in one arm, parses the stream-json transcript.
- `harness/cases.py` — `EvalCase` dataclass, YAML loading, validation
  against the live/pinned environment.
- `harness/verify.py` — static verification of generated code (symbol
  resolution via live introspection).
- `harness/extract.py` — pulls fenced code blocks out of agent output and
  library-symbol usage (dotted paths, method names) out of code via `ast`.
- `harness/report.py` — aggregates per-run JSON into a summary and a
  Markdown report.
- `cases/*.yaml` — the 28 task cases, one file per library.
- `results/` — output directory for `run`/`report` (created on demand; not
  committed except for the recorded baseline).
- `tests/` — unit tests for the harness modules themselves.

## Case format

Each `cases/<library>.yaml` file is a YAML list of cases:

```yaml
- id: polars-group-by
  library: polars
  version: "1.42.1"
  prompt: >
    Read the CSV file "sales.csv" (columns: region, product, revenue) into a
    polars DataFrame and compute the mean revenue per region, sorted by region.
  checks:
    required_symbols: ["polars:read_csv", "polars:DataFrame#group_by"]
    forbidden_symbols: ["polars:DataFrame#groupby"]
```

Symbol ids use the LCP format `module:entity` (`polars:read_csv`) or
`module:Class#method` (`polars:DataFrame#group_by`) — the same convention
used by LCP manifests. `required_symbols` are the correct, current API and
must resolve in the pinned environment; `forbidden_symbols` are APIs that
must **NOT** resolve — typically renamed/removed methods (`groupby`,
`apply`, `with_column`, `frame_equal`) that a model trained on stale docs
is likely to hallucinate. `validate` enforces both directions: it fails if
a required symbol doesn't resolve (broken case) or if a forbidden symbol
*does* resolve (not a valid trap).

There are 28 cases across 7 libraries: polars, httpx, textual, pydantic,
fastmcp, cyhole, hamana.

## Commands

All commands run through `evals/.venv/bin/python evals/run.py`.

```bash
# Validate all case files against the installed (pinned) environment.
evals/.venv/bin/python evals/run.py validate [--cases evals/cases]

# Run the benchmark: both arms x 28 cases x 3 reps by default.
evals/.venv/bin/python evals/run.py run --out evals/results/<name> \
    [--cases evals/cases] [--reps 3] [--arms both|baseline|lcp|lcp-skill] \
    [--model MODEL] [--workers 2] [--case-id ID ...]

# Re-aggregate an existing results directory without re-running anything.
evals/.venv/bin/python evals/run.py report --out evals/results/<name>

# Re-verify an existing results dir with the current verifier (no agent runs).
evals/.venv/bin/python evals/run.py rescore --src evals/results/<old> \
    --out evals/results/<old>-rescored [--cases evals/cases]
```

`run` writes one JSON file per (case, arm, rep) under `<out>/runs/`, then
writes `<out>/summary.json` and `<out>/report.md`. It is resumable: if a
run file already exists it is skipped (`SKIP ... (exists)`), so a failed or
interrupted run can simply be re-invoked with the same `--out`.

Defaults: `--reps 3`, `--arms both`, `--workers 2`. Each agent invocation
has a 600s subprocess timeout; a timeout is recorded as a failed run
(`error: "timeout after 600s"`), not a crash of the harness.

Besides `baseline` and `lcp` there is a third arm, `lcp-skill`: the `lcp`
arm plus `--append-system-prompt` carrying the `lcp-universal` skill body
(`plugin/lcp/skills/lcp-universal/SKILL.md`, frontmatter stripped, injected
verbatim) — it approximates what a developer with the plugin installed
experiences. It is always explicit; `--arms both` still means
`baseline` + `lcp` only. `--model` overrides the pinned default
(`harness/agent.py: MODEL = "claude-haiku-4-5-20251001"`); it exists for
the Phase 2b sonnet probe — results across different models are not
directly comparable, so keep cross-model runs in separate results dirs.

The first LCP-arm run for a given library is noticeably slower than the
rest: `lcp serve-all` has to scan the package and populate
`evals/.lcp-cache/` on first use; subsequent runs for the same library hit
the cache.

## Methodology and caveats

The two arms issue the *exact same* `claude -p` command, differing only in
one flag: the LCP arm adds `--mcp-config` pointing at a generated config
that launches `lcp serve-all --cache-dir evals/.lcp-cache --expose <lib>
...` for the libraries under test; the baseline arm passes no MCP config
at all. Built-in tools (`Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`,
`WebFetch`, `WebSearch`, `Task`, `NotebookEdit`, `TodoWrite`) are denied in
both arms via `--disallowedTools`, so neither arm can shell out, read local
files, or search the web — this isolates the effect of the MCP server
itself rather than measuring general tool/internet access. (`--tools ""`
was deliberately avoided because it also strips MCP tools from the offered
set, which would silently defeat the LCP arm.) `--allowedTools "mcp__lcp"`
pre-approves the MCP server's tools so headless `-p` runs don't silently
deny them for lack of interactive approval; this flag is a no-op in the
baseline arm, which never registers a server named `lcp`.

Verification is static only — there is no code execution or runtime
sandboxing. `harness/extract.py` parses the generated code with `ast` to
collect attribute chains rooted at an import of the target library and bare
method names called on any other receiver; `harness/verify.py` then checks,
against live introspection of the pinned package (not regex, not training
data), whether each required symbol was used, whether any forbidden symbol
was used, and whether any library-rooted attribute chain fails to resolve
at all. A run's `misuse_count` is the sum of (forbidden symbols used) +
(unresolved library-rooted attribute chains) — this catches both direct
use of a renamed/removed method and misuse on a chained/returned object
(e.g. `df.group_by(...).frame_equal(...)`), which a regex-only check would
miss. `symbol_used` accepts any used dotted path that resolves (live
introspection) to the same object as the required symbol's canonical path,
so valid re-export imports (`from cyhole.jupiter import Jupiter` for
`cyhole.jupiter.interaction:Jupiter`) count as usage; `rescore` exists to
re-score older results dirs when the verifier changes.

With ~28 tasks x 3 reps, the sample is far too small to distinguish a small
true effect from run-to-run noise (agents are stochastic). Do not treat
single-digit percentage deltas between arms as meaningful. Per the
roadmap's Phase 0 caveat, only effects of roughly >20% relative magnitude
(e.g. misuse rate or pass rate) should be read as signal; anything smaller
is statistical noise given this sample size, and later phases should not
over-fit changes to marginal wiggles in these numbers.

## Tests

```bash
evals/.venv/bin/python -m pytest evals/tests -v
```

`evals/conftest.py` puts `evals/` on `sys.path` so `harness` is importable
without installing it as a package.
