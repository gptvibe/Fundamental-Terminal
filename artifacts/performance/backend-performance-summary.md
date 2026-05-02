# Backend Performance Regression Summary

Generated at: 2026-05-01T15:20:37.499894+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 4.97 | 6.80 | 766 | 200 |
| financials_payload | 12 | 8.39 | 9.54 | 4040 | 200 |
| models_payload | 12 | 6.86 | 7.61 | 5273 | 200 |
| peers_payload | 12 | 5.87 | 6.78 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 2.80 | 3.39 | 3808 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 22.80 | 30.81 | 10640 | 200 |
