# Backend Performance Regression Summary

Generated at: 2026-04-30T13:14:28.186063+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 1.78 | 2.29 | 766 | 200 |
| financials_payload | 12 | 1.82 | 2.88 | 4040 | 200 |
| models_payload | 12 | 1.89 | 2.93 | 5273 | 200 |
| peers_payload | 12 | 1.79 | 2.41 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 2.12 | 2.84 | 3808 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 26.59 | 31.21 | 10640 | 200 |
