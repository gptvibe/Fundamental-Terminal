from __future__ import annotations

from types import SimpleNamespace

import app.config as config_module
import app.services.sec_edgar as sec_edgar


def test_build_sec_client_config_applies_guardrails() -> None:
    client_config = config_module.build_sec_client_config(
        SimpleNamespace(
            sec_user_agent="",
            sec_timeout_seconds=0.0,
            sec_min_request_interval_seconds=0.01,
            sec_max_retries=0,
            sec_retry_backoff_seconds=0.01,
            sec_max_retry_backoff_seconds=0.05,
            sec_max_retry_after_seconds=0.05,
        )
    )

    assert client_config.user_agent == config_module.DEFAULT_SEC_USER_AGENT
    assert client_config.timeout_seconds == 1.0
    assert client_config.min_request_interval_seconds == config_module.SEC_CLIENT_MIN_REQUEST_INTERVAL_FLOOR_SECONDS
    assert client_config.max_retries == 1
    assert client_config.retry_backoff_seconds == config_module.SEC_CLIENT_RETRY_BACKOFF_FLOOR_SECONDS
    assert client_config.max_retry_backoff_seconds == client_config.retry_backoff_seconds
    assert client_config.max_retry_after_seconds == client_config.retry_backoff_seconds


def test_edgar_client_uses_centralized_sec_client_config(monkeypatch) -> None:
    monkeypatch.setattr(
        sec_edgar,
        "settings",
        SimpleNamespace(
            sec_user_agent="FundamentalTerminal/2.0 (ops@example.com)",
            sec_timeout_seconds=17.0,
            sec_min_request_interval_seconds=0.6,
            sec_max_retries=4,
            sec_retry_backoff_seconds=0.75,
            sec_max_retry_backoff_seconds=6.0,
            sec_max_retry_after_seconds=20.0,
        ),
    )

    client = sec_edgar.EdgarClient()
    try:
        assert client._client_config.user_agent == "FundamentalTerminal/2.0 (ops@example.com)"
        assert client._client_config.timeout_seconds == 17.0
        assert client._client_config.min_request_interval_seconds == 0.6
        assert client._client_config.max_retries == 4
        assert client._client_config.max_retry_backoff_seconds == 6.0
        assert client._http.headers["User-Agent"] == "FundamentalTerminal/2.0 (ops@example.com)"
    finally:
        client.close()


def test_retry_wait_caps_retry_after_and_exponential_backoff() -> None:
    client_config = config_module.SecClientConfig(
        user_agent="FundamentalTerminal/2.0 (ops@example.com)",
        timeout_seconds=15.0,
        min_request_interval_seconds=0.5,
        max_retries=4,
        retry_backoff_seconds=0.5,
        max_retry_backoff_seconds=2.0,
        max_retry_after_seconds=5.0,
    )

    assert sec_edgar._retry_wait("30", client_config, 0) == 5.0
    assert sec_edgar._retry_wait(None, client_config, 4) == 2.0