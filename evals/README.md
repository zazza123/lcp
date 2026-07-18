# LCP Eval Harness

Private benchmark measuring API misuse by a coding agent with and without
the LCP MCP server. Not part of the `lcp` package; nothing here ships.

Two case sets and two profiles:

- **Phase 0 set** (`cases/`, 28 cases, 7 libraries) — the original harness on
  the legacy `evals/.venv` (fastmcp 2.14.4).
- **Phase 8 publication set** (`cases-v2/`, 84 cases, 11 libraries) — the
  grown-up benchmark on `evals/.venv-bench`. Frozen and pre-registered
  (`results/2026-07-09-phase8/PREREGISTRATION.md`); results and analysis in
  `results/2026-07-09-phase8/`. A cheap reusable regression subset lives in
  `profiles/regression.yaml`.

## Environments (three venvs)

| venv | Python | Contents | Used by |
|------|--------|----------|---------|
| `evals/.venv` | 3.12 | lcp editable + the 7 Phase-0 targets (fastmcp **2.14.4**) | Phase-0 `cases/` runs; do NOT `pip install` into it |
| `evals/.venv-bench` | 3.12 | lcp editable + the 11 Phase-8 targets (fastmcp 3.x) | all `cases-v2/` runs, `validate`, harness tests |
| `evals/.venv-registry` | 3.12 | lcp editable ONLY (no targets) | the `registry` arm's server, to force registry-only resolution |

Phase-0 setup (unchanged):

```bash
python3 -m venv evals/.venv
evals/.venv/bin/pip install -e ".[dev]" -r evals/requirements.txt
```

Phase-8 benchmark setup:

```bash
python3 -m venv evals/.venv-bench
evals/.venv-bench/bin/pip install -e . -r evals/bench-requirements.txt
# awkward 1.10.5 (pocket-coffea's stack) has no cp312 wheel; on CMake>=4 hosts
# a cold cache needs: CMAKE_POLICY_VERSION_MINIMUM=3.5 ... pip wheel awkward==1.10.5
python3 -m venv evals/.venv-registry
evals/.venv-registry/bin/pip install -e .
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
- `harness/engagement.py` — engagement-conditioned stats (runs with ≥1
  `mcp__*__*` tool call).
- `harness/stats.py` — seeded bootstrap confidence intervals for the analysis.
- `cases/*.yaml` — the 28 Phase-0 cases; `cases-v2/*.yaml` — the 84 Phase-8
  cases. A run record also carries `tool_results` (captured MCP responses,
  truncated) for reproducibility.
- `profiles/regression.yaml` — the cheap regression subset.
- `results/` — output directory for `run`/`report` (created on demand).
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

Phase-0 runs use `evals/.venv`; Phase-8 (`cases-v2`) runs use
`evals/.venv-bench`.

```bash
# Validate case files against the installed (pinned) environment.
evals/.venv-bench/bin/python evals/run.py validate --cases evals/cases-v2

# Run the benchmark. --arms is repeatable; default is baseline + lcp.
evals/.venv-bench/bin/python evals/run.py run --out evals/results/<name> \
    --cases evals/cases-v2 [--reps N] \
    [--arms baseline] [--arms lcp] [--arms lcp-skill] [--arms sitepkg] \
    [--arms registry] [--arms context7] \
    [--model MODEL] [--workers 3] [--case-id ID ...] \
    [--registry-lcp-bin evals/.venv-registry/bin/lcp]

# Re-aggregate / engagement stats / rescore (no agent runs).
evals/.venv-bench/bin/python evals/run.py report --out evals/results/<name>
evals/.venv-bench/bin/python evals/run.py engagement --out <dir> [--out <dir> ...]
evals/.venv-bench/bin/python evals/run.py rescore --src <old> --out <old>-rescored
```

`run` writes one JSON file per (case, arm, rep) under `<out>/runs/`, then
`<out>/summary.json` and `<out>/report.md`. It is **resumable**: an existing
run file is skipped (`SKIP ... (exists)`), so a failed/interrupted/
rate-limited run is re-invoked with the same `--out`. Each agent invocation
has a 600s subprocess timeout, recorded as a failed run, not a harness crash.

### The six arms (each differs from `baseline` only by CLI flags)

| Arm | What it adds |
|-----|--------------|
| `baseline` | nothing — headless `claude -p`, all built-in tools denied, no MCP |
| `lcp` | `--mcp-config` → `lcp serve-all` (this venv, `--expose` per library) |
| `lcp-skill` | `lcp` + `--append-system-prompt` with the shipped `lcp-universal` skill body (frontmatter stripped) — approximates a developer with the plugin installed |
| `sitepkg` | no MCP; re-enables Read/Glob/Grep + a note naming the site-packages path (the "agent reads the installed source" honest arm) |
| `registry` | `lcp` config but the server runs from `--registry-lcp-bin` (the bare `.venv-registry`), so resolution can only succeed via the public registry |
| `context7` | `--mcp-config` → `npx @upstash/context7-mcp` + the vendor's always-use rule (the competitor arm) |

`--model` overrides the pinned default
(`harness/agent.py: MODEL = "claude-haiku-4-5-20251001"`); results across
models are not directly comparable, so keep cross-model runs in separate
results dirs. The first `lcp`/`lcp-skill` run for a library is slower — the
server scans it and populates the cache on first use.

## Profiles

- **Publication** — the frozen Phase 8 grid (84 cases × 6 arms × haiku 5 +
  sonnet 3 reps). Methodology, metrics and decision rules are pre-registered
  in `results/2026-07-09-phase8/PREREGISTRATION.md`; results and analysis
  (with the reproducible aggregator `analyze_grid.py`) sit beside it.
- **Regression** — a cheap, reusable release monitor: `profiles/regression.yaml`
  (16 discriminative niche cases, baseline + lcp-skill, haiku, 3 reps ≈ 96
  runs). Run it with:

```bash
evals/.venv-bench/bin/python evals/run.py run \
  --out evals/results/<date>-regression \
  --cases evals/cases-v2 --reps 3 --workers 3 \
  --model claude-haiku-4-5-20251001 \
  --arms baseline --arms lcp-skill \
  $(evals/.venv-bench/bin/python -c "import yaml;print(' '.join('--case-id '+c for c in yaml.safe_load(open('evals/profiles/regression.yaml'))['case_ids']))")
```

The profile's header documents the case-refresh policy (retire a library
once baseline reaches ceiling).

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
