# Eval report

Model: `claude-sonnet-5`

## By configuration

| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | Out tok (mean) | Tool calls (mean) | Cost (total) |
|-----|------|-----------|------------|--------|---------------|----------------|-------------------|--------------|
| baseline | 12 | 100% | 0.00 | 0 | 1 | 586 | 0.1 | $0.5484 |
| lcp | 12 | 100% | 0.00 | 0 | 1 | 572 | 0.1 | $0.4839 |

## By case

| Case | Arm | Passes | Misuses |
|------|-----|--------|---------|
| fastmcp-client | baseline | 3/3 | 0 |
| fastmcp-client | lcp | 3/3 | 0 |
| fastmcp-context | baseline | 3/3 | 0 |
| fastmcp-context | lcp | 3/3 | 0 |
| fastmcp-resource | baseline | 3/3 | 0 |
| fastmcp-resource | lcp | 3/3 | 0 |
| fastmcp-server-tool | baseline | 3/3 | 0 |
| fastmcp-server-tool | lcp | 3/3 | 0 |
