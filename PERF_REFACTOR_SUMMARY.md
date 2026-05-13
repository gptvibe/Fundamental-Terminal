# Performance Refactor Summary

## What Changed

- Expanded the SEC HTTP cache policy to use structured cache metadata, immutable accession-known archive artifacts, cached `companyfacts` JSON payloads, submissions history, frames, and broader filing document coverage.
- Added SEC upstream timing and routed SEC XBRL frames through the same SEC disk cache plus shared singleflight coordination used by the Edgar client.
- Cached `EdgarClient.build_filing_index()` output from submissions fingerprints so repeated company flows avoid rebuilding historical filing indexes.
- Added batch data-access helpers for price history, price cache state, regulated bank financials, derived metric rows, and derived metric last-checked state.
- Added compare-route preloading so financials, prices, derived metrics, and cached model runs are loaded in batches before per-ticker serialization.
- Added watchlist calendar preloading so projected filing inputs and filing events are loaded once for the ticker batch.
- Added a screener-oriented derived-metric index:
  - `ix_derived_metric_points_period_type_company_period`
- Added lightweight debug timing around screener candidate loading, ranking, filtering, sorting, and total execution.
- Added focused tests for SEC cache metadata, cached `companyfacts` payloads, SEC frames cache/singleflight behavior, batch cache-query helpers, compare preloading, and watchlist calendar preloading.

## Why It Improves Performance

- Warm SEC `companyfacts` responses can reuse parsed JSON from cache instead of reparsing the same large payload on every request.
- Concurrent identical SEC frame pulls now coalesce behind one upstream request and then serve from the SEC cache.
- Immutable historical filing documents and indexes are not refreshed blindly once accession-specific URLs are cached.
- Compare now avoids repeated per-ticker DB queries for financials, prices, derived metrics, and cached model reads.
- Watchlist calendar now avoids per-ticker financial and filing-event queries when building the batch response.
- Screener latest-period scans have an index aligned with the `period_type -> company_id -> period_end` access pattern.

## Before/After Behavior

- API response contracts remain unchanged; cache metadata stays internal.
- Routes and UI behavior remain unchanged.
- Strict official mode behavior remains intact: price payloads still collapse to empty/fresh where existing code suppresses fallback-backed price data.
- Demo mode and fallback provenance behavior were not changed.
- Measurable validation:
  - Backend test suite: `990 passed, 1 skipped`.
  - Frontend test suite: `520 passed`.
  - Architecture boundary guard: passed.
  - Migration safety checks: passed.
  - Production frontend build: passed.
- Local `python -m alembic upgrade head` could not complete because the configured Postgres credentials for user `fundamental` were rejected. `python -m alembic heads` reports `20260512_0050 (head)`.

## Compatibility Notes

- New API fields were not added and no existing response shape was changed.
- New database migration is additive and checks for the table/index before creating or dropping.
- Existing monkeypatch-heavy route tests remain compatible because preloads fall back to the older per-helper path when session execution is unavailable or preload fails.
- Compare and watchlist calendar preserve requested ticker ordering and existing per-ticker error isolation.

## Remaining Future Improvements

- Materialize more chart/dashboard payloads by source fingerprint so expensive chart recomputation can be skipped more often.
- Add a persisted parser-version column for parsed filing artifacts that are currently invalidated by dataset hashes only.
- Add route-level query-count benchmarks for company bootstrap, compare, watchlist, and screener to track future regressions numerically.
- Consider a compact persisted company bootstrap aggregate for first-page load paths that currently stitch together several cached datasets.
