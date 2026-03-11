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

## Canonical metrics

- `revenue`
- `gross_profit`
- `operating_income`
- `net_income`
- `total_assets`
- `total_liabilities`
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
- `/company/[ticker]` for financial statements and charts
- `/company/[ticker]/models` for cached model outputs

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
POST /api/companies/AAPL/refresh
GET  /api/companies/AAPL/models?model=dcf,dupont,piotroski
```

The API serves cached PostgreSQL data only. If cached data is missing or stale, it returns the cached payload and queues the data fetcher in the background.

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
- `SEC_MAX_RETRIES=3` and `SEC_RETRY_BACKOFF_SECONDS=0.5` for SEC request retries
- `MARKET_MAX_RETRIES=3` and `MARKET_RETRY_BACKOFF_SECONDS=0.5` for market data retries

To pin a specific release, change these in `.env`:

```bash
BACKEND_IMAGE=gptvibe/fundamentalterminal:backend-v1.0.0
FRONTEND_IMAGE=gptvibe/fundamentalterminal:frontend-v1.0.0
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
- Push a version tag like `v1.0.0` publishes `backend-v1.0.0` and `frontend-v1.0.0`.

Example first release:

```bash
git tag v1.0.0
git push origin v1.0.0
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

Run model computations from cached PostgreSQL data only:

```bash
python -m app.model_engine.worker AAPL --models dcf,dupont,piotroski,altman_z,ratios
```
