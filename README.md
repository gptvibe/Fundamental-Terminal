# Fundamental Terminal

Fundamental Terminal is a pull-first Dockerized SEC-first research terminal. It ingests SEC EDGAR submissions and XBRL company facts, normalizes them into a canonical financial schema, stores them in PostgreSQL, and serves a Next.js workspace for search, company research, valuation, earnings, ownership, and browser-local watchlists.

Banks and bank holding companies also support an official regulated-financial path built from FDIC quarterly BankFind financials and optional Federal Reserve FR Y-9C imports, while preserving the same public financials and metrics routes.

The macro context layer also supports official cyclical demand and cost modules from the U.S. Census Bureau, BEA, and BLS, with company-specific relevance filtering so only materially related indicators are emphasized per issuer.

The frontend is organized as a unified company workspace with grouped core views and research feeds, background-first refresh actions, printable research views, and a browser-local watchlist and notes layer.

## Screenshots

Captured from the current local app. The launcher example uses `AAPL`, while company workspace screenshots use `INTC`.

### Research Launcher

![Home research launcher with compact command bar](docs/screenshots/home-search.png)

The home launcher now combines search, live refresh status, and direct handoff into either the company workspace or valuation models from a single search.

### Company Overview

![Company overview workspace for INTC](docs/screenshots/company-overview.png)

The overview workspace keeps grouped core views and research feeds under one header, pairs price-versus-operating performance with side-rail actions, and surfaces local-save state without leaving the page.

### Valuation Models

![Valuation models workspace for INTC](docs/screenshots/company-models.png)

The models workspace now focuses on valuation conclusion, confidence, and scenario context, with background-first refresh controls, export support, and supporting model diagnostics.

### Watchlist Workspace

![Browser-local watchlist workspace](docs/screenshots/watchlist.png)

The watchlist workspace rolls saved companies, alert severity, freshness, valuation gaps, and note coverage into one browser-local triage surface.

### Mobile Company View

![Mobile company workspace for INTC](docs/screenshots/mobile-company.png)

The mobile layout swaps the desktop tab rail for a compact section picker and stacked next-step actions so the company workspace stays usable on phones.

## Roadmap

- See [docs/sec-expansion-roadmap.md](docs/sec-expansion-roadmap.md) for the phased SEC dataset expansion plan, including backend models, API contracts, frontend visualizations, and sprint ordering.
- See [docs/sec-expansion-checklist.md](docs/sec-expansion-checklist.md) for the task-by-task execution checklist.
- See [docs/cache-layers-architecture.md](docs/cache-layers-architecture.md) for the cache-first request-path and refresh orchestration rules.
- See [docs/backend-architecture-boundaries.md](docs/backend-architecture-boundaries.md) for router, schema, `app.main`, and service-layer ownership rules.
- See [docs/data-provenance.md](docs/data-provenance.md) for upstream source policy and diagnostics semantics.
- See [docs/performance-freshness-orchestration.md](docs/performance-freshness-orchestration.md) for performance, freshness, and benchmark notes.
- See [docs/model-evaluation-harness.md](docs/model-evaluation-harness.md) for historical backtesting, persisted evaluation runs, and CI gate rules.

## Canonical metrics

- `revenue`
- `gross_profit`
- `operating_income`
- `net_income`
- `total_assets`
- `total_liabilities`
- `cash_and_cash_equivalents`
- `short_term_investments`
- `cash_and_short_term_investments`
- `current_debt`
- `stockholders_equity`
- `accounts_payable`
- `depreciation_and_amortization`
- `operating_cash_flow`
- `free_cash_flow`

## Bank canonical metrics

- `net_interest_income`
- `provision_for_credit_losses`
- `deposits_total`
- `core_deposits`
- `uninsured_deposits`
- `loans_net`
- `net_interest_margin`
- `nonperforming_assets_ratio`
- `common_equity_tier1_ratio`
- `tier1_risk_weighted_ratio`
- `total_risk_based_capital_ratio`
- `tangible_common_equity`

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Set the database URL and SEC contact:

   ```bash
   set DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/database_name
   set SEC_USER_AGENT=FundamentalTerminal/1.0 (contact@example.com)
   ```

   Optional regulated-bank source configuration:

   ```bash
   set FDIC_API_BASE_URL=https://api.fdic.gov
   set FEDERAL_RESERVE_Y9C_JSON_URL=
   set FEDERAL_RESERVE_Y9C_JSON_PATH=
   ```

   `FEDERAL_RESERVE_Y9C_JSON_URL` or `FEDERAL_RESERVE_Y9C_JSON_PATH` can point to an official FR Y-9C JSON export when bank holding company coverage is needed.

   Optional macro source configuration:

   ```bash
   set CENSUS_API_BASE_URL=https://api.census.gov/data/timeseries/eits
   set CENSUS_API_KEY=
   set BLS_API_BASE_URL=https://api.bls.gov/publicAPI/v2/timeseries/data/
   set BLS_API_KEY=
   set EIA_API_BASE_URL=https://api.eia.gov/v2
   set EIA_API_KEY=
   set BEA_API_BASE_URL=https://apps.bea.gov/api/data
   set BEA_API_KEY=
   ```

   Get a BEA API key from https://apps.bea.gov/api/signup/, a BLS API key from https://data.bls.gov/registrationEngine/, and an EIA API key from https://www.eia.gov/opendata/register.php.
   `BEA_API_KEY` is required for official BEA PCE and GDP-by-industry pulls, `BLS_API_KEY` is used for official BLS v2 series requests, and `EIA_API_KEY` powers the official energy and power sector plug-in.

3. Run migrations:

   ```bash
   alembic upgrade head
   ```

Developer migration workflow:

```bash
alembic revision --autogenerate -m "describe_change"
alembic upgrade head
```

- Keep schema changes reviewable and paired with route/model tests.
- Prefer one migration per feature slice rather than mixing unrelated schema edits.
- If a migration changes persisted research payloads, update backend/frontend contracts and any hot-endpoint tests in the same change.

## Run as FastAPI

```bash
uvicorn app.main:app --reload
```

API composition notes:

- Public routes still mount from `app.main:app`, but route registration now happens through domain routers under `app/api/routers/`.
- Shared response/request models live under `app/api/schemas/`; importing from `app.main` remains compatible for existing tests and consumers.
- Route URLs and response payload shapes are unchanged by this refactor.
- Routers stay registration-only; refresh orchestration and dataset jobs live under `app/services/`, with `app.main` acting as the compatibility bridge.
- Run `python scripts/check_architecture_boundaries.py` to verify routers and services still respect the documented import boundaries.
- Pull requests and pushes to `main` also run `.github/workflows/ci.yml`, which checks the import boundaries and the targeted backend/frontend compatibility tests.
- The same CI workflow also runs a deterministic historical model-evaluation gate against `scripts/model_evaluation_baseline.json`; intentional model changes should update that baseline in the same change.

## Run the Next.js frontend

```bash
cd frontend
set BACKEND_API_BASE_URL=http://127.0.0.1:8000
npm install
npm run dev
```

The frontend proxies backend requests through `/backend/*` and exposes:

- `/` for the research launcher, SEC-backed resolution, and direct company/model handoff
- `/watchlist` — browser-local watchlist workspace for saved companies, note coverage, freshness, and triage filters
- `/company/[ticker]` — company overview workspace with grouped core views, research feeds, priority alerts, and quick peer context
- `/company/[ticker]/financials` — dedicated financial workspace with statements, derived metrics, provenance/quality diagnostics, and a bank-specific regulated-financial view for banks and bank holding companies
- `/company/[ticker]/peers` — dedicated peer-comparison workspace with fair-value gap, ROIC, implied growth, shareholder yield, and valuation-band percentile comparisons
- `/company/[ticker]/earnings` — earnings workspace with release trends, guidance and capital-return signals, and linked filing context
- `/company/[ticker]/filings` — filing timeline and parser insights with integrated filing-event views
- `/company/[ticker]/insiders` — Form 4 insider analytics plus Form 144 planned sale filings
- `/company/[ticker]/models` — valuation workbench with trust-aware DCF, reverse DCF heatmap, ROIC trend, capital-allocation stack, and assumption provenance
- `/company/[ticker]/models` now also includes a company-relevant official macro demand-and-cost panel built from Census M3/retail, BEA, and BLS data
- Model payloads now normalize `model_status` to `supported`, `partial`, `proxy`, `insufficient_data`, or `unsupported`, and each response includes `confidence_score`, `confidence_reasons`, `fields_used`, `proxy_usage`, `stale_inputs`, `sector_suitability`, and `misleading_reasons`.
- `/company/[ticker]/governance` — proxy filings, board & meeting history, vote outcomes panel, executive pay table, and pay trend chart
- `/company/[ticker]/ownership-changes` — beneficial ownership (SC 13D/G) with stake-change timeline, owner table, and activist signals
- `/company/[ticker]/ownership` — institutional holdings analytics and manager activity trends
- `/company/[ticker]/stakes` — legacy path redirected to `/company/[ticker]/ownership-changes`
- `/company/[ticker]/capital-markets` — registration statements, prospectuses, and late-filer notices
- `/company/[ticker]/events` — 8-K events classified by item code with category chart
- `/company/[ticker]/sec-feed` — unified SEC activity feed across all filing types

Personal workspace behavior:

- The `/watchlist` route, watchlist saves, and private notes are stored in browser-local `LocalUserData` only (no account and no backend persistence).
- Users can export/import this local data as JSON from the saved-companies panel and clear all local saves.
- Import is merge-by-default (with an explicit replace option), and clear-all requires confirmation.

Search accepts a ticker, company name, or CIK and shows SEC-backed resolution and autocomplete feedback. Invalid searches stay in the input, turn the field red, and raise a red toast that clears automatically after 3 seconds.

On phones, the `/company/[ticker]` view uses a compact section picker, stacked next-step actions, and hides the large top chrome to preserve space for charts and tables.

Real-time refresh progress streams over Server-Sent Events at `/api/jobs/{job_id}/events` and is rendered in the company console panels.

Frontend data-loading/performance strategy:

- Read endpoints use stale-while-revalidate with request dedupe in `frontend/lib/api.ts` instead of blanket `no-store` fetch behavior.
- Refresh queue and mutation endpoints remain uncached.
- Company route loading/error boundaries provide lightweight transitions while preserving deep-linkable routes.
- Heavy tables use row virtualization and chart-heavy sections are loaded as deferred client islands.

Model evaluation harness:

- `scripts/run_model_evaluation.py` backtests DCF, reverse DCF, residual income, ROIC, and earnings signals using historical snapshots only.
- Completed runs can be stored in PostgreSQL via `model_evaluation_runs` and surfaced through `/api/model-evaluations/latest`.
- The models workspace now includes the latest persisted evaluation summary with provenance, `as_of`, `last_refreshed_at`, and confidence metadata.

Reliability and diagnostics additions:

- Hot company payloads expose a `diagnostics` block with coverage, fallback, stale, parser-confidence, and missing-field metadata.
- Refresh jobs, model runs, and SSE events now share traceable job metadata (`job_id`, `trace_id`, `ticker`, `kind`).
- Golden parser fixtures and hot-endpoint contract tests help catch regressions before they reach persisted routes.
- Default-mode price and market-profile surfaces show a visible `commercial_fallback` disclosure whenever Yahoo-backed context is present, while strict official mode removes those fallbacks entirely.

Point-in-time research mode:

- Company research routes accept an optional `as_of` query parameter so financials, derived metrics, models, and peers can be rendered without lookahead leakage.
- Supported research routes include `/api/companies/{ticker}/financials`, `/metrics-timeseries`, `/metrics`, `/metrics/summary`, `/models`, and `/peers`.
- Date-only values are treated as end-of-day UTC. Full ISO-8601 timestamps are also accepted.
- The frontend automatically forwards `?as_of=...` from the current page URL when it calls these research endpoints.

Financial restatement tracking:

- `/api/companies/{ticker}/financial-restatements` summarizes persisted 10-K/A and 10-Q/A amendment chains, normalized field deltas, and companyfacts revisions already observed in SEC XBRL.
- Each restatement row includes changed metric keys, fact-level before/after context when available, and a confidence impact severity derived from the scope of the revision.
- The route also accepts `as_of` so amendment summaries can be reviewed without including later-known SEC corrections.

Changes since last filing:

- `/api/companies/{ticker}/changes-since-last-filing` compares the latest canonical filing against the prior comparable filing of the same form family.
- The payload highlights metric deltas, newly added filing-derived risk indicators, segment mix shifts, share-count changes, capital-structure changes, and amended prior values sourced from persisted restatements.
- The company overview page now includes a card for this comparison, and the route accepts `as_of` for point-in-time review.

## Docker Compose

1. Copy `.env.example` to `.env` and adjust secrets or ports as needed.
2. Start the full stack:

   ```bash
   docker compose pull
   docker compose up -d
   ```

   This compose file pulls the published Docker Hub images and does not build locally:

   - `gptvibe/fundamentalterminal:backend-latest`
   - `gptvibe/fundamentalterminal:frontend-latest`

   For local development from the checked-out source, keep `docker-compose.yml` as the pull-based default and opt into local builds with `docker-compose.build.yml`:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d
   ```

   That override builds these local images instead of pulling published ones:

   - `fundamental-terminal/backend:local`
   - `fundamental-terminal/frontend:local`

   To refresh to the newest published tags manually:

   ```bash
   docker compose pull
   docker compose up -d
   ```

3. Services on the compose network:
   - `backend` -> FastAPI on port `8000`
   - `data-fetcher` -> periodic refresh worker using `WORKER_IDENTIFIERS`
   - `sp500-prewarm` -> optional one-shot S&P 500 warm-up job (profile: `prewarm`)
   - `frontend` -> Next.js on port `3000`
   - `postgres` -> PostgreSQL on port `5432`
   - `redis` -> short-term cache on port `6379`

The stack uses environment variables for database and cache connectivity via `DATABASE_URL` and `REDIS_URL`, and all services communicate over the `fundamental-terminal-net` compose network.

API endpoints:

```bash
GET  /api/companies/search?query=intel
GET  /api/companies/search?ticker=AAPL
GET  /api/companies/resolve?query=INTC
GET  /api/companies/AAPL/financials
GET  /api/companies/AAPL/financials?as_of=2025-02-01
GET  /api/companies/AAPL/metrics-timeseries?cadence=ttm&max_points=24
GET  /api/companies/AAPL/metrics-timeseries?cadence=ttm&max_points=24&as_of=2025-02-01T21:00:00Z
GET  /api/companies/AAPL/metrics?period_type=ttm&as_of=2025-02-01
GET  /api/companies/AAPL/metrics/summary?period_type=ttm&as_of=2025-02-01
GET  /api/companies/AAPL/financial-history
GET  /api/companies/AAPL/changes-since-last-filing
GET  /api/companies/AAPL/changes-since-last-filing?as_of=2026-03-20
GET  /api/companies/AAPL/financial-restatements
GET  /api/companies/AAPL/financial-restatements?as_of=2026-03-20
GET  /api/companies/AAPL/filings
GET  /api/companies/AAPL/filings/view
GET  /api/companies/AAPL/filing-insights
GET  /api/companies/AAPL/insider-trades
GET  /api/companies/AAPL/form-144-filings
GET  /api/companies/AAPL/institutional-holdings
GET  /api/companies/AAPL/institutional-holdings/summary
GET  /api/companies/AAPL/beneficial-ownership
GET  /api/companies/AAPL/beneficial-ownership/summary
GET  /api/companies/AAPL/governance
GET  /api/companies/AAPL/governance/summary
GET  /api/companies/AAPL/capital-markets
GET  /api/companies/AAPL/capital-markets/summary
GET  /api/companies/AAPL/events
GET  /api/companies/AAPL/filing-events
GET  /api/companies/AAPL/filing-events/summary
GET  /api/companies/AAPL/executive-compensation
GET  /api/companies/AAPL/peers
GET  /api/companies/AAPL/peers?peers=MSFT,NVDA&as_of=2025-02-01
GET  /api/companies/AAPL/activity-feed
GET  /api/companies/AAPL/alerts
GET  /api/companies/AAPL/activity-overview
GET  /api/companies/AAPL/models?model=dcf,reverse_dcf,roic,capital_allocation,dupont,piotroski,altman_z,ratios
GET  /api/companies/AAPL/models?model=dcf,reverse_dcf,roic,capital_allocation,dupont,piotroski,altman_z,ratios&as_of=2025-02-01
GET  /api/jobs/{job_id}/events
GET  /api/insiders/AAPL
GET  /api/ownership/AAPL
GET  /api/filings/AAPL
GET  /api/search_filings?form=8-K&ticker=AAPL
POST /api/companies/AAPL/refresh
```

Cache-first request-path policy:

- Company research surfaces backed by persisted tables are cache-first and do not perform live SEC fetches on the request path.
- This includes governance, beneficial ownership, filing events, capital markets, activity feed, alerts, and watchlist summary.
- If cached data is missing or stale, the API returns the cached (or empty) payload and queues refresh in the background.
- Explicit live SEC utility routes remain available for direct SEC use cases, including `/api/companies/{ticker}/financial-history`, `/api/filings/{ticker}`, `/api/search_filings`, and `/api/companies/{ticker}/filings/view`.

Queue a background refresh manually:

```bash
curl -X POST "http://127.0.0.1:8000/api/companies/AAPL/refresh"
```

Run targeted reliability checks:

```bash
python -m pytest tests/test_hot_endpoint_contracts.py tests/test_parser_goldens.py tests/test_observability.py tests/test_benchmark_infrastructure.py
python scripts/benchmark_hot_endpoints.py --base-url http://127.0.0.1:8000 --ticker AAPL --rounds 20
python scripts/benchmark_model_computation.py --models dcf,reverse_dcf,roic,ratios --rounds 10
```

Run the one-shot Docker prewarm job after the stack is up:

```bash
docker compose --profile prewarm up sp500-prewarm
```

Optional environment variables for the prewarm job:

- `SP500_PREWARM_MODE=core` to warm company metadata, financials, prices, and core models only
- `SP500_PREWARM_MODE=seed` to seed only company metadata
- `SP500_PREWARM_FORCE=true` to bypass the freshness window
- `SP500_PREWARM_LIMIT=100` and `SP500_PREWARM_START_AT=201` to resume in batches

Additional environment variables:

- `SEC_TICKER_CACHE_TTL_SECONDS=86400` to cache SEC ticker mappings
- `SEC_13F_HISTORY_QUARTERS=4` to control how many distinct 13F reporting quarters are retained per manager/company pair
- `SEC_13F_UNIVERSE_MODE=curated` keeps manager coverage on the curated list (default), while `expanded` allows controlled extras
- `SEC_13F_EXTRA_MANAGERS="Manager One,Manager Two"` provides optional manager names used only when `SEC_13F_UNIVERSE_MODE=expanded`
- `SEC_MAX_RETRIES=3` and `SEC_RETRY_BACKOFF_SECONDS=0.5` for SEC request retries
- `MARKET_MAX_RETRIES=3` and `MARKET_RETRY_BACKOFF_SECONDS=0.5` for market data retries
- `STRICT_OFFICIAL_MODE=true` to disable Yahoo-backed price/profile fetches entirely, switch market classification to SEC SIC mapping, and hide price-dependent UI features that lack an official source
- `TREASURY_YIELD_CURVE_CSV_URL` for no-key U.S. Treasury 10-year risk-free rate input
- `TREASURY_HQM_CSV_URLS` (optional) comma-separated fallback URLs for Treasury HQM corporate bond yields; defaults to official Treasury paths
- `TREASURY_MAX_RETRIES=3` and `TREASURY_RETRY_BACKOFF_SECONDS=0.5` for Treasury fetch retries
- `VALUATION_WORKBENCH_ENABLED=true` to enable reverse DCF/ROIC/capital-allocation model surfaces

To pin a specific release, change these in `.env`:

```bash
BACKEND_IMAGE=gptvibe/fundamentalterminal:backend-v1.0.3
FRONTEND_IMAGE=gptvibe/fundamentalterminal:frontend-v1.0.3
```

Quick start after cloning the repo:

```bash
cp .env.example .env
docker compose pull
docker compose up -d
```

Local source build after cloning the repo:

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d
```

Quick start without cloning the repo:

```bash
curl -L -o docker-compose.yml https://raw.githubusercontent.com/gptvibe/Fundamental-Terminal/main/docker-compose.yml
curl -L -o .env https://raw.githubusercontent.com/gptvibe/Fundamental-Terminal/main/.env.example
docker compose pull
docker compose up -d
```

Notes:

- `docker-compose.yml` stays image-first for GitHub users who should pull published images.
- `docker-compose.build.yml` is the opt-in override for maintainers who want to test local code before publishing new images.

## Publish images to Docker Hub

The GitHub Actions workflow at `.github/workflows/publish-images.yml` publishes prebuilt images to Docker Hub.

- Push to `main` updates the `backend-latest` and `frontend-latest` tags.
- Push a version tag like `v1.0.3` publishes `backend-v1.0.3` and `frontend-v1.0.3`.

Example first release:

```bash
git tag v1.0.3
git push origin v1.0.3
```

Add these GitHub repository secrets before using the workflow:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

The workflow pushes to these Docker Hub tags:

- `gptvibe/fundamentalterminal:backend-latest`
- `gptvibe/fundamentalterminal:frontend-latest`

## Run as a worker

```bash
python -m app.worker AAPL MSFT
```

Use `--force` to bypass the 24-hour freshness window.

Prewarm the bundled S&P 500 universe:

```bash
python -m app.prewarm_sp500 --mode refresh
```

For a much faster first pass that skips insider trades and institutional holdings:

```bash
python -m app.prewarm_sp500 --mode core
```

Useful options:

- `--mode seed` to only seed `companies` rows for faster search bootstrapping
- `--mode core` to warm `companies`, financial statements, prices, and core models only
- `--force` to refresh even if the cache is still fresh
- `--limit 50 --start-at 101` to process the list in resumable batches

## Model engine

- Core `ratios` are precomputed automatically whenever canonical financial data is saved.
- Cached model results are stored in PostgreSQL with `model_version` and reused until financial inputs change.
- DCF v2.2.0 adds per-sector risk premium adjustments (e.g., Utilities −1%, Technology +1.5%) layered on the base equity risk premium.
- `residual_income` v1.0.0 is the primary model for financial sector companies (banks, REITs, insurers) where asset-level cash-flow DCF is unsupported. Formula: RI = (ROE − CoE) × Book Equity, with ROE fading toward CoE over a 5-year projection horizon and a Gordon Growth terminal value.
- DCF/reverse-DCF/ROIC assumptions include Treasury-direct 10-year risk-free input with 24-hour cache and provenance metadata.

Run model computations from cached PostgreSQL data only:

```bash
python -m app.model_engine.worker AAPL --models dcf,reverse_dcf,roic,capital_allocation,dupont,piotroski,altman_z,ratios
```

## Macro (Market Context)

The terminal persists macro indicator data in PostgreSQL with a DB-first fetch path. Live fetches are only triggered on cache miss or staleness. Data is grouped into three sections returned by the API:

- `rates_credit` — Treasury par yield curve tenors, HQM 30-year corporate benchmark, and BAA corporate spread
- `inflation_labor` — CPI (Urban All Items), Core CPI, PPI (Final Demand), Unemployment Rate, and Nonfarm Payrolls
- `growth_activity` — Real GDP, Personal Income, PCE, and Corporate Profits (via FRED)

Official data sources:

| Source | Series | Env var required |
|--------|--------|-----------------|
| U.S. Treasury (CSV) | Daily par yield curve | `TREASURY_YIELD_CURVE_CSV_URL` |
| U.S. Treasury HQM | 30-year corporate bond yield | `TREASURY_HQM_CSV_URLS` (optional, comma-separated fallback chain) |
| BLS Public API v2 | CPI, Core CPI, PPI, Unemployment, Payrolls | `BLS_API_KEY` |
| EIA Retail Electricity Sales | U.S. and industrial electricity sales and pricing | `EIA_API_KEY` |
| FRED (BEA proxy) | Real GDP, Personal Income, PCE, Corporate Profits | `FRED_API_KEY` |

When `STRICT_OFFICIAL_MODE=true`, company pages stay official-only: SEC SIC replaces Yahoo market-profile enrichment, commercial equity price fetches are disabled, and price-dependent product surfaces explicitly explain why they are unavailable.

Company pages display a `MacroStrip` with the most relevant indicators filtered by sector exposure. The home dashboard groups indicators under the "Macro" heading.

API endpoints:

```bash
GET /api/market-context               # global macro snapshot (DB-first)
GET /api/companies/AAPL/market-context  # company-specific enriched context
```

