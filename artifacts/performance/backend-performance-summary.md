# Backend Performance Regression Summary

Generated at: 2026-04-19T12:15:18.183418+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: regression

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.02 | 3.84 | 766 | 200 |
| financials_payload | 12 | 5.65 | 7.37 | 4040 | 200 |
| models_payload | 12 | 7.71 | 8.40 | 5135 | 200 |
| peers_payload | 12 | 7.06 | 8.36 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.86 | 3.06 | 3637 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 36.07 | 47.61 | 10640 | 200 |

## Regressions

- hot_endpoints / models_payload / latency_ms.p50: observed 7.71, explicit budget 7.68
- hot_endpoints / models_payload / latency_ms.p95: observed 8.40, explicit budget 7.73
- hot_endpoints / peers_payload / latency_ms.p95: observed 8.36, explicit budget 7.49
- company_brief_concurrency / company_brief_ready / latency_ms.p50: observed 36.07, explicit budget 31.02
- company_brief_concurrency / company_brief_ready / latency_ms.p95: observed 47.61, explicit budget 46.85
