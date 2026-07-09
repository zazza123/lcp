"""Arm-matrix tests for build_command: arms differ ONLY by flags."""

import pytest

from harness import agent


def cmd(arm, mcp_config="cfg.json", append_system=None):
    return agent.build_command(
        "P", arm, mcp_config, model="m", append_system=append_system
    )


class TestMcpArms:
    @pytest.mark.parametrize("arm", ["lcp", "lcp-skill", "registry"])
    def test_lcp_server_arms_use_config_and_allow_lcp(self, arm):
        c = cmd(arm, append_system="skill" if arm == "lcp-skill" else None)
        assert "--mcp-config" in c and "cfg.json" in c
        assert c[c.index("--allowedTools") + 1] == "mcp__lcp"

    def test_context7_allows_context7_tools_only(self):
        c = cmd("context7", append_system=agent.CONTEXT7_RULE)
        assert "--mcp-config" in c
        assert c[c.index("--allowedTools") + 1] == "mcp__context7"
        assert "mcp__lcp" not in c

    @pytest.mark.parametrize("arm", sorted(agent.MCP_ARMS))
    def test_mcp_arms_require_config(self, arm):
        with pytest.raises(ValueError):
            cmd(arm, mcp_config=None)


class TestSitepkgArm:
    def test_keeps_read_glob_grep_denies_the_rest(self):
        c = cmd("sitepkg", mcp_config=None, append_system="site-packages: /x")
        i = c.index("--disallowedTools")
        j = c.index("--allowedTools") if "--allowedTools" in c else len(c)
        denied = c[i + 1:j]
        for keep in agent.SITEPKG_KEEP:
            assert keep not in denied
        assert "Bash" in denied and "WebFetch" in denied and "Write" in denied

    def test_no_mcp_and_no_allowed_tools(self):
        c = cmd("sitepkg", mcp_config=None, append_system="x")
        assert "--mcp-config" not in c and "--allowedTools" not in c


class TestBaselineUnchanged:
    def test_baseline_denies_all_builtins_no_mcp(self):
        c = cmd("baseline", mcp_config=None)
        assert "--mcp-config" not in c
        i = c.index("--disallowedTools")
        denied = c[i + 1:i + 1 + len(agent.BUILTIN_TOOLS)]
        assert denied == agent.BUILTIN_TOOLS


class TestAppendSystem:
    def test_any_arm_gets_append_system_when_given(self):
        c = cmd("context7", append_system="RULE")
        assert c[c.index("--append-system-prompt") + 1] == "RULE"

    def test_lcp_skill_still_requires_it(self):
        with pytest.raises(ValueError):
            cmd("lcp-skill", append_system=None)


class TestToolResultCapture:
    def test_parse_stream_records_block_form_tool_results(self):
        # Anthropic block form: content is a list of text parts.
        lines = [
            '{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "mcp__lcp__search", "input": {"query": "q"}}]}}',
            '{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "RESULT-TEXT"}]}]}}',
            '{"type": "result", "result": "done", "subtype": "success", "usage": {}}',
        ]
        parsed = agent.parse_stream(lines)
        assert parsed["tool_results"] == [
            {"tool_use_id": "t1", "content": "RESULT-TEXT"}
        ]

    def test_parse_stream_records_string_form_tool_results(self):
        # Real CLI stream: content is a plain JSON string (observed shape).
        lines = [
            '{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "mcp__lcp__resolve_library", "input": {"name": "cyhole"}}]}}',
            '{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{\\"status\\":\\"loaded\\",\\"name\\":\\"cyhole\\"}"}]}}',
            '{"type": "result", "result": "done", "subtype": "success", "usage": {}}',
        ]
        parsed = agent.parse_stream(lines)
        assert parsed["tool_results"] == [
            {"tool_use_id": "t1", "content": '{"status":"loaded","name":"cyhole"}'}
        ]

    def test_parse_stream_ignores_non_text_parts(self):
        # A list holding only a tool_reference part yields empty text.
        lines = [
            '{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "mcp__lcp__search", "input": {}}]}}',
            '{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "tool_reference", "tool_name": "mcp__lcp__search"}]}]}}',
            '{"type": "result", "result": "done", "subtype": "success", "usage": {}}',
        ]
        parsed = agent.parse_stream(lines)
        assert parsed["tool_results"] == [{"tool_use_id": "t1", "content": ""}]
