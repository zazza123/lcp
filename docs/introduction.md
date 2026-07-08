# Introduction

The **Library Context Protocol (LCP)** is a machine-readable format for describing software libraries: their public symbols, signatures, types, and semantics — designed to be consumed by AI systems, IDEs, and documentation generators.

AI code assistants are trained on large datasets, but libraries evolve constantly. New versions ship, APIs change, and functions get deprecated. Without accurate, up-to-date context, AI assistants are left guessing from training data — leading to fabricated method names, wrong parameter names, and suggestions that worked in an older version but break at runtime. LCP addresses this by providing a structured, version-specific description of a library's public API that tools can consume directly, rather than inferring from source code or stale training snapshots.

## What does an LCP fragment look like?

```json
{
  "json:loads": {
    "kind": "function",
    "module": "json",
    "signatures": [
      {
        "params": [{ "name": "s", "type": "str", "required": true }],
        "returns": "Any"
      }
    ],
    "semantics": {
      "summary": "Deserialize a JSON document to a Python object."
    },
    "stability": { "level": "stable" }
  }
}
```

A full manifest contains a `manifest` header plus many such entries in the `symbols` map, keyed by stable symbol IDs. The LCP *format* is language-agnostic JSON; the scanner shipped in this SDK introspects **Python** packages — other languages need their own producers. See [Examples](spec/examples.md) for more.

## Who benefits from LCP?

### AI code assistants

AI assistants can use an LCP manifest as ground truth about what a library actually exports. Instead of guessing from training data, the model receives exact function signatures, parameter names, types, and behavioral notes for the specific version installed in the user's environment. This eliminates a class of runtime errors caused by invented methods, renamed parameters, or deprecated call patterns.

### Documentation generators

Documentation tools can consume an LCP manifest as a single authoritative source of record for a library's public API. Because LCP captures not just signatures but also summaries and stability markers, a generator can produce human-readable docs without re-parsing source files or maintaining a separate extraction pipeline per language.

### IDEs and language tooling

An IDE plugin can load an LCP manifest to provide autocomplete, inline documentation, and deprecation warnings for any library, regardless of whether type stubs or source code are available locally. Because the format is language-agnostic JSON, the same manifest can serve tooling written in any language.

## LCP vs. alternatives

Several existing approaches give AI agents some information about library APIs. They solve different problems, and an honest comparison helps you pick the right one — or combine them.

**Context7 and similar remote documentation services** serve curated, narrative documentation for popular public libraries, fetched from a remote service. They are strongest when you want prose: tutorials, guides, upgrade notes. LCP does not compete on narrative quality — it answers a different question: *what exactly does the version installed in this environment expose?* LCP introspects the installed package itself, so it covers private and internal packages no documentation service has ever seen, works fully offline, and returns token-dense structured records (signatures, parameters, raised exceptions, examples) rather than prose pages.

**llms.txt** is a hand-maintained, site-level summary that a project publishes for crawlers and LLMs. It is coarse-grained (library level, not symbol level), only exists if the maintainer writes one, and says nothing about the version you actually installed.

**Letting the agent read `site-packages`** is always available and version-accurate, but token-expensive: the agent navigates raw source files to answer one signature question, with no ranked search and no pre-digested structure. LCP is that same ground truth, pre-indexed — one `search` call returns ranked hits, each with its exact import line.

**Training data** is the zero-setup default: the model has seen API usage in its corpus. It cannot be version-accurate — the model may know `requests.get` but not which keyword arguments exist in the release you installed — and it silently degrades on niche or recently-changed libraries.

| | LCP | Context7 | llms.txt | Reading site-packages |
|---|:---:|:---:|:---:|:---:|
| Matches the *installed* version | yes | no — upstream docs | no | yes |
| Works offline | yes | no | no | yes |
| Private / internal packages | yes | no | only self-published | yes |
| Token-dense structured answers | yes | narrative text | coarse summary | raw source (expensive) |
| Symbol-level signatures | yes | partial | no | yes (manual digging) |
| Narrative guides & tutorials | no | yes | partial | no |

In one sentence: **choose LCP when the agent needs exact, offline ground truth about the library versions installed in your environment — including private packages; choose Context7 when you want curated narrative documentation for popular public libraries.**

## Next steps

- [Quickstart](quickstart.md) — generate your first LCP manifest.
- [LCP v1 spec](spec/index.md) — the full specification.
- [MCP Server](guides/mcp-server.md) — expose an LCP manifest to AI agents.
