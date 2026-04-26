# Postgres Backup And Restore

Take a backup before any migration-bearing deploy.

## Docker Compose Backup

If you are using the default compose Postgres service:

```bash
mkdir -p artifacts/backups
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-fundamental}" -d "${POSTGRES_DB:-fundamentals}" -Fc > artifacts/backups/fundamentals-$(date +%Y%m%d-%H%M%S).dump
```

Plain SQL alternative:

```bash
mkdir -p artifacts/backups
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-fundamental}" -d "${POSTGRES_DB:-fundamentals}" > artifacts/backups/fundamentals-$(date +%Y%m%d-%H%M%S).sql
```

## Restore A Custom-Format Dump

Stop app containers first so nothing writes during restore.

```bash
docker compose stop backend data-fetcher frontend
docker compose exec -T postgres dropdb -U "${POSTGRES_USER:-fundamental}" --if-exists "${POSTGRES_DB:-fundamentals}"
docker compose exec -T postgres createdb -U "${POSTGRES_USER:-fundamental}" "${POSTGRES_DB:-fundamentals}"
docker compose exec -T postgres pg_restore -U "${POSTGRES_USER:-fundamental}" -d "${POSTGRES_DB:-fundamentals}" --clean --if-exists < artifacts/backups/your-backup.dump
docker compose start backend data-fetcher frontend
```

## Restore A Plain SQL Dump

```bash
docker compose stop backend data-fetcher frontend
docker compose exec -T postgres dropdb -U "${POSTGRES_USER:-fundamental}" --if-exists "${POSTGRES_DB:-fundamentals}"
docker compose exec -T postgres createdb -U "${POSTGRES_USER:-fundamental}" "${POSTGRES_DB:-fundamentals}"
docker compose exec -T postgres psql -U "${POSTGRES_USER:-fundamental}" -d "${POSTGRES_DB:-fundamentals}" < artifacts/backups/your-backup.sql
docker compose start backend data-fetcher frontend
```

## Safety Notes

- Prefer `pg_dump -Fc` for production backups because `pg_restore` is more flexible than raw SQL restores.
- Verify that the backup file is non-empty before calling the deploy complete.
- Keep at least one pre-deploy backup for every release that carries a migration.
- If you run an external managed Postgres instead of the bundled container, use the provider-native snapshot mechanism when available.

## After Restore

Run:

```bash
python scripts/verify_deployment_compat.py --backend-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:3000 --ticker AAPL
```

Then confirm:

- `/health`
- `/readyz`
- the company UI for a known ticker
