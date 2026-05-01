# Backend Performance Regression Summary

Generated at: 2026-05-01T13:33:39.264630+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 5.12 | 6.12 | 766 | 200 |
| financials_payload | 12 | 11.25 | 12.75 | 4040 | 200 |
| models_payload | 12 | 9.19 | 10.86 | 5273 | 200 |
| peers_payload | 12 | 8.93 | 10.48 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 3.71 | 4.03 | 3808 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 29.47 | 46.94 | 10640 | 200 |
