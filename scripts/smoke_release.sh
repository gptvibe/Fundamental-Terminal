#!/usr/bin/env bash

set -euo pipefail

BACKEND_URL="http://127.0.0.1:8000"
FRONTEND_URL="http://127.0.0.1:3000"
TICKER="AAPL"

usage() {
  cat <<'EOF'
Usage: bash scripts/smoke_release.sh [options]

Options:
  --backend-url <url>   Backend base URL (default: http://127.0.0.1:8000)
  --frontend-url <url>  Frontend base URL (default: http://127.0.0.1:3000)
  --ticker <symbol>     Ticker symbol (default: AAPL)
  -h, --help            Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-url)
      BACKEND_URL="$2"
      shift 2
      ;;
    --frontend-url)
      FRONTEND_URL="$2"
      shift 2
      ;;
    --ticker)
      TICKER="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 2
  fi
}

check_route() {
  local label="$1"
  local url="$2"
  local body_file
  body_file="$(mktemp)"

  local status
  status="$(curl --silent --show-error --location --output "$body_file" --write-out "%{http_code}" --max-time 30 "$url")"

  if [[ "$status" != "200" ]]; then
    echo "[FAIL] ${label}: ${url} (status=${status})" >&2
    echo "Response excerpt:" >&2
    head -c 400 "$body_file" >&2 || true
    echo >&2
    rm -f "$body_file"
    return 1
  fi

  echo "[OK]   ${label}: ${url}"
  rm -f "$body_file"
}

require_command curl
require_command mktemp

echo "Running release smoke checks"
echo "Backend:  ${BACKEND_URL}"
echo "Frontend: ${FRONTEND_URL}"
echo "Ticker:   ${TICKER}"

check_route "backend health" "${BACKEND_URL}/health"
check_route "frontend reachable" "${FRONTEND_URL}/"
check_route "AAPL overview route" "${BACKEND_URL}/api/companies/${TICKER}/overview"
check_route "AAPL workspace/bootstrap route" "${BACKEND_URL}/api/companies/${TICKER}/workspace-bootstrap"
check_route "watchlist route" "${FRONTEND_URL}/watchlist"
check_route "data sources route" "${FRONTEND_URL}/data-sources"

echo "All smoke checks passed."
