# Eval report

Model: `claude-haiku-4-5-20251001`

## By configuration

| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | Out tok (mean) | Tool calls (mean) | Cost (total) |
|-----|------|-----------|------------|--------|---------------|----------------|-------------------|--------------|
| lcp-skill | 40 | 22% | 0.93 | 0 | 54 | 2498 | 5.3 | $1.8276 |

## By case

| Case | Arm | Passes | Misuses |
|------|-----|--------|---------|
| fastmcp-http-transport | lcp-skill | 2/5 | 2 |
| fastmcp-mount | lcp-skill | 2/5 | 3 |
| fastmcp-openapi | lcp-skill | 1/5 | 2 |
| fastmcp-proxy | lcp-skill | 0/5 | 2 |
| pocket-coffea-configurator | lcp-skill | 0/5 | 7 |
| pocket-coffea-custom-cut | lcp-skill | 4/5 | 1 |
| pocket-coffea-custom-workflow | lcp-skill | 0/5 | 6 |
| pocket-coffea-histograms | lcp-skill | 0/5 | 14 |
