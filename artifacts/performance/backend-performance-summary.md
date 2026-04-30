# Backend Performance Regression Summary

Generated at: 2026-04-29T09:41:04.578411+00:00
Baseline: scripts\performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 4.82 | 5.66 | 766 | 200 |
| financials_payload | 12 | 10.52 | 11.99 | 4040 | 200 |
| models_payload | 12 | 7.64 | 8.99 | 5273 | 200 |
| peers_payload | 12 | 6.96 | 8.72 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 3.56 | 4.04 | 3808 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 40.85 | 56.56 | 10640 | 200 |
