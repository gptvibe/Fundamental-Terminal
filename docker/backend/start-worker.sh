#!/bin/sh
set -eu

INTERVAL="${WORKER_INTERVAL_SECONDS:-3600}"
IDENTIFIERS="${WORKER_IDENTIFIERS:-AAPL MSFT NVDA}"
QUEUE_POLL_INTERVAL="${REFRESH_QUEUE_POLL_SECONDS:-1}"

echo "[worker] starting durable refresh queue consumer"
python -m app.worker --queue-worker --poll-interval "${QUEUE_POLL_INTERVAL}" &
QUEUE_PID="$!"

cleanup() {
  kill "${QUEUE_PID}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

while true; do
  echo "[worker] enqueueing scheduled refresh tickers: ${IDENTIFIERS}"
  # shellcheck disable=SC2086
  python -m app.worker --enqueue ${IDENTIFIERS} || true

  echo "[worker] refreshing market context (FRED/BEA/BLS/Treasury)"
  python -m app.macro_worker || true

  echo "[worker] sleeping for ${INTERVAL}s"
  sleep "${INTERVAL}"
done
