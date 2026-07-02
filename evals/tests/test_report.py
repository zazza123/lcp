import json

from harness.report import aggregate, load_runs, render_markdown


def make_run(case_id="c1", arm="baseline", rep=1, passed=True, misuse=0,
             tokens=100, tool_calls=0, error=None):
    return {
        "case_id": case_id, "arm": arm, "rep": rep,
        "model": "claude-haiku-4-5-20251001",
        "code": "x = 1", "result_text": "", "error": error,
        "metrics": {"input_tokens": tokens, "output_tokens": 50,
                    "cache_read_tokens": 0, "cache_creation_tokens": 0,
                    "cost_usd": 0.001, "num_turns": 1,
                    "tool_calls": tool_calls, "duration_s": 5.0},
        "verification": {"passed": passed, "misuse_count": misuse,
                         "required_missing": [], "forbidden_used": [],
                         "unresolved_usages": [], "error": None},
    }


class TestLoadRuns:
    def test_reads_runs_dir(self, tmp_path):
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        (runs_dir / "c1_baseline_r1.json").write_text(json.dumps(make_run()))
        assert len(load_runs(tmp_path)) == 1


class TestAggregate:
    def test_per_arm_metrics(self):
        runs = [
            make_run(rep=1, passed=True, misuse=0),
            make_run(rep=2, passed=False, misuse=2),
            make_run(arm="lcp", rep=1, passed=True, misuse=0, tool_calls=3),
        ]
        summary = aggregate(runs)
        base = summary["arms"]["baseline"]
        assert base["runs"] == 2
        assert base["pass_rate"] == 0.5
        assert base["total_misuse"] == 2
        assert base["misuse_rate"] == 1.0
        assert summary["arms"]["lcp"]["mean_tool_calls"] == 3

    def test_per_case_breakdown(self):
        runs = [make_run(rep=1, passed=True), make_run(rep=2, passed=False, misuse=1)]
        summary = aggregate(runs)
        assert summary["cases"]["c1"]["baseline"]["passes"] == "1/2"
        assert summary["cases"]["c1"]["baseline"]["misuse"] == 1

    def test_errors_counted(self):
        summary = aggregate([make_run(passed=False, error="timeout after 600s")])
        assert summary["arms"]["baseline"]["errors"] == 1


class TestRenderMarkdown:
    def test_contains_arm_table_and_case_rows(self):
        md = render_markdown(aggregate([make_run(), make_run(arm="lcp")]))
        assert "| baseline |" in md
        assert "| lcp |" in md
        assert "c1" in md
