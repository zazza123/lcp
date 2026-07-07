#!/usr/bin/env python3
"""PreToolUse hook (Write|Edit): once per session, block the first .py write
that happens before any lcp verification call and remind the agent to verify.

Claude Code hook contract:
- stdin: JSON payload with tool_name, tool_input, transcript_path.
- exit 0          -> allow the tool call.
- exit 2 + stderr -> block the call; stderr is fed back to the model.

Fail-open everywhere: a broken hook must never block real work.
"""

import json
import re
import sys
from pathlib import Path

MARKER = "lcp-verify-reminder"
# A real lcp tool call appears in the transcript as a tool_use block whose
# "name" field starts with mcp__lcp__ — prose mentions of tool names don't.
LCP_CALL = re.compile(r'"name"\s*:\s*"mcp__lcp__')
REMINDER = (
    f"[{MARKER}] You are writing a Python file but have made no lcp "
    "verification call this session. If this code imports a third-party "
    'library, verify the APIs first: call resolve_library("<package>"), '
    "then get_symbol on the symbols you use. If the lcp server is "
    "unavailable or no third-party library is involved, repeat this "
    "Write/Edit unchanged and it will go through."
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    tool_input = payload.get("tool_input") or {}
    if not str(tool_input.get("file_path", "")).endswith(".py"):
        return 0
    try:
        transcript = Path(str(payload.get("transcript_path", ""))).read_text()
    except OSError:
        return 0
    if MARKER in transcript or LCP_CALL.search(transcript):
        return 0
    print(REMINDER, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
