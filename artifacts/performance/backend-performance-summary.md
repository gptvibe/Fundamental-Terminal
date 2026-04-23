# Backend Performance Regression Summary

Generated at: 2026-04-23T02:40:12.227105+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.07 | 3.28 | 766 | 200 |
| financials_payload | 12 | 5.18 | 5.49 | 4040 | 200 |
| models_payload | 12 | 5.42 | 5.98 | 5135 | 200 |
| peers_payload | 12 | 5.32 | 5.68 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.15 | 1.62 | 3637 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 21.05 | 26.80 | 10640 | 200 |
