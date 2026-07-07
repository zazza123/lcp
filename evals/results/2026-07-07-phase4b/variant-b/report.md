# Eval report

Model: `claude-haiku-4-5-20251001`

## By configuration

| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | Out tok (mean) | Tool calls (mean) | Cost (total) |
|-----|------|-----------|------------|--------|---------------|----------------|-------------------|--------------|
| lcp-skill | 24 | 71% | 0.33 | 0 | 63 | 1867 | 7.9 | $1.4951 |

## By case

| Case | Arm | Passes | Misuses |
|------|-----|--------|---------|
| cyhole-birdeye-price | lcp-skill | 3/3 | 0 |
| cyhole-jupiter-swap | lcp-skill | 2/3 | 1 |
| cyhole-missing-api-key | lcp-skill | 3/3 | 0 |
| cyhole-rugcheck-report | lcp-skill | 2/3 | 2 |
| fastmcp-client | lcp-skill | 2/3 | 1 |
| fastmcp-context | lcp-skill | 3/3 | 0 |
| fastmcp-resource | lcp-skill | 1/3 | 2 |
| fastmcp-server-tool | lcp-skill | 1/3 | 2 |
