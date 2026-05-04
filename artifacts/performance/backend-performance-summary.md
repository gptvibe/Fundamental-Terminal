# Backend Performance Regression Summary

Generated at: 2026-05-03T13:11:42.554947+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.78 | 4.48 | 766 | 200 |
| financials_payload | 12 | 9.18 | 10.81 | 4040 | 200 |
| models_payload | 12 | 5.18 | 5.78 | 5273 | 200 |
| peers_payload | 12 | 5.13 | 5.39 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 2.36 | 2.97 | 3808 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 20.15 | 29.83 | 10713 | 200 |
