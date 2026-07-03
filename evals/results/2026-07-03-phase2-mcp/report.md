# Eval report

Model: `claude-haiku-4-5-20251001`

## By configuration

| Arm | Runs | Pass rate | Misuse/run | Errors | In tok (mean) | Out tok (mean) | Tool calls (mean) | Cost (total) |
|-----|------|-----------|------------|--------|---------------|----------------|-------------------|--------------|
| baseline | 84 | 45% | 0.31 | 0 | 11 | 1653 | 0.3 | $1.3740 |
| lcp | 84 | 52% | 0.32 | 0 | 13 | 1405 | 0.7 | $1.4662 |

## By case

| Case | Arm | Passes | Misuses |
|------|-----|--------|---------|
| cyhole-birdeye-price | baseline | 0/3 | 0 |
| cyhole-birdeye-price | lcp | 0/3 | 4 |
| cyhole-jupiter-swap | baseline | 0/3 | 1 |
| cyhole-jupiter-swap | lcp | 0/3 | 3 |
| cyhole-missing-api-key | baseline | 0/3 | 4 |
| cyhole-missing-api-key | lcp | 2/3 | 1 |
| cyhole-rugcheck-report | baseline | 0/3 | 3 |
| cyhole-rugcheck-report | lcp | 0/3 | 0 |
| fastmcp-client | baseline | 1/3 | 4 |
| fastmcp-client | lcp | 1/3 | 3 |
| fastmcp-context | baseline | 0/3 | 2 |
| fastmcp-context | lcp | 0/3 | 1 |
| fastmcp-resource | baseline | 0/3 | 3 |
| fastmcp-resource | lcp | 0/3 | 4 |
| fastmcp-server-tool | baseline | 3/3 | 0 |
| fastmcp-server-tool | lcp | 0/3 | 6 |
| hamana-connector-not-initialised | baseline | 0/3 | 3 |
| hamana-connector-not-initialised | lcp | 1/3 | 1 |
| hamana-csv-to-sqlite | baseline | 0/3 | 3 |
| hamana-csv-to-sqlite | lcp | 0/3 | 0 |
| hamana-internal-shortcuts | baseline | 2/3 | 0 |
| hamana-internal-shortcuts | lcp | 2/3 | 0 |
| hamana-sqlite-execute | baseline | 0/3 | 0 |
| hamana-sqlite-execute | lcp | 0/3 | 0 |
| httpx-async | baseline | 3/3 | 0 |
| httpx-async | lcp | 3/3 | 0 |
| httpx-client | baseline | 3/3 | 0 |
| httpx-client | lcp | 3/3 | 0 |
| httpx-retries | baseline | 0/3 | 0 |
| httpx-retries | lcp | 1/3 | 1 |
| httpx-stream | baseline | 3/3 | 0 |
| httpx-stream | lcp | 3/3 | 0 |
| polars-equals | baseline | 2/3 | 1 |
| polars-equals | lcp | 2/3 | 1 |
| polars-group-by | baseline | 3/3 | 0 |
| polars-group-by | lcp | 3/3 | 0 |
| polars-map-elements | baseline | 1/3 | 0 |
| polars-map-elements | lcp | 1/3 | 0 |
| polars-with-columns | baseline | 3/3 | 0 |
| polars-with-columns | lcp | 3/3 | 0 |
| pydantic-field-validator | baseline | 3/3 | 0 |
| pydantic-field-validator | lcp | 3/3 | 0 |
| pydantic-json-schema | baseline | 3/3 | 0 |
| pydantic-json-schema | lcp | 3/3 | 0 |
| pydantic-settings | baseline | 3/3 | 0 |
| pydantic-settings | lcp | 3/3 | 0 |
| pydantic-validate-call | baseline | 1/3 | 0 |
| pydantic-validate-call | lcp | 3/3 | 0 |
| textual-layout | baseline | 1/3 | 1 |
| textual-layout | lcp | 2/3 | 1 |
| textual-post-message | baseline | 2/3 | 1 |
| textual-post-message | lcp | 2/3 | 1 |
| textual-richlog | baseline | 1/3 | 0 |
| textual-richlog | lcp | 3/3 | 0 |
| textual-scroll | baseline | 0/3 | 0 |
| textual-scroll | lcp | 0/3 | 0 |
