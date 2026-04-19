# Backend Performance Regression Summary

Generated at: 2026-04-19T04:47:05.007770+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 1.08 | 2.30 | 766 | 200 |
| financials_payload | 12 | 1.25 | 2.11 | 4040 | 200 |
| models_payload | 12 | 1.21 | 2.01 | 5135 | 200 |
| peers_payload | 12 | 1.06 | 2.33 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.78 | 2.72 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 10.33 | 15.95 | 10640 | 200 |
