# Backend Performance Regression Summary

Generated at: 2026-04-11T01:59:21.474073+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.88 | 4.60 | 766 | 200 |
| financials_payload | 12 | 3.35 | 3.60 | 4040 | 200 |
| models_payload | 12 | 3.42 | 3.85 | 5158 | 200 |
| peers_payload | 12 | 3.07 | 3.58 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.84 | 2.71 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 7.04 | 12.38 | 10640 | 200 |
