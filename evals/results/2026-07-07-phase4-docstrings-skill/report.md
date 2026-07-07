# Eval report

Model: `claude-haiku-4-5-20251001`

## By configuration

| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | Out tok (mean) | Tool calls (mean) | Cost (total) |
|-----|------|-----------|------------|--------|---------------|----------------|-------------------|--------------|
| lcp-skill | 24 | 54% | 0.71 | 0 | 54 | 2096 | 6.8 | $1.3100 |

## By case

| Case | Arm | Passes | Misuses |
|------|-----|--------|---------|
| cyhole-birdeye-price | lcp-skill | 2/3 | 2 |
| cyhole-jupiter-swap | lcp-skill | 2/3 | 0 |
| cyhole-missing-api-key | lcp-skill | 3/3 | 0 |
| cyhole-rugcheck-report | lcp-skill | 1/3 | 3 |
| fastmcp-client | lcp-skill | 0/3 | 6 |
| fastmcp-context | lcp-skill | 2/3 | 2 |
| fastmcp-resource | lcp-skill | 1/3 | 2 |
| fastmcp-server-tool | lcp-skill | 2/3 | 2 |
