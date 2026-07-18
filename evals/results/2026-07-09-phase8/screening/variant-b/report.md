# Eval report

Model: `claude-haiku-4-5-20251001`

## By configuration

| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | Out tok (mean) | Tool calls (mean) | Cost (total) |
|-----|------|-----------|------------|--------|---------------|----------------|-------------------|--------------|
| lcp-skill | 40 | 18% | 0.85 | 0 | 56 | 2399 | 5.6 | $1.8977 |

## By case

| Case | Arm | Passes | Misuses |
|------|-----|--------|---------|
| fastmcp-http-transport | lcp-skill | 1/5 | 1 |
| fastmcp-mount | lcp-skill | 4/5 | 1 |
| fastmcp-openapi | lcp-skill | 0/5 | 1 |
| fastmcp-proxy | lcp-skill | 0/5 | 4 |
| pocket-coffea-configurator | lcp-skill | 0/5 | 5 |
| pocket-coffea-custom-cut | lcp-skill | 2/5 | 3 |
| pocket-coffea-custom-workflow | lcp-skill | 0/5 | 7 |
| pocket-coffea-histograms | lcp-skill | 0/5 | 12 |
