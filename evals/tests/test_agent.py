import json
from pathlib import Path

import pytest

from harness.agent import (
    BUILTIN_TOOLS,
    MODEL,
    build_command,
    load_skill_text,
    parse_stream,
)

STREAM_LINES = [
    json.dumps({"type": "system", "subtype": "init", "tools": ["mcp__lcp__resolve_library"]}),
    json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "mcp__lcp__resolve_library", "input": {}}]}}),
    json.dumps({"type": "user", "message": {"content": [{"type": "tool_result"}]}}),
    json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "```python\nx = 1\n```"}]}}),
    json.dumps({"type": "result", "subtype": "success",
                "result": "```python\nx = 1\n```",
                "usage": {"input_tokens": 100, "output_tokens": 50,
                          "cache_read_input_tokens": 10,
                          "cache_creation_input_tokens": 5},
                "total_cost_usd": 0.001, "num_turns": 2, "is_error": False}),
]


class TestParseStream:
    def test_counts_tool_calls(self):
        assert parse_stream(STREAM_LINES)["tool_calls"] == 1

    def test_extracts_result_and_usage(self):
        parsed = parse_stream(STREAM_LINES)
        assert parsed["result_text"] == "```python\nx = 1\n```"
        assert parsed["input_tokens"] == 100
        assert parsed["output_tokens"] == 50
        assert parsed["cache_read_tokens"] == 10
        assert parsed["cost_usd"] == 0.001
        assert parsed["num_turns"] == 2
        assert parsed["is_error"] is False

    def test_tolerates_garbage_and_blank_lines(self):
        parsed = parse_stream(["", "not json", *STREAM_LINES])
        assert parsed["tool_calls"] == 1

    def test_missing_result_is_error(self):
        parsed = parse_stream(STREAM_LINES[:2])
        assert parsed["is_error"] is True
        assert parsed["result_text"] == ""

    def test_collects_tool_call_details(self):
        details = parse_stream(STREAM_LINES)["tool_call_details"]
        assert details == [
            {"name": "mcp__lcp__resolve_library", "input": {}}
        ]

    def test_tool_call_input_is_truncated(self):
        lines = [
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "mcp__lcp__search",
                 "input": {"query": "x" * 2000}}]}}),
            STREAM_LINES[-1],
        ]
        details = parse_stream(lines)["tool_call_details"]
        assert details[0]["name"] == "mcp__lcp__search"
        assert len(json.dumps(details[0]["input"])) <= 520


class TestBuildCommand:
    def test_baseline_has_no_mcp_config(self):
        cmd = build_command("do it", "baseline", None)
        assert cmd[:3] == ["claude", "-p", "do it"]
        assert "--mcp-config" not in cmd
        assert "--strict-mcp-config" in cmd
        assert MODEL in cmd

    def test_lcp_arm_appends_mcp_config(self):
        cmd = build_command("do it", "lcp", "/tmp/mcp.json")
        assert cmd[-2:] == ["--mcp-config", "/tmp/mcp.json"]

    def test_web_tools_disallowed(self):
        cmd = build_command("do it", "baseline", None)
        assert "WebFetch" in cmd and "WebSearch" in cmd

    def test_builtin_tools_denied_via_disallowed_not_tools_flag(self):
        # `--tools ""` strips MCP tools along with built-ins (see Task 10
        # smoke test); built-ins must instead be blocked individually via
        # --disallowedTools so MCP tools stay visible to the lcp arm.
        cmd = build_command("do it", "baseline", None)
        assert "--tools" not in cmd
        assert "--disallowedTools" in cmd
        idx = cmd.index("--disallowedTools")
        denied = cmd[idx + 1 : idx + 1 + len(BUILTIN_TOOLS)]
        assert set(denied) == set(BUILTIN_TOOLS)

    def test_lcp_skill_arm_appends_system_prompt(self):
        cmd = build_command(
            "do things", "lcp-skill", "/tmp/mcp.json",
            append_system="SKILL BODY",
        )
        assert "--mcp-config" in cmd
        i = cmd.index("--append-system-prompt")
        assert cmd[i + 1] == "SKILL BODY"

    def test_lcp_skill_arm_requires_append_system(self):
        with pytest.raises(ValueError):
            build_command("p", "lcp-skill", "/tmp/mcp.json")

    def test_model_override(self):
        cmd = build_command("p", "baseline", None, model="claude-sonnet-5")
        i = cmd.index("--model")
        assert cmd[i + 1] == "claude-sonnet-5"

    def test_default_model_unchanged(self):
        cmd = build_command("p", "baseline", None)
        assert cmd[cmd.index("--model") + 1] == MODEL

    def test_mcp_tools_preallowed(self):
        # Headless `-p` runs auto-deny any tool call that needs interactive
        # permission approval unless pre-approved via --allowedTools (see
        # Task 10 report's "Fix report: allowedTools" section). The lcp arm
        # must carry --allowedTools "mcp__lcp" to unblock real MCP tool
        # calls. The baseline arm never registers a server named "lcp", so
        # it must not carry a no-op --allowedTools flag.
        cmd = build_command("do it", "lcp", "/tmp/mcp.json")
        assert "--allowedTools" in cmd
        idx = cmd.index("--allowedTools")
        assert cmd[idx + 1] == "mcp__lcp"
        cmd = build_command("do it", "baseline", None)
        assert "--allowedTools" not in cmd


class TestLoadSkillText:
    def test_strips_frontmatter(self, tmp_path: Path):
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: x\ndescription: y\n---\n\n# Body\n\ntext\n")
        body = load_skill_text(skill)
        assert body.startswith("# Body")
        assert "name: x" not in body

    def test_real_skill_loads(self):
        real = Path(__file__).parents[2] / "plugin/lcp/skills/lcp-universal/SKILL.md"
        body = load_skill_text(real)
        assert "resolve_library" in body
        assert not body.startswith("---")
