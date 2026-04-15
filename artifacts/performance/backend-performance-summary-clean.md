# Backend Performance Regression Summary

Generated at: 2026-04-15T01:32:18.332601+00:00
Baseline: scripts/performance_regression_baseline.json
Overall status: regression

## Warm-Cache Hot Read Routes

Config: `{"rounds": 12, "ticker": "AAPL"}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_search | 12 | 3.30 | 5.84 | 766 | 200 |
| financials_payload | 12 | 5.24 | 5.58 | 4040 | 200 |
| models_payload | 12 | 4.80 | 5.30 | 5135 | 200 |
| peers_payload | 12 | 4.77 | 5.30 | 3631 | 200 |
| metrics_timeseries_payload | 12 | 1.06 | 1.47 | 3615 | 200 |

## Company Brief Simulated Concurrency

Config: `{"concurrency": 6, "requests_per_worker": 4, "ticker": "AAPL", "total_requests": 24}`

| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |
|---|---:|---:|---:|---:|---|
| company_brief_ready | 24 | 20.22 | 27.05 | 10640 | 200 |

## Regressions

- hot_endpoints / financials_payload / latency_ms.p50: observed 5.24, explicit budget 4.48
- hot_endpoints / models_payload / latency_ms.p50: observed 4.80, explicit budget 4.51
- hot_endpoints / peers_payload / latency_ms.p50: observed 4.77, explicit budget 4.34
