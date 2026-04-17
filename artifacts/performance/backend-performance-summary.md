# Backend Performance Regression Summary

Generated at: 2026-04-17T00:57:23.479833+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: regression

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 5.39 | 6.08 | 766 | 200 |
| financials_payload | 12 | 7.92 | 8.78 | 4040 | 200 |
| models_payload | 12 | 8.05 | 9.42 | 5135 | 200 |
| peers_payload | 12 | 7.64 | 8.42 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.93 | 2.48 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 25.18 | 36.68 | 10640 | 200 |

## Regressions

- hot_endpoints / company_search / latency_ms.p50: observed 5.39, explicit budget 4.32
- hot_endpoints / financials_payload / latency_ms.p95: observed 8.78, explicit budget 7.85
- hot_endpoints / models_payload / latency_ms.p50: observed 8.05, explicit budget 7.68
- hot_endpoints / models_payload / latency_ms.p95: observed 9.42, explicit budget 7.73
- hot_endpoints / peers_payload / latency_ms.p50: observed 7.64, explicit budget 7.63
- hot_endpoints / peers_payload / latency_ms.p95: observed 8.42, explicit budget 7.49
