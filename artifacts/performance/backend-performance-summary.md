# Backend Performance Regression Summary

Generated at: 2026-04-27T01:56:53.414941+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 9.18 | 9.77 | 766 | 200 |
| financials_payload | 12 | 16.80 | 19.35 | 4040 | 200 |
| models_payload | 12 | 10.11 | 10.78 | 5273 | 200 |
| peers_payload | 12 | 8.75 | 9.52 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 5.90 | 6.39 | 3808 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 35.79 | 48.04 | 10640 | 200 |
