# Cache Layers Architecture

## Goal
Fundamental Terminal is intentionally cache-first. Company research routes should return quickly from persisted or warm caches and queue refresh work in the background instead of blocking on live SEC fetches.

## Layers
1. Process hot-response cache

- Used for hot read endpoints such as search, financials, models, peers, and metrics-timeseries.
- Optimized for repeated identical reads inside a single backend process.
- Supports stale-while-revalidate semantics so callers receive a response even when a refresh has been queued.

2. Redis short-term cache

- Used for short-lived shared cache entries and coordination where cross-process reuse matters.
- Reduces duplicate work when multiple requests converge on the same data close together.
- If Redis is unavailable, the hot-response cache falls back to local in-process memory.
- This fallback preserves availability, but cross-instance cache reuse and shared singleflight coordination become weaker because each backend process keeps its own hot cache.
- Operators should treat `local_memory_fallback` as an availability-preserving degraded mode rather than an equivalent Redis-backed deployment.

3. PostgreSQL persisted research tables

- Source of truth for product-facing company workspaces.
- Routes backed by persisted SEC-derived tables stay cache-first and should not perform live upstream fetches on the request path.

4. Refresh-state persistence

- `dataset_refresh_state` stores freshness and active refresh metadata per company/dataset.
- Prevents duplicate refresh storms and lets the app answer stale/missing requests with cached payloads while one refresh job is already in flight.

5. SSE status stream

- `/api/jobs/{job_id}/events` exposes the background refresh and model-compute lifecycle to the frontend.
- Job events now carry `job_id`, `trace_id`, `ticker`, and `kind` so logs, refresh orchestration, model runs, and UI status rows can be correlated.

## Request Path Policy
- Persisted company research endpoints are cache-first.
- If data is present and fresh, return it immediately.
- If data is stale or missing, return the cached or partial payload immediately and queue background refresh work.
- Direct live-fetch utility routes remain separate for explicit SEC exploration flows.

## Batch Preload Pattern
- Compare and watchlist calendar routes normalize the ticker batch, load company snapshots once, then preload route-specific supporting data into a request-local `ContextVar`.
- `/api/companies/compare` preloads financial statements, price cache state, price history, derived metric points, derived metric freshness, and latest model runs for the requested companies.
- `/api/watchlist/calendar` preloads visible financial statements and filing events for the full watchlist request.
- Item builders still keep the older per-company query path as a fallback. This is intentional: preload failures should degrade to a slower response instead of failing the endpoint, and monkeypatch-heavy legacy tests can still exercise builders with lightweight sessions.
- Preload failures are logged. Treat those logs as performance warnings, because response schemas and fallback behavior are intentionally unchanged.

## SEC Cache Visibility
- `SecHttpCache.prune_expired()` only removes expired or corrupted expiring entries. Accession-known SEC archive artifacts marked `immutable=true` are intentionally retained because they are official historical artifacts.
- Use `get_sec_cache_disk_usage()` or `log_sec_cache_disk_usage()` from `app.services.sec_cache` to inspect cache file count, total bytes, immutable bytes, expiring bytes, stale bytes, and unreadable files without deleting anything.
- Disk-size controls should prefer monitoring and alerting first. Do not add size-based eviction that can delete immutable SEC archive artifacts unless the retention policy is explicitly changed and documented.

## Manual Regression Checks
- Compare maximum batch: request `/api/companies/compare?tickers=AAPL,MSFT,GOOG,AMZN,META` and confirm all five companies return financials, metrics, model payloads, provenance, and unchanged fallback disclosures.
- Compare missing ticker: request `/api/companies/compare?tickers=AAPL,UNKNOWN` and confirm the unknown ticker returns the existing `company_missing`/missing refresh shape without affecting AAPL.
- Full watchlist calendar: request `/api/watchlist/calendar` with 50 `tickers` query parameters and confirm expected filing projections, SEC events, and 13F deadline events are sorted and not duplicated.
- Cold SEC cache: move or empty `data/sec_cache/` in a local environment, trigger a company refresh or SEC frames screener request, then confirm SEC responses repopulate cache files with structured metadata.
- SEC 429 retry: in a mocked or staging client, return repeated 429 responses for a frames URL and confirm the client waits according to `Retry-After`, retries up to the configured attempts, and returns no frame instead of failing the route.
- Migration: run `alembic upgrade head`, then `python scripts/check_migration_safety.py`, and verify the screener derived-metric index exists.

## Developer Rules
- Do not add request-path live fetches to persisted research endpoints.
- Reuse the existing refresh queue and SSE flow instead of inventing parallel status plumbing.
- Keep backend and frontend contracts aligned whenever payload metadata changes.
- Add contract tests when a hot endpoint response shape changes.

## Operator Checks
- Inspect startup logs for `shared_hot_cache.backend` to confirm the active backend mode.
- Inspect runtime logs for `shared_hot_cache.local_fallback` when Redis operations fail and requests drop to process-local fallback.
- Inspect `/api/internal/cache-metrics` for `hot_cache_backend`, `hot_cache_backend_mode`, `hot_cache_status`, `hot_cache_operator_summary`, plus `hot_cache.backend_details.startup_reason`, `fallback_events_total`, and `cross_instance_reuse`.
- Periodically call `log_sec_cache_disk_usage()` from an operational shell or scheduled health task to capture SEC disk-cache growth, especially immutable archive artifact growth.
- If the cache is in `local_memory_fallback`, verify `REDIS_URL`, Redis health, and network reachability from every app instance.

Sample metrics signal:

```json
{
  "hot_cache_backend": "local",
  "hot_cache_backend_mode": "local_memory_fallback",
  "hot_cache_status": "fallback",
  "hot_cache_scope": "process-local",
  "hot_cache_cross_instance_reuse": "disabled",
  "hot_cache_operator_summary": "Redis was configured, but the app is currently using process-local hot-cache fallback."
}
```

Sample logs:

```json
{"event":"shared_hot_cache.backend","backend":"local","backend_mode":"local_memory_fallback","status":"fallback","summary":"Redis was configured, but the app is currently using process-local hot-cache fallback.","operational_impact":"Cross-instance cache reuse and shared singleflight coordination are weaker because each backend process keeps its own hot cache.","startup_reason":"redis_connect_failed"}
{"event":"shared_hot_cache.local_fallback","backend":"redis","backend_mode":"redis_with_local_fallbacks","status":"degraded","operation":"read","summary":"Redis is configured as the shared hot-cache backend, but one or more operations fell back to process-local memory.","operational_impact":"Cross-instance cache reuse and shared singleflight coordination may be partial until Redis recovers.","fallback_reason":"redis_read_failed"}
```

## Module Boundaries
- Routers under `app/api/routers/` stay registration-only and may depend on FastAPI, Starlette, and `app/api/schemas/` only.
- `app.main` remains the compatibility layer that binds handlers to routers and serializes service output into frontend-facing schemas.
- Orchestration belongs in `app/services/`, including policy-driven refresh coordination, dataset jobs, persistence, and SSE reporting helpers.
- Service modules must not import `app/api/` modules or frontend-facing schemas.
- Boundary violations are checked by `python scripts/check_architecture_boundaries.py` and `tests/test_architecture_boundaries.py`.
