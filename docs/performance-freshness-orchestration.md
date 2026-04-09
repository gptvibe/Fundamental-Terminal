# Performance and Freshness Orchestration Notes

## Scope
This update hardens backend latency and refresh coordination without changing product semantics.

## Frontend performance follow-up
- Replaced blanket frontend `fetch(..., { cache: "no-store" })` behavior with endpoint-aware read caching in `frontend/lib/api.ts`.
- Added stale-while-revalidate read policy with in-flight dedupe for read endpoints and explicit uncached behavior for mutations and refresh queue requests.
- Added ticker-scoped cache invalidation that is triggered by refresh actions and SSE terminal events to keep freshness status aligned with the existing background refresh flow.
- Added cross-tab cache sync (localStorage + BroadcastChannel invalidation) for shared read payload reuse across tabs/components.
- Deferred heavy client charts/tables on company financials and peers pages through dynamic islands with lightweight placeholders.
- Added virtualization for large financial and peer metrics tables to reduce client render and commit cost on long lists.
- Added route-level loading and error boundaries for the company workspace to improve transitions and failure recovery.

## Frontend hotspot follow-up (models + earnings)
- Added a reusable viewport-gated client deferral helper (`DeferredClientSection`) so heavy islands mount only when close to view.
- Deferred model-heavy islands (DCF scenario analysis and full model analytics) on `/company/[ticker]/models`.
- Dynamically loaded the advanced AG Grid section on `/company/[ticker]/models` to avoid pulling grid runtime into the initial route payload.
- Moved SEC-heavy earnings chart stack into a dedicated dynamically loaded island component (`SecHeavyModelsPanel`) so `/company/[ticker]/earnings` no longer statically imports Recharts-heavy analytics.

## What changed
- Added DB pool tuning knobs with safe defaults in environment-backed settings.
- Added `dataset_refresh_state` table keyed by `(company_id, dataset)` to persist freshness and active refresh lock metadata.
- Replaced repeated `MAX(last_checked)` scan patterns with refresh-state lookups where practical, with scan fallback for migration safety.
- Refactored `EdgarIngestionService.refresh_company` into a policy-driven orchestrator with dataset-specific refresh jobs so partial refresh branches and failure isolation stay explicit.
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
- metrics-timeseries payload

CI regression gate:

```bash
python scripts/run_performance_regression_gate.py --baseline-file scripts/performance_regression_baseline.json --fail-on-regression --json-out artifacts/performance/backend-performance-summary.json --markdown-out artifacts/performance/backend-performance-summary.md
```

The gate runs deterministic in-process benchmarks against synthetic route fixtures so CI can enforce explicit budgets for:
- request count
- p50 latency
- p95 latency
- average payload size

It covers the warm-cache hot read routes above and the `/api/companies/{ticker}/brief` route under simulated concurrency. The JSON and Markdown outputs are uploaded from CI as build artifacts.

Model-computation benchmark:

```bash
python scripts/benchmark_model_computation.py --models dcf,reverse_dcf,roic,ratios --rounds 10
```

This benchmark executes model definitions in-process against a deterministic SEC-style dataset so model latency regressions can be detected without depending on live upstream traffic.

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
- Dataset jobs for statements, prices, insiders, Form 144, institutional holdings, beneficial ownership, earnings, filing events, and capital markets now sit behind a single service orchestrator while preserving the existing SSE event flow.
- Dataset lock timeout is controlled with `REFRESH_LOCK_TIMEOUT_SECONDS`.
- Structured logs now emit refresh, model-compute, and SSE job events with a shared traceable `job_id`/`trace_id` path.
- Frontend console rows and SSE payloads expose `ticker` and `kind` metadata so operators can correlate UI events with backend logs.
- Response cache TTLs are controlled with:
  - `HOT_RESPONSE_CACHE_TTL_SECONDS`
  - `HOT_RESPONSE_CACHE_STALE_TTL_SECONDS`
- Cache effectiveness counters include hot cache hit/miss/stale/expired/store and conditional 304 counts.
