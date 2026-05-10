# Codex Implementation Map

Generated from a repository audit on 2026-05-06. This is a pre-change implementation map only; it does not describe any behavior change.

## Repo Architecture Summary

Fundamental Terminal is an official-source-first U.S. public equities research workspace. The backend is a FastAPI app, the frontend is a Next.js App Router app, and the product contract depends on stable routes, explicit source provenance, cache-first company research reads, and visible fallback disclosures.

Backend entry point:
- `app/main.py` builds the FastAPI app in `create_app()`, registers auth, rate-limit, conditional GET, performance audit, and security middleware, then registers routers through `app.api.register_routers`.
- `app/main.py` also exports legacy handler names from `app.legacy_api` so existing tests and monkeypatches can continue to treat `app.main` as the compatibility boundary.

Backend shape:
- `app/api/routers/` registers public route URLs and response models.
- `app/api/schemas/` owns frontend-facing request and response schemas.
- `app/api/handlers/` bridges route handlers to service code and keeps compatibility with legacy `app.main` symbols.
- `app/services/` owns ingestion, normalization, persistence, analytics, refresh policy, cache queries, and source-specific clients.
- `app/api/endpoint_source_contract_manifest.py` and `app/api/source_contracts.py` enforce user-visible endpoint provenance contracts at app startup and response time.

Frontend entry point:
- `frontend/app/layout.tsx` wraps the app shell.
- `frontend/components/layout/app-chrome.tsx` owns global navigation, top-bar search, command palette, refresh/export commands, and the data-source panel.
- `frontend/app/page.tsx` is the home/search workspace.
- `frontend/app/company/[ticker]/layout.tsx` wraps company routes in `CompanyLayoutProvider` and `CompanySubnav`.
- `frontend/lib/api.ts` is the public frontend API barrel; focused API modules live in `frontend/lib/api/`.

Core frontend data path:
- `frontend/hooks/use-company-workspace.ts` loads `/workspace-bootstrap` first, falls back only on compatibility statuses, shares financials into the frontend read cache, tracks refresh jobs, and wires SSE reloads.
- `frontend/app/company/[ticker]/_hooks/use-research-brief-data.ts` loads the persisted `/brief` payload for the default Research Brief.
- `frontend/lib/api/cachePolicy.ts`, `frontend/lib/api/cacheStore.ts`, and `frontend/components/layout/company-layout-context.tsx` control client-side reuse across company tabs.

## Backend Boundaries

Routers:
- Keep routers thin. Route registration belongs in `app/api/routers/` and should use `add_user_visible_route()` or `add_internal_route()`.
- Routers should import FastAPI/Starlette helpers, API schemas, source-contract route helpers, and handlers only.
- Routers must not import `app/services/`, database sessions, or model-engine helpers.

Schemas:
- Frontend-facing payload contracts belong in `app/api/schemas/`.
- Schema changes are public API changes and should be paired with deterministic tests and frontend type updates.

Handlers:
- Handler functions live in `app/api/handlers/`.
- `app/api/handlers/_dispatch.py` maps compatibility names to handlers.
- `app/legacy_api.py` clones/export legacy handler globals so `app.main` stays the public compatibility surface.
- Handler code can serialize service/domain output into API schemas, but orchestration should stay in services.

Services:
- `app/services/sec/refresh_orchestrator.py` contains `EdgarIngestionService`, SEC clients, normalization, dataset refresh methods, and strict-official price/market-profile handling.
- `app/services/company_research_brief.py` composes the persisted Research Brief from cached official/public inputs, derived analytics, and labeled price fallback where allowed.
- `app/services/cache_queries.py` is a central read path for persisted company datasets.
- `app/services/market_data.py` is the Yahoo-backed price/profile fallback boundary and must honor `STRICT_OFFICIAL_MODE`.
- `app/services/status_stream.py` and `app/services/fetch_trigger.py` own refresh queue/SSE job semantics.
- `app/services/hot_cache.py`, `app/middleware/company_cache.py`, and `app/middleware/conditional_get.py` are sensitive cache/conditional-read infrastructure.

Source contracts:
- Every user-visible `/api/...` route must have a manifest entry in `app/api/endpoint_source_contract_manifest.py`.
- `ensure_user_visible_routes_have_source_contracts(app)` runs after router registration and fails startup if route metadata and manifest entries drift.
- Runtime validation rejects unauthorized source ids, disallowed fallback sources, or strict-official payloads that still expose fallback sources.

## Public API Map

Core company research:
- `GET /api/companies/{ticker}/workspace-bootstrap`: hot default company workspace bootstrap; sensitive because the default frontend route depends on it and shares cache entries from it.
- `GET /api/companies/{ticker}/brief`: persisted Research Brief summary payload; sensitive because it composes many section summaries.
- `GET /api/companies/{ticker}/overview`: legacy overview compatibility payload; keep stable.
- `GET /api/companies/{ticker}/financials`: canonical financials, price history, reconciliation, segment analysis, compact `view` options.
- `GET /api/companies/{ticker}/changes-since-last-filing`: latest-vs-prior SEC-derived comparison.
- `GET /api/companies/{ticker}/activity-overview`: unified filing, ownership, governance, capital markets, and monitor activity.

Financials, charts, and models:
- `GET /api/companies/compare`
- `GET /api/companies/{ticker}/charts`
- `POST /api/companies/{ticker}/charts/what-if`
- `GET|POST /api/companies/{ticker}/charts/scenarios...`
- `POST|GET /api/companies/{ticker}/charts/share-snapshots...`
- `GET /api/companies/{ticker}/segment-history`
- `GET /api/companies/{ticker}/capital-structure`
- `GET /api/companies/{ticker}/equity-claim-risk`
- `GET /api/companies/{ticker}/metrics-timeseries`
- `GET /api/companies/{ticker}/metrics`
- `GET /api/companies/{ticker}/metrics/summary`
- `GET /api/companies/{ticker}/models`
- `GET /api/companies/{ticker}/peers`
- `GET /api/model-evaluations/latest`

Filings, events, governance, ownership:
- `GET /api/companies/{ticker}/filings`
- `GET /api/filings/{ticker}`
- `GET /api/search_filings`
- `GET /api/companies/{ticker}/filings/view`
- `GET /api/companies/{ticker}/filing-insights`
- `GET /api/companies/{ticker}/filing-risk-signals`
- `GET /api/companies/{ticker}/events`
- `GET /api/companies/{ticker}/filing-events`
- `GET /api/companies/{ticker}/filing-events/summary`
- `GET /api/companies/{ticker}/comment-letters`
- `GET /api/companies/{ticker}/capital-markets`
- `GET /api/companies/{ticker}/capital-markets/summary`
- `GET /api/companies/{ticker}/governance`
- `GET /api/companies/{ticker}/governance/summary`
- `GET /api/companies/{ticker}/executive-compensation`
- `GET /api/companies/{ticker}/insider-trades`
- `GET /api/companies/{ticker}/institutional-holdings`
- `GET /api/companies/{ticker}/institutional-holdings/summary`
- `GET /api/companies/{ticker}/form-144-filings`
- `GET /api/companies/{ticker}/beneficial-ownership`
- `GET /api/companies/{ticker}/beneficial-ownership/summary`

Search, context, workspace, and control plane:
- `GET /api/companies/search`
- `GET /api/companies/resolve`
- `POST /api/companies/{ticker}/refresh`
- `GET /api/jobs/{job_id}/events`
- `GET /api/source-registry`
- `GET /api/companies/{ticker}/market-context`
- `GET /api/market-context`
- `GET /api/companies/{ticker}/sector-context`
- `GET /api/screener/filters`
- `POST /api/screener/search`
- `GET /api/screener/sec-frames`
- `POST /api/watchlist/summary`
- `GET /api/watchlist/calendar`
- `GET|POST /api/research-workspace...`
- Internal only: `/health`, `/readyz`, `/api/internal/cache-metrics`, `/api/internal/observability`, `/api/internal/performance-audit`.

## Frontend Route And Component Map

Global routes:
- `/`: `frontend/app/page.tsx`, home/search workspace.
- `/compare`: `frontend/app/compare/page.tsx`, local compare page.
- `/watchlist`: `frontend/app/watchlist/page.tsx`, browser-saved watchlist plus backend summary/calendar.
- `/data-sources`: `frontend/app/data-sources/page.tsx`, source registry and cache status.
- `/screener`: `frontend/app/screener/page.tsx`, official-data screener.
- `/research-workspace`: `frontend/app/research-workspace/page.tsx`, server-side workspace persistence.
- `/api/cache/company/[ticker]`: Next route handler that revalidates company cache tags after refresh.

Company shell:
- `/company/[ticker]/layout.tsx`: company provider plus `CompanySubnav`.
- `frontend/components/layout/company-subnav.tsx`: primary nav (`Brief`, `Financials`, `Charts`, `Models`, `Peers`) plus More menu; hover/focus prefetches tab data.
- `frontend/components/layout/company-workspace-shell.tsx`: shared main/utility-rail layout.
- `frontend/components/layout/company-utility-rail.tsx`: refresh actions, next steps, and job/status context.

Company routes:
- `/company/[ticker]`: `page.tsx`, default Research Brief with Snapshot, What Changed, Business Quality, Capital & Risk, Valuation, Monitor, and data-quality appendix.
- `/company/[ticker]/financials`: server entry plus `financials-client-page.tsx`; canonical statements, segment/geography, reconciliation, metrics.
- `/company/[ticker]/charts`: server entry plus projection studio hydration; chart dashboard, scenarios, share snapshots.
- `/company/[ticker]/models`: valuation/model workspace, market/sector context, commercial fallback notices, model evaluation.
- `/company/[ticker]/peers`: peer comparison snapshot with fallback disclosure.
- `/company/[ticker]/filings`: filing timeline, filing risk signals, changes, parser insights, SEC evidence.
- `/company/[ticker]/earnings`: earnings workspace from SEC-derived releases.
- `/company/[ticker]/events`: filing-event workspace.
- `/company/[ticker]/capital-markets`: equity claim risk and capital-markets event pack.
- `/company/[ticker]/governance`: governance and executive compensation.
- `/company/[ticker]/ownership`: institutional ownership.
- `/company/[ticker]/ownership-changes`: beneficial ownership/stake changes.
- `/company/[ticker]/insiders`: insider trades and Form 144.
- `/company/[ticker]/sec-feed`: unified SEC activity feed and source freshness.
- `/company/[ticker]/oil`: oil overlay/model extension workspace.
- `/company/[ticker]/stakes`: redirect to `/ownership-changes`.

Frontend provenance surfaces:
- `frontend/components/ui/commercial-fallback-notice.tsx`
- `frontend/components/ui/source-freshness-summary.tsx`
- `frontend/components/company/source-freshness-timeline.tsx`
- `frontend/components/ui/data-quality-diagnostics.tsx`
- `frontend/app/data-sources/page.tsx`

## Data Provenance Rules

Source policy:
- Core fundamentals, filings, ownership, governance, capital markets, and official-derived analytics must stay SEC-first/public-data-first.
- Allowed official/public sources include SEC EDGAR/submissions/companyfacts, U.S. Treasury/FiscalData, Census, BLS, BEA, Treasury HQM, FRED optional macro support, and approved sector official datasets.
- Yahoo Finance is allowed only as a clearly labeled fallback for price, volume, and market-profile context.
- Do not add paid/auth-gated vendor fundamentals APIs, unofficial scraped fundamentals feeds, or third-party fundamentals providers that obscure SEC provenance.

Strict official mode:
- `STRICT_OFFICIAL_MODE=true` must suppress Yahoo-backed price and market-profile payloads and UI surfaces.
- Strict official mode should derive market sector/industry from SEC SIC mapping where possible.
- Price-dependent models or UI should hide, disable, or explain that no official equity-price source is configured.

Payload contract:
- Hot company payloads should expose `provenance[]`, `as_of`, `last_refreshed_at`, `source_mix`, `confidence_flags`, and `diagnostics`.
- Each provenance entry carries canonical `source_id`, source tier, display label, canonical URL, freshness TTL, disclosure note, role, per-source `as_of`, and per-source `last_refreshed_at`.
- `source_mix` is the frontend summary for official-only vs fallback-influenced payloads.
- Point-in-time `as_of` uses public visibility semantics, not fetch time; date-only `as_of` values are end-of-day UTC.

New data surfaces:
- Document provenance before shipping product routes.
- Add or reuse canonical source ids in the source registry.
- Add endpoint source-contract manifest entries for all user-visible routes.
- Keep official sources dominant when supplemental data is present.
- Add deterministic tests for source contracts, strict official mode, fallback disclosure, and point-in-time behavior where relevant.

## Routes And Services Most Sensitive To Breaking Changes

Highest sensitivity:
- `frontend/app/company/[ticker]/page.tsx`, `use-company-workspace.ts`, `use-research-brief-data.ts`, `/workspace-bootstrap`, `/brief`, `/overview`, and `/financials` because they define the default Research Brief and shared company cache path.
- `app/api/endpoint_source_contract_manifest.py`, `app/api/source_contracts.py`, and `app/source_registry.py` because route registration and runtime payload validation depend on them.
- `app/services/sec/refresh_orchestrator.py`, `app/services/status_stream.py`, and `app/services/fetch_trigger.py` because refresh queue behavior, SSE progress, and worker semantics are user-visible.
- `app/services/market_data.py`, price-backed model paths, `/models`, `/peers`, `/compare`, `/metrics*`, and `/watchlist/summary` because fallback disclosure and strict official mode are easy to regress.
- `frontend/lib/api/client.ts`, `frontend/lib/api/cachePolicy.ts`, `frontend/lib/api/cacheStore.ts`, and `company-layout-context.tsx` because small cache changes can alter fan-out, stale reads, or refresh invalidation.

Performance-sensitive endpoints from the baseline:
- `/api/companies/{ticker}/governance/summary`
- `/api/companies/{ticker}/changes-since-last-filing`
- `/api/companies/{ticker}/activity-overview`
- `/api/watchlist/summary`
- `/api/companies/{ticker}/insider-trades`
- `/api/companies/{ticker}/financials`
- `/api/companies/{ticker}/institutional-holdings`
- `/api/companies/{ticker}/capital-markets/summary`
- `/api/companies/search`

Contract-sensitive tests:
- `tests/test_architecture_boundaries.py`
- `tests/test_api_route_inventory.py`
- `tests/test_endpoint_provenance_contracts.py`
- `tests/test_endpoint_source_contract_manifest.py`
- `tests/test_source_contract_runtime_enforcement.py`
- `tests/test_hot_endpoint_contracts.py`
- `tests/test_market_data_strict_mode.py`
- `frontend/lib/api.routes.test.ts`
- `frontend/app/company/[ticker]/page.activity-feed.test.ts`
- `frontend/e2e/company-workspace.smoke.spec.ts`

## AI And BYOK Placement

AI/BYOK features should be added as a grounded, provenance-aware vertical slice rather than mixed into route or ingestion layers.

Backend placement:
- Put AI orchestration in a new service module such as `app/services/ai_research.py` or `app/services/ai/`, not in routers.
- Service inputs should be persisted or documented payloads from cache/query services; do not live-fetch new fundamentals or filings on the request path.
- Add frontend-facing schemas under `app/api/schemas/ai.py` and thin route registration under `app/api/routers/ai.py`.
- If handlers are needed, place them under `app/api/handlers/ai.py` and serialize service/domain output there.
- Add source registry ids for AI-derived outputs, for example an `ft_ai_*` derived source, and add manifest contracts before exposing routes.

BYOK handling:
- Treat user-provided model keys as secrets: do not log them, do not include them in provenance, and do not persist them unless an explicit encrypted secret store is introduced.
- Prefer ephemeral request/session use or browser-local BYOK storage with clear user control.
- Redact AI provider/key fields from observability and performance audit payloads.

Product constraints:
- AI output must stay grounded in persisted/documented inputs, cite source/provenance rows, avoid investment advice or recommendations, and disclose derived/model status.
- If AI uses price-backed or market-profile context, preserve commercial fallback badges and suppress those sections in strict official mode.
- Existing deterministic Markdown export in `frontend/lib/investment-memo.ts` is not an LLM path; it is a useful non-AI baseline for any future memo/summarization UX.

Frontend placement:
- Add API client functions in `frontend/lib/api/ai.ts` and export them through `frontend/lib/api.ts`.
- Put company-specific AI UI in focused components under `frontend/components/company/` or `frontend/app/company/[ticker]/_components/`; avoid further bloating the default `page.tsx`.
- Reuse existing provenance components and source/freshness badges rather than creating parallel disclosure UI.

## Performance Instrumentation

Backend instrumentation:
- `app/performance_audit.py` defines `PerformanceAuditJSONResponse`, request metrics, SQLAlchemy instrumentation hooks, sanitized query strings, and snapshots/resets.
- `app/middleware/performance_audit.py` records route duration, SQL count/time, Redis/cache/upstream metrics, serialization time, payload bytes, and errors when audit or observability is enabled.
- `app/main.py` sets `PerformanceAuditJSONResponse` as the default response class.
- Internal endpoints are `GET /api/internal/performance-audit` and `POST /api/internal/performance-audit/reset`.

Frontend instrumentation:
- `frontend/lib/performance-audit.ts` installs `window.__FT_PERFORMANCE_AUDIT__` when `NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED=true`.
- `frontend/lib/api/client.ts` records network/cache/inflight-dedupe/background-revalidate behavior for API reads.
- `withPerformanceAuditSource()` tags calls by page route, scenario, and source; it is already used in company workspace loading, research-brief loading, prefetching, top-bar search, and audit scenarios.

Audit runner:
- `frontend/scripts/run-performance-audit.mjs` drives Playwright page-flow audits and backend hot-route benchmarks.
- It writes `artifacts/performance/baselines/performance-baseline.md` and `artifacts/performance/baselines/performance-baseline.json`.
- Current page flows include home search, top-bar search, `/company/[ticker]`, Models, Financials, and Watchlist.
- Current hot-route cases include search, financials, insider/institutional, activity overview, changes, earnings summary, capital structure, governance summary, models, peers, market/sector context, source registry, watchlist, and refresh queue.

## Test And Check Commands

Backend setup:
```bash
pip install -r requirements-dev.txt
docker compose up -d postgres redis
alembic upgrade head
```

Backend tests and guards:
```bash
python -m pytest
python scripts/check_architecture_boundaries.py
python scripts/check_migration_safety.py
python scripts/verify_docker_healthchecks.py
python scripts/run_model_evaluation.py --fixture historical_fixture_v1 --baseline-file scripts/model_evaluation_baseline.json --fail-on-delta --persist
python scripts/run_performance_regression_gate.py --baseline-file scripts/performance_regression_baseline.json --fail-on-regression
```

Frontend checks:
```bash
npm --prefix frontend install
npm --prefix frontend run test
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

CI targeted checks in `.github/workflows/ci.yml`:
```bash
pytest tests/test_architecture_boundaries.py tests/test_sec_edgar_refresh_orchestrator.py tests/test_fetch_trigger_dedupe.py tests/test_api_route_inventory.py tests/test_deployment_release_lock.py tests/test_docker_healthchecks.py tests/test_model_evaluation_harness.py tests/test_benchmark_infrastructure.py tests/test_hot_endpoint_contracts.py tests/test_macro_worker.py tests/test_refresh_worker.py
npm run test -- lib/api.routes.test.ts lib/api.auth.test.ts next.config.test.ts app/company/[ticker]/models/page.test.ts
npm run build
```

Release workflow:
- `.github/workflows/publish-images.yml` builds and pushes aligned backend/frontend Docker tags, then runs `python scripts/verify_deployment_compat.py --backend-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:3000 --ticker AAPL --wait-timeout 240`.

## Performance Audit Commands

Local audit prerequisites:
```bash
PERFORMANCE_AUDIT_ENABLED=true
NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED=true
```

Default local audit:
```bash
npm --prefix frontend run audit:performance -- --ticker AAPL
```

Expanded search-flow audit:
```bash
npm --prefix frontend run audit:performance -- --ticker AAPL --search-query AAPL --topbar-query MSFT --resolve-query NET
```

Custom ports:
```bash
npm --prefix frontend run audit:performance -- --ticker AAPL --frontend-url http://127.0.0.1:3000 --backend-url http://127.0.0.1:8000
```

Backend regression gate:
```bash
python scripts/run_performance_regression_gate.py --baseline-file scripts/performance_regression_baseline.json --fail-on-regression --json-out artifacts/performance/backend-performance-summary.json --markdown-out artifacts/performance/backend-performance-summary.md
```

## Suggested PR Order

1. Contract and provenance first: update docs, source registry ids, endpoint source-contract manifest entries, and schema tests before adding visible data or AI surfaces.
2. Backend service slice: add or change service/domain logic, persistence/cache reads, refresh policy, and deterministic backend tests without changing routers beyond registration.
3. API exposure: add thin router entries, schema serialization, handler compatibility exports, route inventory tests, source-contract tests, and architecture-boundary guard coverage.
4. Frontend data client and cache: add `frontend/lib/api/*` calls, cache policies, typed payload handling, and fallback/strict-mode UI states.
5. Frontend UI slice: compose focused route/components, preserve provenance/freshness/fallback badges, and update Vitest/Playwright coverage for important states.
6. Performance pass: run the local audit or backend regression gate, reduce request fan-out/payload weight if needed, and update performance docs only when a new baseline is intentionally accepted.
7. Release compatibility: run build/test gates, preserve route URLs and Docker tag alignment, and update release docs/checks only when release behavior changes.
