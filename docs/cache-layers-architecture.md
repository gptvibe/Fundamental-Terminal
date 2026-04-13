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

## Developer Rules
- Do not add request-path live fetches to persisted research endpoints.
- Reuse the existing refresh queue and SSE flow instead of inventing parallel status plumbing.
- Keep backend and frontend contracts aligned whenever payload metadata changes.
- Add contract tests when a hot endpoint response shape changes.

## Operator Checks
- Inspect startup logs for `shared_hot_cache.backend` to confirm the active backend mode.
- Inspect runtime logs for `shared_hot_cache.local_fallback` when Redis operations fail and requests drop to process-local fallback.
- Inspect `/api/internal/cache-metrics` for `hot_cache_backend_mode` plus `hot_cache.backend_details.startup_reason`, `fallback_events_total`, and `cross_instance_reuse`.
- If the cache is in `local_memory_fallback`, verify `REDIS_URL`, Redis health, and network reachability from every app instance.

## Module Boundaries
- Routers under `app/api/routers/` stay registration-only and may depend on FastAPI, Starlette, and `app/api/schemas/` only.
- `app.main` remains the compatibility layer that binds handlers to routers and serializes service output into frontend-facing schemas.
- Orchestration belongs in `app/services/`, including policy-driven refresh coordination, dataset jobs, persistence, and SSE reporting helpers.
- Service modules must not import `app/api/` modules or frontend-facing schemas.
- Boundary violations are checked by `python scripts/check_architecture_boundaries.py` and `tests/test_architecture_boundaries.py`.
