"""Invoke `claude -p` (headless) and parse its stream-json output."""

import json
import subprocess
import time
from dataclasses import dataclass
from typing import Iterable

from harness import extract

MODEL = "claude-haiku-4-5-20251001"
TIMEOUT_S = 600

PROMPT_TEMPLATE = """{prompt}

Requirements:
- Use the `{library}` Python library, version {version} (already installed).
- Reply with exactly one fenced Python code block containing complete, runnable code.
- Do not include explanations outside the code block.
"""


BUILTIN_TOOLS = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep",
    "WebFetch", "WebSearch", "Task", "NotebookEdit", "TodoWrite",
]


def build_command(prompt: str, arm: str, mcp_config: str | None) -> list[str]:
    """Build the claude CLI command; arms differ ONLY by --mcp-config.

    Built-in tools (Bash, Read, Write, etc.) are denied via --disallowedTools
    rather than `--tools ""`: the latter also strips MCP tools from the
    offered set, which would silently defeat the LCP arm.

    `--allowedTools "mcp__lcp"` pre-approves every tool on the MCP server
    named "lcp" (the documented server-level wildcard pattern). Headless
    `-p` runs auto-deny any tool call requiring interactive permission
    approval, so without this an actual mcp__lcp__* call by the model would
    silently fail with a permission denial (see Task 10 smoke test). This
    flag is a no-op in the baseline arm, which never registers a server
    named "lcp".
    """
    cmd = [
        "claude", "-p", prompt,
        "--model", MODEL,
        "--output-format", "stream-json", "--verbose",
        "--strict-mcp-config",
        "--disallowedTools", *BUILTIN_TOOLS,
        "--allowedTools", "mcp__lcp",
    ]
    if arm == "lcp":
        if mcp_config is None:
            raise ValueError("lcp arm requires an mcp_config path")
        cmd += ["--mcp-config", str(mcp_config)]
    return cmd


def parse_stream(lines: Iterable[str]) -> dict:
    """Parse stream-json lines: count tool_use blocks, read the final result."""
    tool_calls = 0
    result: dict = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            content = event.get("message", {}).get("content", [])
            tool_calls += sum(
                1 for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use"
            )
        elif event.get("type") == "result":
            result = event
    usage = result.get("usage", {})
    return {
        "result_text": result.get("result") or "",
        "tool_calls": tool_calls,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
        "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
        "cost_usd": result.get("total_cost_usd", 0.0),
        "num_turns": result.get("num_turns", 0),
        "is_error": (not result) or bool(result.get("is_error"))
                    or result.get("subtype") != "success",
    }


@dataclass
class AgentRun:
    result_text: str
    code: str | None
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float
    num_turns: int
    duration_s: float
    error: str | None = None


def run_agent(case, arm: str, mcp_config=None, timeout: int = TIMEOUT_S) -> AgentRun:
    """Run one case in one arm; never raises on agent failure (records error)."""
    prompt = PROMPT_TEMPLATE.format(
        prompt=case.prompt, library=case.library, version=case.version
    )
    cmd = build_command(prompt, arm, mcp_config)
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return AgentRun(
            result_text="", code=None, tool_calls=0, input_tokens=0,
            output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0,
            cost_usd=0.0, num_turns=0, duration_s=time.monotonic() - start,
            error=f"timeout after {timeout}s",
        )
    duration = time.monotonic() - start
    parsed = parse_stream(proc.stdout.splitlines())
    blocks = extract.extract_code_blocks(parsed["result_text"])
    error = None
    if proc.returncode != 0:
        error = f"claude exited {proc.returncode}: {proc.stderr.strip()[-500:]}"
    elif parsed["is_error"]:
        error = "agent returned an error result"
    return AgentRun(
        result_text=parsed["result_text"],
        code="\n\n".join(blocks) if blocks else None,
        tool_calls=parsed["tool_calls"],
        input_tokens=parsed["input_tokens"],
        output_tokens=parsed["output_tokens"],
        cache_read_tokens=parsed["cache_read_tokens"],
        cache_creation_tokens=parsed["cache_creation_tokens"],
        cost_usd=parsed["cost_usd"],
        num_turns=parsed["num_turns"],
        duration_s=duration,
        error=error,
    )
