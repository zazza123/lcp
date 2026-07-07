from harness.engagement import engagement_stats, is_engaged


def make_run(case_id="cyhole-birdeye-price", passed=True, misuse=0, tools=()):
    return {
        "case_id": case_id,
        "verification": {"passed": passed, "misuse_count": misuse},
        "tool_call_details": [{"name": n, "input": {}} for n in tools],
    }


class TestIsEngaged:
    def test_lcp_call_counts(self):
        assert is_engaged(make_run(tools=("mcp__lcp__resolve_library",)))

    def test_toolsearch_alone_is_not_engaged(self):
        # The Phase 4 stall pattern: deferred-tool load with no lcp call after.
        assert not is_engaged(make_run(tools=("ToolSearch",)))

    def test_no_tool_calls(self):
        assert not is_engaged(make_run())


class TestEngagementStats:
    def test_buckets_and_prefixes(self):
        runs = [
            make_run(tools=("mcp__lcp__resolve_library",), passed=True),
            make_run(passed=False, misuse=2),
            make_run(case_id="fastmcp-client", tools=("ToolSearch",),
                     passed=False, misuse=1),
        ]
        stats = engagement_stats(runs)
        assert stats["total"] == {"runs": 3, "passed": 1, "misuse": 3}
        assert stats["engaged"] == {"runs": 1, "passed": 1, "misuse": 0}
        assert stats["non_engaged"] == {"runs": 2, "passed": 0, "misuse": 3}
        assert stats["by_prefix"]["cyhole"] == {"runs": 2, "engaged": 1}
        assert stats["by_prefix"]["fastmcp"] == {"runs": 1, "engaged": 0}
