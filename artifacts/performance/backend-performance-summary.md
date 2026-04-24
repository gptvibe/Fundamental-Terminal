# Backend Performance Regression Summary

Generated at: 2026-04-23T23:58:25.323396+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 0.89 | 1.20 | 766 | 200 |
| financials_payload | 12 | 1.03 | 1.59 | 4040 | 200 |
| models_payload | 12 | 1.01 | 1.94 | 5135 | 200 |
| peers_payload | 12 | 1.03 | 1.46 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.32 | 1.51 | 3637 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 9.07 | 13.89 | 10640 | 200 |
