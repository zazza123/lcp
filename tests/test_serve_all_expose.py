"""Tests for serve-all --expose/--preload package allow-list."""

from __future__ import annotations

import pytest
from lcp import mcp_server


def _build(expose=None, preload=None):
    # build the server object without entering the stdio loop
    return mcp_server.build_universal_server(expose=expose, preload=preload)


def test_expose_blocks_unlisted_package():
    server = _build(expose=["json"])
    resolve = server.tool_funcs["resolve_library"]
    blocked = resolve("os")
    assert blocked.get("error")
    assert "not exposed" in blocked["error"].lower()


def test_expose_allows_listed_package():
    server = _build(expose=["json"])
    resolve = server.tool_funcs["resolve_library"]
    ok = resolve("json")
    assert not ok.get("error")


def test_no_expose_allows_any_package():
    server = _build(expose=None)
    resolve = server.tool_funcs["resolve_library"]
    ok = resolve("json")
    assert not ok.get("error")
