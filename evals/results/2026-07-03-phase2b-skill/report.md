# Eval report

Model: `claude-haiku-4-5-20251001`

## By configuration

| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | Out tok (mean) | Tool calls (mean) | Cost (total) |
|-----|------|-----------|------------|--------|---------------|----------------|-------------------|--------------|
| lcp-skill | 24 | 42% | 0.54 | 0 | 52 | 2030 | 6.1 | $1.1917 |

## By case

| Case | Arm | Passes | Misuses |
|------|-----|--------|---------|
| cyhole-birdeye-price | lcp-skill | 3/3 | 0 |
| cyhole-jupiter-swap | lcp-skill | 0/3 | 0 |
| cyhole-missing-api-key | lcp-skill | 3/3 | 0 |
| cyhole-rugcheck-report | lcp-skill | 1/3 | 3 |
| fastmcp-client | lcp-skill | 0/3 | 3 |
| fastmcp-context | lcp-skill | 0/3 | 1 |
| fastmcp-resource | lcp-skill | 3/3 | 0 |
| fastmcp-server-tool | lcp-skill | 0/3 | 6 |
