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
