from __future__ import annotations

from pathlib import Path


def test_lite_env_example_has_conservative_defaults() -> None:
    contents = Path(".env.lite.example").read_text(encoding="utf-8")

    assert "APP_PROFILE=lite" in contents
    assert "UVICORN_WORKERS=1" in contents
    assert "DB_POOL_SIZE=2" in contents
    assert "DB_MAX_OVERFLOW=1" in contents
    assert "REFRESH_QUEUE_POLL_SECONDS=10" in contents
    assert "DATA_FETCHER_STARTUP_DELAY_SECONDS=180" in contents
    assert "DATA_FETCHER_HEALTH_START_PERIOD=210s" in contents
    assert "DATA_FETCHER_RUN_MACRO_WORKER=false" in contents
    assert "WORKER_IDENTIFIERS=AAPL,MSFT" in contents
    assert "SP500_PREWARM_LIMIT=0" in contents
    assert "OBSERVABILITY_MAX_RECORDS=500" in contents
    assert "PERFORMANCE_AUDIT_ENABLED=false" in contents
    assert "HOT_RESPONSE_CACHE_ENABLED=true" in contents
    assert "STRICT_OFFICIAL_MODE=true" in contents


def test_lite_compose_override_applies_low_compute_settings() -> None:
    contents = Path("docker-compose.lite.yml").read_text(encoding="utf-8")

    assert "UVICORN_WORKERS: ${UVICORN_WORKERS:-1}" in contents
    assert "DB_POOL_SIZE: ${DB_POOL_SIZE:-2}" in contents
    assert "DB_MAX_OVERFLOW: ${DB_MAX_OVERFLOW:-1}" in contents
    assert "REFRESH_QUEUE_POLL_SECONDS: ${REFRESH_QUEUE_POLL_SECONDS:-10}" in contents
    assert "DATA_FETCHER_STARTUP_DELAY_SECONDS: ${DATA_FETCHER_STARTUP_DELAY_SECONDS:-180}" in contents
    assert "start_period: ${DATA_FETCHER_HEALTH_START_PERIOD:-210s}" in contents
    assert "DATA_FETCHER_ENQUEUE_ON_STARTUP: ${DATA_FETCHER_ENQUEUE_ON_STARTUP:-false}" in contents
    assert "DATA_FETCHER_RUN_MACRO_WORKER: ${DATA_FETCHER_RUN_MACRO_WORKER:-false}" in contents
    assert "WORKER_IDENTIFIERS: ${WORKER_IDENTIFIERS:-AAPL,MSFT}" in contents
    assert "SP500_PREWARM_LIMIT: ${SP500_PREWARM_LIMIT:-0}" in contents
    assert "profiles:" in contents
    assert "- prewarm" in contents


def test_worker_startup_script_respects_lite_profile_defaults() -> None:
    contents = Path("docker/backend/start-worker.sh").read_text(encoding="utf-8")

    assert 'APP_PROFILE="$(printf \'%s\' "${APP_PROFILE:-full}" | tr \'[:upper:]\' \'[:lower:]\')"' in contents
    assert 'elif [ "${APP_PROFILE}" = "lite" ]; then' in contents
    assert 'ENQUEUE_ON_STARTUP="false"' in contents
    assert 'RUN_MACRO_WORKER="false"' in contents
    assert 'IDENTIFIERS_RAW="AAPL,MSFT"' in contents
    assert 'IDENTIFIERS="$(printf \'%s\' "${IDENTIFIERS_RAW}" | tr \',\' \' \')"' in contents
