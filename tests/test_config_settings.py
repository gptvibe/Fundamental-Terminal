from __future__ import annotations

import app.config as config_module


def test_settings_reads_env_at_instantiation_time(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    before_override = config_module.Settings()
    assert (
        before_override.database_url
        == "postgresql+psycopg://fundamental:fundamental@localhost:5432/fundamentals"
    )

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://override:override@localhost:5432/override")
    after_override = config_module.Settings()
    assert after_override.database_url == "postgresql+psycopg://override:override@localhost:5432/override"

    # Keep compatibility for modules that import the singleton.
    assert isinstance(config_module.settings, config_module.Settings)


def test_settings_parsing_bool_int_float_and_csv(monkeypatch) -> None:
    monkeypatch.setenv("SEC_MAX_RETRIES", "7")
    monkeypatch.setenv("SEC_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("MARKET_TIMEOUT_SECONDS", "9.5")
    monkeypatch.setenv("API_RATE_LIMIT_ENABLED", "off")
    monkeypatch.setenv("RATE_LIMIT_NAMESPACE", "ft:custom-rate-limit")
    monkeypatch.setenv("STRICT_OFFICIAL_MODE", "yes")
    monkeypatch.setenv("AUTH_REQUIRED_PATH_PREFIXES", " /api/a , ,/api/b ")

    parsed = config_module.Settings()

    assert parsed.sec_max_retries == 7
    assert parsed.sec_timeout_seconds == 12.5
    assert parsed.market_timeout_seconds == 9.5
    assert parsed.api_rate_limit_enabled is False
    assert parsed.rate_limit_namespace == "ft:custom-rate-limit"
    assert parsed.strict_official_mode is True
    assert parsed.auth_required_path_prefixes == ("/api/a", "/api/b")


def test_market_settings_fall_back_to_sec_values(monkeypatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "FundamentalTerminal/2.0 (ops@example.com)")
    monkeypatch.setenv("SEC_TIMEOUT_SECONDS", "17.5")
    monkeypatch.delenv("MARKET_USER_AGENT", raising=False)
    monkeypatch.delenv("MARKET_TIMEOUT_SECONDS", raising=False)

    parsed = config_module.Settings()

    assert parsed.market_user_agent == "FundamentalTerminal/2.0 (ops@example.com)"
    assert parsed.market_timeout_seconds == 17.5


def test_settings_defaults_match_intended_values(monkeypatch) -> None:
    for name in (
        "DATABASE_URL",
        "REDIS_URL",
        "AUTH_MODE",
        "VALUATION_WORKBENCH_ENABLED",
        "AUTH_REQUIRED_PATH_PREFIXES",
    ):
        monkeypatch.delenv(name, raising=False)

    default_settings = config_module.Settings()

    assert (
        default_settings.database_url
        == "postgresql+psycopg://fundamental:fundamental@localhost:5432/fundamentals"
    )
    assert default_settings.redis_url == "redis://localhost:6379/0"
    assert default_settings.auth_mode == "off"
    assert default_settings.valuation_workbench_enabled is True
    assert default_settings.rate_limit_namespace == "ft:rate-limit"
    assert default_settings.auth_required_path_prefixes == ("/api/internal",)


def test_hot_response_cache_ttl_unified_across_environments(monkeypatch) -> None:
    """Verify Docker and non-Docker deployments use the same cache freshness default."""
    for name in (
        "HOT_RESPONSE_CACHE_TTL_SECONDS",
        "HOT_RESPONSE_CACHE_STALE_TTL_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    parsed = config_module.Settings()

    # Both Docker compose files default to 120; config.py should match (not 20).
    assert parsed.hot_response_cache_ttl_seconds == 120, (
        "hot_response_cache_ttl_seconds default must match Docker compose defaults (120) "
        "to prevent silent behavior changes between Docker and non-Docker deployments"
    )
    assert parsed.hot_response_cache_stale_ttl_seconds == 120


def test_hot_response_cache_ttl_can_be_overridden(monkeypatch) -> None:
    """Verify cache TTL can be customized via environment variables."""
    monkeypatch.setenv("HOT_RESPONSE_CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("HOT_RESPONSE_CACHE_STALE_TTL_SECONDS", "180")

    parsed = config_module.Settings()

    assert parsed.hot_response_cache_ttl_seconds == 60
    assert parsed.hot_response_cache_stale_ttl_seconds == 180
