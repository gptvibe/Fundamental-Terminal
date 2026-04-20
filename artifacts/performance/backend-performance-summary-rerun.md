# Backend Performance Regression Summary

Generated at: 2026-04-19T12:15:37.654665+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 2.69 | 3.78 | 766 | 200 |
| financials_payload | 12 | 4.31 | 5.07 | 4040 | 200 |
| models_payload | 12 | 4.83 | 5.36 | 5135 | 200 |
| peers_payload | 12 | 4.21 | 4.80 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.03 | 1.48 | 3637 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 17.90 | 26.70 | 10640 | 200 |
