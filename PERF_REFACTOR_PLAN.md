# Performance Refactor Plan

## Current Bottlenecks

- SEC payload handling still reparses some large cached JSON responses, especially `companyfacts`, because only selected endpoints attach a cached JSON payload to the `httpx.Response`.
- `EdgarClient.build_filing_index()` rebuilds the same filing index and may refetch historical submissions pages whenever the same CIK is requested in separate flows.
- SEC archive documents and non-XML filing documents are not consistently treated as immutable cache entries once an accession is known.
- SEC frames pulls bypass the shared SEC HTTP cache/singleflight path, so concurrent screener frame refreshes can duplicate upstream calls.
- Compare builds each ticker mostly one at a time, causing repeated financial, price, metrics, model, and cache-state queries.
- Watchlist calendar loads financials and filing events per ticker even though the route already has the full ticker batch.
- Screener already reads from `derived_metric_points`, but latest-period selection and common filter/sort paths need a better composite index.
- Request paths still contain some fallback recomputation paths for charts/models/metrics; warm snapshots should be preferred whenever available and refresh work should stay in the background.

## Files To Change

- `app/services/sec_cache.py`: normalize SEC cache key metadata, cache parsed `companyfacts`, add submissions-history, archive document, and frames policies.
- `app/services/sec/refresh_orchestrator.py`: cache/reuse filing-index builds and align SEC request logging with cache/source outcomes.
- `app/services/sec/frames.py`: route frame pulls through SEC cache plus singleflight.
- `app/services/cache_queries.py`: add batch helpers for compare/watchlist price history, price states, regulated financials, and derived metrics.
- `app/api/handlers/_shared.py`: use batch preloads for compare and watchlist calendar while preserving response shapes.
- `app/services/screener.py`: add lightweight timing around candidate load/filter/sort.
- `alembic/versions/*` and `app/models/derived_metric_point.py`: add safe composite indexes for common screener queries.
- Relevant tests under `tests/`: cache policy, singleflight/cache behavior, compare/watchlist batching, and screener index/query compatibility.

## Expected Performance Wins

- Warm SEC reads avoid repeated JSON parsing for `companyfacts` and filing index payloads.
- Concurrent identical SEC pulls coalesce across more endpoint types, including frames and immutable archive documents.
- Historical filing documents/indexes are cached indefinitely instead of refreshed blindly.
- Compare and watchlist calendar should reduce DB query count from roughly per-ticker fan-out to a small fixed set of batch queries.
- Screener latest-period scans get an index that matches `period_type -> company_id -> period_end DESC` access.
- User-facing requests should return cached/stale-labeled data faster while refresh jobs handle expensive upstream and recompute work.

## Risks And Compatibility Safeguards

- API response shapes must remain unchanged; any new cache metadata stays internal or additive diagnostics only.
- Strict official mode remains unchanged: price-backed payloads stay suppressed where existing code suppresses them.
- SEC cache TTLs keep the official-source-first model: submissions and companyfacts remain expiring, accession-known archive artifacts are immutable, and frames remain TTL-bound.
- Batch loaders must preserve ordering by requested ticker and per-company row order.
- Existing monkeypatch-heavy tests depend on `app.main` compatibility names, so new preloads are guarded and route builders keep existing helper fallbacks.
- New indexes are additive and created only if missing.

## Tests And Benchmarks To Run

- Baseline relevant backend slice already run: SEC cache/shared upstream/fetch dedupe/hot cache/derived metrics/screener/bootstrap.
- Add focused tests for `companyfacts` cached JSON payloads, immutable SEC archive policy, frames singleflight/cache usage, compare batch preloading, and watchlist calendar batch preloading.
- Run `python -m pytest`.
- Run `python scripts/check_architecture_boundaries.py`.
- Run frontend validation: `npm --prefix frontend run test`, `npm --prefix frontend run lint`, and `npm --prefix frontend run build`.
- If environment limits prevent full runs, record the exact failure in `PERF_REFACTOR_SUMMARY.md`.
