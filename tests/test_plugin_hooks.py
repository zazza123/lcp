"""Tests for the plugin's PreToolUse verify-reminder hook.

The hook is exercised exactly as Claude Code runs it: a subprocess with the
hook payload on stdin. Exit 0 = allow the tool call; exit 2 = block it and
feed stderr back to the model. The hook must fail OPEN on every anomaly.
"""

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "plugin/lcp/hooks/verify_reminder.py"
HOOKS_JSON = Path(__file__).parent.parent / "plugin/lcp/hooks/hooks.json"


def run_hook(payload):
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=data, capture_output=True, text=True, timeout=10,
    )


def payload(tmp_path, transcript_text, file_path="script.py"):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(transcript_text)
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": "import x"},
        "transcript_path": str(transcript),
    }


class TestVerifyReminderHook:
    def test_blocks_py_write_without_lcp_call(self, tmp_path):
        result = run_hook(payload(tmp_path, '{"type": "user"}\n'))
        assert result.returncode == 2
        assert "lcp-verify-reminder" in result.stderr
        assert "resolve_library" in result.stderr

    def test_allows_after_lcp_call(self, tmp_path):
        transcript = json.dumps({
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "name": "mcp__lcp__resolve_library",
                "input": {"name": "cyhole"},
            }]},
        }) + "\n"
        assert run_hook(payload(tmp_path, transcript)).returncode == 0

    def test_reminds_only_once(self, tmp_path):
        # After one block, the marker is in the transcript: never nag again.
        transcript = '{"type": "user", "content": "[lcp-verify-reminder] ..."}\n'
        assert run_hook(payload(tmp_path, transcript)).returncode == 0

    def test_mention_of_tool_name_in_prose_does_not_count_as_a_call(self, tmp_path):
        # e.g. a deferred-tools listing that cites mcp__lcp__resolve_library
        # as plain text is NOT an lcp call.
        result = run_hook(payload(
            tmp_path,
            '{"type": "user", "content": "tools: mcp__lcp__resolve_library"}\n',
        ))
        assert result.returncode == 2

    def test_ignores_non_python_files(self, tmp_path):
        result = run_hook(payload(tmp_path, "{}", file_path="notes.md"))
        assert result.returncode == 0

    def test_fails_open_on_missing_transcript(self):
        p = {"tool_name": "Write", "tool_input": {"file_path": "a.py"},
             "transcript_path": "/nonexistent/transcript.jsonl"}
        assert run_hook(p).returncode == 0

    def test_fails_open_on_malformed_stdin(self):
        assert run_hook("not json").returncode == 0


class TestHooksJson:
    def test_wires_pretooluse_to_hook_script(self):
        config = json.loads(HOOKS_JSON.read_text())
        pre = config["hooks"]["PreToolUse"]
        assert pre[0]["matcher"] == "Write|Edit"
        assert "verify_reminder.py" in pre[0]["hooks"][0]["command"]
        assert "${CLAUDE_PLUGIN_ROOT}" in pre[0]["hooks"][0]["command"]

    def test_keeps_sessionstart_hook(self):
        config = json.loads(HOOKS_JSON.read_text())
        assert "SessionStart" in config["hooks"]
