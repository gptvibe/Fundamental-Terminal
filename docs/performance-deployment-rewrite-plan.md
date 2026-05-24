# Performance and Deployment Rewrite Plan

## Goal

Make Fundamental Terminal faster to load, cheaper to operate, and easier to deploy without changing what the product is.

This is a partial rewrite of read-path execution and deployment defaults, not a product reset. The current company routes, specialist workspaces, charts, source disclosures, refresh behavior, watchlist, screener, compare, and data-sources views stay available. The SEC-first/public-data-first trust model remains the constraint that every performance shortcut must respect.

## Operating Principles

- Preserve stable URLs and public API response contracts. Any breaking contract change must ship as an additive version, alias, redirect, or compatibility adapter first.
- Keep `/company/[ticker]` as the Research Brief with the six-section flow: snapshot, what changed, business quality, capital/risk, valuation, and monitor.
- Keep charts, projection studio, share snapshots, model pages, financials, ownership, governance, filings, events, compare, screener, watchlist, and data sources reachable.
- Keep official data dominant. Do not add unofficial fundamentals providers or hide SEC/public-data provenance.
- Keep Yahoo Finance limited to clearly labeled price, volume, and market-profile fallback context.
- When `STRICT_OFFICIAL_MODE=true`, do not expose fallback-backed price or market-profile payloads or UI.
- Keep routers thin, orchestration in `app/services/`, and `app.main` as the compatibility boundary for public handler serialization.
- Prefer persisted or cache-first endpoints for company research surfaces. Do not add live SEC fetches or expensive recomputation to normal request paths.

## Current State

The repo is already pointed in the right direction:

- Persisted/cache-first foundations exist: hot-response cache, `dataset_refresh_state`, route timing, performance audit tooling, batch preload helpers, company workspace bootstrap, and persisted brief/chart snapshots.
- Existing snapshot tables include `company_research_brief_snapshots` and `company_charts_dashboard_snapshots`.
- Existing bootstrap support includes `sections` and `compact=true` query options, but the route can still assemble expensive payloads on a hot-cache miss.
- Existing deployment support includes `.env.lite.example` and `docker-compose.lite.yml`, but the default compose graph still treats Redis and the separate data-fetcher as normal-path services.
- Existing frontend read caching and lazy islands reduce repeated work, but first-load company pages can still fan out across endpoint-shaped payloads and oversized compatibility responses.

The rewrite should deepen these foundations rather than replace them.

## Target Architecture

### 1. Read Models Before Request-Path Composition

Company research routes should read versioned, page-ready or section-ready payloads keyed by company, `as_of`, schema version, and source fingerprint.

Use these persisted read models:

- `company_research_brief_snapshots`: default read source for `/api/companies/{ticker}/brief` and the six Research Brief sections.
- `company_charts_dashboard_snapshots`: default read source for `/api/companies/{ticker}/charts` baseline dashboard reads.
- New `company_workspace_bootstrap_snapshots`: compact first-load payload for `/company/[ticker]`.
- New optional `company_route_payload_snapshots`: generic persisted payloads for stable specialist summaries where a dedicated table would be premature.

Existing snapshot rows can keep metadata in `payload` during migration, but every read model must eventually expose or derive:

- `schema_version`
- `source_fingerprint`
- `source_mix`
- `provenance[]`
- `as_of`, `last_checked`, and freshness state
- confidence flags
- fallback flags and strict-official-mode eligibility

Normal handlers should do one of three things:

- Return a fresh persisted payload.
- Return a stale persisted payload with freshness/provenance cues and queue refresh.
- Return a minimal building/partial payload and queue refresh.

Normal handlers should not perform live SEC fetches, model recomputation, chart dashboard rebuilding, or cross-surface composition for core company research reads.

### 2. Background Builders Own Composition

Move expensive composition into idempotent builders run by refresh jobs, prewarm tasks, or explicit maintenance commands:

- Research brief builder composes financials, changes, activity, governance, ownership, capital markets, models, peers, and monitor cues into one persisted brief payload.
- Charts builder composes reported series, forecast cards, event overlays, forecast stability, chart specs, and projection-studio baseline data into one persisted dashboard payload.
- Bootstrap builder writes a compact first-load payload with first-viewport company summary, latest financials, recent filings/events, source freshness, warnings, and enough brief metadata to render the Research Brief shell immediately.
- Specialist builders write persisted summaries for capital structure, earnings, governance, ownership, peers, models, compare, watchlist, and screener only where benchmarks show repeated request-path composition.

Builder rules:

- Builders are idempotent for `(company_id, as_of_key, schema_version, source_fingerprint)`.
- Builders record input source ids and freshness in the payload metadata.
- Builders reuse existing refresh queue and SSE status plumbing.
- Builders may call expensive SEC/model/chart services; request handlers may not.
- Failed builders leave the previous good snapshot readable and mark the queued refresh as failed with operator-visible diagnostics.

### 3. Compatibility Adapters, Not Contract Churn

Public routes remain stable while internals move behind read models:

- `/api/companies/{ticker}/financials` still returns `CompanyFinancialsResponse`.
- `/api/companies/{ticker}/brief` still returns `CompanyResearchBriefResponse`.
- `/api/companies/{ticker}/charts` still returns `CompanyChartsDashboardResponse`.
- `/api/companies/{ticker}/workspace-bootstrap` remains the first-load route and keeps legacy include flags while promoting `sections` and `compact=true`.

The adapter layer should deserialize persisted payloads into the existing response models, apply strict-official-mode suppression, attach fallback disclosures, and keep monkeypatch-heavy compatibility tests stable through `app.main`.

Migration mode should be explicit:

- `observe`: build snapshots in the background, compare to live legacy output, but serve legacy output.
- `prefer_snapshot`: serve valid snapshots; fall back to legacy builders with structured warnings.
- `snapshot_only`: serve snapshots, stale snapshots, or queued/building payloads; no request-path rebuilds.

The final state is `snapshot_only` for company brief, bootstrap, and charts warm paths.

### 4. Frontend Loader Rewrite

Keep the UI, change the loading model:

- `/company/[ticker]` first load requests one compact bootstrap payload.
- Six Research Brief sections hydrate from embedded bootstrap/brief data wherever possible.
- Specialist tabs reuse the bootstrap, brief, or route read-model payload already in the frontend cache when navigating from the brief.
- Fallback section fetches exist only for explicit retry, direct subroute entry, or compatibility gaps.
- Idle prefetch is budget-aware: at most two low-priority requests, disabled during active refresh, disabled in low-data mode, and measured by the performance audit.
- Charts remain dynamically loaded, but the server route reads one persisted chart snapshot on baseline GET.

The frontend must keep provenance, freshness, fallback, strict-official, and building/stale states visible. Faster cannot mean less honest.

### 5. Deployment Profiles

Make the easiest path the smallest path that still preserves the product:

- `lite`: Postgres, backend-with-worker, and frontend. Redis disabled by default, S&P 500 prewarm disabled, macro worker disabled, one Uvicorn worker, small DB pool.
- `standard`: Postgres, Redis, backend, data-fetcher, and frontend. Prewarm remains opt-in.
- `prewarm`: explicit profile for S&P 500 or broad-universe warmup.

Implementation details:

- Add `APP_PROFILE` to `app/config.py` and centralize profile defaults there instead of scattering defaults across compose files and shell scripts.
- Split compose so `lite` does not start or depend on Redis unless `REDIS_URL` is explicitly configured.
- Merge API serving and queue consumption for `lite`; keep the separate data-fetcher for `standard`.
- Keep Redis as an accelerator for shared hot cache and coordination, not a single-host availability requirement.
- Ensure `/health`, `/readyz`, and `/api/internal/cache-metrics` report whether cache coordination is `redis_active`, `redis_degraded`, `local_memory_fallback`, or `disabled_by_profile`.

Later, add an optional all-in-one image for demos and small machines:

- One container runs FastAPI, the queue worker, and the Next standalone server.
- Postgres remains separate.
- This image is optional; separated frontend/backend images remain the production default.

### 6. Smaller Operator Config Surface

The first-run environment file should ask for only decisions an operator truly needs to make.

Required for local Docker:

```env
POSTGRES_PASSWORD=change_me
SEC_USER_AGENT=FundamentalTerminal/1.0 (you@example.com)
APP_PROFILE=lite
STRICT_OFFICIAL_MODE=true
```

Common optional settings:

```env
AUTH_MODE=off
AUTH_BEARER_TOKEN=
NEXT_PUBLIC_DEMO_MODE=false
BACKEND_IMAGE=
FRONTEND_IMAGE=
```

Everything else should be one of:

- A code default in `app/config.py`.
- A profile default for `lite`, `standard`, or `prewarm`.
- An advanced override documented in `.env.advanced.example` and the deployment runbook.

Compose should build `DATABASE_URL`, `REDIS_URL`, and `BACKEND_API_BASE_URL` from service names by default so users do not copy connection strings by hand. If a setting is needed only for tuning, benchmarking, or heavy ingestion, it belongs outside the main `.env.example`.

## Rewrite Phases

### Phase 0: Baseline and Contract Freeze

- Run backend and frontend test suites.
- Run `npm --prefix frontend run audit:performance -- --ticker AAPL`.
- Save frozen fixtures for brief, charts, workspace bootstrap, financials, compare, watchlist, screener, and data-sources route shapes.
- Add contract tests for provenance fields, fallback labels, strict official mode, chart payload versions, and building/stale snapshot states.
- Record request count, p95 latency, SQL count, serialization time, and payload bytes for cold and warm paths.

Exit criteria:

- Baselines exist before internals move.
- Compatibility fixtures cover the public routes this rewrite touches.
- The architecture boundary guard passes before the first refactor.

### Phase 1: Deployment Profile Hardening

- Add centralized `APP_PROFILE` handling and profile defaults in `app/config.py`.
- Make Redis truly opt-in for `lite`; remove backend startup dependency on Redis in that profile.
- Run the queue worker inside the backend service for `lite`.
- Keep `sp500-prewarm` behind the explicit `prewarm` profile.
- Replace the main `.env.example` with a short operator file and move advanced knobs to `.env.advanced.example`.
- Update README and `docs/deployment-runbook.md` so the lite path is the default quickstart.

Exit criteria:

- A fresh user can run the app with Postgres, backend, and frontend only.
- Existing standard deployment still works with Redis and a separate data-fetcher.
- Health/cache endpoints clearly distinguish disabled, degraded, fallback, and active cache coordination.

### Phase 2: Snapshot Schema and Builder Contracts

- Add `company_workspace_bootstrap_snapshots`.
- Add generic route payload snapshots only for summaries selected by benchmark evidence.
- Formalize source fingerprint helpers in `app/services/`.
- Define payload metadata contracts shared by brief, bootstrap, charts, and specialist summaries.
- Backfill or rebuild snapshots for seeded companies.
- Add migration safety checks for new tables, indexes, uniqueness constraints, and JSON defaults.

Exit criteria:

- Snapshot tables can store versioned payloads and freshness/provenance metadata.
- Builders can upsert snapshots idempotently.
- `alembic upgrade head` and `python scripts/check_migration_safety.py` pass.

### Phase 3: Builder Migration

- Move bootstrap composition into a background builder.
- Move chart missing/legacy rebuilds out of `/api/companies/{ticker}/charts` GET paths.
- Ensure research brief snapshot refresh covers all six sections and explicit partial/building states.
- Keep slow legacy builders only behind migration mode, structured logs, and removal issues.
- Add deterministic tests for stale snapshot serving, missing snapshot queueing, strict official mode suppression, and previous-good-snapshot behavior after builder failure.

Exit criteria:

- Warm `/brief`, `/charts`, and `/workspace-bootstrap` are mostly one snapshot read plus model serialization.
- Missing or stale data queues refresh without blocking on live fetch/recompute.
- Legacy request-path builders are observable and removable.

### Phase 4: Handler Adapter Rewrite

- Keep public route functions and response models.
- Replace per-route composition with snapshot loads and compatibility serialization.
- Apply strict official mode and fallback disclosure logic at the adapter boundary.
- Add route-level query-count tests for workspace bootstrap, charts, brief, compare, watchlist, screener, and data sources.
- Keep `app/api/routers/`, `app/api/schemas/`, `app/services/`, and `app.main` boundaries aligned with `docs/backend-architecture-boundaries.md`.

Exit criteria:

- API response shapes match frozen fixtures.
- `python scripts/check_architecture_boundaries.py` passes.
- Warm company page routes show lower SQL count, lower serialization cost, and no request-path rebuild warnings.

### Phase 5: Frontend Loader Rewrite

- Update `useCompanyWorkspace` to request compact sectioned bootstrap by default.
- Prefer embedded brief/bootstrap payloads for all six Research Brief sections.
- Reuse cached read-model payloads across brief, financials, models, peers, and charts navigation.
- Cap idle prefetch and make it visible in the performance audit.
- Keep chart and grid dynamic imports; remove accidental direct heavy imports from default company routes.
- Add frontend tests for stale/building payload rendering, strict official mode hiding, and fallback disclosure persistence.

Exit criteria:

- Cold `/company/AAPL` stays within the documented request budget.
- Warm navigation between Brief, Financials, Models, Peers, and Charts reuses cached payloads.
- Provenance, freshness, fallback, and strict-official UI states remain visible.

### Phase 6: Charts and What-If Optimization

- Persist chart spec and all baseline series in `company_charts_dashboard_snapshots`.
- Store forecast accuracy as a snapshot-backed read instead of rebuilding it on baseline GET.
- Make what-if requests recompute only the changed projection layer from persisted baseline inputs.
- Keep share snapshots and Open Graph image routes stable.

Exit criteria:

- `/api/companies/{ticker}/charts` is a snapshot read on warm baseline paths.
- `/api/companies/{ticker}/charts/what-if` avoids rebuilding unrelated cards, baseline series, and provenance.
- Chart UI, share URLs, and chart payload versions remain compatible.

### Phase 7: Cutover and Cleanup

- Move brief, bootstrap, and charts to `snapshot_only` mode.
- Remove or demote legacy request-path builders once fixtures and performance budgets are stable.
- Update deployment docs, cache docs, performance docs, and architecture docs.
- Run full backend tests, frontend tests, lint, typecheck, build, migration safety, architecture guard, and performance audit.
- Promote performance budgets to CI or release-check gates.

Exit criteria:

- Lite deployment is the default README quickstart.
- Standard and prewarm profiles remain documented for heavier use.
- Warm company research routes no longer depend on request-path composition.
- Performance budgets are enforced, not just documented.

## Success Targets

- `/company/[ticker]` cold load: at most 6 blocking backend requests.
- `/company/[ticker]` warm load: at most 3 blocking backend requests.
- Warm `/api/companies/{ticker}/brief`: p95 under 150 ms on local Docker after data is warm.
- Warm `/api/companies/{ticker}/workspace-bootstrap`: p95 under 150 ms on local Docker after data is warm.
- Warm `/api/companies/{ticker}/charts`: p95 under 150 ms on local Docker after data is warm.
- Warm chart baseline GET: no heavy chart recomputation.
- Main `.env.example`: under 12 operator-facing variables.
- Default Docker quickstart: no Redis and no prewarm container required.
- No loss of provenance, freshness, fallback labeling, strict official mode behavior, or route compatibility.

## Primary Risks and Controls

- Snapshot staleness could make the UI fast but wrong. Control it with source fingerprints, schema versions, freshness badges, invalidation tests, and previous-good-snapshot semantics.
- Compatibility adapters could preserve duplicate code for too long. Control it with migration modes, structured warnings, ownership notes, and removal issues for every fallback.
- Redis-free lite mode reduces cross-process cache reuse. Control it with one backend worker, DB-backed queue claiming, clear cache-mode health reporting, and standard profile documentation.
- Compact payloads could drop provenance. Control it with contract tests requiring `provenance[]`, `source_mix`, confidence flags, fallback labels, and strict official mode suppression.
- Builder failures could hide behind stale payloads. Control it with visible stale/building states, SSE job events, operator logs, and health summaries.
- Snapshot schemas could ossify too early. Control it with versioned payloads, compatibility adapters, and fixture-based contract tests before removing legacy paths.

## First Implementation Slice

Start with the smallest slice that improves setup and the default company load without touching every specialist workspace:

1. Centralize `APP_PROFILE=lite` defaults and make Redis optional in the lite compose path.
2. Shorten `.env.example`; move advanced knobs to `.env.advanced.example`.
3. Add `company_workspace_bootstrap_snapshots` with metadata for schema version, source fingerprint, provenance, source mix, freshness, confidence, and fallback flags.
4. Add a bootstrap builder that persists the compact first-load payload.
5. Teach `/api/companies/{ticker}/workspace-bootstrap` to prefer the snapshot, queue refresh on stale/missing data, and avoid request-path composition in `snapshot_only` mode.
6. Update `useCompanyWorkspace` to request `sections=company_summary,latest_financials,recent_filings,recent_events,source_freshness,warnings&compact=true` for the default brief load.
7. Add performance audit assertions for company page request count, bootstrap payload bytes, and warm bootstrap latency.

This slice gives users a simpler first run and attacks the highest-impact company-page bottleneck while keeping specialist workspaces, route contracts, and source-policy behavior intact.
