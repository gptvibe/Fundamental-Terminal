# Backend Performance Regression Summary

Generated at: 2026-04-24T10:59:29.010475+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.23 | 4.04 | 766 | 200 |
| financials_payload | 12 | 5.43 | 7.28 | 4040 | 200 |
| models_payload | 12 | 4.80 | 5.23 | 5162 | 200 |
| peers_payload | 12 | 4.34 | 4.87 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 0.99 | 1.62 | 3637 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 19.88 | 26.73 | 10640 | 200 |
