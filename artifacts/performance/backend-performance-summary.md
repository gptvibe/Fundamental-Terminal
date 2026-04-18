# Backend Performance Regression Summary

Generated at: 2026-04-18T00:28:21.877654+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 0.87 | 1.31 | 766 | 200 |
| financials_payload | 12 | 0.78 | 0.97 | 4040 | 200 |
| models_payload | 12 | 0.88 | 1.17 | 5135 | 200 |
| peers_payload | 12 | 0.71 | 1.34 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 0.95 | 1.90 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 7.87 | 11.31 | 10640 | 200 |
