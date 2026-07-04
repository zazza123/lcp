# Phase 2b Exp2 — model-class probe (claude-sonnet-5, no skill)

24 runs: 4 fastmcp cases x 3 reps x both arms (baseline + lcp), model
`claude-sonnet-5`, claude CLI 2.1.200, lcp at the Phase 2 V2 surface.
Reference: Phase 2 `lcp` arm (haiku), same cases: 0.0 calls/run, 1/12 pass;
Exp1 `lcp-skill` (haiku, V2): 1.42 lcp calls/run, 3/12 pass.

## Gate metric

Counting only `mcp__lcp__*` calls (the two nonzero `tool_calls` runs were
the CLI's built-in `Skill` tool, not lcp):

| arm      | lcp calls/run | pass  | misuse |
|----------|---------------|-------|--------|
| baseline | 0.00          | 12/12 | 0      |
| lcp      | **0.00**      | 12/12 | 0      |

**Gate (fastmcp mean voluntary lcp calls in the lcp arm >= 1.0/run):
FAILED — sonnet does not adopt from server instructions alone.** The
outcome decision is unaffected: Exp1 already passed its gate, so the
phase closes on outcome A; Exp2's role reduces to context.

And the context inverts the haiku story: sonnet's **baseline** passes all
12 runs with zero misuse — it writes correct fastmcp 2.x API
(`from fastmcp import FastMCP`, `@mcp.tool`, `Client` async usage) from
parametric knowledge. There is no `fastmcp.Server` hallucination to fix,
hence nothing to verify and no reason to call the tools: sonnet's
confidence on fastmcp is *calibrated*, where haiku's is not (haiku without
the skill: equally zero calls, but 1/12 pass).

## Implications recorded

1. **The F1 false-confidence failure is model-bound.** It exists only for
   haiku-class models on these cases; for sonnet-class the fastmcp cases
   are at ceiling. Product guidance: small models need the plugin skill
   (Exp1 shows it works); capable models self-serve on well-known libraries.
2. **Phase 8 task-mix note (E4-style calibration):** these 4 fastmcp cases
   cannot differentiate anything for capable models — the published
   benchmark needs cases outside a capable model's parametric knowledge
   (post-cutoff API changes, niche libraries like cyhole/hamana) or the
   LCP arms will show zero delta by construction.
