# Backend Performance Regression Summary

Generated at: 2026-04-22T05:27:47.766247+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 2.53 | 3.37 | 766 | 200 |
| financials_payload | 12 | 4.75 | 6.79 | 4040 | 200 |
| models_payload | 12 | 4.80 | 5.22 | 5135 | 200 |
| peers_payload | 12 | 4.79 | 5.29 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.13 | 1.69 | 3637 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 20.13 | 29.58 | 10640 | 200 |
