---
title: Library Context Protocol
hide:
  - navigation
  - toc
---

<h1 style="display:none">Library Context Protocol</h1>

<div class="home-hero" markdown>
  <img src="assets/logo.png" alt="LCP Logo" width="128" style="margin-bottom: 0.5rem;">

  <p style="text-align: justify;"><b>lcp</b> (<i>Library Context Protocol</i>) is primarly a protocol designed to solve the problem of AI agents not having access to up-to-date library documentation, which leads to hallucinations and inaccurate code generation. The LCP SDK provides tools to scan Python packages, extract API information, and generate LCP-compliant JSON manifests. It also includes features for analyzing documentation coverage and generating missing docstrings using AI.</p>

  ```bash
  pip install lcp
  ```
</div>

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } __Get Started__

    ---

    Install LCP and generate your first manifest in 60 seconds.

    [:octicons-arrow-right-24: Quickstart](docs/quickstart.md)

-   :material-server:{ .lg .middle } __MCP Server__

    ---

    Expose LCP manifests to AI agents via the Model Context Protocol.

    [:octicons-arrow-right-24: MCP Server guide](docs/guides/mcp-server.md)

-   :material-book-open-variant:{ .lg .middle } __LCP v1 Specification__

    ---

    Document structure, symbols, signatures, types, and semantics.

    [:octicons-arrow-right-24: Read the spec](docs/spec/index.md)

</div>
