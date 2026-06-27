---
description: Set up or repair the LCP plugin's .lcp.json — pick the launcher, registry, expose/preload, then verify the lcp serve-all MCP server actually starts.
---

# Configure the LCP plugin

Run the guided `.lcp.json` setup. Follow the **lcp-configure** skill: locate the
right config file (project `.lcp.json` vs global `~/.lcp/config.json`), walk the
user through the launcher (`command`/`python`), `registries`, `expose`, and
`preload` one step at a time, write valid merged JSON, and verify it by probing
`lcp --version` and any registry URL.

If the user passed an argument describing a symptom (e.g. "server won't start",
"can't resolve numpy"), go straight to the skill's **repair mode** and fix only
the failing piece: $ARGUMENTS
