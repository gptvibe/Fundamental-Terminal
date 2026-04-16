# Backend Performance Regression Summary

Generated at: 2026-04-16T02:30:04.908875+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: regression

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 6.22 | 7.35 | 766 | 200 |
| financials_payload | 12 | 7.08 | 7.56 | 4040 | 200 |
| models_payload | 12 | 6.90 | 8.33 | 5135 | 200 |
| peers_payload | 12 | 6.06 | 6.42 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.74 | 2.09 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 20.13 | 37.65 | 10640 | 200 |

## Regressions

- hot_endpoints / company_search / latency_ms.p50: observed 6.22, explicit budget 4.32
- hot_endpoints / models_payload / latency_ms.p95: observed 8.33, explicit budget 7.73
