# Backend Performance Regression Summary

Generated at: 2026-04-19T03:26:58.104575+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 1.21 | 1.79 | 766 | 200 |
| financials_payload | 12 | 1.23 | 1.75 | 4040 | 200 |
| models_payload | 12 | 1.20 | 1.72 | 5135 | 200 |
| peers_payload | 12 | 1.19 | 2.00 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.43 | 1.99 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 9.09 | 14.08 | 10640 | 200 |
