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
Baseline "before" values were not captured in this patch run; use the benchmark script on the pre-change revision to fill those columns.
Sample "after" values from this branch (Docker compose local run, 3 warm rounds):

| Endpoint | Before p50 (ms) | After p50 (ms) | Before p95 (ms) | After p95 (ms) | Notes |
|---|---:|---:|---:|---:|---|
| company search | _TBD_ | 3.25 | _TBD_ | 3.47 | warm-cache |
| financials payload | _TBD_ | 45.09 | _TBD_ | 51.92 | warm-cache |
| models payload | _TBD_ | 7.46 | _TBD_ | 17.71 | warm-cache |
| peers payload | _TBD_ | 26.98 | _TBD_ | 30.84 | warm-cache |

## Operational notes
- Refresh orchestration remains cache-first and non-blocking:
  stale/missing data returns cached payload immediately and queues a background refresh.
- Dataset lock timeout is controlled with `REFRESH_LOCK_TIMEOUT_SECONDS`.
- Response cache TTLs are controlled with:
  - `HOT_RESPONSE_CACHE_TTL_SECONDS`
  - `HOT_RESPONSE_CACHE_STALE_TTL_SECONDS`
