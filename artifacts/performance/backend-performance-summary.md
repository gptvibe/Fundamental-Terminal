# Backend Performance Regression Summary

Generated at: 2026-04-22T00:39:58.838503+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 2.79 | 3.03 | 766 | 200 |
| financials_payload | 12 | 5.17 | 7.43 | 4040 | 200 |
| models_payload | 12 | 4.60 | 4.85 | 5135 | 200 |
| peers_payload | 12 | 4.13 | 4.41 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.40 | 1.51 | 3637 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 20.56 | 35.14 | 10640 | 200 |
