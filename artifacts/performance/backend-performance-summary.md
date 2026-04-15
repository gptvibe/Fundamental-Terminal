# Backend Performance Regression Summary

Generated at: 2026-04-15T01:29:45.147955+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: regression

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 2.89 | 3.84 | 766 | 200 |
| financials_payload | 12 | 4.65 | 5.75 | 4040 | 200 |
| models_payload | 12 | 3.94 | 4.18 | 5135 | 200 |
| peers_payload | 12 | 3.88 | 4.27 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 0.92 | 1.03 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 18.98 | 23.09 | 10640 | 200 |

## Regressions

- hot_endpoints / financials_payload / latency_ms.p50: observed 4.65, explicit budget 4.48
- company_brief_concurrency / company_brief_ready / latency_ms.p50: observed 18.98, explicit budget 16.74
