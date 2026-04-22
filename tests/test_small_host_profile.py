from __future__ import annotations

from pathlib import Path


def test_small_host_override_documents_conservative_worker_settings() -> None:
    contents = Path("docker-compose.small-host.yml").read_text(encoding="utf-8")

    assert "DB_POOL_SIZE: 5" in contents
    assert "DB_MAX_OVERFLOW: 5" in contents
    assert "REFRESH_QUEUE_POLL_SECONDS: 5" in contents
    assert "DATA_FETCHER_STARTUP_DELAY_SECONDS: 120" in contents
    assert "WORKER_IDENTIFIERS: AAPL MSFT" in contents
    assert 'DATA_FETCHER_RUN_MACRO_WORKER: "false"' in contents
    assert "SP500_PREWARM_MODE: core" in contents
    assert "SP500_PREWARM_LIMIT: 25" in contents
