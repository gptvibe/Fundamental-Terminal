#!/bin/sh
set -eu

echo "[backend] running migrations"
alembic upgrade head

echo "[backend] starting FastAPI on ${API_HOST:-0.0.0.0}:${API_PORT:-8000}"
exec uvicorn app.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}"
