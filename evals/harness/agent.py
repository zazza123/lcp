"""Invoke `claude -p` (headless) and parse its stream-json output."""

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
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


def load_skill_text(path) -> str:
    """Return a SKILL.md body with the YAML frontmatter stripped.

    Injected verbatim via --append-system-prompt: the experiment measures
    the shipped skill artifact, not a paraphrase of it.
    """
    text = Path(path).read_text()
    if text.startswith("---"):
        end = text.index("---", 3)
        text = text[end + 3:]
    return text.strip() + "\n"


def build_command(
    prompt: str,
    arm: str,
    mcp_config: str | None,
    model: str = MODEL,
    append_system: str | None = None,
) -> list[str]:
    """Build the claude CLI command; arms differ ONLY by flags.

    baseline    : no MCP config.
    lcp         : + --mcp-config (the server's instructions are the only nudge).
    lcp-skill   : lcp + --append-system-prompt with the lcp-universal skill
                  body — approximates what a developer with the plugin
                  installed experiences (the skill fires task-side).

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
        "--model", model,
        "--output-format", "stream-json", "--verbose",
        "--strict-mcp-config",
        "--disallowedTools", *BUILTIN_TOOLS,
        "--allowedTools", "mcp__lcp",
    ]
    if arm in ("lcp", "lcp-skill"):
        if mcp_config is None:
            raise ValueError(f"{arm} arm requires an mcp_config path")
        cmd += ["--mcp-config", str(mcp_config)]
    if arm == "lcp-skill":
        if append_system is None:
            raise ValueError("lcp-skill arm requires append_system text")
        cmd += ["--append-system-prompt", append_system]
    return cmd


def _truncate_input(value: dict, limit: int = 500) -> dict:
    """Keep tool inputs analyzable without bloating run files.

    The truncated wrapper (envelope + re-escaping of the snippet) must
    itself stay within ~limit chars once JSON-encoded, so trim until it fits.
    """
    encoded = json.dumps(value)
    if len(encoded) <= limit:
        return value
    snippet = encoded[:limit]
    while len(json.dumps({"_truncated": snippet})) > limit + 20:
        snippet = snippet[:-8]
    return {"_truncated": snippet}


def parse_stream(lines: Iterable[str]) -> dict:
    """Parse stream-json lines: count tool_use blocks, read the final result."""
    tool_calls = 0
    tool_call_details: list[dict] = []
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
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tool_calls += 1
                    tool_call_details.append(
                        {
                            "name": b.get("name", ""),
                            "input": _truncate_input(b.get("input") or {}),
                        }
                    )
        elif event.get("type") == "result":
            result = event
    usage = result.get("usage", {})
    return {
        "result_text": result.get("result") or "",
        "tool_calls": tool_calls,
        "tool_call_details": tool_call_details,
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
    tool_call_details: list = field(default_factory=list)
    error: str | None = None


def run_agent(
    case,
    arm: str,
    mcp_config=None,
    timeout: int = TIMEOUT_S,
    model: str = MODEL,
    append_system: str | None = None,
) -> AgentRun:
    """Run one case in one arm; never raises on agent failure (records error)."""
    prompt = PROMPT_TEMPLATE.format(
        prompt=case.prompt, library=case.library, version=case.version
    )
    cmd = build_command(prompt, arm, mcp_config, model=model, append_system=append_system)
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return AgentRun(
            result_text="", code=None, tool_calls=0, input_tokens=0,
            output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0,
            cost_usd=0.0, num_turns=0, duration_s=time.monotonic() - start,
            tool_call_details=[],
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
        tool_call_details=parsed["tool_call_details"],
        error=error,
    )
