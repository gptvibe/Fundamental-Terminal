#!/bin/sh
set -eu

echo "[backend] validating migration safety"
python /app/scripts/check_migration_safety.py

echo "[backend] running migrations"
alembic upgrade head

echo "[backend] starting FastAPI on ${API_HOST:-0.0.0.0}:${API_PORT:-8000}"
exec uvicorn app.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}"
