# Fundamental Terminal

Fundamental Terminal is an official-source-first research workspace for U.S. public equities. It turns SEC filings, XBRL companyfacts, and selected public macro datasets into a faster workflow for building a company view, comparing businesses, screening for ideas, and monitoring what changed.

The product is built around a simple idea: public market research should be easier to trust. Core company views stay anchored to official disclosures, fallback market context is labeled when it appears, and the app keeps freshness, provenance, and background refresh state visible instead of hiding it behind a black box.

## What Is In The App Today

- Research launcher with ticker, company, and CIK search, live refresh status, macro backdrop, data-health summary, recent companies, and local watchlist context.
- Company workspace with a research brief, financials, charts, models, peers, earnings, filings, events, capital markets, governance, ownership and stakes, insiders, and SEC feed sections.
- Official Screener for official/public-only cross-sectional discovery with saved browser-local presets, ranking-aware sorts, and quality filters.
- Compare workspace for side-by-side statements, derived operating metrics, and model outputs across up to five tickers.
- Watchlist workspace for browser-local triage, thesis notes, valuation gaps, alerts, and upcoming filing or reporting dates.
- Data Sources workspace for source registry visibility, strict official mode behavior, recent source errors, and shared hot-cache diagnostics.
- Point-in-time research support on major company endpoints through `as_of` so historical workflows avoid lookahead leakage.

## Why It Is Different

- Official-source-first fundamentals from the SEC and other public agencies.
- Transparent provenance with freshness, source mix, fallback disclosures, and confidence flags.
- Cache-first request paths with background refreshes instead of live-fetching every page view.
- Local-first saved companies, notes, and watchlist behavior without requiring an account.
- Published Docker images for quick setup, with local-source builds available for maintainers.

## Source Policy

Fundamental Terminal is official-source-first, not official-source-only at all costs.

- Core fundamentals, filings, ownership, governance, and most research views are built from official public sources.
- Derived views are labeled as internal outputs built on top of those official inputs.
- Commercial fallbacks stay narrow, explicit, and are used for non-core market context where official coverage is not practical.
- `STRICT_OFFICIAL_MODE=true` removes those fallback-backed surfaces entirely.

## Screenshots

### Home Launcher

![Home launcher with macro and data-health panels](docs/screenshots/home-search.png)

Search is the entry point, but the launcher now keeps macro context, source health, recent companies, saved names, and background refresh activity in the same workspace.

### Research Brief

![Company research brief for Apple](docs/screenshots/company-overview.png)

The default company page is now a research brief: snapshot first, plain-English framing, risk signals, filing context, and quick paths into deeper workspaces.

### Charts Dashboard

![Charts dashboard for Apple](docs/screenshots/charts-dashboard.png)

The charts workspace separates reported history from projected scenarios and gives each chart a clear modeling context instead of treating it like a generic chart gallery.

### Valuation Models

![Valuation models workspace for Intel](docs/screenshots/company-models.png)

Models stay connected to source freshness, assumption provenance, and background refresh controls so valuation work is visible and debuggable.

### Watchlist Workspace

![Watchlist workspace with cross-company triage](docs/screenshots/watchlist.png)

Saved companies, local notes, valuation gaps, status, and calendar items roll up into a browser-local triage surface for follow-up work.

### Data Sources

![Data sources workspace with source registry and health panels](docs/screenshots/data-sources.png)

The transparency view exposes source tiers, strict official mode behavior, cache coverage, recent source errors, and hot-cache visibility in one place.

### Mobile Company View

![Mobile company workspace](docs/screenshots/mobile-company.png)

On phones, the company workspace shifts to a compact section picker and stacked next-step actions so research stays usable on smaller screens.

## Quick Start With Docker

The default compose file pulls the published images from Docker Hub.

```bash
cp .env.example .env
# Edit .env and set required secrets (at minimum POSTGRES_PASSWORD and DATABASE_URL).
docker compose pull
docker compose up -d
python scripts/verify_deployment_compat.py --backend-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:3000 --ticker AAPL
```

After startup:

- Frontend: `http://127.0.0.1:3000`
- Backend API: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`

By default, the published deploy uses:

- `gptvibe/fundamentalterminal:backend-latest`
- `gptvibe/fundamentalterminal:frontend-latest`

To pin a matched release instead of `latest`, set both image references in `.env`:

```bash
BACKEND_IMAGE=gptvibe/fundamentalterminal:backend-v1.0.3
FRONTEND_IMAGE=gptvibe/fundamentalterminal:frontend-v1.0.3
```

To build from your checked-out source instead of pulling published images:

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d
```

For deployments around 1 GB RAM, add the dedicated small-host override so the worker competes less aggressively with API traffic:

```bash
docker compose -f docker-compose.yml -f docker-compose.small-host.yml up -d
```

For local source builds:

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml -f docker-compose.small-host.yml up --build -d
```

To smoke-check the frontend container standalone production server directly:

```bash
docker build -f frontend/Dockerfile -t fundamental-terminal-frontend:standalone ./frontend
docker run --rm -p 3000:3000 -e BACKEND_API_BASE_URL=http://host.docker.internal:8000 fundamental-terminal-frontend:standalone
```

Then verify it responds:

```bash
curl -f http://127.0.0.1:3000/
```

The small-host override keeps the main compose defaults unchanged for larger machines, but applies these safer worker settings on constrained hosts:

- backend and worker DB pools pinned to `5` with `5` overflow
- idle queue polling relaxed to `5s`
- worker startup delayed by `120s`
- scheduled refresh scope narrowed to `AAPL MSFT`
- worker-driven macro refresh disabled
- optional S&P 500 prewarm capped to `core` mode with a `25` ticker limit

## Local Development

Install backend dependencies:

```bash
pip install -r requirements-dev.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

Start local infrastructure:

```bash
docker compose up -d postgres redis
```

Run migrations:

```bash
alembic upgrade head
```

Set local environment variables and start the backend:

```bash
set DATABASE_URL=postgresql+psycopg://fundamental:fundamental@localhost:5432/fundamentals
set REDIS_URL=redis://localhost:6379/0
set SEC_USER_AGENT=FundamentalTerminal/1.0 (contact@example.com)
set MARKET_USER_AGENT=FundamentalTerminal/1.0 (contact@example.com)
uvicorn app.main:app --reload
```

Start the frontend in another shell:

```bash
cd frontend
set BACKEND_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

Useful optional environment variables live in [.env.example](.env.example).

To verify the checked-in Docker health checks without starting the stack:

```bash
python scripts/verify_docker_healthchecks.py
```

## Production Hardening

The app now includes:

- public API rate limiting with configurable limits and proxy awareness
- opt-in auth enforcement for internal routes through bearer-token or forwarded-user modes
- `/health` component checks for API, DB, Redis/cache backend, worker heartbeat visibility, and SEC upstream reachability
- security headers on backend responses and frontend pages
- a migration safety guard that runs before backend container migrations

The public API limiter uses its own Redis key namespace by default:

- `RATE_LIMIT_NAMESPACE=ft:rate-limit`

That namespace is intentionally separate from `HOT_RESPONSE_CACHE_NAMESPACE` so hot-cache flushes do not wipe rate-limit counters unless you explicitly point them back at the same prefix.

Operator guides:

- [docs/deployment-runbook.md](docs/deployment-runbook.md)
- [docs/postgres-backup-restore.md](docs/postgres-backup-restore.md)

If you want frontend-driven auth, the shared API client exposes `setApiAuthHeadersProvider(...)` in `frontend/lib/api.ts` so an app-specific auth layer can inject bearer or forwarded-user headers without rewriting every request helper.

## Observability

The backend now ships with a lightweight internal observability layer for API routes, workers, cache activity, and upstream fetches.

- `OBSERVABILITY_ENABLED=true` keeps the lightweight tracing middleware on. This is the default and powers `/api/internal/observability`.
- `OBSERVABILITY_ENABLED=false` disables request and worker trace collection if you want the lowest-overhead local or production runtime.
- `OBSERVABILITY_MAX_RECORDS=5000` controls how many recent request and worker records stay in memory for the internal endpoint.
- `PERFORMANCE_AUDIT_ENABLED=true` keeps the legacy request-audit workflow explicitly enabled if you still use `/api/internal/performance-audit` during deep route triage.

The main internal endpoint is:

- `/api/internal/observability`

It reports:

- route duration with DB, Redis, upstream, serialization, and residual calculation time buckets
- cache hit / stale / miss counts from the shared hot cache path
- singleflight wait counts and total wait time
- upstream request counts and durations
- worker job durations and aggregate failed refresh count

The route-level breakdown is intended to answer a simple question quickly: when a route is slow, is the time in DB work, Redis/cache coordination, upstream fetches, JSON serialization, or application-side calculation.

For a longer operator guide, see [docs/observability.md](docs/observability.md).

Recent backend performance optimization outcomes are captured in [docs/performance-notes.md](docs/performance-notes.md).

## Key Workspaces

- `/` - research launcher with search, macro backdrop, data health, recent companies, saved names, and recent change feed.
- `/screener` - official/public-only screener with saved local presets and ranking-aware sorting.
- `/watchlist` - browser-local triage board for saved names, notes, alerts, valuation gaps, and calendar items.
- `/compare?tickers=AAPL,MSFT` - side-by-side company comparison for statements, metrics, and model outputs.
- `/data-sources` - source registry, cache coverage, source health, and strict official mode visibility.
- `/company/[ticker]` - research brief workspace.
- `/company/[ticker]/financials` - dedicated statements, derived metrics, charts, provenance, and bank-specific regulated-financial view.
- `/company/[ticker]/charts` - reported-versus-forecast chart dashboard with scenario framing and an explicit routing gate that keeps banks / regulated financials off the industrial forecast path.
- `/company/[ticker]/models` - valuation workbench with DCF, reverse DCF, ROIC, and assumption context.
- `/company/[ticker]/peers` - peer comparison workspace.
- `/company/[ticker]/oil` - oil scenario overlay for supported companies.

## Key API Examples

```bash
GET  /health
GET  /readyz
GET  /api/companies/search?query=intel
GET  /api/companies/resolve?query=INTC
GET  /api/companies/AAPL/financials
GET  /api/companies/AAPL/financials?as_of=2025-02-01
GET  /api/companies/AAPL/models?model=dcf,reverse_dcf,roic,ratios
GET  /api/companies/AAPL/peers?peers=MSFT,NVDA&as_of=2025-02-01
GET  /api/companies/AAPL/changes-since-last-filing
GET  /api/companies/AAPL/financial-restatements
GET  /api/jobs/{job_id}/events
POST /api/companies/AAPL/refresh
```

Useful diagnostics endpoints:

- `/api/source-registry`
- `/api/internal/cache-metrics`
- `/api/internal/observability`
- `/api/model-evaluations/latest`

## Testing And Diagnostics

Backend tests:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Frontend tests:

```bash
cd frontend
npm test
```

Targeted performance and reliability checks:

```bash
python scripts/benchmark_hot_endpoints.py --base-url http://127.0.0.1:8000 --ticker AAPL --rounds 20
python scripts/benchmark_api_routes.py --base-url http://127.0.0.1:8000 --ticker AAPL --compare-tickers AAPL,MSFT --rounds 12 --cache-mode both --json-out artifacts/performance/api-route-benchmark.json
python scripts/benchmark_derived_metrics_price_matching.py --financial-rows 240 --price-rows 20000 --rounds 5
python scripts/run_performance_regression_gate.py --baseline-file scripts/performance_regression_baseline.json --fail-on-regression --json-out artifacts/performance/backend-performance-summary.json --markdown-out artifacts/performance/backend-performance-summary.md
python scripts/run_model_evaluation.py
```

Backfill calculation-versioned model rows after a valuation-basis migration:

```bash
python scripts/backfill_model_cache.py --help
python scripts/backfill_model_cache.py --preflight-only
python scripts/backfill_model_cache.py --dry-run --tickers AAPL --models dcf reverse_dcf piotroski --limit 1
python scripts/backfill_model_cache.py --dry-run --tickers AAPL,MSFT HIMS --models dcf reverse_dcf piotroski --limit 5
python scripts/backfill_model_cache.py --tickers AAPL MSFT HIMS --models dcf reverse_dcf piotroski
python scripts/backfill_model_cache.py --all --models dcf reverse_dcf piotroski
```

Useful operational notes:

- `--preflight-only` / `--check-db` creates the DB engine/session, runs `SELECT 1`, prints connectivity status, and exits without scanning cache rows.
- `--db-timeout-seconds` defaults to `15` and is applied to DB connect time plus PostgreSQL `statement_timeout` where supported.
- `--limit` caps ticker/model work items after scope expansion, which is useful for safe first-pass dry runs.
- `--tickers` and `--models` accept space-delimited values plus comma-separated groups.
- `--dry-run` never writes. It reports exactly which rows would be recomputed, which are skipped, and any failures discovered while selecting work.

The backfill script is resumable. It logs engine/session creation, DB preflight, cache-row query phases, and per-row outcomes. Each ticker/model row is emitted as JSON with `old_version`, `new_version`, `status`, and `reason`.

How to read row output:

- `status=would_recompute`: the row is stale, legacy, or missing and would be recomputed in a real run.
- `status=recomputed`: a new row was written for the current calculation version.
- `status=cached`: another current row already existed by recompute time, so no new write was needed.
- `status=skipped`: the row was already current, produced no new model output, or a newer calculation version already exists and will not be overwritten.
- `status=failed`: the requested ticker was missing, the DB preflight/query failed, or the recomputation raised an error.

On non-PostgreSQL URLs, the script still enforces bounded pool/connect waits but may not be able to apply SQL statement timeouts directly.

## Architecture Notes

- Public routes still mount from `app.main:app`, while domain routers live under `app/api/routers/`.
- Shared request and response models live under `app/api/schemas/`.
- Cache-first persisted views queue background refreshes when data is missing or stale instead of performing live SEC fetches on the hot request path.
- Frontend read endpoints use stale-while-revalidate and request dedupe in `frontend/lib/api.ts`.
- Refresh progress streams over Server-Sent Events from `/api/jobs/{job_id}/events`.

## Further Reading

- [docs/backend-architecture-boundaries.md](docs/backend-architecture-boundaries.md)
- [docs/api-route-benchmark-harness.md](docs/api-route-benchmark-harness.md)
- [docs/cache-layers-architecture.md](docs/cache-layers-architecture.md)
- [docs/data-provenance.md](docs/data-provenance.md)
- [docs/model-evaluation-harness.md](docs/model-evaluation-harness.md)
- [docs/deployment-runbook.md](docs/deployment-runbook.md)
- [docs/performance-freshness-orchestration.md](docs/performance-freshness-orchestration.md)
- [docs/postgres-backup-restore.md](docs/postgres-backup-restore.md)
- [docs/release-process.md](docs/release-process.md)
- [docs/sec-expansion-roadmap.md](docs/sec-expansion-roadmap.md)
- [docs/sec-expansion-checklist.md](docs/sec-expansion-checklist.md)

## Docker Image Publishing

The GitHub Actions workflow at `.github/workflows/publish-images.yml` publishes Docker images:

- Push to `main` publishes `backend-latest` and `frontend-latest`.
- Push a version tag like `v1.0.3` publishes `backend-v1.0.3` and `frontend-v1.0.3`.
- The publish workflow now runs a compatibility smoke check against the published frontend/backend image pair, including `/api/companies/{ticker}/workspace-bootstrap`.

Required repository secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`
