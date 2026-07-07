"""Argument-plumbing tests for evals/run.py (no agents are run)."""

from pathlib import Path

from run import build_parser

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestSkillFileFlag:
    def test_default_is_the_shipped_plugin_skill(self):
        args = build_parser().parse_args(["run", "--out", "x"])
        assert args.skill_file == (
            REPO_ROOT / "plugin/lcp/skills/lcp-universal/SKILL.md"
        )

    def test_override(self, tmp_path):
        skill = tmp_path / "SKILL.md"
        args = build_parser().parse_args(
            ["run", "--out", "x", "--skill-file", str(skill)]
        )
        assert args.skill_file == skill


class TestEngagementSubcommand:
    def test_accepts_multiple_out_dirs(self):
        args = build_parser().parse_args(
            ["engagement", "--out", "a", "--out", "b"]
        )
        assert args.out == ["a", "b"]
