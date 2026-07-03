"""Phase 0 eval harness CLI: validate cases, run the benchmark, report.

Run with the evals venv: evals/.venv/bin/python evals/run.py ...
See evals/README.md.
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from itertools import chain
from pathlib import Path

EVALS_DIR = Path(__file__).parent
sys.path.insert(0, str(EVALS_DIR))

from harness import agent, cases, report, verify  # noqa: E402


def cmd_validate(args) -> int:
    loaded = cases.load_cases(args.cases)
    problems = cases.validate_cases(loaded)
    for p in problems:
        print(f"INVALID  {p}")
    print(f"{len(loaded)} cases, {len(problems)} problems")
    return 1 if problems else 0


def _write_mcp_config(out_dir: Path, libraries: list[str]) -> Path:
    lcp_bin = Path(sys.executable).with_name("lcp")
    expose = list(chain.from_iterable(("--expose", lib) for lib in libraries))
    config = {
        "mcpServers": {
            "lcp": {
                "command": str(lcp_bin),
                "args": [
                    "serve-all",
                    "--cache-dir", str(EVALS_DIR / ".lcp-cache"),
                    *expose,
                ],
            }
        }
    }
    path = out_dir / "mcp-config.json"
    path.write_text(json.dumps(config, indent=2))
    return path


def _run_one(case, arm: str, rep: int, mcp_config: Path, runs_dir: Path) -> str:
    out_path = runs_dir / f"{case.id}_{arm}_r{rep}.json"
    if out_path.exists():
        return f"SKIP     {out_path.name} (exists)"
    result = agent.run_agent(case, arm, mcp_config if arm == "lcp" else None)
    verification = verify.verify_code(result.code, case)
    record = {
        "case_id": case.id,
        "arm": arm,
        "rep": rep,
        "model": agent.MODEL,
        "code": result.code,
        "result_text": result.result_text,
        "error": result.error,
        "metrics": {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cache_read_tokens": result.cache_read_tokens,
            "cache_creation_tokens": result.cache_creation_tokens,
            "cost_usd": result.cost_usd,
            "num_turns": result.num_turns,
            "tool_calls": result.tool_calls,
            "duration_s": round(result.duration_s, 1),
        },
        "tool_call_details": result.tool_call_details,
        "verification": asdict(verification),
    }
    out_path.write_text(json.dumps(record, indent=2))
    status = "PASS" if verification.passed else "FAIL"
    return (
        f"{status:8}{out_path.name}  misuse={verification.misuse_count}"
        f"  tools={result.tool_calls}  {record['metrics']['duration_s']}s"
        + (f"  ERROR: {result.error}" if result.error else "")
    )


def cmd_run(args) -> int:
    loaded = cases.load_cases(args.cases)
    if args.case_id:
        loaded = [c for c in loaded if c.id in args.case_id]
        missing = set(args.case_id) - {c.id for c in loaded}
        if missing:
            print(f"unknown case ids: {sorted(missing)}", file=sys.stderr)
            return 1
    problems = cases.validate_cases(loaded)
    if problems:
        for p in problems:
            print(f"INVALID  {p}", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    libraries = sorted({c.library for c in loaded})
    mcp_config = _write_mcp_config(out_dir, libraries)

    arms = ["baseline", "lcp"] if args.arms == "both" else [args.arms]
    jobs = [
        (case, arm, rep)
        for case in loaded
        for arm in arms
        for rep in range(1, args.reps + 1)
    ]
    print(f"{len(jobs)} runs ({len(loaded)} cases x {arms} x {args.reps} reps)")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(_run_one, case, arm, rep, mcp_config, runs_dir)
            for case, arm, rep in jobs
        ]
        for future in as_completed(futures):
            print(future.result(), flush=True)
    return _report(out_dir)


def _report(out_dir: Path) -> int:
    runs = report.load_runs(out_dir)
    if not runs:
        print("no runs found", file=sys.stderr)
        return 1
    summary = report.aggregate(runs)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "report.md").write_text(report.render_markdown(summary))
    print(f"wrote {out_dir / 'summary.json'} and {out_dir / 'report.md'}")
    return 0


def cmd_report(args) -> int:
    return _report(Path(args.out))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="validate case files")
    p_validate.add_argument("--cases", type=Path, default=EVALS_DIR / "cases")
    p_validate.set_defaults(func=cmd_validate)

    p_run = sub.add_parser("run", help="run the benchmark")
    p_run.add_argument("--out", required=True)
    p_run.add_argument("--cases", type=Path, default=EVALS_DIR / "cases")
    p_run.add_argument("--reps", type=int, default=3)
    p_run.add_argument("--arms", choices=["both", "baseline", "lcp"], default="both")
    p_run.add_argument("--workers", type=int, default=2)
    p_run.add_argument("--case-id", action="append", default=[])
    p_run.set_defaults(func=cmd_run)

    p_report = sub.add_parser("report", help="re-aggregate an existing results dir")
    p_report.add_argument("--out", required=True)
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
