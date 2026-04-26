# Backend Performance Regression Summary

Generated at: 2026-04-25T03:41:57.569659+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 1.41 | 2.54 | 766 | 200 |
| financials_payload | 12 | 1.46 | 2.39 | 4040 | 200 |
| models_payload | 12 | 1.66 | 2.90 | 5162 | 200 |
| peers_payload | 12 | 1.37 | 2.21 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 2.09 | 3.24 | 3637 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 11.70 | 43.08 | 10640 | 200 |
