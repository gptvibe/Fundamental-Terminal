# Backend Performance Regression Summary

Generated at: 2026-04-13T01:56:46.163650+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 0.87 | 1.25 | 766 | 200 |
| financials_payload | 12 | 0.67 | 1.35 | 4040 | 200 |
| models_payload | 12 | 0.88 | 1.22 | 5135 | 200 |
| peers_payload | 12 | 0.63 | 0.84 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.15 | 1.43 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 6.73 | 8.67 | 10640 | 200 |
