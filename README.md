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
# Set APP_IMAGE_TAG to one published release tag, for example v1.0.3.
docker compose pull
docker compose up -d
python scripts/verify_deployment_compat.py --backend-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:3000 --ticker AAPL
```

After startup:

- Frontend: `http://127.0.0.1:3000`
- Backend API: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`

The deploy-time image pattern is:

- `gptvibe/fundamentalterminal:backend-${APP_IMAGE_TAG}`
- `gptvibe/fundamentalterminal:frontend-${APP_IMAGE_TAG}`

Use one shared tag suffix in `.env` to keep frontend, backend, and the data-fetcher on the same published revision:

```bash
APP_IMAGE_TAG=v1.0.3
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
pip install -r requirements.txt
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
uvicorn app.main:app --reload
```

Start the frontend in another shell:

```bash
cd frontend
set BACKEND_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

Useful optional environment variables live in [.env.example](.env.example).

## Key Workspaces

- `/` - research launcher with search, macro backdrop, data health, recent companies, saved names, and recent change feed.
- `/screener` - official/public-only screener with saved local presets and ranking-aware sorting.
- `/watchlist` - browser-local triage board for saved names, notes, alerts, valuation gaps, and calendar items.
- `/compare?tickers=AAPL,MSFT` - side-by-side company comparison for statements, metrics, and model outputs.
- `/data-sources` - source registry, cache coverage, source health, and strict official mode visibility.
- `/company/[ticker]` - research brief workspace.
- `/company/[ticker]/financials` - dedicated statements, derived metrics, charts, provenance, and bank-specific regulated-financial view.
- `/company/[ticker]/charts` - reported-versus-forecast chart dashboard with scenario framing.
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
- `/api/model-evaluations/latest`

## Testing And Diagnostics

Backend tests:

```bash
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
python scripts/run_performance_regression_gate.py --baseline-file scripts/performance_regression_baseline.json --fail-on-regression --json-out artifacts/performance/backend-performance-summary.json --markdown-out artifacts/performance/backend-performance-summary.md
python scripts/run_model_evaluation.py
```

## Architecture Notes

- Public routes still mount from `app.main:app`, while domain routers live under `app/api/routers/`.
- Shared request and response models live under `app/api/schemas/`.
- Cache-first persisted views queue background refreshes when data is missing or stale instead of performing live SEC fetches on the hot request path.
- Frontend read endpoints use stale-while-revalidate and request dedupe in `frontend/lib/api.ts`.
- Refresh progress streams over Server-Sent Events from `/api/jobs/{job_id}/events`.

## Further Reading

- [docs/backend-architecture-boundaries.md](docs/backend-architecture-boundaries.md)
- [docs/cache-layers-architecture.md](docs/cache-layers-architecture.md)
- [docs/data-provenance.md](docs/data-provenance.md)
- [docs/model-evaluation-harness.md](docs/model-evaluation-harness.md)
- [docs/performance-freshness-orchestration.md](docs/performance-freshness-orchestration.md)
- [docs/release-process.md](docs/release-process.md)
- [docs/sec-expansion-roadmap.md](docs/sec-expansion-roadmap.md)
- [docs/sec-expansion-checklist.md](docs/sec-expansion-checklist.md)

## Docker Image Publishing

The GitHub Actions workflow at `.github/workflows/publish-images.yml` publishes Docker images:

- Push to `main` publishes commit-pinned images `backend-sha-<gitsha>` and `frontend-sha-<gitsha>`.
- Push a version tag like `v1.0.3` publishes `backend-v1.0.3` and `frontend-v1.0.3`.
- The publish workflow now runs a compatibility smoke check against the published frontend/backend image pair, including `/api/companies/{ticker}/workspace-bootstrap`.

Required repository secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`
