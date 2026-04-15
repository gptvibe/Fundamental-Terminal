# Backend Performance Regression Summary

Generated at: 2026-04-15T01:30:15.804594+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: regression

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 2.94 | 3.74 | 766 | 200 |
| financials_payload | 12 | 4.46 | 5.43 | 4040 | 200 |
| models_payload | 12 | 4.43 | 4.89 | 5135 | 200 |
| peers_payload | 12 | 4.19 | 4.90 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.01 | 1.22 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 19.39 | 29.28 | 10640 | 200 |

## Regressions

- company_brief_concurrency / company_brief_ready / latency_ms.p50: observed 19.39, explicit budget 16.74
- company_brief_concurrency / company_brief_ready / latency_ms.p95: observed 29.28, explicit budget 25.14
