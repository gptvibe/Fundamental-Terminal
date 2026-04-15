# Backend Performance Regression Summary

Generated at: 2026-04-15T01:31:44.491310+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: regression

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 6.20 | 7.61 | 766 | 200 |
| financials_payload | 12 | 8.65 | 12.46 | 4040 | 200 |
| models_payload | 12 | 9.57 | 16.03 | 5135 | 200 |
| peers_payload | 12 | 6.47 | 7.06 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.66 | 1.92 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 29.04 | 37.50 | 10640 | 200 |

## Regressions

- hot_endpoints / company_search / latency_ms.p50: observed 6.20, explicit budget 4.32
- hot_endpoints / financials_payload / latency_ms.p50: observed 8.65, explicit budget 4.48
- hot_endpoints / financials_payload / latency_ms.p95: observed 12.46, explicit budget 7.85
- hot_endpoints / models_payload / latency_ms.p50: observed 9.57, explicit budget 4.51
- hot_endpoints / models_payload / latency_ms.p95: observed 16.03, explicit budget 7.73
- hot_endpoints / peers_payload / latency_ms.p50: observed 6.47, explicit budget 4.34
