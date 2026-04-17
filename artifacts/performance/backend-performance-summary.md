# Backend Performance Regression Summary

Generated at: 2026-04-17T06:18:14.925206+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 2.97 | 3.45 | 766 | 200 |
| financials_payload | 12 | 4.60 | 5.20 | 4040 | 200 |
| models_payload | 12 | 5.35 | 5.61 | 5135 | 200 |
| peers_payload | 12 | 5.62 | 7.30 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.12 | 1.72 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 21.49 | 33.63 | 10640 | 200 |
