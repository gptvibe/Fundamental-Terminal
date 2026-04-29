# Backend Performance Regression Summary

Generated at: 2026-04-29T01:43:18.485433+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 6.76 | 8.07 | 766 | 200 |
| financials_payload | 12 | 14.17 | 16.07 | 4040 | 200 |
| models_payload | 12 | 9.78 | 11.08 | 5273 | 200 |
| peers_payload | 12 | 9.17 | 10.57 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 4.11 | 4.89 | 3808 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 45.23 | 70.51 | 10640 | 200 |
