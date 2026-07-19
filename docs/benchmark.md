# Benchmark

**On niche and post-cutoff Python libraries — the case LCP is built for — the
shipped LCP plugin lifts a small model's task success rate from 28% to 66% and
cuts its API-misuse rate in half, outperforming an agent that reads the
installed package source.** For a frontier model the same libraries rise from
68% to 92%.

The full harness, cases, pre-registration and per-run data live in
[`lcp-benchmark`](https://github.com/zazza123/lcp-benchmark) so every number
below is reproducible.

## What was measured

A coding agent (Claude, headless) is asked to write a small, self-contained
program against a specific Python library. The generated code is checked — not
executed — against **live introspection of the installed library**: did it use
the correct current API, and did it use any API that does not exist (the
hallucination trap)? Two numbers summarize each run: whether the task passed
all checks, and how many API misuses it contained.

- **84 tasks**, all new (never used to tune earlier development), across **11
  libraries** in three classes:
    - *niche / post-cutoff* (7): cyhole, hamana, pocket-coffea, narwhals,
      griffe, cyclopts, pixeltable — libraries a model has little or no
      training data for;
    - *churned* (2): fastmcp (2.x→3.x rewrite), polars (pre-1.0 renames) —
      where stale training data actively misleads;
    - *control* (2): requests, flask — well-known, expected at ceiling.
- **Two models:** a small one (`claude-haiku-4-5`) and a frontier one
  (`claude-sonnet-5`).
- **3968 runs** total, integrity-checked (every case/rep present, zero errored
  records).

## The six configurations (arms)

Every arm issues the *same* prompt; they differ only in what the agent is given.

| Arm | What the agent gets |
|-----|---------------------|
| **baseline** | Nothing — no tools, no docs. Pure parametric knowledge. |
| **lcp** | The LCP MCP server (introspects the installed package on demand). |
| **lcp-skill** | LCP **+ the shipped plugin skill** that tells the agent to verify before writing. This is what a developer who installs the plugin actually runs. |
| **sitepkg** | No LCP; instead the agent may read the installed package's source with Read/Glob/Grep — the honest "just let the agent read the code" arm. |
| **registry** | LCP resolving from the public registry, with the package **not installed locally** — the case where reading source is impossible. |
| **context7** | The [Context7](https://context7.com) documentation MCP server, with the same always-use nudge — the competitor arm. |

## Results

Pass rate on the **niche** libraries (the target workload) — the headline lives
here; control libraries are at ceiling in every arm and measure little.

| Model | baseline | **lcp-skill** | sitepkg | lcp | registry | context7 |
|-------|----------|---------------|---------|-----|----------|----------|
| haiku | 28.2% | **65.7%** | 55.4% | 34.3% | 26.2% | 26.1% |
| sonnet | 68.5% | 91.7% | **96.4%** | 85.1% | 66.7% | 69.0% |

Overall, by arm:

| Model | Arm | Pass% (95% CI) | Misuse/run | Tokens/task |
|-------|-----|----------------|------------|-------------|
| haiku | baseline | 41.0% (36–45) | 0.70 | 2079 |
| haiku | **lcp-skill** | **69.0% (65–73)** | **0.35** | 2113 |
| haiku | sitepkg | 61.4% (57–66) | 0.34 | 2128 |
| sonnet | baseline | 75.8% (70–81) | 0.22 | 1496 |
| sonnet | lcp-skill | 91.7% (88–95) | 0.04 | 2312 |
| sonnet | sitepkg | 92.9% (90–96) | 0.02 | 1320 |

Confidence intervals are seeded percentile bootstraps. The full six-arm
table for every model, with per-class breakdowns, is in
[`analysis.md`](https://github.com/zazza123/lcp-benchmark/blob/main/results/2026-07-09-phase8/analysis.md).

## What the numbers say — honestly

- **For a small model, the shipped plugin is the strongest configuration on the
  target workload**: niche pass 28% → 66% (a 2.3× improvement, disjoint CIs),
  misuse halved. This is where LCP earns its place.
- **The skill is the lever, not just the server.** The bare `lcp` arm (server,
  no skill) barely moves the niche number, because the small model rarely calls
  the tools on its own. The plugin skill closes that adoption gap.
- **Against reading the installed source, LCP wins for the small model and
  ties-to-loses for the frontier model.** On sonnet, `sitepkg` slightly beats
  `lcp-skill` on niche accuracy *and* uses fewer tokens — a capable model that
  can read source effectively does well without LCP. We publish that plainly.
  LCP's distinct value is (1) the large gain for small/cheap models, and (2)
  the **registry** arm: it works when the package is not installed at all — a
  private or uninstalled dependency — which `sitepkg` structurally cannot.
- **Context7 did not move the niche numbers** (it sits at baseline), even with
  the same always-use nudge. Narrative docs for popular libraries are not what
  post-cutoff or private libraries need; introspected ground truth of the
  *installed version* is.

## Reproduce it

```bash
git clone https://github.com/zazza123/lcp-benchmark
cd lcp-benchmark
# Environment setup and the full grid procedure:
# https://github.com/zazza123/lcp-benchmark/blob/main/docs/reproduce.md
# One arm over the full 84-case set at 5 reps is 420 agent runs and costs
# real API budget. Add --case-id <id> (repeatable) to try a few cases first.
.venv-bench/bin/python run.py run \
  --out results/<name> --cases cases/python/publication \
  --model claude-haiku-4-5-20251001 --reps 5 --arms lcp-skill
```

The frozen methodology, metrics and decision rules are pre-registered in
[`results/2026-07-09-phase8/PREREGISTRATION.md`](https://github.com/zazza123/lcp-benchmark/blob/main/results/2026-07-09-phase8/PREREGISTRATION.md);
the full analysis with per-class breakdowns and caveats is in the sibling
`analysis.md`. Cases are pinned in `bench-requirements.lock.txt`; the
harness commit and model ids are recorded in each results directory's
`meta.json`.

## Caveats

Static verification only (code is checked by introspection, not executed).
Both models are Claude — the mechanism (MCP + introspected manifests) is
vendor-neutral but that is not demonstrated here. Costs were subscription-paced
and the reported figures are notional. Context7 responses are recorded for
reproducibility but its upstream content is not pinnable.
