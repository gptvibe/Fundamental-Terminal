# Backend Performance Regression Summary

Generated at: 2026-04-20T09:46:28.941514+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 2.70 | 3.06 | 766 | 200 |
| financials_payload | 12 | 4.48 | 6.19 | 4040 | 200 |
| models_payload | 12 | 6.22 | 7.52 | 5135 | 200 |
| peers_payload | 12 | 4.97 | 5.41 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.16 | 1.45 | 3637 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 18.24 | 23.30 | 10640 | 200 |
