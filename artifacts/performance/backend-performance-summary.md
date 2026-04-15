# Backend Performance Regression Summary

Generated at: 2026-04-15T03:41:28.789402+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 2.24 | 2.50 | 766 | 200 |
| financials_payload | 12 | 3.65 | 4.35 | 4040 | 200 |
| models_payload | 12 | 4.08 | 4.50 | 5135 | 200 |
| peers_payload | 12 | 3.62 | 3.92 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.13 | 1.44 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 19.06 | 24.77 | 10640 | 200 |
