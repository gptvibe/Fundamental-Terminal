# Backend Performance Regression Summary

Generated at: 2026-05-06T01:35:51.996973+00:00
Baseline: scripts\performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.83 | 4.60 | 766 | 200 |
| financials_payload | 12 | 12.06 | 17.49 | 4040 | 200 |
| models_payload | 12 | 5.77 | 6.58 | 5273 | 200 |
| peers_payload | 12 | 6.32 | 7.64 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.90 | 2.53 | 3808 | 200 |
| beneficial_ownership_summary | 12 | 1.71 | 2.78 | 1162 | 200 |
| governance_summary | 12 | 2.08 | 2.95 | 1188 | 200 |
| filing_events_summary | 12 | 1.32 | 2.05 | 1096 | 200 |
| capital_markets_summary | 12 | 2.35 | 4.40 | 1197 | 200 |
| earnings_summary | 12 | 1.39 | 1.93 | 1374 | 200 |
| metrics_summary | 12 | 1.73 | 2.12 | 2725 | 200 |
| institutional_holdings_summary | 12 | 1.71 | 2.03 | 860 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 17.47 | 22.04 | 10713 | 200 |
