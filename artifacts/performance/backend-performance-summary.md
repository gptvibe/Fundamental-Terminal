# Backend Performance Regression Summary

Generated at: 2026-05-02T04:48:10.299285+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.87 | 4.79 | 766 | 200 |
| financials_payload | 12 | 7.93 | 8.43 | 4040 | 200 |
| models_payload | 12 | 6.26 | 7.06 | 5273 | 200 |
| peers_payload | 12 | 5.49 | 7.70 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 2.35 | 3.44 | 3808 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 21.92 | 32.38 | 10640 | 200 |
