# Backend Performance Regression Summary

Generated at: 2026-04-11T14:52:54.168794+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: ok

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.46 | 4.07 | 766 | 200 |
| financials_payload | 12 | 3.58 | 4.01 | 4040 | 200 |
| models_payload | 12 | 3.56 | 4.12 | 5158 | 200 |
| peers_payload | 12 | 3.44 | 3.84 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.53 | 2.32 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 12.12 | 18.56 | 10640 | 200 |
