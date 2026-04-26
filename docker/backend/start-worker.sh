#!/bin/sh
set -eu

is_truthy() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

ENABLED="${DATA_FETCHER_ENABLED:-true}"
STARTUP_DELAY="${DATA_FETCHER_STARTUP_DELAY_SECONDS:-0}"
ENQUEUE_ON_STARTUP="${DATA_FETCHER_ENQUEUE_ON_STARTUP:-true}"
RUN_MACRO_WORKER="${DATA_FETCHER_RUN_MACRO_WORKER:-true}"
INTERVAL="${WORKER_INTERVAL_SECONDS:-3600}"
IDENTIFIERS="${WORKER_IDENTIFIERS:-AAPL MSFT NVDA}"
QUEUE_POLL_INTERVAL="${REFRESH_QUEUE_POLL_SECONDS:-1}"

ensure_queue_worker_running() {
  if [ -z "${QUEUE_PID:-}" ]; then
    return 0
  fi
  if ! kill -0 "${QUEUE_PID}" 2>/dev/null; then
    echo "[worker] durable refresh queue consumer exited unexpectedly"
    wait "${QUEUE_PID}" || true
    exit 1
  fi
}

monitored_sleep() {
  remaining="${1:-0}"
  while [ "${remaining}" != "0" ] && [ "${remaining}" != "0.0" ]; do
    ensure_queue_worker_running
    case "${remaining}" in
      *.*)
        sleep "${remaining}"
        remaining=0
        ;;
      *)
        if [ "${remaining}" -gt 5 ] 2>/dev/null; then
          sleep 5
          remaining=$((remaining - 5))
        else
          sleep "${remaining}"
          remaining=0
        fi
        ;;
    esac
  done
}

if ! is_truthy "${ENABLED}"; then
  echo "[worker] data fetcher disabled by DATA_FETCHER_ENABLED=${ENABLED}"
  exit 0
fi

if [ "${STARTUP_DELAY}" != "0" ] && [ "${STARTUP_DELAY}" != "0.0" ]; then
  echo "[worker] delaying startup for ${STARTUP_DELAY}s"
  monitored_sleep "${STARTUP_DELAY}"
fi

echo "[worker] starting durable refresh queue consumer"
python -m app.worker --queue-worker --poll-interval "${QUEUE_POLL_INTERVAL}" &
QUEUE_PID="$!"

cleanup() {
  kill "${QUEUE_PID}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

FIRST_CYCLE=true

while true; do
  ensure_queue_worker_running
  if [ "${FIRST_CYCLE}" = "true" ] && ! is_truthy "${ENQUEUE_ON_STARTUP}"; then
    echo "[worker] skipping initial enqueue because DATA_FETCHER_ENQUEUE_ON_STARTUP=${ENQUEUE_ON_STARTUP}"
  else
    echo "[worker] enqueueing scheduled refresh tickers: ${IDENTIFIERS}"
    # shellcheck disable=SC2086
    python -m app.worker --enqueue ${IDENTIFIERS} || true
  fi

  if is_truthy "${RUN_MACRO_WORKER}"; then
    echo "[worker] refreshing market context (FRED/BEA/BLS/Treasury)"
    python -m app.macro_worker || true
  else
    echo "[worker] skipping macro refresh because DATA_FETCHER_RUN_MACRO_WORKER=${RUN_MACRO_WORKER}"
  fi

  FIRST_CYCLE=false

  echo "[worker] sleeping for ${INTERVAL}s"
  monitored_sleep "${INTERVAL}"
done
