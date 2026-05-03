# Backend Performance Regression Summary

Generated at: 2026-05-03T08:46:42.068420+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 6.38 | 8.10 | 766 | 200 |
| financials_payload | 12 | 11.73 | 13.90 | 4040 | 200 |
| models_payload | 12 | 9.92 | 10.90 | 5273 | 200 |
| peers_payload | 12 | 9.57 | 10.54 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 4.18 | 4.56 | 3808 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 35.14 | 51.54 | 10713 | 200 |
