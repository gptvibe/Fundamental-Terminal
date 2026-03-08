# SEC EDGAR ingestion service

This project pulls SEC EDGAR submissions and XBRL company facts, normalizes them into a canonical financial schema, and stores the results in PostgreSQL.

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

2. Set the database URL:

   ```bash
   set DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/database_name
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

- `/` for search and trending tickers
- `/company/[ticker]` for financial statements and charts
- `/company/[ticker]/models` for cached model outputs

Real-time refresh progress streams over Server-Sent Events at `/api/jobs/{job_id}/events` and is rendered in the company console panels.

## Docker Compose

1. Copy `.env.example` to `.env` and adjust secrets or ports as needed.
2. Start the full stack:

   ```bash
   docker compose up --build
   ```

3. Services on the compose network:

   - `backend` → FastAPI on port `8000`
   - `data-fetcher` → periodic refresh worker using `WORKER_IDENTIFIERS`
   - `sp500-prewarm` → optional one-shot S&P 500 warm-up job (profile: `prewarm`)
   - `frontend` → Next.js on port `3000`
   - `postgres` → PostgreSQL on port `5432`
   - `redis` → short-term cache on port `6379`

The stack uses environment variables for database and cache connectivity via `DATABASE_URL` and `REDIS_URL`, and all services communicate over the `fundamental-terminal-net` compose network.

API endpoints:

```bash
GET  /api/companies/search?ticker=AAPL
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
