# Eval report

Model: `claude-haiku-4-5-20251001`

## By configuration

| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | Out tok (mean) | Tool calls (mean) | Cost (total) |
|-----|------|-----------|------------|--------|---------------|----------------|-------------------|--------------|
| lcp-skill | 40 | 25% | 0.72 | 0 | 61 | 2332 | 6.2 | $2.0765 |

## By case

| Case | Arm | Passes | Misuses |
|------|-----|--------|---------|
| fastmcp-http-transport | lcp-skill | 0/5 | 0 |
| fastmcp-mount | lcp-skill | 5/5 | 0 |
| fastmcp-openapi | lcp-skill | 0/5 | 3 |
| fastmcp-proxy | lcp-skill | 1/5 | 0 |
| pocket-coffea-configurator | lcp-skill | 0/5 | 7 |
| pocket-coffea-custom-cut | lcp-skill | 4/5 | 1 |
| pocket-coffea-custom-workflow | lcp-skill | 0/5 | 5 |
| pocket-coffea-histograms | lcp-skill | 0/5 | 13 |
