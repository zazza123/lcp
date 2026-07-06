"""rescore re-verifies stored runs with the current verifier."""

import json
import subprocess
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parents[1]

CASE_YAML = """\
- id: json-loads
  library: json
  version: "X"
  prompt: parse JSON
  checks:
    required_symbols: ["json:loads"]
"""


def test_rescore_recomputes_verification(tmp_path):
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "json.yaml").write_text(CASE_YAML)

    src = tmp_path / "old"
    (src / "runs").mkdir(parents=True)
    stale = {
        "case_id": "json-loads",
        "arm": "lcp",
        "rep": 1,
        "model": "test-model",
        "code": "import json\njson.loads('1')",
        "metrics": {
            "input_tokens": 10,
            "output_tokens": 100,
            "tool_calls": 0,
            "cost_usd": 0.01,
        },
        "verification": {
            "passed": False,
            "misuse_count": 9,
            "required_missing": ["json:loads"],
            "forbidden_used": [],
            "unresolved_usages": [],
            "error": None,
        },
    }
    (src / "runs" / "json-loads_lcp_r1.json").write_text(json.dumps(stale))

    out = tmp_path / "new"
    proc = subprocess.run(
        [
            sys.executable,
            str(EVALS_DIR / "run.py"),
            "rescore",
            "--src", str(src),
            "--out", str(out),
            "--cases", str(cases_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    rescored = json.loads((out / "runs" / "json-loads_lcp_r1.json").read_text())
    assert rescored["verification"]["passed"] is True
    assert rescored["verification"]["required_missing"] == []
    assert (out / "summary.json").exists()
