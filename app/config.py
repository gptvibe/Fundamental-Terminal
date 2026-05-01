from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any


DEFAULT_SEC_USER_AGENT = "FundamentalTerminal/1.0 (contact@example.com)"
SEC_CLIENT_MIN_REQUEST_INTERVAL_FLOOR_SECONDS = 0.2
SEC_CLIENT_RETRY_BACKOFF_FLOOR_SECONDS = 0.1
DEFAULT_SEC_MAX_RETRY_BACKOFF_SECONDS = 8.0
DEFAULT_SEC_MAX_RETRY_AFTER_SECONDS = 30.0


def _int_env(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value >= minimum else default


def _float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value >= minimum else default


def _bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _load_sec_user_agent() -> str:
    raw_value = os.getenv("SEC_USER_AGENT", "").strip()
    value = raw_value or DEFAULT_SEC_USER_AGENT
    return _validate_contact_user_agent(value, setting_name="SEC_USER_AGENT")


def _validate_contact_user_agent(value: str, *, setting_name: str) -> str:
    if "@" not in value and "http://" not in value and "https://" not in value:
        logging.getLogger(__name__).warning(
            "%s should include a contact email or URL (for example: 'FundamentalTerminal/1.0 (contact@example.com)').",
            setting_name,
        )
    return value


def _load_market_user_agent() -> str:
    raw_value = os.getenv("MARKET_USER_AGENT", "").strip()
    if raw_value:
        return _validate_contact_user_agent(raw_value, setting_name="MARKET_USER_AGENT")
    return _load_sec_user_agent()


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    values = [value.strip() for value in raw.split(",")]
    return tuple(value for value in values if value)


def _str_env(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    return value or default


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://fundamental:fundamental@localhost:5432/fundamentals",
        )
    )
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    sec_user_agent: str = field(default_factory=_load_sec_user_agent)
    market_user_agent: str = field(default_factory=_load_market_user_agent)
    sec_ticker_lookup_url: str = "https://www.sec.gov/files/company_tickers.json"
    sec_ticker_cache_ttl_seconds: int = field(default_factory=lambda: _int_env("SEC_TICKER_CACHE_TTL_SECONDS", 86400, minimum=60))
    sec_submissions_base_url: str = "https://data.sec.gov/submissions"
    sec_companyfacts_base_url: str = "https://data.sec.gov/api/xbrl/companyfacts"
    sec_search_base_url: str = "https://efts.sec.gov/LATEST/search-index"
    sec_timeout_seconds: float = field(default_factory=lambda: _float_env("SEC_TIMEOUT_SECONDS", 30.0, minimum=1.0))
    market_timeout_seconds: float = field(
        default_factory=lambda: _float_env(
            "MARKET_TIMEOUT_SECONDS",
            _float_env("SEC_TIMEOUT_SECONDS", 30.0, minimum=1.0),
            minimum=1.0,
        )
    )
    sec_min_request_interval_seconds: float = field(default_factory=lambda: _float_env("SEC_MIN_REQUEST_INTERVAL_SECONDS", 0.2))
    fdic_api_base_url: str = field(default_factory=lambda: os.getenv("FDIC_API_BASE_URL", "https://api.fdic.gov/banks"))
    fdic_timeout_seconds: float = field(default_factory=lambda: _float_env("FDIC_TIMEOUT_SECONDS", 30.0, minimum=1.0))
    federal_reserve_y9c_json_url: str | None = field(default_factory=lambda: os.getenv("FEDERAL_RESERVE_Y9C_JSON_URL", "").strip() or None)
    federal_reserve_y9c_json_path: str | None = field(default_factory=lambda: os.getenv("FEDERAL_RESERVE_Y9C_JSON_PATH", "").strip() or None)
    federal_reserve_y9c_timeout_seconds: float = field(default_factory=lambda: _float_env("FEDERAL_RESERVE_Y9C_TIMEOUT_SECONDS", 60.0, minimum=1.0))
    census_api_base_url: str = field(default_factory=lambda: os.getenv("CENSUS_API_BASE_URL", "https://api.census.gov/data/timeseries/eits"))
    census_api_key: str | None = field(default_factory=lambda: os.getenv("CENSUS_API_KEY", "").strip() or None)
    census_timeout_seconds: float = field(default_factory=lambda: _float_env("CENSUS_TIMEOUT_SECONDS", 30.0, minimum=1.0))
    bls_api_base_url: str = field(default_factory=lambda: os.getenv("BLS_API_BASE_URL", "https://api.bls.gov/publicAPI/v2/timeseries/data/"))
    bls_api_key: str | None = field(default_factory=lambda: os.getenv("BLS_API_KEY", "").strip() or None)
    bls_timeout_seconds: float = field(default_factory=lambda: _float_env("BLS_TIMEOUT_SECONDS", 30.0, minimum=1.0))
    eia_api_base_url: str = field(default_factory=lambda: os.getenv("EIA_API_BASE_URL", "https://api.eia.gov/v2"))
    eia_api_key: str | None = field(default_factory=lambda: os.getenv("EIA_API_KEY", "").strip() or None)
    eia_timeout_seconds: float = field(default_factory=lambda: _float_env("EIA_TIMEOUT_SECONDS", 30.0, minimum=1.0))
    bea_api_base_url: str = field(default_factory=lambda: os.getenv("BEA_API_BASE_URL", "https://apps.bea.gov/api/data"))
    bea_api_key: str | None = field(default_factory=lambda: os.getenv("BEA_API_KEY", "").strip() or None)
    bea_timeout_seconds: float = field(default_factory=lambda: _float_env("BEA_TIMEOUT_SECONDS", 30.0, minimum=1.0))
    bea_pce_table_name: str = field(default_factory=lambda: os.getenv("BEA_PCE_TABLE_NAME", "T20805"))
    bea_pce_line_number: str = field(default_factory=lambda: os.getenv("BEA_PCE_LINE_NUMBER", "1"))
    bea_gdp_by_industry_table_id: str = field(default_factory=lambda: os.getenv("BEA_GDP_BY_INDUSTRY_TABLE_ID", "1"))
    sec_filings_timeline_ttl_seconds: int = field(default_factory=lambda: _int_env("SEC_FILINGS_TIMELINE_TTL_SECONDS", 300, minimum=30))
    sec_form4_max_filings_per_refresh: int = field(default_factory=lambda: _int_env("SEC_FORM4_MAX_FILINGS_PER_REFRESH", 80, minimum=1))
    sec_13f_manager_limit: int = field(default_factory=lambda: _int_env("SEC_13F_MANAGER_LIMIT", 8, minimum=1))
    sec_13f_history_quarters: int = field(default_factory=lambda: _int_env("SEC_13F_HISTORY_QUARTERS", 4, minimum=2))
    sec_13f_universe_mode: str = field(default_factory=lambda: os.getenv("SEC_13F_UNIVERSE_MODE", "curated").strip().lower())
    sec_13f_extra_managers: tuple[str, ...] = field(default_factory=lambda: _csv_env("SEC_13F_EXTRA_MANAGERS"))
    sec_max_retries: int = field(default_factory=lambda: _int_env("SEC_MAX_RETRIES", 3, minimum=1))
    sec_retry_backoff_seconds: float = field(default_factory=lambda: _float_env("SEC_RETRY_BACKOFF_SECONDS", 0.5))
    sec_max_retry_backoff_seconds: float = field(default_factory=lambda: _float_env("SEC_MAX_RETRY_BACKOFF_SECONDS", DEFAULT_SEC_MAX_RETRY_BACKOFF_SECONDS, minimum=SEC_CLIENT_RETRY_BACKOFF_FLOOR_SECONDS))
    sec_max_retry_after_seconds: float = field(default_factory=lambda: _float_env("SEC_MAX_RETRY_AFTER_SECONDS", DEFAULT_SEC_MAX_RETRY_AFTER_SECONDS, minimum=1.0))
    sec_cache_prune_interval_seconds: int = field(default_factory=lambda: _int_env("SEC_CACHE_PRUNE_INTERVAL_SECONDS", 3600, minimum=60))
    sec_cache_prune_max_entries: int = field(default_factory=lambda: _int_env("SEC_CACHE_PRUNE_MAX_ENTRIES", 5000, minimum=0))
    market_max_retries: int = field(default_factory=lambda: _int_env("MARKET_MAX_RETRIES", 3, minimum=1))
    market_retry_backoff_seconds: float = field(default_factory=lambda: _float_env("MARKET_RETRY_BACKOFF_SECONDS", 0.5))
    market_history_overlap_days: int = field(default_factory=lambda: _int_env("MARKET_HISTORY_OVERLAP_DAYS", 7, minimum=1))
    market_profile_cache_ttl_seconds: int = field(default_factory=lambda: _int_env("MARKET_PROFILE_CACHE_TTL_SECONDS", 21600, minimum=0))
    treasury_yield_curve_csv_url: str = field(
        default_factory=lambda: os.getenv(
            "TREASURY_YIELD_CURVE_CSV_URL",
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/all?type=daily_treasury_yield_curve&page&_format=csv",
        )
    )
    treasury_hqm_csv_urls: tuple[str, ...] = field(
        default_factory=lambda: _csv_env("TREASURY_HQM_CSV_URLS")
        or (
            "https://home.treasury.gov/system/files/276/hqmYieldCurveData.csv",
            "https://home.treasury.gov/sites/default/files/interest-rates/hqmYieldCurveData.csv",
        )
    )
    treasury_max_retries: int = field(default_factory=lambda: _int_env("TREASURY_MAX_RETRIES", 3, minimum=1))
    treasury_retry_backoff_seconds: float = field(default_factory=lambda: _float_env("TREASURY_RETRY_BACKOFF_SECONDS", 0.5))
    market_context_cache_ttl_hours: int = field(default_factory=lambda: _int_env("MARKET_CONTEXT_CACHE_TTL_HOURS", 6, minimum=1))
    sector_context_cache_ttl_hours: int = field(default_factory=lambda: _int_env("SECTOR_CONTEXT_CACHE_TTL_HOURS", 24, minimum=1))
    fred_api_key: str | None = field(default_factory=lambda: os.getenv("FRED_API_KEY", "").strip() or None)
    freshness_window_hours: int = field(default_factory=lambda: _int_env("FRESHNESS_WINDOW_HOURS", 24, minimum=1))
    strict_official_mode: bool = field(default_factory=lambda: _bool_env("STRICT_OFFICIAL_MODE", False))
    db_pool_size: int = field(default_factory=lambda: _int_env("DB_POOL_SIZE", 20, minimum=1))
    db_max_overflow: int = field(default_factory=lambda: _int_env("DB_MAX_OVERFLOW", 40, minimum=0))
    db_pool_timeout_seconds: int = field(default_factory=lambda: _int_env("DB_POOL_TIMEOUT_SECONDS", 30, minimum=1))
    db_pool_recycle_seconds: int = field(default_factory=lambda: _int_env("DB_POOL_RECYCLE_SECONDS", 1800, minimum=30))
    model_engine_max_financial_periods: int = field(default_factory=lambda: _int_env("MODEL_ENGINE_MAX_FINANCIAL_PERIODS", 16, minimum=4))
    refresh_lock_timeout_seconds: int = field(default_factory=lambda: _int_env("REFRESH_LOCK_TIMEOUT_SECONDS", 900, minimum=30))
    refresh_queue_poll_seconds: float = field(default_factory=lambda: _float_env("REFRESH_QUEUE_POLL_SECONDS", 5.0, minimum=0.1))
    refresh_queue_block_seconds: float = field(default_factory=lambda: _float_env("REFRESH_QUEUE_BLOCK_SECONDS", 15.0, minimum=1.0))
    refresh_recovery_interval_seconds: float = field(default_factory=lambda: _float_env("REFRESH_RECOVERY_INTERVAL_SECONDS", 30.0, minimum=5.0))
    refresh_status_poll_seconds: float = field(default_factory=lambda: _float_env("REFRESH_STATUS_POLL_SECONDS", 5.0, minimum=0.1))
    worker_heartbeat_interval_seconds: float = field(default_factory=lambda: _float_env("WORKER_HEARTBEAT_INTERVAL_SECONDS", 15.0, minimum=2.0))
    worker_heartbeat_ttl_seconds: int = field(default_factory=lambda: _int_env("WORKER_HEARTBEAT_TTL_SECONDS", 45, minimum=5))
    refresh_aux_io_max_workers: int = field(default_factory=lambda: _int_env("REFRESH_AUX_IO_MAX_WORKERS", 2, minimum=1))
    hot_response_cache_ttl_seconds: int = field(default_factory=lambda: _int_env("HOT_RESPONSE_CACHE_TTL_SECONDS", 120, minimum=1))
    hot_response_cache_stale_ttl_seconds: int = field(default_factory=lambda: _int_env("HOT_RESPONSE_CACHE_STALE_TTL_SECONDS", 120, minimum=1))
    hot_response_cache_namespace: str = field(default_factory=lambda: os.getenv("HOT_RESPONSE_CACHE_NAMESPACE", "ft:hot-cache").strip() or "ft:hot-cache")
    rate_limit_namespace: str = field(default_factory=lambda: os.getenv("RATE_LIMIT_NAMESPACE", "ft:rate-limit").strip() or "ft:rate-limit")
    hot_response_cache_singleflight_lock_seconds: int = field(default_factory=lambda: _int_env("HOT_RESPONSE_CACHE_SINGLEFLIGHT_LOCK_SECONDS", 30, minimum=1))
    hot_response_cache_singleflight_wait_seconds: float = field(default_factory=lambda: _float_env("HOT_RESPONSE_CACHE_SINGLEFLIGHT_WAIT_SECONDS", 15.0, minimum=0.1))
    hot_response_cache_singleflight_poll_seconds: float = field(default_factory=lambda: _float_env("HOT_RESPONSE_CACHE_SINGLEFLIGHT_POLL_SECONDS", 0.05, minimum=0.01))
    hot_response_cache_upstream_local_max_entries: int = field(default_factory=lambda: _int_env("HOT_RESPONSE_CACHE_UPSTREAM_LOCAL_MAX_ENTRIES", 512, minimum=0))
    hot_response_cache_upstream_local_max_bytes: int = field(default_factory=lambda: _int_env("HOT_RESPONSE_CACHE_UPSTREAM_LOCAL_MAX_BYTES", 16 * 1024 * 1024, minimum=0))
    observability_enabled: bool = field(default_factory=lambda: _bool_env("OBSERVABILITY_ENABLED", True))
    observability_max_records: int = field(default_factory=lambda: _int_env("OBSERVABILITY_MAX_RECORDS", 5000, minimum=100))
    performance_audit_enabled: bool = field(default_factory=lambda: _bool_env("PERFORMANCE_AUDIT_ENABLED", False))
    performance_audit_max_records: int = field(default_factory=lambda: _int_env("PERFORMANCE_AUDIT_MAX_RECORDS", 5000, minimum=100))
    dupont_mode: str = field(default_factory=lambda: os.getenv("DUPONT_MODE", "auto").lower())
    valuation_workbench_enabled: bool = field(default_factory=lambda: os.getenv("VALUATION_WORKBENCH_ENABLED", "true").strip().lower() not in {"0", "false", "no"})
    api_rate_limit_enabled: bool = field(default_factory=lambda: _bool_env("API_RATE_LIMIT_ENABLED", True))
    api_rate_limit_requests: int = field(default_factory=lambda: _int_env("API_RATE_LIMIT_REQUESTS", 180, minimum=1))
    api_rate_limit_window_seconds: int = field(default_factory=lambda: _int_env("API_RATE_LIMIT_WINDOW_SECONDS", 60, minimum=1))
    api_rate_limit_trust_proxy: bool = field(default_factory=lambda: _bool_env("API_RATE_LIMIT_TRUST_PROXY", False))
    api_rate_limit_exempt_paths: tuple[str, ...] = field(
        default_factory=lambda: _csv_env("API_RATE_LIMIT_EXEMPT_PATHS")
        or (
            "/health",
            "/readyz",
            "/docs",
            "/redoc",
            "/openapi.json",
        )
    )
    auth_mode: str = field(default_factory=lambda: _str_env("AUTH_MODE", "off").lower())
    auth_bearer_token: str | None = field(default_factory=lambda: os.getenv("AUTH_BEARER_TOKEN", "").strip() or None)
    auth_forwarded_user_header: str = field(default_factory=lambda: _str_env("AUTH_FORWARDED_USER_HEADER", "X-Forwarded-User"))
    auth_required_path_prefixes: tuple[str, ...] = field(default_factory=lambda: _csv_env("AUTH_REQUIRED_PATH_PREFIXES") or ("/api/internal",))
    auth_exempt_paths: tuple[str, ...] = field(
        default_factory=lambda: _csv_env("AUTH_EXEMPT_PATHS")
        or (
            "/health",
            "/readyz",
        )
    )
    health_sec_check_enabled: bool = field(default_factory=lambda: _bool_env("HEALTH_SEC_CHECK_ENABLED", True))
    health_sec_check_timeout_seconds: float = field(default_factory=lambda: _float_env("HEALTH_SEC_CHECK_TIMEOUT_SECONDS", 2.5, minimum=0.5))
    health_sec_check_cache_seconds: int = field(default_factory=lambda: _int_env("HEALTH_SEC_CHECK_CACHE_SECONDS", 30, minimum=5))
    security_headers_enabled: bool = field(default_factory=lambda: _bool_env("SECURITY_HEADERS_ENABLED", True))


@dataclass(frozen=True, slots=True)
class SecClientConfig:
    user_agent: str
    timeout_seconds: float
    min_request_interval_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    max_retry_backoff_seconds: float
    max_retry_after_seconds: float


def build_sec_client_config(settings_like: Any) -> SecClientConfig:
    user_agent = str(getattr(settings_like, "sec_user_agent", DEFAULT_SEC_USER_AGENT) or DEFAULT_SEC_USER_AGENT).strip() or DEFAULT_SEC_USER_AGENT
    timeout_seconds = max(1.0, float(getattr(settings_like, "sec_timeout_seconds", 30.0)))
    min_request_interval_seconds = max(
        SEC_CLIENT_MIN_REQUEST_INTERVAL_FLOOR_SECONDS,
        float(getattr(settings_like, "sec_min_request_interval_seconds", SEC_CLIENT_MIN_REQUEST_INTERVAL_FLOOR_SECONDS)),
    )
    max_retries = max(1, int(getattr(settings_like, "sec_max_retries", 3)))
    retry_backoff_seconds = max(
        SEC_CLIENT_RETRY_BACKOFF_FLOOR_SECONDS,
        float(getattr(settings_like, "sec_retry_backoff_seconds", 0.5)),
    )
    max_retry_backoff_seconds = max(
        retry_backoff_seconds,
        float(getattr(settings_like, "sec_max_retry_backoff_seconds", DEFAULT_SEC_MAX_RETRY_BACKOFF_SECONDS)),
    )
    max_retry_after_seconds = max(
        retry_backoff_seconds,
        float(getattr(settings_like, "sec_max_retry_after_seconds", DEFAULT_SEC_MAX_RETRY_AFTER_SECONDS)),
    )
    return SecClientConfig(
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
        min_request_interval_seconds=min_request_interval_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        max_retry_backoff_seconds=max_retry_backoff_seconds,
        max_retry_after_seconds=max_retry_after_seconds,
    )


settings = Settings()
