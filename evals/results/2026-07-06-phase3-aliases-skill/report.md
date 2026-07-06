# Eval report

Model: `claude-haiku-4-5-20251001`

## By configuration

| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | Out tok (mean) | Tool calls (mean) | Cost (total) |
|-----|------|-----------|------------|--------|---------------|----------------|-------------------|--------------|
| lcp-skill | 24 | 67% | 0.33 | 0 | 61 | 2018 | 7.9 | $1.3671 |

## By case

| Case | Arm | Passes | Misuses |
|------|-----|--------|---------|
| cyhole-birdeye-price | lcp-skill | 2/3 | 2 |
| cyhole-jupiter-swap | lcp-skill | 3/3 | 0 |
| cyhole-missing-api-key | lcp-skill | 3/3 | 0 |
| cyhole-rugcheck-report | lcp-skill | 3/3 | 0 |
| fastmcp-client | lcp-skill | 1/3 | 3 |
| fastmcp-context | lcp-skill | 0/3 | 1 |
| fastmcp-resource | lcp-skill | 2/3 | 1 |
| fastmcp-server-tool | lcp-skill | 2/3 | 1 |
