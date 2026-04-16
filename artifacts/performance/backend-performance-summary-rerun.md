# Backend Performance Regression Summary

Generated at: 2026-04-16T02:17:22.366248+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: regression

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 4.41 | 5.81 | 766 | 200 |
| financials_payload | 12 | 5.18 | 6.04 | 4040 | 200 |
| models_payload | 12 | 5.95 | 6.43 | 5135 | 200 |
| peers_payload | 12 | 6.13 | 7.38 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.50 | 1.92 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 22.94 | 32.17 | 10640 | 200 |

## Regressions

- hot_endpoints / company_search / latency_ms.p50: observed 4.41, explicit budget 4.32
