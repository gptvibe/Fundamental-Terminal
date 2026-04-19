# Backend Performance Regression Summary

Generated at: 2026-04-19T03:26:29.588260+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 0.89 | 1.16 | 766 | 200 |
| financials_payload | 12 | 0.75 | 0.90 | 4040 | 200 |
| models_payload | 12 | 1.09 | 1.71 | 5135 | 200 |
| peers_payload | 12 | 1.10 | 1.39 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.20 | 1.76 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 7.25 | 10.30 | 10640 | 200 |
