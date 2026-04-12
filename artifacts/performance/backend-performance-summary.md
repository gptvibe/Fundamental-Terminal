# Backend Performance Regression Summary

Generated at: 2026-04-12T12:26:11.235367+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 4.04 | 5.01 | 766 | 200 |
| financials_payload | 12 | 4.28 | 4.99 | 4040 | 200 |
| models_payload | 12 | 4.09 | 4.70 | 5158 | 200 |
| peers_payload | 12 | 4.00 | 4.31 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 2.05 | 2.89 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 9.61 | 21.18 | 10640 | 200 |
