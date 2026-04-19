# Backend Performance Regression Summary

Generated at: 2026-04-19T06:19:14.727212+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 2.50 | 3.56 | 766 | 200 |
| financials_payload | 12 | 2.73 | 3.66 | 4040 | 200 |
| models_payload | 12 | 2.32 | 4.05 | 5135 | 200 |
| peers_payload | 12 | 1.99 | 3.54 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 3.35 | 4.31 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 16.98 | 34.57 | 10640 | 200 |
