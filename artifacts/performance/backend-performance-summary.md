# Backend Performance Regression Summary

Generated at: 2026-05-04T05:33:58.821241+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.46 | 4.29 | 766 | 200 |
| financials_payload | 12 | 6.48 | 6.85 | 4040 | 200 |
| models_payload | 12 | 4.36 | 5.45 | 5273 | 200 |
| peers_payload | 12 | 4.36 | 5.95 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.40 | 1.68 | 3808 | 200 |
| beneficial_ownership_summary | 12 | 1.32 | 1.55 | 1162 | 200 |
| governance_summary | 12 | 1.28 | 1.50 | 1188 | 200 |
| filing_events_summary | 12 | 1.21 | 1.44 | 1096 | 200 |
| capital_markets_summary | 12 | 1.22 | 1.78 | 1197 | 200 |
| earnings_summary | 12 | 1.32 | 1.70 | 1374 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 15.83 | 18.68 | 10713 | 200 |
