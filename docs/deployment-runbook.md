# Deployment Runbook

This runbook is the shortest safe path for a new deployer.

## What You Need

- Docker Engine with the Compose plugin
- A checked-out copy of the repo
- A `.env` file based on `.env.example`
- A valid `SEC_USER_AGENT` with a monitored email or URL

Required core settings:

- `POSTGRES_PASSWORD`
- `SEC_USER_AGENT`
- `APP_PROFILE=lite`
- `STRICT_OFFICIAL_MODE=true`

The lite profile builds `DATABASE_URL` from Compose service names and leaves Redis disabled by default.

Optional market-data overrides:

- `MARKET_USER_AGENT` (falls back to `SEC_USER_AGENT` if unset)
- `MARKET_TIMEOUT_SECONDS` (falls back to `SEC_TIMEOUT_SECONDS` if unset)

Optional external integrations:

- `FRED_API_KEY`
- `CENSUS_API_KEY`
- `BLS_API_KEY`
- `EIA_API_KEY`
- `BEA_API_KEY`

Optional security settings:

- `AUTH_MODE`
- `AUTH_BEARER_TOKEN`
- `AUTH_FORWARDED_USER_HEADER`
- `AUTH_REQUIRED_PATH_PREFIXES`
- `API_RATE_LIMIT_ENABLED`
- `API_RATE_LIMIT_REQUESTS`
- `API_RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_NAMESPACE`

## Auth Integration Points

Backend modes:

- `AUTH_MODE=off`: no application-layer auth checks
- `AUTH_MODE=bearer`: protect configured path prefixes with `Authorization: Bearer ...`
- `AUTH_MODE=forwarded-user`: trust a reverse proxy to inject `X-Forwarded-User` or your configured header

Default protected paths:

- `/api/internal`

Frontend integration hook:

- `frontend/lib/api.ts` exports `setApiAuthHeadersProvider(...)`
- Use it in your app bootstrap to attach `Authorization`, `X-Forwarded-User`, or similar headers to every API request
- Example:

```ts
import { setApiAuthHeadersProvider } from "@/lib/api";

setApiAuthHeadersProvider(() => ({
  Authorization: `Bearer ${token}`,
}));
```

Transport security note:

- Do not rely on app-level unconditional `Strict-Transport-Security` headers from Next.js.
- Set HSTS at the TLS-terminating reverse proxy/load balancer for HTTPS-only deployments.

For proxy-auth deployments, prefer terminating auth at the edge and forwarding only trusted identity headers to the app.

## First Deployment

1. Copy `.env.example` to `.env`.
2. Set `POSTGRES_PASSWORD` and set `SEC_USER_AGENT` to a real operator contact.
3. Decide whether auth should stay off, use a bearer token, or trust a reverse proxy header.
4. Start the lite stack:

```bash
docker compose up -d
```

5. Verify the deployment:

```bash
python scripts/verify_deployment_compat.py --backend-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:3000 --ticker AAPL
```

6. Check health manually:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/readyz`
- `http://127.0.0.1:8000/api/internal/observability`

Healthy deploy expectations:

- `/health` returns `status=ok`
- `components.db.status=ok`
- `components.redis.cache_coordination` is `disabled_by_profile` in lite, `redis_active` in standard, or `redis_degraded` / `local_memory_fallback` when Redis is configured but unavailable
- `components.worker.status` is `ok` or `idle`
- `components.api.auth_mode` and `components.api.rate_limit` match your intended config

## Standard and Prewarm Profiles

Use the standard profile when you want Redis-backed cache coordination and a separate data-fetcher container:

```bash
cp .env.advanced.example .env
docker compose --profile standard up -d
```

Use the prewarm profile only for explicit broad-universe warmup:

```bash
docker compose --profile standard --profile prewarm up -d
```

Keep `SP500_PREWARM_LIMIT` unset only when you intentionally want the broad warmup workload.

## Migration Safety

Every backend image now runs the migration safety guard before `alembic upgrade head`.

Manual preflight:

```bash
python scripts/check_migration_safety.py
```

What it blocks:

- multiple Alembic heads
- missing downgrades
- no-op downgrades on non-merge revisions
- raw `DROP TABLE` or `DROP INDEX` execution through `op.execute(...)`

## Backup Before Upgrades

Take a Postgres backup before any schema-changing deploy.

See [postgres-backup-restore.md](./postgres-backup-restore.md).

Recommended sequence:

1. `python scripts/check_migration_safety.py`
2. take a fresh database backup
3. deploy
4. run `scripts/verify_deployment_compat.py`
5. confirm `/health` and the UI

## Diagnosing Failures

Start with:

- `docker compose ps`
- `docker compose logs backend`
- `docker compose logs data-fetcher`
- `docker compose logs postgres`
- `docker compose logs redis`

Then check `/health`.

Important signals:

- `degraded_components`: top-level list of broken dependencies
- `components.redis.summary`: whether the app fell back to process-local cache
- `components.worker.live_worker_count`: whether a refresh worker heartbeat is visible
- `components.worker.registry_detail`: whether the worker registry itself is unavailable
- `components.sec_upstream.status_code`: whether SEC is reachable but rejecting requests

If `AUTH_MODE=bearer` and internal routes return `401`:

- verify `AUTH_BEARER_TOKEN`
- verify your caller sends `Authorization: Bearer <token>`

If `AUTH_MODE=forwarded-user` and internal routes return `401`:

- verify your reverse proxy injects the configured forwarded-user header
- verify the backend is not reachable directly without the proxy in front

If the worker is degraded:

- in lite, check `docker compose logs backend` because the queue consumer runs inside the backend container
- in standard, check `docker compose logs data-fetcher`
- confirm Redis is reachable when `APP_PROFILE=standard`
- confirm the worker heartbeat is appearing in `/health`

If Redis is degraded:

- the app can still run in local fallback mode
- cross-instance cache reuse and shared singleflight coordination will be weaker
- in lite, `disabled_by_profile` is expected and does not indicate an incident

## Rollback

If a deploy fails after migrations:

1. stop the new app containers
2. restore the latest Postgres backup
3. bring the previous image version back up
4. rerun deployment verification

Prefer restoring the database instead of relying on manual ad hoc downgrade steps during an incident.
