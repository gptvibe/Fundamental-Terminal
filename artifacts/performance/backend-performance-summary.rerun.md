# Backend Performance Regression Summary

Generated at: 2026-04-17T00:57:55.799393+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.47 | 4.81 | 766 | 200 |
| financials_payload | 12 | 5.70 | 6.96 | 4040 | 200 |
| models_payload | 12 | 4.94 | 5.40 | 5135 | 200 |
| peers_payload | 12 | 4.45 | 5.34 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.01 | 1.60 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 19.27 | 26.79 | 10640 | 200 |
