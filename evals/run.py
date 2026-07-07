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

from harness import agent, cases, engagement, report, verify  # noqa: E402


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


def _run_one(
    case, arm: str, rep: int, mcp_config: Path, runs_dir: Path,
    model: str, append_system: str | None,
) -> str:
    out_path = runs_dir / f"{case.id}_{arm}_r{rep}.json"
    if out_path.exists():
        return f"SKIP     {out_path.name} (exists)"
    result = agent.run_agent(
        case, arm,
        mcp_config if arm in ("lcp", "lcp-skill") else None,
        model=model,
        append_system=append_system if arm == "lcp-skill" else None,
    )
    verification = verify.verify_code(result.code, case)
    record = {
        "case_id": case.id,
        "arm": arm,
        "rep": rep,
        "model": model,
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
    append_system = None
    if "lcp-skill" in arms:
        append_system = agent.load_skill_text(args.skill_file)
    jobs = [
        (case, arm, rep)
        for case in loaded
        for arm in arms
        for rep in range(1, args.reps + 1)
    ]
    print(f"{len(jobs)} runs ({len(loaded)} cases x {arms} x {args.reps} reps)")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(
                _run_one, case, arm, rep, mcp_config, runs_dir,
                args.model, append_system,
            )
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


def cmd_engagement(args) -> int:
    for out in args.out:
        runs = report.load_runs(Path(out))
        if not runs:
            print(f"{out}: no runs found", file=sys.stderr)
            return 1
        print(f"== {out}")
        print(json.dumps(engagement.engagement_stats(runs), indent=2))
    return 0


def cmd_rescore(args) -> int:
    """Re-verify stored runs with the CURRENT verifier into a new dir.

    Copies each <src>/runs/*.json record, recomputes its "verification"
    against the (unchanged) generated code, and re-aggregates. Use when the
    verifier changes (e.g. Phase 3 alias awareness) to separate "the
    verifier got fairer" from "the server got better".
    """
    loaded = {c.id: c for c in cases.load_cases(args.cases)}
    src = Path(args.src)
    out = Path(args.out)
    runs_dir = out / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    for run_file in sorted((src / "runs").glob("*.json")):
        record = json.loads(run_file.read_text())
        case = loaded.get(record["case_id"])
        if case is None:
            print(f"SKIP     {run_file.name} (unknown case id)")
            continue
        record["verification"] = asdict(
            verify.verify_code(record.get("code"), case)
        )
        record["rescored_from"] = str(src)
        (runs_dir / run_file.name).write_text(json.dumps(record, indent=2))
        status = "PASS" if record["verification"]["passed"] else "FAIL"
        print(f"{status:8}{run_file.name}")
    return _report(out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="validate case files")
    p_validate.add_argument("--cases", type=Path, default=EVALS_DIR / "cases")
    p_validate.set_defaults(func=cmd_validate)

    p_run = sub.add_parser("run", help="run the benchmark")
    p_run.add_argument("--out", required=True)
    p_run.add_argument("--cases", type=Path, default=EVALS_DIR / "cases")
    p_run.add_argument("--reps", type=int, default=3)
    p_run.add_argument(
        "--arms",
        choices=["both", "baseline", "lcp", "lcp-skill"],
        default="both",
    )
    p_run.add_argument("--model", default=agent.MODEL)
    p_run.add_argument("--workers", type=int, default=2)
    p_run.add_argument("--case-id", action="append", default=[])
    p_run.add_argument(
        "--skill-file", type=Path,
        default=EVALS_DIR.parent / "plugin/lcp/skills/lcp-universal/SKILL.md",
        help="SKILL.md injected in the lcp-skill arm "
             "(default: the shipped plugin skill)",
    )
    p_run.set_defaults(func=cmd_run)

    p_report = sub.add_parser("report", help="re-aggregate an existing results dir")
    p_report.add_argument("--out", required=True)
    p_report.set_defaults(func=cmd_report)

    p_eng = sub.add_parser(
        "engagement",
        help="engagement-conditioned stats for one or more results dirs",
    )
    p_eng.add_argument("--out", action="append", required=True)
    p_eng.set_defaults(func=cmd_engagement)

    p_rescore = sub.add_parser(
        "rescore",
        help="re-verify an existing results dir with the current verifier",
    )
    p_rescore.add_argument("--src", required=True)
    p_rescore.add_argument("--out", required=True)
    p_rescore.add_argument("--cases", type=Path, default=EVALS_DIR / "cases")
    p_rescore.set_defaults(func=cmd_rescore)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
