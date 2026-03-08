#!/bin/sh
set -eu

MODE="${SP500_PREWARM_MODE:-refresh}"
CONSTITUENTS_FILE="${SP500_CONSTITUENTS_FILE:-/app/app/data/sp500_tickers.txt}"

set -- python -m app.prewarm_sp500 --mode "$MODE" --constituents-file "$CONSTITUENTS_FILE"

if [ "${SP500_PREWARM_FORCE:-false}" = "true" ]; then
  set -- "$@" --force
fi

if [ -n "${SP500_PREWARM_LIMIT:-}" ]; then
  set -- "$@" --limit "${SP500_PREWARM_LIMIT}"
fi

if [ -n "${SP500_PREWARM_START_AT:-}" ]; then
  set -- "$@" --start-at "${SP500_PREWARM_START_AT}"
fi

echo "[prewarm] running: $*"
exec "$@"
