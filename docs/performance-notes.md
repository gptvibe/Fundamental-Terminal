# Performance Notes

## Scope

This pass focused on the user-requested order of operations:

1. Remove avoidable database work from repeated company GET requests.
2. Make market-data refreshes incremental instead of re-pulling full history.
3. Reduce worker and status-stream polling churn.
4. Cut JSON serialization overhead on large cached responses.
5. Validate behavior before any broader runtime tuning.

## What Changed

- Company-route cache middleware now prefers fresh hot-cache metadata before opening database sessions, and it upgrades first-response headers to the hot-cache validator once the route fills cache.
- Company compare freshness checks now batch ticker snapshot lookup instead of walking tickers one by one.
- Market-data refreshes now request only the trailing overlap window from the latest stored trade date instead of full price history on every refresh.
- Refresh workers now block on Redis-backed queue signals when available and run expired-job recovery on a slower cadence instead of every claim loop.
- Async status subscriptions now prefer Redis pub/sub fanout with persisted-event catch-up instead of pure polling.
- Hot-cache payload encode/decode and the default API JSON response path now use orjson-backed serialization.

## Measurements

Warm-cache benchmark results came from the passing regression gate in [artifacts/performance/backend-performance-summary.md](artifacts/performance/backend-performance-summary.md), compared against [scripts/performance_regression_baseline.json](scripts/performance_regression_baseline.json).

| Case | Baseline p50 ms | Current p50 ms | Delta | Baseline p95 ms | Current p95 ms | Delta |
|---|---:|---:|---:|---:|---:|---:|
| company_search | 1.32 | 0.87 | -34.1% | 2.37 | 1.25 | -47.3% |
| financials_payload | 1.48 | 0.67 | -54.7% | 1.85 | 1.35 | -27.0% |
| models_payload | 1.51 | 0.88 | -41.7% | 1.73 | 1.22 | -29.5% |
| peers_payload | 1.34 | 0.63 | -53.0% | 1.49 | 0.84 | -43.6% |
| metrics_timeseries_payload | 1.39 | 1.15 | -17.3% | 1.64 | 1.43 | -12.8% |
| company_brief_ready | 9.30 | 6.73 | -27.6% | 12.57 | 8.67 | -31.0% |

Current gate status: pass, with zero regressions against the repo budget thresholds.

## Validation

- Focused backend verification: `46 passed`
- Backend CI-targeted architecture/regression coverage: `36 passed`
- Frontend CI-targeted route compatibility coverage: `12 passed`
- Backend performance regression gate: `ok`
- Model evaluation gate against Docker-backed Postgres: passed with zero baseline deltas
- Docker stack: `docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d` completed successfully and all services reached healthy/running state

## End-to-End Smoke Checks

- Cold missing ticker behavior was checked with CRM on financials, models, and peers pages. The frontend rendered without application errors and the backend returned structured missing-company payloads while queuing a background refresh.
- Existing stale ticker behavior was checked with IBM on financials, models, and peers pages. The frontend loaded populated cached data, showed background refresh status, and the backend returned the expected cached payload shapes.

## Notes

- The default JSON response path now uses a plain custom `Response` with `orjson` rendering, which removes the prior FastAPI `ORJSONResponse` deprecation warning without changing payload behavior.
- Tracked bytecode artifacts were restored before the final validation pass so the working tree stays focused on intentional source, test, and benchmark changes.
- Refresh orchestration now overlaps one bounded Yahoo fetch (price history) with SEC normalization when `refresh_aux_io_max_workers > 1`; writes remain sequential and SEC dataset jobs remain serialized.
- Synthetic timing note for this overlap: if statement normalization takes ~150ms and Yahoo fetch takes ~150ms, end-to-end wall time is expected to move from roughly ~300ms (sequential) toward ~150-180ms (overlapped plus coordination overhead).
- Upstream cache validation now uses `Last-Modified` revalidation only for `www.sec.gov/files/company_tickers.json`, because sampled SEC submissions/companyfacts endpoints did not emit reliable validators and Yahoo search/chart responses exposed explicit short `max-age` windows but no stable validators.
- Yahoo market profile and chart fetches now use a short shared parsed-result cache plus singleflight keyed by symbol/request shape, which cuts duplicate network calls and repeated upstream JSON parsing across concurrent requests and workers without serving stale data beyond the upstream-declared `max-age` window.
