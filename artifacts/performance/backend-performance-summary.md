# Backend Performance Regression Summary

Generated at: 2026-04-12T13:33:42.710034+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 1.69 | 2.23 | 766 | 200 |
| financials_payload | 12 | 1.81 | 2.18 | 4040 | 200 |
| models_payload | 12 | 1.95 | 2.39 | 5158 | 200 |
| peers_payload | 12 | 1.95 | 2.75 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 2.17 | 2.83 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 10.52 | 16.96 | 10640 | 200 |
