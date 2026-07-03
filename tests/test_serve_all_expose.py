"""Tests for serve-all --expose/--preload package allow-list."""

from __future__ import annotations

from lcp.mcp_server import create_universal_server


def _build(expose=None, preload=None):
    return create_universal_server(expose=expose, preload=preload, no_cache=True)


def test_expose_blocks_unlisted_package():
    server = _build(expose=["json"])
    blocked = server.tools["resolve_library"]("os")
    assert blocked["error"]["code"] == "library_not_exposed"


def test_expose_allows_listed_package():
    server = _build(expose=["json"])
    ok = server.tools["resolve_library"]("json")
    assert not ok.get("error")


def test_no_expose_allows_any_package():
    server = _build(expose=None)
    ok = server.tools["resolve_library"]("json")
    assert not ok.get("error")
