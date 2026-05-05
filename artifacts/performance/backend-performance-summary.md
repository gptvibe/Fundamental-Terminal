# Backend Performance Regression Summary

Generated at: 2026-05-05T00:49:17.557719+00:00
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 8.78 | 9.88 | 766 | 200 |
| financials_payload | 12 | 14.52 | 17.59 | 4040 | 200 |
| models_payload | 12 | 7.01 | 8.22 | 5273 | 200 |
| peers_payload | 12 | 8.79 | 9.28 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 2.72 | 3.50 | 3808 | 200 |
| beneficial_ownership_summary | 12 | 2.28 | 3.76 | 1162 | 200 |
| governance_summary | 12 | 2.36 | 3.36 | 1188 | 200 |
| filing_events_summary | 12 | 1.87 | 2.83 | 1096 | 200 |
| capital_markets_summary | 12 | 1.88 | 2.65 | 1197 | 200 |
| earnings_summary | 12 | 2.25 | 3.07 | 1374 | 200 |
| metrics_summary | 12 | 2.14 | 3.15 | 2725 | 200 |
| institutional_holdings_summary | 12 | 1.79 | 2.44 | 860 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 26.65 | 34.82 | 10713 | 200 |
