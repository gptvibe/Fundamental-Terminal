# Backend Performance Regression Summary

Generated at: 2026-04-26T08:01:48.093222+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 4.66 | 5.26 | 766 | 200 |
| financials_payload | 12 | 8.54 | 9.38 | 4040 | 200 |
| models_payload | 12 | 5.84 | 6.23 | 5273 | 200 |
| peers_payload | 12 | 5.61 | 6.48 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 2.80 | 3.43 | 3808 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 26.65 | 29.11 | 10640 | 200 |
