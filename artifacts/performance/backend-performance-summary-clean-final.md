# Backend Performance Regression Summary

Generated at: 2026-04-15T01:33:01.876067+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 2.57 | 2.83 | 766 | 200 |
| financials_payload | 12 | 4.09 | 4.23 | 4040 | 200 |
| models_payload | 12 | 4.22 | 4.48 | 5135 | 200 |
| peers_payload | 12 | 3.93 | 4.45 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 0.96 | 1.05 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 17.10 | 23.83 | 10640 | 200 |
