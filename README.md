# Fundamental Terminal

Fundamental Terminal is a pull-first Dockerized SEC-first fundamental terminal. It ingests SEC EDGAR submissions and XBRL company facts, normalizes them into a canonical financial schema, stores them in PostgreSQL, and serves a Next.js research UI for searching by ticker or company name.

## Screenshots

Captured from the local app with `INTC` as the demo company.

### Home Search

![Home search with autocomplete](docs/screenshots/home-search.png)

### Company Overview

![Company overview for INTC](docs/screenshots/company-overview.png)

### Valuation Models

![Valuation models for INTC](docs/screenshots/company-models.png)

### Mobile Company View

![Mobile company view for INTC](docs/screenshots/mobile-company.png)

## Roadmap

- See [docs/sec-expansion-roadmap.md](docs/sec-expansion-roadmap.md) for the phased SEC dataset expansion plan, including backend models, API contracts, frontend visualizations, and sprint ordering.
- See [docs/sec-expansion-checklist.md](docs/sec-expansion-checklist.md) for the task-by-task execution checklist.

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

3. Run migrations:

   ```bash
   alembic upgrade head
   ```

## Run as FastAPI

```bash
uvicorn app.main:app --reload
```

## Run the Next.js frontend

```bash
cd frontend
set BACKEND_API_BASE_URL=http://127.0.0.1:8000
npm install
npm run dev
```

The frontend proxies backend requests through `/backend/*` and exposes:

- `/` for search, autocomplete, and trending tickers
- `/company/[ticker]` — company overview with unified activity feed, priority alerts, and quick peer comparison
- `/company/[ticker]/financials` — dedicated financial workspace with statements, margin trends, cash-flow waterfall, liquidity/capital, balance-sheet history, and quality summary
- `/company/[ticker]/financials` — dedicated financial workspace with statements, margin trends, derived SEC metrics (quarterly/annual/TTM with provenance and quality flags), cash-flow waterfall, liquidity/capital, balance-sheet history, and quality summary
- `/company/[ticker]/peers` — dedicated peer-comparison workspace with fair-value gap, ROIC, implied growth, shareholder yield, and valuation-band percentile comparisons
- `/company/[ticker]/filings` — filing timeline and parser insights with integrated filing-event views
- `/company/[ticker]/insiders` — Form 4 insider analytics plus Form 144 planned sale filings
- `/company/[ticker]/models` — valuation workbench with trust-aware DCF, reverse DCF heatmap, ROIC trend, capital-allocation stack, and assumption provenance
- `/company/[ticker]/governance` — proxy filings, board & meeting history, vote outcomes panel, executive pay table, and pay trend chart
- `/company/[ticker]/ownership-changes` — beneficial ownership (SC 13D/G) with stake-change timeline, owner table, and activist signals
- `/company/[ticker]/ownership` — institutional holdings analytics and manager activity trends
- `/company/[ticker]/stakes` — legacy path redirected to `/company/[ticker]/ownership-changes`
- `/company/[ticker]/capital-markets` — registration statements, prospectuses, and late-filer notices
- `/company/[ticker]/events` — 8-K events classified by item code with category chart
- `/company/[ticker]/sec-feed` — unified SEC activity feed across all filing types

Personal workspace behavior:

- Watchlist saves and private notes are stored in browser-local `LocalUserData` only (no account and no backend persistence).
- Users can export/import this local data as JSON from the saved-companies panel and clear all local saves.
- Import is merge-by-default (with an explicit replace option), and clear-all requires confirmation.

Search accepts either a ticker or a company name and shows an autocomplete dropdown with SEC-backed matches. Invalid searches stay in the input, turn the field red, and raise a red toast that clears automatically after 3 seconds.

On phones, the `/company/[ticker]` view hides the large top chrome to preserve space for charts and tables.

Real-time refresh progress streams over Server-Sent Events at `/api/jobs/{job_id}/events` and is rendered in the company console panels.

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
GET  /api/companies/AAPL/metrics-timeseries?cadence=ttm&max_points=24
GET  /api/companies/AAPL/financial-history
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
GET  /api/companies/AAPL/activity-feed
GET  /api/companies/AAPL/alerts
GET  /api/companies/AAPL/activity-overview
GET  /api/companies/AAPL/models?model=dcf,reverse_dcf,roic,capital_allocation,dupont,piotroski,altman_z,ratios
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
- `TREASURY_YIELD_CURVE_CSV_URL` for no-key U.S. Treasury 10-year risk-free rate input
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
| U.S. Treasury HQM | 30-year corporate bond yield | none (public) |
| BLS Public API v1 | CPI, Core CPI, PPI, Unemployment, Payrolls | none (public, rate-limited) |
| FRED (BEA proxy) | Real GDP, Personal Income, PCE, Corporate Profits | `FRED_API_KEY` |

Company pages display a `MacroStrip` with the most relevant indicators filtered by sector exposure. The home dashboard groups indicators under the "Macro" heading.

API endpoints:

```bash
GET /api/market-context               # global macro snapshot (DB-first)
GET /api/companies/AAPL/market-context  # company-specific enriched context
```

