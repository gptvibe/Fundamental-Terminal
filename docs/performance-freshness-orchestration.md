# Performance and Freshness Orchestration Notes

## Scope
This update hardens backend latency and refresh coordination without changing product semantics.

## What changed
- Added DB pool tuning knobs with safe defaults in environment-backed settings.
- Added `dataset_refresh_state` table keyed by `(company_id, dataset)` to persist freshness and active refresh lock metadata.
- Replaced repeated `MAX(last_checked)` scan patterns with refresh-state lookups where practical, with scan fallback for migration safety.
- Optimized model retrieval and peer assembly query paths to reduce N+1 database access.
- Added stale-while-revalidate process cache for hot read endpoints:
  - `/api/companies/search`
  - `/api/companies/{ticker}/financials`
  - `/api/companies/{ticker}/models`
  - `/api/companies/{ticker}/peers`
- Added `ETag` and `Last-Modified` support for conditional GET on those endpoints.
- Added persistent refresh dedupe/lock path in queueing (`company_refresh` dataset lock).
- Added in-memory cache effectiveness counters and an inspection route:
  - `/api/internal/cache-metrics`

## Benchmark script
Run:

```bash
python scripts/benchmark_hot_endpoints.py --base-url http://127.0.0.1:8000 --ticker AAPL --rounds 20
```

The script runs warm-cache benchmark cases for:
- company search
- financials payload
- models payload
- peers payload

## Before/after notes
Before values are from the pre-follow-up implementation benchmark run.
After values are from this follow-up implementation run.
Both were captured from local Docker runs against `AAPL` after a warm-up pass.

| Endpoint | Before p50 (ms) | After p50 (ms) | Before p95 (ms) | After p95 (ms) | Notes |
|---|---:|---:|---:|---:|---|
| company search | 3.25 | 4.13 | 3.47 | 27.28 | warm-cache |
| financials payload | 45.09 | 47.29 | 51.92 | 49.79 | warm-cache |
| models payload | 7.46 | 30.75 | 17.71 | 31.70 | warm-cache |
| peers payload | 26.98 | 6.41 | 30.84 | 30.27 | warm-cache |

## Operational notes
- Refresh orchestration remains cache-first and non-blocking:
  stale/missing data returns cached payload immediately and queues a background refresh.
- Dataset lock timeout is controlled with `REFRESH_LOCK_TIMEOUT_SECONDS`.
- Response cache TTLs are controlled with:
  - `HOT_RESPONSE_CACHE_TTL_SECONDS`
  - `HOT_RESPONSE_CACHE_STALE_TTL_SECONDS`
- Cache effectiveness counters include hot cache hit/miss/stale/expired/store and conditional 304 counts.
