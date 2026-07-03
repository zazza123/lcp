# Eval report

Model: `claude-haiku-4-5-20251001`

## By configuration

| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | Out tok (mean) | Tool calls (mean) | Cost (total) |
|-----|------|-----------|------------|--------|---------------|----------------|-------------------|--------------|
| lcp | 24 | 21% | 1.08 | 0 | 17 | 2126 | 1.2 | $0.5943 |

## By case

| Case | Arm | Passes | Misuses |
|------|-----|--------|---------|
| cyhole-birdeye-price | lcp | 2/3 | 2 |
| cyhole-jupiter-swap | lcp | 0/3 | 4 |
| cyhole-missing-api-key | lcp | 2/3 | 1 |
| cyhole-rugcheck-report | lcp | 0/3 | 6 |
| fastmcp-client | lcp | 0/3 | 3 |
| fastmcp-context | lcp | 0/3 | 2 |
| fastmcp-resource | lcp | 1/3 | 2 |
| fastmcp-server-tool | lcp | 0/3 | 6 |
