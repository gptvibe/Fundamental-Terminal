#!/bin/sh
set -eu

HEARTBEAT_FILE="${DATA_FETCHER_HEALTH_HEARTBEAT_FILE:-/tmp/data-fetcher-worker-heartbeat}"
QUEUE_PID_FILE="${DATA_FETCHER_HEALTH_QUEUE_PID_FILE:-/tmp/data-fetcher-queue.pid}"
MAX_STALE_SECONDS="${DATA_FETCHER_HEALTH_MAX_STALE_SECONDS:-75}"

if [ ! -s "${HEARTBEAT_FILE}" ]; then
  echo "[healthcheck] missing worker heartbeat file: ${HEARTBEAT_FILE}" >&2
  exit 1
fi

if [ ! -s "${QUEUE_PID_FILE}" ]; then
  echo "[healthcheck] missing queue worker pid file: ${QUEUE_PID_FILE}" >&2
  exit 1
fi

QUEUE_PID="$(cat "${QUEUE_PID_FILE}" 2>/dev/null | tr -cd '0-9')"
if [ -z "${QUEUE_PID}" ]; then
  echo "[healthcheck] invalid queue worker pid" >&2
  exit 1
fi
if ! kill -0 "${QUEUE_PID}" 2>/dev/null; then
  echo "[healthcheck] queue worker process is not running" >&2
  exit 1
fi

LAST_SEEN="$(cat "${HEARTBEAT_FILE}" 2>/dev/null | tr -cd '0-9')"
if [ -z "${LAST_SEEN}" ]; then
  echo "[healthcheck] invalid worker heartbeat timestamp" >&2
  exit 1
fi

NOW="$(date +%s)"
AGE="$((NOW - LAST_SEEN))"
if [ "${AGE}" -gt "${MAX_STALE_SECONDS}" ]; then
  echo "[healthcheck] stale worker heartbeat: age=${AGE}s max=${MAX_STALE_SECONDS}s" >&2
  exit 1
fi

exit 0
