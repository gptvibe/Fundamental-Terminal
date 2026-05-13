# Unpushed Changes Audit

**Date**: 2026-05-12  
**Scope**: All staged and unstaged changes against HEAD on `main`  
**Files changed**: 15 tracked files (+1116 / -134 lines) + untracked planning/migration/report files  
**Commit message**: `performance improvement`

---

## Follow-up Review and Fixes

This follow-up review checked the audit against the current working tree instead of accepting the report at face value. The original report is broadly directionally correct, but several risks were overstated or already covered by the current architecture.

### Valid Points

- **SEC frames 429 handling was a real regression risk.** `app/services/sec/frames.py` retried a 429 only once before `raise_for_status()`, which could turn SEC rate limiting into a route failure.
- **Derived metric batch loading had a real efficiency issue.** `get_company_derived_metric_points_by_company_ids()` discovered all periods for each company and truncated in Python before fetching rows.
- **The repeated compare model list was worth cleaning up.** The same `dcf/piotroski/altman_z` list appeared in multiple compare code paths.
- **The preload and cache/index improvements generally make sense.** Compare/watchlist preloads preserve fallbacks, the screener index is additive, and the SEC cache expansion stays within official-source data.

### Not Valid or Deferred

- **Filing index cache key claim was not valid as written.** The cache key fingerprints `recent.get("accessionNumber")`, which is the SEC columnar accession list when present, not just a single accession number.
- **Duplicate active route shadowing was overstated.** `_shared.py` uses `_LegacyRouteDecorators` identity decorators for compatibility export; the live FastAPI app registers split routers from `app/api/routers/`. The split handlers delegate back to shared builders, so this is a maintenance concern, not an active import-order route shadowing bug.
- **Cache pruning is not missing.** `SecHttpCache.prune_expired()` and `prune_sec_cache_periodic()` exist. Immutable SEC archive artifacts intentionally do not expire, so disk-size monitoring remains a follow-up concern rather than a correctness bug.
- **Model-run dict/list shape was not changed.** `get_company_models_by_company_ids()` intentionally returns latest runs keyed by model name, and the compare consumer converts the dict values before serialization. This remains slightly fragile but is covered by the new preload test and was not worth changing in this pass.
- **TypedDicts and broader route/module cleanup were deferred.** They are useful maintainability work, but not necessary for the verified bugs and would broaden the change.

### Changes Made

- Updated `app/services/sec/frames.py` to allow three 429 attempts, parse invalid `Retry-After` defensively, and return `None` after repeated rate limiting instead of raising an HTTP 429 through the caller.
- Updated `app/services/cache_queries.py` so `get_company_derived_metric_points_by_company_ids()` ranks distinct periods per company in SQL with `row_number()` and applies `max_periods` in the database query.
- Removed the multi-column tuple `IN` query from that derived-metric batch path as a side effect of the SQL ranking change.
- Added `COMPARE_REQUESTED_MODELS` in `app/api/handlers/_shared.py` and used it in compare response/model paths.
- Added SEC frames tests for successful retry and exhausted 429 behavior.

### Why The Changes Are Safe

- No public response schema, route URL, source contract, or frontend behavior changed.
- The SEC frames change only affects repeated rate-limit failures and preserves 404-as-missing behavior.
- The derived-metric query returns the same grouped rows for the latest periods but avoids transferring unneeded period candidates to Python.
- The compare model constant preserves the exact existing model set.
- Strict official mode behavior and Yahoo fallback suppression paths were left unchanged.

### Checks Run

- `python -m ruff check app/main.py app/api/routers app/api/schemas app/services scripts/check_architecture_boundaries.py --select F401,F821,F822,F823,E9` — passed.
- `python scripts/check_architecture_boundaries.py` — passed.
- `python -m pytest tests/test_company_compare_route.py tests/test_query_optimization.py tests/test_sec_cache.py tests/test_sec_expansion_routes.py tests/test_sec_frames_screener.py` — 85 passed, 5 pre-existing warnings.

### Manual Testing Still Needed

- Compare 5 tickers through `/api/companies/compare` and confirm financials, metrics, and models still appear.
- Test `/api/watchlist/calendar` with a full watchlist and verify expected filing projections plus SEC events.
- Run `alembic upgrade head` in an environment with database credentials to apply the new index migration.
- Exercise a cold SEC cache and, if feasible, simulate repeated SEC 429 responses against frames.

### Remaining Risks

- Model computation can still happen during compare reads when cached model runs are stale; this behavior pre-existed the preload refactor.
- Preload failures intentionally log and fall back to per-company queries, so performance regressions may require log/performance monitoring to detect.
- `_shared.py` remains very large and should still be split in a separate architecture-focused pass.
- Immutable SEC cache entries can grow over time; pruning exists for expiring entries, but production disk usage should be monitored.

---

## 1. Summary

### What Changed Overall

This is a **performance optimization batch** targeting three distinct areas:

1. **SEC upstream caching overhaul** — Expanded HTTP cache policy coverage to include frames, companyfacts, filing documents, and submissions history. Added immutable markers for accession-known artifacts. Routed SEC XBRL frames through the shared SEC disk cache + singleflight dedupe. Cached parsed filing-index output from submissions fingerprints.

2. **Route-level batch preloading** — Added batch DB query helpers (`_by_company_ids` variants) for financials, price history, price cache status, derived metrics, derived metrics last-checked, and regulated bank financials. Introduced `ContextVar`-based preload dicts for `/api/companies/compare` and `/api/watchlist/calendar` so repeated per-ticker queries are replaced by a single batch fetch before per-ticker item construction.

3. **Screener diagnostics + index** — Added a composite DB index (`ix_derived_metric_points_period_type_company_period`) aligned with the screener's `period_type → company_id → period_end` access pattern. Added lightweight `perf_counter` timing logs for screener candidate load, ranking, and filter/sort phases.

4. **Tests** — 5 test files expanded to cover cache policy metadata, companyfacts JSON payload caching, frames singleflight/cache dedupe, batch query helpers, and compare/watchlist preload correctness.

### Which Parts of the App Are Affected

| Layer | Files | Impact |
|-------|-------|--------|
| API handlers | `_shared.py`, `financials.py`, `workspace.py` | Compare and watchlist-calendar routes refactored with preload pattern; financials route refactored to delegate to shared builder |
| Models | `derived_metric_point.py` | New composite index added |
| Services | `cache_queries.py`, `screener.py`, `sec_cache.py`, `sec/frames.py`, `sec/refresh_orchestrator.py` | New batch query functions, cache policy expansion, frames cache integration, filing-index caching, screener timing |
| Service init | `services/__init__.py` | Re-export new batch helpers |
| DB migration | `alembic/versions/20260512_0050_*.py` | Additive index (untracked) |
| Documentation | `PERF_REFACTOR_PLAN.md`, `PERF_REFACTOR_SUMMARY.md` | Project planning artifacts (untracked) |
| Tests | 5 test files | New tests for batch queries, preload, cache, frames |

### Overall Assessment

The changes are **mostly well-structured for a performance refactor**. The preload pattern is clean: batch-fetch once, store in a `ContextVar`, consume per-item with fallback to the old per-company path. API contracts are preserved. The cache expansion and singleflight integration look solid.

However, there were **several medium-severity issues** identified in the original audit. The follow-up section above documents which were fixed, which were overstated, and which remain as future maintainability work.

---

## 2. File-by-File Review

### 2.1 `app/api/handlers/_shared.py` (+332 / -about 20 lines)

**What the file does**: Central route handler module containing most of the API endpoint implementations and their helper functions.

**What changed**:
- Added 2 new `ContextVar` globals: `_watchlist_calendar_preload_ctx` and `_company_compare_preload_ctx`
- Added `_visible_financials_by_company_ids()` — batch version of `_visible_financials_for_company()` that queries both SEC and regulated bank financials for multiple companies at once
- Added `_load_company_compare_preload()` — builds a preload dict with financials, prices, derived metrics, and model runs for all tickers in a compare request
- Extracted `_build_company_compare_response()` from the `company_compare` route — same logic, now with preload support
- Changed `company_compare` endpoint to delegate to `_build_company_compare_response()`
- Added `_load_watchlist_calendar_preload()` — batch preload for watchlist calendar (financials + filing events)
- Refactored `watchlist_calendar` endpoint to use preload pattern
- Refactored `_build_watchlist_calendar_company_events()` to consume preloaded financials/filing events
- Extracted `_project_watchlist_expected_filing_from_financials()` — split the financials-to-event logic from the DB-fetch logic
- Refactored `_build_company_compare_item()` to consume preloaded financials, prices, metrics, and model runs with per-field fallback
- **New imports**: `get_company_derived_metric_points_by_company_ids`, `get_company_derived_metrics_last_checked_by_company_ids`, `get_company_regulated_bank_financials_by_company_ids`, `get_company_price_cache_status_by_company_ids`, `get_company_price_history_by_company_ids`

**Assessment**: The core idea is sound and the fallback pattern is well-implemented. However:
- **Problem**: The model runs preload uses `model_runs = list(model_runs_by_company_id.get(company_id, {}).values())`. This means the preload stores `model_runs_by_company_id[company_id]` as a dict keyed by model_name, but `get_company_models()` returns a list. These are different structures and the test confirms the dict approach. This **works only because downstream code iterates the list**. If downstream accesses list-specific methods, it won't fail, but the data shape differs between preloaded and non-preloaded paths. This is fragile.
- **Problem**: `_load_company_compare_preload` calls `ModelEngine(session).compute_models()` inside the preload, which can trigger DB writes (`session.commit()` if models were recomputed). This mixes read-path preloading with write-path model computation. If the preload fails partway, some models may have been computed and committed while others haven't — and the exception is swallowed.
- `_visible_financials_by_company_ids` is shared between compare and calendar preloads but only the compare path passes a limit argument through the preload function signature. The calendar path hardcodes `limit=24`. Both are reasonable but the asymmetry is easy to miss.

### 2.2 `app/api/handlers/financials.py` (+22 / -12 lines)

**What the file does**: Appears to be a parallel/forked route handler for financial endpoints.

**What changed**: The `company_compare` function body was replaced with a delegation to `_build_company_compare_response()`, identical to the change in `_shared.py`.

**Assessment**: This is correct and eliminates code duplication. However, the fact that `_shared.py` and `financials.py` both define the same `/api/companies/compare` route is concerning — having two files register the same route means one shadows the other depending on import order. This is a pre-existing issue, not introduced here.

### 2.3 `app/api/handlers/workspace.py` (+37 / -23 lines)

**What the file does**: Route handler for workspace/watchlist endpoints.

**What changed**: `watchlist_calendar` endpoint refactored identically to `_shared.py` — added preload with try/except, `ContextVar.set()`/`reset()` wrapping, and `_load_watchlist_calendar_preload()` call.

**Assessment**: Same concern as above — if both `workspace.py` and `_shared.py` register `watchlist_calendar`, one shadows the other. This change correctly mirrors the `_shared.py` version. The deduplication refactoring is correct.

### 2.4 `app/models/derived_metric_point.py` (+7 lines)

**What the file does**: SQLAlchemy model for derived metric data points.

**What changed**: Added a new composite index `ix_derived_metric_points_period_type_company_period` on `(period_type, company_id, period_end, metric_key)`.

**Assessment**: **Good change**. The screener's `_load_official_screener_candidates` function filters and groups by `period_type` first, then `company_id`, then orders by `period_end DESC`. This index covers that access pattern precisely. No downside beyond the standard write-amplification cost, which is acceptable for a read-heavy analytics table.

### 2.5 `app/services/__init__.py` (+10 lines)

**What the file does**: Service layer re-exports.

**What changed**: Added imports and `__all__` entries for 6 new batch query functions: `get_company_derived_metric_points_by_company_ids`, `get_company_derived_metrics_last_checked_by_company_ids`, `get_company_regulated_bank_financials_by_company_ids`, `get_company_price_cache_status_by_company_ids`, `get_company_price_history_by_company_ids`, and `get_company_models_by_company_ids`.

**Assessment**: Clean, correct re-exports. **Minor**: `get_company_models_by_company_ids` is added to `__all__` but wasn't in the import block shown in the diff. It may already have been there before this change.

### 2.6 `app/services/cache_queries.py` (+176 lines)

**What the file does**: Database query functions for cached company data.

**What changed**:
- Added `get_company_regulated_bank_financials_by_company_ids()` — batch version using `_load_rows_by_company_ids` and `_load_top_rows_by_company_ids`
- Added `get_company_price_history_by_company_ids()` — batch price history
- Added `get_company_derived_metric_points_by_company_ids()` — **most complex new function**: two-phase approach (find top-N periods per company, then fetch points matching those periods)
- Added `get_company_derived_metrics_last_checked_by_company_ids()` — batch last-checked with fallback to `DerivedMetricPoint.last_checked` scan
- Added `get_company_price_cache_status_by_company_ids()` — batch price cache status with `DatasetRefreshState` + fallback to `PriceHistory` scan
- Follow-up removed the multi-column `tuple_` import by changing the derived-metric period selection to a SQL window-function subquery

**Assessment**: Generally well-implemented batch queries, but with several concerns:
- **Fixed in follow-up**: `get_company_derived_metric_points_by_company_ids()` now ranks periods with `row_number()` in SQL, applies `max_periods` in the database, and no longer uses a multi-column tuple `IN`.
- **Minor**: `periods_by_company_id` is initialized with `{company_id: [] for company_id in normalized_ids}` but then immediately mutated with `.setdefault()`. The initialization is redundant since `setdefault` creates the list if missing.
- **Minor**: Three new functions (`price_cache_status`, `derived_metrics_last_checked`, and `derived_metric_points_by_company_ids`) each repeat the same fallback pattern: check `DatasetRefreshState` first, then fall back to scanning the data table and calling `mark_dataset_checked()`. This could be DRY'd up.

### 2.7 `app/services/screener.py` (+22 / -4 lines)

**What the file does**: Stock screener service — loads candidates, ranks, filters, sorts.

**What changed**: Added `perf_counter` timing around candidate loading, ranking, filter/sort phases, and total execution. Logs a debug-level PERF line with counts and timings in milliseconds.

**Assessment**: **Good, non-invasive diagnostics**. The timing is lightweight (`time.perf_counter()`) and logged at DEBUG level, so it has zero impact in production unless debug logging is enabled. The only cost is a few floating-point subtractions.

### 2.8 `app/services/sec/frames.py` (+118 / -53 lines)

**What the file does**: SEC XBRL frames client — fetches concept aggregations from `data.sec.gov/api/xbrl/frames`.

**What changed**:
- Added imports for `observe_upstream_request`, `sec_http_cache`, `shared_upstream_cache`
- Added `_MAX_RETRIES = 2` constant
- Refactored `fetch_frame()` to delegate to new `_request_frame()` method
- Added `_request_frame()` — checks SEC HTTP disk cache first, falls through to singleflight-coordinated upstream fetch with retry loop
- Extracted `_frame_response_from_http_response()` — pure function that parses a raw HTTP response into a `FrameResponse`
- Fetch logic now wrapped in `observe_upstream_request(source="sec_xbrl_frames")`

**Assessment**: **Good change; the main retry concern was fixed in follow-up**:
- **Fixed in follow-up**: `_request_frame()` now allows three attempts for 429 responses, handles invalid `Retry-After` defensively, and returns `None` after repeated rate limiting instead of raising an HTTP 429 through the caller.
- **Good**: The singleflight dedupe prevents thundering-herd SEC requests when multiple threads request the same frame simultaneously. The test confirms this.
- **Good**: The cache-first approach avoids upstream calls entirely for cached frames within TTL.
- **Minor**: After a 429 retry, `sec_http_cache.put()` is called on the successful response, but the failed 429 response isn't cached (correct). However, if the retry succeeds, the original throttle delay was already consumed, but the `while True` loop means the successful response path also calls `self._throttle()` again (via the next iteration of the `_fetch_response` inner function) — actually no, after the retry succeeds the `while True` returns, so the throttle only fires once more for the successful call. This is correct.

### 2.9 `app/services/sec/refresh_orchestrator.py` (+75 lines)

**What the file does**: Edgar SEC client — fetches submissions, company facts, filing indexes, etc.

**What changed**:
- Added imports for `observe_upstream_request` (was imported in `app.observability` but not used here before)
  - Actually it was already imported from `app.observability` line 28. The diff shows it added alongside `emit_structured_log`. Wait, it was already in the import line: `from app.observability import emit_structured_log, observe_upstream_request`. The old import was `from app.observability import emit_structured_log`. So `observe_upstream_request` was added to the import.
- Added `_filing_index_cache_key()` — generates a cache key from submissions fingerprint (recent accessions, dates, acceptance times, files list)
- Added `_serialize_filing_index()` / `_deserialize_filing_index()` — serialization helpers for the filing index cache
- Modified `EdgarClient._request()` to wrap upstream calls in `observe_upstream_request(source="sec_edgar")`
- Modified `EdgarClient.build_filing_index()` to check `shared_upstream_cache` before building, and store the result after building

**Assessment**: **Good change with one issue**:
- **Problem (Medium)**: `_filing_index_cache_key()` uses `recent.get("accessionNumber")` (singular) but `_ingest_columnar_filings` expects `recent.get("accessionNumber")` to be either a list or a dict. The cache key only fingerprints a single accession number. If the submissions payload returns a list of accession numbers (columnar format), the cache key may not uniquely identify the payload, potentially causing cache collisions.
- **Good**: Cache TTL is 24 hours for filing indexes, which is reasonable since submissions data changes infrequently.
- **Good**: The fingerprint approach (SHA-256 of key fields) is efficient and avoids re-serializing the full submissions payload.

### 2.10 `app/services/sec_cache.py` (+96 / -16 lines)

**What the file does**: SEC HTTP response disk cache.

**What changed**:
- Added `record_cache_event` import
- Expanded `CachePolicy` dataclass with `source`, `taxonomy`, `tag`, `period`, `as_of`, `immutable` fields
- Added cache event recording (hit/miss/stale) in `SecHttpCache.get()`
- Expanded cache payload to include structured metadata (`cache_key`, `source`, `taxonomy`, `tag`, `period`, `as_of`, `immutable`)
- Added cache policies for: `submissions_history`, `frames` (with taxonomy/tag/period), and expanded archive document matching (`.xsd`, `.html`, `.htm`, `.xhtml`, `.txt`)
- Added `immutable=True` for accession-known artifacts: filing indexes, Form 4 XMLs, 13F XMLs, filing XMLs/XSDs, and general filing documents
- Added three new helper functions: `_safe_key_part()`, `_structured_cache_key()`, and expanded `_cached_json_payload()` to include `submissions_history`, `companyfacts`, `frames`

**Assessment**: **Generally solid with several small issues**:
- **Problem (Low)**: New `CachePolicy` fields (`taxonomy`, `tag`, `period`, `as_of`) have default `None` and are only set for frames. All existing callers that construct `CachePolicy` directly use positional args and won't set these fields — that's fine since they default to `None`.
- **Problem (Low)**: `immutable=True` means TTL is effectively infinite since `created_at + None = None`, but there's no explicit infinite-TTL marker. The code relies on the implicit behavior that `expires_at=None` is never considered expired. An explicit `is_immutable` check would be clearer.
- **Good**: The archive document regex now covers `.xsd`, `.html`, `.htm`, `.xhtml`, `.txt` in addition to `.xml`, which was the only extension matched before. This means 13F information tables (`.htm`/`.html`) and XBRL schema files (`.xsd`) are now cached. The previous regex only matched `.xml`, so many filing documents were fetched fresh every time.
- **Good**: Cache event recording gives observability into cache hit rates — important for validating the performance improvement.
- **Good**: The `_structured_cache_key` function provides a human-readable key format that includes all cache dimensions, making debugging much easier.

---

## 3. Performance Review

### 3.1 Positive Changes

- **Compare route**: N+1 DB queries replaced by constant batch queries. For a 10-ticker compare, this reduces ~60 per-ticker queries (financials + prices + metrics + models + cache states) to ~6 batch queries. Expected latency reduction: 50-80% for the compare endpoint.
- **Watchlist calendar**: Same pattern. Per-ticker financials + filing events replaced by a single batch load.
- **SEC frames cache**: Identical frame URLs hit disk cache instead of making upstream HTTP calls. With singleflight, concurrent identical requests coalesce to one upstream fetch.
- **Filing index cache**: `build_filing_index()` is called during company refresh, which can be triggered from multiple routes. Caching this avoids rebuilding the same index for the same CIK within 24 hours.
- **New DB index**: The composite index directly supports screener queries that filter by `period_type` and group by `company_id`, ordered by `period_end DESC`. This should notably improve screener candidate loading times for large universes.

### 3.2 Concerns

- **Fixed in follow-up**: `get_company_derived_metric_points_by_company_ids` no longer fetches all periods before truncation. It now ranks distinct periods per company in SQL and applies `max_periods` in the database.
- **Fixed in follow-up**: The derived-metric batch path no longer uses a multi-column tuple `IN` clause.
- **Preload exception swallowing**: `_load_company_compare_preload` and `_load_watchlist_calendar_preload` both catch all exceptions and log them. If the preload fails (e.g., DB timeout), the route silently degrades to N+1 queries. This is intentional graceful degradation, but it means a broken preload won't trigger alerts — users will just experience slower responses.
- **Model computation in read path**: `_load_company_compare_preload` calls `ModelEngine(session).compute_models()` which can trigger expensive model computations and DB writes. If a model is stale, the compare endpoint now blocks on model recomputation. This was already the case (the per-item builder also called `compute_models`), but now it happens for ALL tickers upfront before any response is built.

### 3.3 Screener Timing Logs

The new debug-level timing is useful for diagnostics but has no runtime impact. The format string is clear and includes candidate count, matched count, and per-phase millisecond breakdown.

---

## 4. Data Handling Review

### 4.1 Data Fetching

- Batch queries correctly handle empty company ID lists (return `{}`).
- The fallback pattern (preload dict → per-company DB call) is consistently applied.
- `get_company_price_cache_status_by_company_ids` and `get_company_derived_metrics_last_checked_by_company_ids` both have a primary path (query `DatasetRefreshState`) and a fallback path (scan data tables and call `mark_dataset_checked()`). The fallback has a side effect (writing to `DatasetRefreshState`), which is intentional — it backfills missing refresh-state rows.

### 4.2 Caching

- SEC HTTP cache now has much broader coverage. Frames, companyfacts, submissions history, and all archive document types (not just XML) are cached.
- Immutable artifacts (filing documents, indexes) are cached without TTL — correct since SEC archive documents never change.
- The structured cache key and filename formats are well-designed for debuggability.
- **Missing**: No cache eviction or size management is visible in the diff. The `SecHttpCache` appears to use filesystem-based storage with no pruning of old entries except the periodic prune mentioned in `_last_periodic_prune_monotonic`. If the cache grows unboundedly, disk usage could become a problem.

### 4.3 Error Handling

- Preload failures are caught and logged — routes continue with per-company fallback.
- Individual per-ticker failures in `watchlist_calendar` and `company_compare` are caught and logged without failing the entire response — this was pre-existing and remains unchanged.
- SEC frames 429 handling: **fixed in follow-up**. The code now retries three attempts using `Retry-After` and returns `None` after repeated rate limiting.

### 4.4 Loading and Empty States

- Empty company ID lists return early with `{}` in all batch functions.
- Companies with no financial data get `[]` assigned in the preload dict.
- Strict official mode correctly returns empty price data (`[]` for history, `("fresh", None)` for status).

### 4.5 Data Structures

- **Inconsistency**: `model_runs_by_company_id` stores model runs as dicts keyed by model name (`{"dcf": {...}, "piotroski": {...}}`) while the non-preloaded path returns a list from `get_company_models()`. The test confirms the dict format. The consumer (`_build_company_compare_item`) handles both by checking `has_preloaded_model_runs` and calling `.values()` on the dict. This works but is fragile — a future change to `get_company_models_by_company_ids()` that changes the return format would silently break the preload path.
- The preload dict structure is typed as `dict[str, Any]` throughout — no TypedDict or dataclass. This means typos in key names (e.g., `"financials_by_company_ids"` vs `"financials_by_company_id"`) would silently result in empty data and fallback queries. Consider a TypedDict for the preload shape.

---

## 5. UI/UX Review

**No user-facing changes**. API response contracts remain identical. No new fields, no changed field types, no route changes. Users will experience:

- **Faster compare page loads** — batch preloading reduces per-ticker query overhead
- **Faster watchlist calendar loads** — same batch optimization
- **Same behavior on errors** — pre-existing per-ticker error isolation is preserved

**No UX regressions detected.**

---

## 6. Code Quality Review

### 6.1 Duplication

- **Watchlist calendar preload pattern** is duplicated in `_shared.py` (line ~5531) and `workspace.py` (line ~79). The try/except → preload → ContextVar.set() → try/finally → ContextVar.reset() pattern is identical. This is a known consequence of having the same route registered in two files.
- **Fallback pattern**: Three batch functions (`price_cache_status_by_company_ids`, `derived_metrics_last_checked_by_company_ids`, and the regulated financial's `_load_top_rows_by_company_ids` usage) all share the same pattern of "check DatasetRefreshState → fall back to data table scan → call mark_dataset_checked". This could be extracted into a helper.

### 6.2 Overly Complex Functions

- `_load_company_compare_preload()` at ~50 lines is reasonable but mixes pure data fetching with model computation side effects. Would benefit from splitting the "fetch" and "compute" phases.
- `get_company_derived_metric_points_by_company_ids()` is still the most complex new function, but the follow-up moved `max_periods` truncation into SQL.

### 6.3 Naming

- Function names are verbose but unambiguous: `get_company_derived_metrics_last_checked_by_company_ids` is 57 characters but leaves no doubt about what it does.
- `_visible_financials_by_company_ids` is slightly misleading — the "visible" prefix suggests filtering for display, but its primary purpose is batch querying with regulated/non-regulated routing.

### 6.4 Weak Typing

- Preload dicts are `dict[str, Any]` — no shape enforcement.
- `_frame_response_from_http_response()` parameter `response: Any` should be `httpx.Response`.
- `_serialize_filing_index()` parameter `filing_index: dict[str, FilingMetadata]` is correct, but `_deserialize_filing_index()` takes `dict[str, Any]` which is less precise.

### 6.5 Missing Validation

- No validation that `company_ids` contains valid integer IDs before passing to DB queries. The `_normalize_company_ids` function converts to `int`, which would raise `ValueError` for non-numeric inputs. This is fine since callers pass DB-derived IDs.
- `get_company_derived_metric_points_by_company_ids` now returns empty grouped results when `max_periods <= 0`, matching the effective behavior of a zero-row limit.

### 6.6 Fragile Assumptions

- `_build_company_compare_item` relies on `model_runs_by_company_id[company_id]` being a dict when preloaded but a list when not preloaded. This implicit data shape difference is a maintenance trap.
- `_load_company_compare_preload` checks `if not hasattr(session, "execute"): return None` — assumes any non-DB session is a mock. A session wrapper or proxy that delegates via `__getattr__` would pass this check but fail at query time.

### 6.7 Dead Code / Unused Imports

- `time` import added to `screener.py` — used, correct.
- No unused imports detected in the diff.

### 6.8 Hardcoded Values

- `max_periods=24` is hardcoded in both `_load_company_compare_preload()` and the per-item fallback — at least they're consistent.
- `WATCHLIST_CALENDAR_WINDOW_DAYS` appears to be a pre-existing constant — not introduced here.
- `_MAX_RETRIES = 2` is a module-level constant — good.
- `"dcf", "piotroski", "altman_z"` — requested models are hardcoded in two places (in `_load_company_compare_preload` and `_build_company_compare_item`). The test also hardcodes the same list. These should be a module-level constant.

### 6.9 File Size

- `_shared.py` is now over 11,000 lines. The preload functions add ~200 lines to an already monolithic file. This file desperately needs to be split into route-specific modules.

---

## 7. Risks and Possible Bugs

### Critical

None identified.

### High

1. **Model run data shape inconsistency** (`_shared.py`): Preloaded model runs are stored as `dict[str, dict]` (keyed by model name) while the non-preloaded path returns a `list`. The consumer handles both via `has_preloaded_model_runs` flag, but if someone modifies `get_company_models_by_company_ids()` return format without updating the preload construction, the response will break silently (empty model results).
   - **Mitigation**: The test `test_company_compare_item_uses_preloaded_batch_data` validates the dict shape, so a regression would be caught.

2. **Fixed in follow-up — SEC frames 429 handling regression** (`frames.py`): The code now retries three attempts with `Retry-After` delay and returns `None` after repeated rate limiting instead of propagating HTTP 429.
   - **Impact**: Screener frame refreshes should degrade by treating a repeatedly rate-limited frame as unavailable rather than failing the caller.
   - **Mitigation**: Singleflight dedupe still reduces total upstream requests, and the retry behavior is now covered by tests.

### Medium

3. **Preload writes during read path** (`_shared.py`): `_load_company_compare_preload` calls `ModelEngine.compute_models()` which can trigger DB writes. If the preload fails partway, partial model recomputation may have been committed. The exception is caught and the route falls back to per-item computation, potentially doubling the work.
   - **Mitigation**: Model computation is idempotent. Repeated computation wastes CPU but doesn't corrupt data.

4. **Fixed in follow-up — `get_company_derived_metric_points_by_company_ids` fetched all periods before truncation** (`cache_queries.py`): Period ranking now happens in SQL with `row_number()`, so the database applies `max_periods`.
   - **Impact**: Avoids unnecessary period transfer for long-history companies while preserving grouped response shape.

5. **Duplicate route registration** (`_shared.py` + `financials.py`, `_shared.py` + `workspace.py`): The same endpoints are registered in two files. Import order determines which one is active. If the versions diverge, the "inactive" version becomes dead code that still passes code review.
   - **Mitigation**: This change keeps both versions in sync. Not introduced here, but made worse by the added complexity.

6. **No cache pruning visible**: The SEC HTTP cache now stores more data (frames, companyfacts JSON, all archive documents). Without visible pruning logic, disk usage could grow significantly in production.
   - **Mitigation**: There's a reference to `_last_periodic_prune_monotonic` in the file (line 17), but the pruning logic isn't visible in this diff. It may exist elsewhere.

### Low

7. **Done in follow-up — hardcoded model list** (`_shared.py`): `COMPARE_REQUESTED_MODELS` now centralizes the compare model set.
8. **`frames_match` regex** (`sec_cache.py`): The regex `([^/]+)/([^/]+)/([^/]+)/([^/]+)\.json$` only matches non-empty segments, which is correct for SEC frames URLs. But if the SEC ever changes the URL format, frames caching silently stops.
9. **`fallback_taxonomy`/`fallback_tag`** (`frames.py`): `_frame_response_from_http_response` uses fallback values from the request parameters if the response JSON doesn't include them. This is defensive but may hide upstream data issues.
10. **`ContextVar` lifecycle**: If `_build_company_compare_response` is ever called from a background task or thread pool, the `ContextVar` state will not propagate. The code handles this via the `None` fallback, so it degrades gracefully.

---

## 8. Recommended Next Steps

### Before Pushing

1. **Done in follow-up — fix the SEC frames 429 retry**: `_MAX_RETRIES` is now 3, invalid `Retry-After` values are handled defensively, and repeated 429s return `None` instead of raising through the caller.

2. **Done in follow-up — consolidate the requested_models list**: `COMPARE_REQUESTED_MODELS` is now the shared compare model list.

3. **Decide on `financials.py` / `workspace.py` duplication**: If `_shared.py` is the canonical handler file, the duplicate routes in `financials.py` and `workspace.py` should either be removed or clearly marked as overrides. As-is, the duplication creates maintenance risk.

### Can Wait

4. **Add TypedDict for preload shapes**: Replace `dict[str, Any]` with typed dicts for compare and calendar preloads. This would prevent key-name typos and document the expected structure.

5. **Done in follow-up — optimize `get_company_derived_metric_points_by_company_ids`**: The period-discovery phase now uses a SQL window function so truncation happens in the database.

6. **Extract shared fallback pattern**: The "check DatasetRefreshState → scan data table → mark_dataset_checked" pattern is used in 3 functions. Could be a helper.

7. **Split `_shared.py`**: At 11,000+ lines, this file should be broken into route modules. The preload functions are good candidates for extraction to a dedicated `preloads.py` or per-route module.

### Manual Testing Needed

8. **Test compare with maximum allowed tickers**: Compare 5 companies simultaneously and verify response time is reasonable and all data is present.
9. **Test compare with unknown/missing tickers**: Verify graceful degradation when some tickers have no data.
10. **Test watchlist calendar with full watchlist**: Verify events are correctly projected and no events are duplicated or missing.
11. **Test SEC cache with cold cache**: Delete the cache directory and verify frames, companyfacts, and filing documents are fetched and cached correctly.
12. **Test SEC rate-limiting**: If possible, trigger 429 responses from SEC and verify the retry behavior is acceptable.
13. **Run the DB migration**: `alembic upgrade head` — the PR summary notes a credential issue. This must be verified in each environment.

### Improve Later

14. **Add route-level query-count benchmarks**: As noted in the PR summary, automated benchmarks would catch N+1 query regressions.
15. **Consider a compact bootstrap aggregate**: The PR summary mentions this — a pre-computed company overview payload could further reduce first-page load queries.
16. **Add cache pruning monitoring**: Track SEC cache directory size and add alerts if it exceeds reasonable bounds.

---

## 9. Suggested Codex Follow-up Prompts

The retry, compare-model constant, and derived-metric SQL-window work have been completed. Remaining prompts are intentionally limited to deferred maintainability work.

### Add TypedDict for preload data

```
In app/api/handlers/_shared.py, create TypedDict classes for the
company compare preload dict and the watchlist calendar preload dict.
Replace the dict[str, Any] type annotations with these typed dicts.
This will catch key-name typos at type-checking time. Make sure the
tests are updated if key names change.
```

### DRY up the DatasetRefreshState fallback pattern

```
In app/services/cache_queries.py, the functions
get_company_price_cache_status_by_company_ids,
get_company_derived_metrics_last_checked_by_company_ids share the same
pattern: query DatasetRefreshState, collect missing IDs, fall back to
scanning the data table, and call mark_dataset_checked for backfill.
Extract this into a shared helper function to reduce duplication.
```

### Verify and potentially remove duplicate route handlers

```
In the repo, /api/companies/compare and /api/watchlist/calendar are
registered in both app/api/handlers/_shared.py and either financials.py
or workspace.py. Audit which registrations are actually active (based on
import order in app/main.py) and remove the dead registrations, or add
a comment explaining why both exist. The current duplication risks one
version silently diverging from the other.
```
