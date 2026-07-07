# Eval report

Model: `claude-haiku-4-5-20251001`

## By configuration

| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | Out tok (mean) | Tool calls (mean) | Cost (total) |
|-----|------|-----------|------------|--------|---------------|----------------|-------------------|--------------|
| lcp-skill | 24 | 83% | 0.17 | 0 | 70 | 2092 | 8.5 | $1.6565 |

## By case

| Case | Arm | Passes | Misuses |
|------|-----|--------|---------|
| cyhole-birdeye-price | lcp-skill | 3/3 | 0 |
| cyhole-jupiter-swap | lcp-skill | 3/3 | 0 |
| cyhole-missing-api-key | lcp-skill | 2/3 | 1 |
| cyhole-rugcheck-report | lcp-skill | 2/3 | 2 |
| fastmcp-client | lcp-skill | 2/3 | 1 |
| fastmcp-context | lcp-skill | 3/3 | 0 |
| fastmcp-resource | lcp-skill | 3/3 | 0 |
| fastmcp-server-tool | lcp-skill | 2/3 | 0 |
