#!/bin/sh
set -eu

echo "[backend] validating migration safety"
python /app/scripts/check_migration_safety.py

echo "[backend] running migrations"
alembic upgrade head

APP_PROFILE="$(printf '%s' "${APP_PROFILE:-lite}" | tr '[:upper:]' '[:lower:]')"
if [ "${APP_PROFILE}" = "lite" ]; then
  QUEUE_POLL_INTERVAL="${REFRESH_QUEUE_POLL_SECONDS:-10}"
  echo "[backend] starting lite refresh queue consumer with ${QUEUE_POLL_INTERVAL}s poll interval"
  python -m app.worker --queue-worker --poll-interval "${QUEUE_POLL_INTERVAL}" &
fi

UVICORN_WORKERS="${UVICORN_WORKERS:-1}"

echo "[backend] starting FastAPI on ${API_HOST:-0.0.0.0}:${API_PORT:-8000} with ${UVICORN_WORKERS} worker(s)"
exec uvicorn app.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}" --workers "${UVICORN_WORKERS}"
