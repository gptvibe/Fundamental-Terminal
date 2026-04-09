# Backend Performance Regression Summary

Generated at: 2026-04-09T14:03:42.295504+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.78 | 4.22 | 766 | 200 |
| financials_payload | 12 | 3.34 | 4.27 | 4040 | 200 |
| models_payload | 12 | 3.19 | 3.86 | 5158 | 200 |
| peers_payload | 12 | 3.64 | 4.94 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.64 | 2.67 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 10.14 | 15.52 | 10640 | 200 |
