"""Aggregate per-run JSON results into a summary and a Markdown report."""

import json
from pathlib import Path
from statistics import mean


def load_runs(results_dir: Path) -> list[dict]:
    """Load all run JSON files from results_dir/runs/."""
    return [
        json.loads(p.read_text())
        for p in sorted((Path(results_dir) / "runs").glob("*.json"))
    ]


def aggregate(runs: list[dict]) -> dict:
    """Aggregate runs into per-arm and per-case summaries."""
    arms: dict[str, dict] = {}
    for arm in sorted({r["arm"] for r in runs}):
        arm_runs = [r for r in runs if r["arm"] == arm]
        n = len(arm_runs)
        total_misuse = sum(r["verification"]["misuse_count"] for r in arm_runs)
        arms[arm] = {
            "runs": n,
            "pass_rate": sum(r["verification"]["passed"] for r in arm_runs) / n,
            "total_misuse": total_misuse,
            "misuse_rate": total_misuse / n,
            "errors": sum(1 for r in arm_runs if r.get("error")),
            "mean_input_tokens": mean(r["metrics"]["input_tokens"] for r in arm_runs),
            "mean_output_tokens": mean(r["metrics"]["output_tokens"] for r in arm_runs),
            "mean_tool_calls": mean(r["metrics"]["tool_calls"] for r in arm_runs),
            "mean_cost_usd": mean(r["metrics"]["cost_usd"] for r in arm_runs),
            "total_cost_usd": sum(r["metrics"]["cost_usd"] for r in arm_runs),
        }
    cases: dict[str, dict] = {}
    for case_id in sorted({r["case_id"] for r in runs}):
        cases[case_id] = {}
        for arm in arms:
            case_runs = [r for r in runs if r["case_id"] == case_id and r["arm"] == arm]
            if not case_runs:
                continue
            passed = sum(r["verification"]["passed"] for r in case_runs)
            cases[case_id][arm] = {
                "passes": f"{passed}/{len(case_runs)}",
                "misuse": sum(r["verification"]["misuse_count"] for r in case_runs),
            }
    model = runs[0]["model"] if runs else ""
    return {"model": model, "arms": arms, "cases": cases}


def render_markdown(summary: dict) -> str:
    """Render the summary as a Markdown report."""
    lines = [
        "# Eval report",
        "",
        f"Model: `{summary['model']}`",
        "",
        "## By configuration",
        "",
        "| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | "
        "Out tok (mean) | Tool calls (mean) | Cost (total) |",
        "|-----|------|-----------|------------|--------|---------------|"
        "----------------|-------------------|--------------|",
    ]
    for arm, s in summary["arms"].items():
        lines.append(
            f"| {arm} | {s['runs']} | {s['pass_rate']:.0%} | "
            f"{s['misuse_rate']:.2f} | {s['errors']} | "
            f"{s['mean_input_tokens']:.0f} | {s['mean_output_tokens']:.0f} | "
            f"{s['mean_tool_calls']:.1f} | ${s['total_cost_usd']:.4f} |"
        )
    lines += ["", "## By case", "", "| Case | Arm | Passes | Misuses |",
              "|------|-----|--------|---------|"]
    for case_id, by_arm in summary["cases"].items():
        for arm, s in by_arm.items():
            lines.append(f"| {case_id} | {arm} | {s['passes']} | {s['misuse']} |")
    return "\n".join(lines) + "\n"
