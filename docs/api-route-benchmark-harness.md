# API Route Benchmark Harness

This repository includes a repeatable benchmark harness for the main API routes:

- company overview
- company financials
- charts
- derived metrics
- models
- compare
- screener
- source registry and source status

The harness script is [scripts/benchmark_api_routes.py](../scripts/benchmark_api_routes.py).

## What It Measures

For each benchmarked route and cache mode, the script records:

- latency statistics: p50, p95, p99, min, max, avg
- status codes and per-status counts
- payload bytes: min, avg, max
- cache-related response headers when present
- inferred cache states from headers (`hit`, `stale`, `fresh`) when available

## Cache Modes

- `warm`: one warm-up request per route, then measured rounds
- `cold`: each measured request includes a unique query nonce and `no-cache` headers to reduce cache reuse
- `both`: runs warm and cold suites in one invocation (default)

## Run Locally

Start the backend locally, then run:

```bash
python scripts/benchmark_api_routes.py \
  --base-url http://127.0.0.1:8000 \
  --ticker AAPL \
  --compare-tickers AAPL,MSFT \
  --rounds 12 \
  --cache-mode both \
  --json-out artifacts/performance/api-route-benchmark.json
```

## JSON Output For CI

The JSON output is deterministic enough for regression checks in CI:

- schema id: `api_route_benchmark_v1`
- includes run metadata and route inventory
- includes warm/cold suites and per-route measurement summaries

Example fields:

- `schema_version`
- `generated_at`
- `cache_modes`
- `routes[]`
- `suites[].cache_mode`
- `suites[].results[].latency_ms.p50`
- `suites[].results[].latency_ms.p95`
- `suites[].results[].latency_ms.p99`
- `suites[].results[].status_code_counts`
- `suites[].results[].payload_bytes.avg`
- `suites[].results[].cache_headers.state_counts`

You can compare two JSON artifacts in CI to detect regressions for specific routes or cache modes.