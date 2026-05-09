# Fundamental Terminal

Official-source-first research workspace for U.S. public equities.

Fundamental Terminal helps you move from ticker to evidence quickly, with company research pages, chart workspaces, watchlists, and source transparency built on official/public data.

## What You Get

- Fast search and launch for U.S. listed companies.
- Company research brief workspace with snapshot, filings context, and operating signals.
- Financial charts workspace with reported history and scenario-aware projections.
- Watchlist workspace for local triage, notes, and follow-up.
- Data Sources workspace for provenance, freshness, and source health.

## Screenshots

### Home / Search

![Home and search workspace](docs/screenshots/home-search.png)

### Company Brief

![Company research brief workspace](docs/screenshots/company-overview.png)

### Financial Charts

![Financial charts workspace](docs/screenshots/charts-dashboard.png)

### Watchlist

![Watchlist workspace](docs/screenshots/watchlist.png)

### Data Sources

![Data sources workspace](docs/screenshots/data-sources.png)

## Quickstart (Docker)

The checked-in example env files are runnable for local evaluation. Change `POSTGRES_PASSWORD`, `DATABASE_URL`, and user-agent contact values before exposing the stack outside your machine.

### 1) Lite profile (lowest resource use)

```bash
cp .env.lite.example .env
docker compose -f docker-compose.yml -f docker-compose.lite.yml up -d
```

### 2) Normal profile (default)

```bash
cp .env.example .env
docker compose up -d
```

### 3) Build from local source (normal profile)

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d
```

### 4) Verify stack health

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:3000/
curl -fsS http://127.0.0.1:8000/api/companies/AAPL/workspace-bootstrap > /dev/null
```

Endpoints:

- Frontend: http://127.0.0.1:3000
- Backend API: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs

### 5) Deterministic demo mode (explicit opt-in)

Use demo mode when you need populated home/company/watchlist-like surfaces without relying on live upstream freshness.

```bash
# In .env
DEMO_MODE=true
NEXT_PUBLIC_DEMO_MODE=true

# Build from local source so frontend demo env is baked into the client bundle
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d
```

Demo mode behavior:

- Fixture-backed payloads are deterministic and explicitly labeled as demo data.
- Provenance and source-mix UI remain active; demo payloads carry a labeled manual-override source.
- Demo mode is off by default and must be enabled explicitly.

## Not Investment Advice

Fundamental Terminal is software for research workflow support. It does not provide investment advice, recommendations, or portfolio management.

## Data Sources and Limitations

### Core sources

- SEC EDGAR submissions and filings.
- SEC XBRL companyfacts.
- Public macro datasets (for context panels).
- Labeled fallback market-context sources where official coverage is not practical.

### Source policy

- Official-source-first for core fundamentals and filing-driven research.
- Derived analytics are clearly marked as internal computations.
- `STRICT_OFFICIAL_MODE=true` suppresses fallback-backed surfaces.

### Known limitations

- Coverage is focused on U.S. public equities.
- Data freshness depends on source availability, worker throughput, and cache state.
- Some routes support point-in-time (`as_of`) workflows; coverage depth varies by endpoint.
- Derived/model outputs are sensitive to assumptions and source timeliness.

## Key Routes

- `/`
- `/company/[ticker]`
- `/company/[ticker]/charts`
- `/watchlist`
- `/data-sources`
- `/compare?tickers=AAPL,MSFT`
- `/screener`

## Development

### Local development

```bash
pip install -r requirements-dev.txt
cd frontend && npm install && cd ..
docker compose up -d postgres redis
alembic upgrade head
```

Run backend (PowerShell):

```powershell
$env:DATABASE_URL = "postgresql+psycopg://fundamental:fundamental@localhost:5432/fundamentals"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:SEC_USER_AGENT = "FundamentalTerminal/1.0 (contact@example.com)"
$env:MARKET_USER_AGENT = "FundamentalTerminal/1.0 (contact@example.com)"
uvicorn app.main:app --reload
```

Run frontend:

```bash
cd frontend
npm run dev
```

### Tests and checks

```bash
python -m pytest
cd frontend && npm test && npm run lint && npm run build && cd ..
```

### Additional references

- docs/deployment-runbook.md
- docs/release-process.md
- docs/RELEASE_CHECKLIST.md
- docs/backend-architecture-boundaries.md
- docs/data-provenance.md
