# Unpushed Performance Refactor Follow-up Fixes

**Date**: 2026-05-12

## Audit Verification

- Confirmed already fixed: SEC frames 429 handling now retries three attempts and returns no frame after repeated rate limiting.
- Confirmed already fixed: `get_company_derived_metric_points_by_company_ids()` ranks distinct periods with SQL `row_number()` and applies `max_periods` in SQL.
- Confirmed already fixed: `COMPARE_REQUESTED_MODELS` is centralized for compare responses.
- Confirmed still valid: compare and watchlist calendar preload dictionaries were loosely typed.
- Confirmed still valid: `DatasetRefreshState` fallback/backfill logic was repeated in batch cache-query helpers.
- Confirmed still valid as maintainability concern: `_shared.py` keeps compatibility route decorators while active route registration lives in `app/api/routers/`.
- Confirmed still valid: SEC immutable cache entries should not be evicted casually; disk-size visibility is the safer follow-up.

## Changes Made

- Added `TypedDict` preload structures for company compare and watchlist calendar internals.
- Kept compare/watchlist response schemas and route URLs unchanged.
- Extracted simple cache-query helpers for loading `DatasetRefreshState` rows and backfilling last-checked timestamps from data tables.
- Added comments clarifying that `_shared.py` route decorators are legacy identity decorators and split handlers are the active router path.
- Added SEC cache disk-usage reporting via `SecHttpCache.disk_usage()`, `get_sec_cache_disk_usage()`, and `log_sec_cache_disk_usage()`.
- Added regression tests for compare max ticker preload usage, unknown compare tickers, preload failure fallback, full watchlist calendar preload usage, and SEC cache disk visibility.
- Updated `docs/cache-layers-architecture.md` with preload behavior, fallback rationale, SEC cache visibility, and manual regression steps.

## Intentionally Not Changed

- Did not change public API response schemas or route URLs.
- Did not remove compatibility handlers or broad-split `_shared.py`; comments were added instead because removal would be riskier.
- Did not change official-source-first behavior, Yahoo fallback behavior, or `STRICT_OFFICIAL_MODE`.
- Did not add size-based SEC cache eviction, because immutable SEC archive artifacts are intentionally retained.
- Did not move model computation out of compare read paths; that behavior pre-existed this follow-up and is safer as a separate design change.

## Checks Run

- `python -m pytest tests/test_company_compare_route.py` - passed, 5 tests.
- `python -m pytest tests/test_sec_expansion_routes.py -k "watchlist_calendar"` - passed, 4 selected tests.
- `python -m pytest tests/test_sec_cache.py -k "disk_usage or immutable or companyfacts"` - passed, 3 selected tests.
- `python -m ruff check app/main.py app/api/routers app/api/schemas app/services scripts/check_architecture_boundaries.py --select F401,F821,F822,F823,E9` - passed.
- `python scripts/check_architecture_boundaries.py` - passed.
- `python -m pytest tests/test_company_compare_route.py tests/test_query_optimization.py tests/test_sec_cache.py tests/test_sec_expansion_routes.py tests/test_sec_frames_screener.py` - passed, 90 tests, 5 warnings.

## Remaining Risks

- Preload failures intentionally fall back to per-company queries, so regressions may appear as latency/log warnings rather than hard failures.
- Compare can still compute stale/missing model runs during a read path; this remains documented as pre-existing behavior.
- SEC cache disk usage now has visibility, but production alert thresholds still need an operational decision.
- Full manual SEC 429 and cold-cache exercises still need an environment that can safely mock or stage upstream SEC behavior.

## Manual Testing Still Needed

- Request `/api/companies/compare?tickers=AAPL,MSFT,GOOG,AMZN,META`.
- Request `/api/companies/compare?tickers=AAPL,UNKNOWN`.
- Request `/api/watchlist/calendar` with 50 tickers.
- Exercise a cold `data/sec_cache/` and confirm structured metadata is recreated.
- Simulate repeated SEC frames 429 responses.
- Run `alembic upgrade head` and `python scripts/check_migration_safety.py` in an environment with valid database credentials.
