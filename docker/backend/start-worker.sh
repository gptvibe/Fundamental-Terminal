#!/bin/sh
set -eu

INTERVAL="${WORKER_INTERVAL_SECONDS:-3600}"
IDENTIFIERS="${WORKER_IDENTIFIERS:-AAPL MSFT NVDA}"

while true; do
  echo "[worker] refreshing tickers: ${IDENTIFIERS}"
  # shellcheck disable=SC2086
  python -m app.worker ${IDENTIFIERS} || true

  echo "[worker] refreshing market context (FRED/BEA/BLS/Treasury)"
  python -m app.macro_worker || true

  echo "[worker] sleeping for ${INTERVAL}s"
  sleep "${INTERVAL}"
done
