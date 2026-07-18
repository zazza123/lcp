"""Argument-plumbing tests for evals/run.py (no agents are run)."""

from pathlib import Path

from run import build_parser, resolve_arms

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


class TestArmsMatrix:
    def test_arms_repeatable(self):
        args = build_parser().parse_args(
            ["run", "--out", "x", "--arms", "baseline", "--arms", "registry"]
        )
        assert args.arms == ["baseline", "registry"]

    def test_default_arms(self):
        args = build_parser().parse_args(["run", "--out", "x"])
        assert resolve_arms(args.arms) == ["baseline", "lcp"]

    def test_registry_lcp_bin_default(self):
        args = build_parser().parse_args(["run", "--out", "x"])
        assert str(args.registry_lcp_bin).endswith(".venv-registry/bin/lcp")


class TestArmConfigs:
    def test_writes_one_config_per_mcp_arm_family(self, tmp_path):
        from run import _write_arm_configs

        configs = _write_arm_configs(
            tmp_path, ["polars"],
            ["baseline", "lcp", "lcp-skill", "sitepkg", "registry", "context7"],
            registry_lcp_bin="/reg/bin/lcp",
        )
        assert configs["baseline"] is None and configs["sitepkg"] is None
        assert configs["lcp"] == configs["lcp-skill"]
        import json

        lcp_cfg = json.loads(configs["lcp"].read_text())
        assert "--expose" in lcp_cfg["mcpServers"]["lcp"]["args"]
        reg_cfg = json.loads(configs["registry"].read_text())
        assert reg_cfg["mcpServers"]["lcp"]["command"] == "/reg/bin/lcp"
        assert "--expose" not in reg_cfg["mcpServers"]["lcp"]["args"]
        assert ".lcp-registry-cache" in " ".join(
            reg_cfg["mcpServers"]["lcp"]["args"]
        )
        c7 = json.loads(configs["context7"].read_text())
        assert c7["mcpServers"]["context7"]["command"] == "npx"
