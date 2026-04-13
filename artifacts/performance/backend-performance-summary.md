# Backend Performance Regression Summary

Generated at: 2026-04-13T01:15:13.123282+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: regression

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 5.21 | 7.80 | 766 | 200 |
| financials_payload | 12 | 6.44 | 7.84 | 4040 | 200 |
| models_payload | 12 | 7.01 | 8.78 | 5135 | 200 |
| peers_payload | 12 | 6.75 | 7.49 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 2.58 | 3.41 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 12.23 | 22.46 | 10640 | 200 |

## Regressions

- hot_endpoints / company_search / latency_ms.p50: observed 5.21, explicit budget 4.32
- hot_endpoints / financials_payload / latency_ms.p50: observed 6.44, explicit budget 4.48
- hot_endpoints / models_payload / latency_ms.p50: observed 7.01, explicit budget 4.51
- hot_endpoints / models_payload / latency_ms.p95: observed 8.78, explicit budget 7.73
- hot_endpoints / peers_payload / latency_ms.p50: observed 6.75, explicit budget 4.34
