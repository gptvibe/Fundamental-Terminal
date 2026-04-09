# Backend Performance Regression Summary

Generated at: 2026-04-09T23:43:02.795767+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 1.50 | 1.96 | 766 | 200 |
| financials_payload | 12 | 1.87 | 2.53 | 4040 | 200 |
| models_payload | 12 | 1.72 | 2.02 | 5158 | 200 |
| peers_payload | 12 | 1.52 | 1.78 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.61 | 1.98 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 8.60 | 14.78 | 10640 | 200 |
