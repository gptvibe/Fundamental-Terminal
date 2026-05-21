# Performance Rewrite Decision

Date: 2026-05-21

## Current Architecture Summary

Fundamental Terminal is a FastAPI + Next.js research workspace for U.S. public equities. The backend keeps public route registration and response schemas in `app/api/routers/` and `app/api/schemas/`, while legacy-compatible handler serialization still lives behind the `app.main` compatibility boundary. Ingestion, SEC normalization, derived metrics, model execution, hot-cache behavior, and refresh policy live under `app/services/`.

The product is already built around persisted/cache-first reads. Company research flows use cached company snapshots, persisted financial statements, derived metric mart rows, hot response cache entries, and background refresh jobs. The frontend uses Next.js app routes, a shared API read cache, and lazy/deferred client sections for heavier chart and grid surfaces.

The correct architecture direction is not a full rewrite. The existing layering is intentional, guarded by `scripts/check_architecture_boundaries.py`, and already has performance-specific cache, query, and audit infrastructure. The remaining work should keep stable public contracts while removing specific request-path waste and expanding regression coverage.

## Audit Evidence

- Read project guidance and constraints in `AGENTS.md`, `README.md`, `PERF_REFACTOR_PLAN.md`, `PERF_REFACTOR_SUMMARY.md`, `docs/backend-architecture-boundaries.md`, and existing performance docs/tooling.
- Inspected backend performance tools:
  - `scripts/run_performance_regression_gate.py`
  - `scripts/benchmark_hot_endpoints.py`
  - `scripts/benchmark_api_routes.py`
  - `app/performance_audit.py`
  - `app/middleware/performance_audit.py`
  - `app/middleware/route_timing.py`
- Inspected frontend performance audit tooling:
  - `frontend/scripts/run-performance-audit.mjs`
  - `frontend/lib/performance-audit.ts`
  - `docs/company-page-request-budget.md`
  - `docs/lazy-loading-bundle-reduction.md`
- Ran deterministic backend regression gate:
  - Command: `python scripts/run_performance_regression_gate.py --baseline-file scripts/performance_regression_baseline.json --fail-on-regression --json-out artifacts/performance/backend-performance-summary-current.json --markdown-out artifacts/performance/backend-performance-summary-current.md`
  - Result: passed, zero regressions.
  - Current synthetic highlights: `company_brief_ready` p50 8.45 ms, p95 9.28 ms; warm hot endpoints p95 roughly 2.22-3.02 ms in the synthetic harness.
  - Environment note: Redis was configured but unreachable, so the local run used process-local hot-cache fallback.
- Ran production frontend build:
  - Command: `npm --prefix frontend run build`
  - Result: passed.
  - First Load JS: `/` 117 kB, `/company/[ticker]` 183 kB, `/company/[ticker]/charts` 243 kB, `/compare` 123 kB, `/watchlist` 116 kB, `/screener` 128 kB, `/data-sources` 110 kB.
- Ran browser performance audit against the rebuilt Docker stack:
  - Command: `npm --prefix frontend run audit:performance -- --ticker AAPL`
  - Result: passed and wrote `artifacts/performance/baselines/performance-baseline.md` plus `artifacts/performance/baselines/performance-baseline.json`.
  - The audit now completes every page scenario and every hot-route benchmark, including model evaluation, source registry, watchlist, and refresh queue routes.
- The audit exposed a strict-official-mode source-contract bug on `/api/model-evaluations/latest` before the final pass:
  - Failing route result: HTTP 500.
  - Cause: a synthetic fixture model-evaluation run exposed `ft_model_evaluation_fixture`, whose registry tier is `manual_override`, while `STRICT_OFFICIAL_MODE=true`.
  - Decision: targeted backend refactor. Suppress strict-mode-ineligible model-evaluation runs behind the existing nullable `run` contract instead of changing routes or payload shape.
- Inspected previous live/container audit artifacts:
  - `artifacts/performance/baselines/performance-baseline.md`
  - `artifacts/performance/baselines/current-stack-benchmark.json`
  - `reports/performance-audit-latest.md`

## Top 10 Performance Problems

| Rank | Problem | User Impact | Evidence | Decision | Files / Routes | Risk | Expected Win |
|---:|---|---|---|---|---|---|---|
| 1 | Company bootstrap can still assemble expensive cold/warm-miss payloads at request time | High on `/company/[ticker]` first load and ticker changes | Prior live/container artifacts show `workspace_bootstrap` warm p50 around 8.6s and payload around 1.5 MB before recent cache-key fixes; current code still composes financials, brief, and optional sections when hot cache misses | Partial rewrite later: persisted/materialized bootstrap aggregate by source fingerprint; not in this immediate pass because it is higher blast radius | `app/api/handlers/company_overview.py`, `/api/companies/{ticker}/workspace-bootstrap`, `frontend/hooks/use-company-workspace.ts` | Medium | Large: fewer DB reads, less serialization, faster cold/warm-miss company page |
| 2 | Charts route has inline recompute fallback when persisted snapshots are missing | High on `/company/[ticker]/charts` cold or legacy-snapshot paths | `_build_company_charts_response` calls `recompute_and_persist_company_charts_dashboard` in the request path when payload is missing | Partial rewrite later: move missing/legacy rebuild to refresh/prewarm path and return queued/building state | `app/api/handlers/_shared.py`, `app/services/company_charts_dashboard.py`, `/api/companies/{ticker}/charts` | Medium | Large tail-latency and CPU reduction on chart cold paths |
| 3 | Source registry/data-source route repeats refresh-state scans | Medium on `/data-sources`; grows with companies/datasets | `source_registry()` builds status, health, error payloads, and worker health through separate `DatasetRefreshState` queries; the dedicated handler also calls `app.main` compatibility functions | Targeted refactor now: load refresh-state rows once, derive status/errors/worker health from that snapshot, preserve response shape | `app/api/handlers/source_registry.py`, `app/api/handlers/_shared.py`, `/api/source-registry`, `/data-sources` | Low | Moderate: reduces DB query count and CPU for freshness route |
| 4 | Benchmark coverage does not directly pin all requested hot flows | Medium; regressions can land unseen | `scripts/benchmark_api_routes.py` lacks `workspace-bootstrap`, watchlist summary/calendar, and freshness/status split coverage despite user-requested flows | Targeted refactor now: expand harness route inventory and tests | `scripts/benchmark_api_routes.py`, `tests/test_api_route_benchmark_harness.py` | Low | Moderate: better regression detection; no runtime cost |
| 5 | Compare still computes missing model snapshots on request path | Medium/high on `/compare` cold caches | `_load_company_compare_preload` calls `ModelEngine.compute_models(..., force=False)` for fresh snapshots when not as-of | Partial rewrite later: move missing model computation to refresh/background and return persisted/unavailable states | `app/api/handlers/_shared.py`, `/api/companies/compare` | Medium | Moderate to large CPU and latency reduction on cold compare |
| 6 | Screener ranks and sorts full candidate universe in Python | Medium on `/screener` as coverage grows | `run_official_screener` loads latest candidate rows, attaches cross-sectional rankings, filters, sorts, then paginates | No immediate rewrite; keep for explainable ranking semantics. Add larger synthetic benchmark later before SQL prefilters | `app/services/screener.py`, `/api/screener/search` | Medium | Medium future win; premature SQL rewrite risks ranking drift |
| 7 | Oversized compatibility payloads still exist for full financials and overview variants | Medium on company tabs and API serialization | Prior artifacts show `/financials` around 1 MB full payload; current build keeps compact views but default full contract remains for compatibility | No breaking change now. Continue compact internal views and only version/shim any future payload narrowing | `app/api/handlers/_shared.py`, financials schemas, frontend company routes | Medium | Moderate when callers adopt compact variants |
| 8 | Frontend heavy company subroutes still have higher first-load JS | Medium on charts/models/ownership/financials | Current build: models 274 kB, ownership 270 kB, financials 265 kB, charts 243 kB first-load JS | Targeted future frontend splits; current default routes are acceptable and prior lazy-loading work already reduced risk | `frontend/app/company/[ticker]/*`, chart/grid components | Low/Medium | Medium for subroute TTI |
| 9 | SEC parsed JSON cache trades CPU for disk/memory | Low/medium on ingestion/cache-heavy systems | `PERF_REFACTOR_SUMMARY.md` notes cached `companyfacts` JSON payloads avoid reparsing but duplicate raw and parsed payload storage | No change now; keep CPU win and monitor cache size before adding thresholds | `app/services/sec_cache.py`, SEC ingestion services | Low | Prevents accidental regression rather than direct speedup |
| 10 | Docker normal profile can start heavier background work than small local hosts want | Medium on local startup/resource feel | `current-stack-benchmark.json` shows backend/data-fetcher memory and CPU peaks; README documents lite profile | No code rewrite; validate build stack and keep lite/small-host profiles documented | `docker-compose.yml`, `docker-compose.lite.yml`, `docker-compose.small-host.yml` | Low | Operational, not code-path speed |

## Recommendation

Choose targeted refactor, not a full rewrite.

The evidence does not justify replacing the project. The current system has clear architectural boundaries, persisted/cache-first data surfaces, hot response cache behavior, official-source provenance, and performance regression tooling. A full rewrite would create high risk to response contracts, route stability, provenance disclosures, strict official mode, and SEC-first trust rules without addressing the measured bottlenecks more directly.

The immediate implementation should address the lowest-risk confirmed issue:

1. Coalesce `/api/source-registry` refresh-state scans into a single reusable route snapshot.
2. Expand backend benchmark route coverage so the requested flows are measured by default.
3. Preserve every response shape and compatibility export.

The larger company-bootstrap and charts-backgrounding changes should be handled as a follow-up partial rewrite because they touch more contracts, cache invalidation rules, and frontend loading states.

## Step-By-Step Implementation Plan

1. Add an internal source-registry refresh-state snapshot helper that fetches all `DatasetRefreshState` columns needed for status, recent errors, and worker queue health in one query.
2. Update source status, error, and worker queue builders to accept preloaded rows while preserving their current public helper signatures.
3. Update the `/api/source-registry` handler to load the snapshot once and pass it through to source entries and health construction.
4. Mirror the optional preloaded-row path in the `app.main` compatibility helpers in `app/api/handlers/_shared.py`.
5. Add deterministic tests that prove source-registry health can build status, errors, and worker health from one refresh-state query after the latest-company-age query.
6. Expand `scripts/benchmark_api_routes.py` route cases to include workspace bootstrap, watchlist summary, watchlist calendar, and freshness/source-registry paths.
7. Update benchmark harness tests to lock the expanded coverage.
8. Run focused tests, then required backend/frontend validation.
9. Bring up the build Docker stack, run the browser performance audit when services and audit flags allow it, and manually check changed pages including a not-cached ticker path.

## Compatibility Safeguards

- No API response fields will be removed or renamed.
- No route URL will change.
- No unofficial fundamentals feed will be added.
- Strict official mode behavior is preserved and now explicitly suppresses model-evaluation payloads backed by manual override or commercial fallback sources.
- Provenance, source mix, freshness, and fallback disclosures remain in place.
- Routers remain thin; handler/service boundaries stay within the current architecture rules.

## Implementation Outcome

Implemented the targeted refactor, not a full rewrite:

1. `/api/source-registry` now loads `DatasetRefreshState` once and reuses the in-memory route snapshot to build source status, recent errors, worker queue health, and compatibility health payloads.
2. The `app.main` compatibility helpers accept the same optional preloaded rows, so the route no longer has to trigger duplicate refresh-state scans to preserve the old response shape.
3. `scripts/benchmark_api_routes.py` now covers the requested hot flows: company workspace bootstrap, charts, compare, watchlist summary, watchlist calendar, screener, source registry, and cache metrics. It also supports repeated query params correctly.
4. Docker build/local profiles now expose opt-in performance audit env vars with defaults still off: `PERFORMANCE_AUDIT_ENABLED`, `PERFORMANCE_AUDIT_MAX_RECORDS`, and `NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED`.
5. `frontend/scripts/run-performance-audit.mjs` now reads both legacy `sql_*` and current `db_*` audit field names, bounds route fetch waits, bounds page-idle/context/browser-close waits, and includes a `--self-test` mode for the audit summarizers.
6. Fixed a live metrics route regression found during validation: derived metrics handlers were passing the old `background_tasks` argument to `_refresh_for_financial_page`.
7. Fixed the strict-official-mode model-evaluation contract failure found by the final audit. `/api/model-evaluations/latest` now returns `run: null` with confidence flags when the latest run is backed by `manual_override` or `commercial_fallback` sources, preserving the existing response shape while avoiding fallback/manual provenance exposure.

## Post-Implementation Evidence

- Deterministic source-registry route test now proves the endpoint builds the refresh-state dependent payload with two executes in the fake session: one unified refresh-state load plus the latest-company-age query.
- Backend synthetic regression gate passed with zero regressions after the refactor.
- Final restored-stack API benchmark (`artifacts/performance/api-route-benchmark-current.json`) returned 200 for every covered route. Warm AAPL highlights from the final run:
  - `company_workspace_bootstrap`: p50 20.38 ms, p95 31.54 ms, payload 632,055 bytes.
  - `company_charts`: p50 17.43 ms, p95 24.58 ms, payload 313,767 bytes.
  - `derived_metrics`: p50 61.68 ms, p95 117.49 ms, payload 757,122 bytes.
  - `company_compare`: p50 196.12 ms, p95 207.98 ms, payload 843,087 bytes.
  - `source_registry`: p50 94.01 ms, p95 115.30 ms on the just-restarted Docker stack; a direct restored-stack curl immediately before the benchmark returned 200 in 95 ms.
- Direct browser checks against the rebuilt stack rendered these pages with HTTP 200 and no console errors: `/`, `/data-sources`, `/company/AAPL`, `/company/AAPL/charts`, `/compare?tickers=AAPL,MSFT`, `/watchlist`, `/screener`, `/company/RDDT`, and `/company/CRWV`.
- `CRWV` was absent from the local `companies` table before navigation; `/company/CRWV` still rendered the company brief shell without surfacing a UI error.
- The final full browser performance audit passed after the strict-mode model-evaluation fix:
  - Command: `npm --prefix frontend run audit:performance -- --ticker AAPL`
  - Result: completed all page scenarios and route benchmarks, writing fresh baseline artifacts.
  - Current frontend build highlights: `/` 117 kB first-load JS, `/company/[ticker]` 183 kB, `/company/[ticker]/charts` 243 kB, `/compare` 123 kB, `/watchlist` 116 kB, `/screener` 128 kB, `/data-sources` 110 kB.
- In strict official mode, a synthetic fixture model-evaluation run now returns HTTP 200 with `run: null`, empty provenance, and confidence flags `model_evaluation_suppressed_strict_official_mode`, `strict_official_mode`, and `synthetic_fixture_suppressed`.

## Validation Outcome

Passed:

- `python -m pytest` -> 1004 passed, 1 skipped.
- `python scripts/check_architecture_boundaries.py` -> passed.
- `python scripts/check_migration_safety.py` -> passed.
- `python -m ruff check app/main.py app/api/routers app/api/schemas app/services scripts/check_architecture_boundaries.py --select F401,F821,F822,F823,E9` -> passed.
- Focused Ruff for touched backend/scripts/tests -> passed.
- `npm --prefix frontend run test` -> 114 files passed, 526 tests passed.
- `npm --prefix frontend run lint` -> passed.
- `npm --prefix frontend run typecheck` -> passed.
- `npm --prefix frontend run build` -> passed.
- `npm --prefix frontend run audit:performance -- --self-test` -> passed.
- `npm --prefix frontend run audit:performance -- --ticker AAPL` -> passed.
- `docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d` -> passed; final restored stack is healthy with `performance_audit_enabled:false`.

## Remaining Work

The next high-impact performance work should be a partial rewrite of company bootstrap materialization and chart cold-path refresh behavior, behind existing public contracts. The current evidence still points to oversized compatibility payloads, repeated company bootstrap requests, and cold-path recomputation risk on company, charts, compare, and metrics flows, but the present change deliberately stayed on the lower-risk source/freshness, strict-mode compatibility, and observability path.
