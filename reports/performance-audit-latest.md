# Performance Audit - Latest

Date: 2026-05-14

## Executive Summary

Fundamental Terminal has already absorbed a meaningful first performance refactor: SEC cache widening, compare/watchlist batch preloads, a screener metric index, and chart/dashboard snapshots are present in the current tree. The remaining highest-confidence issues are not broad rewrite candidates; they are cache-key mismatches, request-path recomputation risks, oversized warm-read variants, and places where route-level benchmarks do not yet pin query counts.

Phase 1 implemented in this pass keeps API response contracts, route URLs, source disclosures, strict official mode behavior, demo behavior, and provenance rules unchanged. The fixes are:

- Compare `as_of` requests now batch-read only price rows visible at the requested date instead of loading full price histories and filtering them in Python.
- Workspace-bootstrap conditional cache keys now match the route's real price, section, and compact controls, including legacy flag expansion into concrete sections.
- Workspace-bootstrap section-based hot-cache tags now include the datasets actually loaded, so section-only brief payloads are invalidated with brief refreshes.
- Frontend read caching now reuses complete `workspace-bootstrap?include_overview_brief=true` payloads; placeholder/missing bootstrap guards remain active.

## Phase 1 Before/After Impact

- Compare `as_of` price history: before, the compare preload used one batch query but loaded all historical price rows for each requested ticker and filtered after the fact. After, the batch query keeps `trade_date <= as_of` in SQL and still executes as one query. The deterministic test proves bounded rows for two companies and one SQL execution.
- Workspace-bootstrap hot cache: before, middleware hot-cache lookup normalized section and price variants differently from the route, so repeated matching requests could miss hot payloads and execute the route again. After, middleware and route keys agree on legacy sections, explicit sections, compact mode, and price tokens.
- Workspace-bootstrap invalidation tags: before, section-only payloads were tagged from legacy include flags, so a brief-only request using `sections=` could miss the dataset tag it actually depended on. After, tags are derived from the sections that were actually loaded.
- Frontend workspace bootstrap cache reuse: before, complete overview bootstrap payloads always bypassed the frontend read cache. After, the read cache reuses complete bootstrap payloads; the test changes two identical calls from two network fetches to one.
- Runtime benchmark limitation: the local performance audit could not run because no backend/frontend audit services were listening on `127.0.0.1:8000` and `127.0.0.1:3000`. The exact failed command is recorded in the validation log.

## Top 10 Bottlenecks

1. Workspace-bootstrap frontend read-cache bypass
   - Affected: `frontend/lib/api/cachePolicy.ts`, `frontend/hooks/use-company-workspace.ts`, `/api/companies/{ticker}/workspace-bootstrap`
   - Why slow: complete company-page bootstrap payloads bypassed the shared frontend read cache whenever `include_overview_brief=true`, causing repeated network reads outside the short layout cache window.
   - Estimated impact: network latency and backend request count; repeated company-page navigations can drop from repeated fetches to one fresh-cache hit within the stable SEC TTL.
   - Risk: low.
   - Recommended fix: implemented. Keep placeholder/missing payload compatibility guards active.
   - Tests/benchmarks needed: `frontend/lib/api.cache.test.ts` verifies a complete overview bootstrap is fetched once and reused; existing placeholder tests verify missing payloads are still dropped.

2. Workspace-bootstrap hot-cache key mismatch for sections and price controls
   - Affected: `app/middleware/company_cache.py`, `app/api/handlers/company_overview.py`, `/api/companies/{ticker}/workspace-bootstrap`
   - Why slow: middleware looked for `sections=all` and default price controls while the route stores hot payloads under resolved sections and price tokens. Conditional GET often could not short-circuit the matching hot payload.
   - Estimated impact: latency and CPU; fewer unnecessary route executions on repeated bootstrap variants.
   - Risk: low.
   - Recommended fix: implemented. Middleware now mirrors route normalization for legacy flags, `sections`, `compact`, and price trimming.
   - Tests/benchmarks needed: `tests/test_company_cache_helpers.py` and `tests/test_conditional_get_routes.py` cover normalized hot keys.

3. Compare `as_of` price history over-read
   - Affected: `app/services/cache_queries.py`, `app/api/handlers/_shared.py`, `/api/companies/compare?tickers=...&as_of=...`
   - Why slow: compare preloading loaded full per-company price history batches before Python-side `as_of` filtering.
   - Estimated impact: DB rows, RAM, CPU, serialization prep; most visible for older companies with long daily price histories.
   - Risk: low.
   - Recommended fix: implemented. Add a batch SQL helper that filters `trade_date <= as_of.date()` in one query and use it from compare preloading.
   - Tests/benchmarks needed: `tests/test_query_optimization.py` confirms one query and date filtering; `tests/test_company_compare_route.py` confirms compare preload avoids unbounded price history for `as_of`.

4. Compare request-path model computation
   - Affected: `app/api/handlers/_shared.py::_load_company_compare_preload`, `_build_company_compare_item`, `/api/companies/compare`
   - Why slow: fresh snapshots can still call `ModelEngine.compute_models(..., force=False)` on the request path when model snapshots are missing.
   - Estimated impact: CPU and latency spikes, especially with five tickers and cold model caches.
   - Risk: medium, because cold-cache response content can change if request-time computation is removed.
   - Recommended fix: move missing model computation to refresh/background paths and return persisted model snapshots with explicit unavailable states when cold.
   - Tests/benchmarks needed: compare route cold-cache contract tests; query/timing benchmark with five tickers and no cached model runs.

5. Company charts still has inline rebuild fallback
   - Affected: `app/api/handlers/_shared.py::company_charts`, `app/services/company_charts_dashboard.py`
   - Why slow: persisted chart snapshots exist, but missing or legacy snapshots can still trigger inline dashboard recomputation.
   - Estimated impact: CPU and latency on `/company/[ticker]/charts`, plus extra DB reads for statements, earnings, restatements, and events.
   - Risk: medium; tests currently assert inline rebuild behavior for some missing/legacy cases.
   - Recommended fix: make first-request fallback return queued/building snapshot unless explicitly operating in a maintenance/prewarm mode.
   - Tests/benchmarks needed: chart route contract tests for missing, legacy, and what-if modes; performance audit route timing.

6. Company bootstrap aggregate is still assembled at request time
   - Affected: `app/api/handlers/company_overview.py`, `app/services/company_research_brief.py`, financials and brief helper calls.
   - Why slow: even with hot cache, cold/warm-miss bootstrap stitches financials, price history, brief, and optional sections each time.
   - Estimated impact: latency, DB queries, payload construction CPU.
   - Risk: medium.
   - Recommended fix: add a compact persisted bootstrap aggregate keyed by ticker, `as_of`, view, price token, sections, compact, and source fingerprint.
   - Tests/benchmarks needed: route-level query-count benchmark for bootstrap; invalidation tests for financials, prices, brief, insider, institutional, and earnings tags.

7. Screener still ranks and filters the full candidate universe in Python
   - Affected: `app/services/screener.py::run_official_screener`
   - Why slow: latest candidate rows are batch-read, but ranking/filtering/sorting are in memory for the full candidate set before pagination.
   - Estimated impact: CPU and RAM as coverage grows.
   - Risk: medium; ranking semantics are cross-sectional and must remain deterministic.
   - Recommended fix: keep current behavior for explainable rankings, but add a route-level timing/query benchmark and consider SQL prefilters only for simple numeric filters.
   - Tests/benchmarks needed: screener route benchmark with large synthetic candidate count; ranking snapshot tests.

8. Data Sources health performs repeated full refresh-state scans
   - Affected: `app/api/handlers/source_registry.py`, `/api/source-registry`, `/data-sources`
   - Why slow: status, health, errors, and SLOs separately scan or derive from `DatasetRefreshState`.
   - Estimated impact: DB queries and CPU for installations with many cached companies/datasets.
   - Risk: low to medium.
   - Recommended fix: build a single service-level source-registry snapshot from one refresh-state row set and reuse it across status/health/error derivation.
   - Tests/benchmarks needed: source registry route query-count test; provenance contract tests.

9. SEC cached JSON still doubles disk memory for very large payloads
   - Affected: `app/services/sec_cache.py`, SEC companyfacts, submissions history, filing index, frames.
   - Why slow/heavy: cache files store both `content_b64` and parsed `json_payload` for selected JSON endpoints. This avoids reparsing but increases disk footprint and read memory.
   - Estimated impact: disk and RAM; positive CPU tradeoff on hot reads.
   - Risk: low if left as-is, higher if changed.
   - Recommended fix: keep current policy for large parse-heavy endpoints, but monitor cache disk usage and consider per-endpoint thresholds before storing parsed JSON.
   - Tests/benchmarks needed: SEC cache parse benchmark by payload size; disk usage monitor threshold tests.

10. Docker normal profile starts background refresh and macro work by default
   - Affected: `docker-compose.yml`, `docker/backend/start-worker.sh`
   - Why heavy: normal profile runs data-fetcher queue consumer and macro refresh; default worker identifiers can create startup and hourly CPU/network spikes.
   - Estimated impact: CPU, memory, upstream requests, DB pool pressure.
   - Risk: low for documentation/config, medium for changing defaults.
   - Recommended fix: keep normal profile behavior documented; use `docker-compose.lite.yml` or `docker-compose.small-host.yml` for low-resource hosts. Consider a documented `APP_PROFILE=lite` default for local evaluation only.
   - Tests/benchmarks needed: container startup memory sample and worker queue smoke checks.

## Do Not Fix

- Do not remove fallback disclosures or strict official mode suppression to simplify payloads.
- Do not replace SEC-derived fundamentals with unofficial vendor fundamentals feeds for speed.
- Do not move routers into service orchestration or let services import `app/api`.
- Do not drop chart, compare, or brief fields to shrink payloads unless the contract is explicitly versioned or the field is already optional and unused.
- Do not add size-based SEC cache eviction that deletes immutable accession-known archive artifacts.
- Do not remove cross-sectional screener ranking context just to push all ranking into SQL.

## Implementation Plan

Phase 1, completed in this pass:
- Batch compare `as_of` price history reads in SQL.
- Align workspace-bootstrap hot cache keys and cache tags with actual loaded sections and price variants.
- Re-enable frontend read-cache reuse for complete overview bootstrap payloads while preserving missing-placeholder rejection.
- Add deterministic tests for cache keys, frontend cache reuse, and batch as-of price query count.

Phase 2, safe follow-up:
- Add route-level query-count/timing benchmarks for workspace-bootstrap, compare, watchlist summary/calendar, and screener.
- Add a compact persisted company bootstrap aggregate keyed by source fingerprint and request controls.
- Refactor source-registry health to derive status/health/error/SLO payloads from one refresh-state scan.

Phase 3, higher-risk follow-up:
- Remove compare request-path model computation after defining cold-cache unavailable-state behavior.
- Convert chart missing/legacy inline rebuilds into queued/background rebuilds except for explicit maintenance paths.
- Evaluate parser-version persistence for parsed filing artifacts with migration-safe invalidation.

## Validation Log

Targeted backend and frontend checks:
- `python -m pytest tests/test_query_optimization.py -q` -> 16 passed, 1 existing unknown-mark warning.
- `python -m pytest tests/test_company_cache_helpers.py tests/test_conditional_get_routes.py -q` -> 36 passed.
- `python -m pytest tests/test_company_compare_route.py -q` -> 6 passed in 271.45s.
- `npm --prefix frontend run test -- lib/api/cachePolicy.test.ts lib/api.cache.test.ts` -> 55 passed.

Requested backend validation:
- `python -m ruff check app/main.py app/api/routers app/api/schemas app/services scripts/check_architecture_boundaries.py --select F401,F821,F822,F823,E9` -> passed.
- `python scripts/check_architecture_boundaries.py` -> passed.
- `python scripts/check_migration_safety.py` -> passed.
- `python -m alembic heads` -> `20260512_0050 (head)`.
- `python -m pytest` -> timed out after 1,204,043 ms with no returned test summary.

Requested frontend validation:
- `npm --prefix frontend run typecheck` -> passed.
- `npm --prefix frontend run test` -> 114 test files passed, 526 tests passed. Existing harness noise: Vite CJS API deprecation warning and jsdom `Not implemented: navigation to another Document`.
- `npm --prefix frontend run lint` -> passed with no ESLint warnings or errors.
- `npm --prefix frontend run build` -> passed. Noted Next.js warning: using edge runtime disables static generation for that page.

Requested performance validation:
- `$env:PERFORMANCE_AUDIT_ENABLED='true'; $env:NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED='true'; npm --prefix frontend run audit:performance -- --ticker AAPL` -> failed immediately with `TypeError: fetch failed`.
- Environment check after the failure: `127.0.0.1:8000` and `127.0.0.1:3000` were not accepting TCP connections, so the backend/frontend audit prerequisites were not running.

Initial command issues:
- `python -m pytest tests/test_query_optimization.py tests/test_company_compare_route.py tests/test_company_cache_helpers.py tests/test_conditional_get_routes.py -q` timed out at 124 seconds before output; rerun in smaller slices passed.
- `npm --prefix frontend run test -- frontend/lib/api/cachePolicy.test.ts frontend/lib/api.cache.test.ts --runInBand` failed because Vitest does not support `--runInBand`; rerun with native Vitest file arguments passed.
