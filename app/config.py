from __future__ import annotations

import logging
import os
from dataclasses import dataclass
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
    if "@" not in value and "http://" not in value and "https://" not in value:
        logging.getLogger(__name__).warning(
            "SEC_USER_AGENT should include a contact email or URL (for example: 'FundamentalTerminal/1.0 (contact@example.com)')."
        )
    return value


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    values = [value.strip() for value in raw.split(",")]
    return tuple(value for value in values if value)


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://fundamental:fundamental@localhost:5432/fundamentals",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    sec_user_agent: str = _load_sec_user_agent()
    sec_ticker_lookup_url: str = "https://www.sec.gov/files/company_tickers.json"
    sec_ticker_cache_ttl_seconds: int = _int_env("SEC_TICKER_CACHE_TTL_SECONDS", 86400, minimum=60)
    sec_submissions_base_url: str = "https://data.sec.gov/submissions"
    sec_companyfacts_base_url: str = "https://data.sec.gov/api/xbrl/companyfacts"
    sec_search_base_url: str = "https://efts.sec.gov/LATEST/search-index"
    sec_timeout_seconds: float = _float_env("SEC_TIMEOUT_SECONDS", 30.0, minimum=1.0)
    sec_min_request_interval_seconds: float = _float_env("SEC_MIN_REQUEST_INTERVAL_SECONDS", 0.2)
    fdic_api_base_url: str = os.getenv("FDIC_API_BASE_URL", "https://api.fdic.gov/banks")
    fdic_timeout_seconds: float = _float_env("FDIC_TIMEOUT_SECONDS", 30.0, minimum=1.0)
    federal_reserve_y9c_json_url: str | None = os.getenv("FEDERAL_RESERVE_Y9C_JSON_URL", "").strip() or None
    federal_reserve_y9c_json_path: str | None = os.getenv("FEDERAL_RESERVE_Y9C_JSON_PATH", "").strip() or None
    federal_reserve_y9c_timeout_seconds: float = _float_env("FEDERAL_RESERVE_Y9C_TIMEOUT_SECONDS", 60.0, minimum=1.0)
    census_api_base_url: str = os.getenv("CENSUS_API_BASE_URL", "https://api.census.gov/data/timeseries/eits")
    census_api_key: str | None = os.getenv("CENSUS_API_KEY", "").strip() or None
    census_timeout_seconds: float = _float_env("CENSUS_TIMEOUT_SECONDS", 30.0, minimum=1.0)
    bls_api_base_url: str = os.getenv("BLS_API_BASE_URL", "https://api.bls.gov/publicAPI/v2/timeseries/data/")
    bls_api_key: str | None = os.getenv("BLS_API_KEY", "").strip() or None
    bls_timeout_seconds: float = _float_env("BLS_TIMEOUT_SECONDS", 30.0, minimum=1.0)
    eia_api_base_url: str = os.getenv("EIA_API_BASE_URL", "https://api.eia.gov/v2")
    eia_api_key: str | None = os.getenv("EIA_API_KEY", "").strip() or None
    eia_timeout_seconds: float = _float_env("EIA_TIMEOUT_SECONDS", 30.0, minimum=1.0)
    bea_api_base_url: str = os.getenv("BEA_API_BASE_URL", "https://apps.bea.gov/api/data")
    bea_api_key: str | None = os.getenv("BEA_API_KEY", "").strip() or None
    bea_timeout_seconds: float = _float_env("BEA_TIMEOUT_SECONDS", 30.0, minimum=1.0)
    bea_pce_table_name: str = os.getenv("BEA_PCE_TABLE_NAME", "T20805")
    bea_pce_line_number: str = os.getenv("BEA_PCE_LINE_NUMBER", "1")
    bea_gdp_by_industry_table_id: str = os.getenv("BEA_GDP_BY_INDUSTRY_TABLE_ID", "1")
    sec_filings_timeline_ttl_seconds: int = _int_env("SEC_FILINGS_TIMELINE_TTL_SECONDS", 300, minimum=30)
    sec_form4_max_filings_per_refresh: int = _int_env("SEC_FORM4_MAX_FILINGS_PER_REFRESH", 80, minimum=1)
    sec_13f_manager_limit: int = _int_env("SEC_13F_MANAGER_LIMIT", 8, minimum=1)
    sec_13f_history_quarters: int = _int_env("SEC_13F_HISTORY_QUARTERS", 4, minimum=2)
    sec_13f_universe_mode: str = os.getenv("SEC_13F_UNIVERSE_MODE", "curated").strip().lower()
    sec_13f_extra_managers: tuple[str, ...] = _csv_env("SEC_13F_EXTRA_MANAGERS")
    sec_max_retries: int = _int_env("SEC_MAX_RETRIES", 3, minimum=1)
    sec_retry_backoff_seconds: float = _float_env("SEC_RETRY_BACKOFF_SECONDS", 0.5)
    sec_max_retry_backoff_seconds: float = _float_env("SEC_MAX_RETRY_BACKOFF_SECONDS", DEFAULT_SEC_MAX_RETRY_BACKOFF_SECONDS, minimum=SEC_CLIENT_RETRY_BACKOFF_FLOOR_SECONDS)
    sec_max_retry_after_seconds: float = _float_env("SEC_MAX_RETRY_AFTER_SECONDS", DEFAULT_SEC_MAX_RETRY_AFTER_SECONDS, minimum=1.0)
    sec_cache_prune_interval_seconds: int = _int_env("SEC_CACHE_PRUNE_INTERVAL_SECONDS", 3600, minimum=60)
    sec_cache_prune_max_entries: int = _int_env("SEC_CACHE_PRUNE_MAX_ENTRIES", 5000, minimum=0)
    market_max_retries: int = _int_env("MARKET_MAX_RETRIES", 3, minimum=1)
    market_retry_backoff_seconds: float = _float_env("MARKET_RETRY_BACKOFF_SECONDS", 0.5)
    treasury_yield_curve_csv_url: str = os.getenv(
        "TREASURY_YIELD_CURVE_CSV_URL",
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/all?type=daily_treasury_yield_curve&page&_format=csv",
    )
    treasury_hqm_csv_urls: tuple[str, ...] = _csv_env("TREASURY_HQM_CSV_URLS") or (
        "https://home.treasury.gov/system/files/276/hqmYieldCurveData.csv",
        "https://home.treasury.gov/sites/default/files/interest-rates/hqmYieldCurveData.csv",
    )
    treasury_max_retries: int = _int_env("TREASURY_MAX_RETRIES", 3, minimum=1)
    treasury_retry_backoff_seconds: float = _float_env("TREASURY_RETRY_BACKOFF_SECONDS", 0.5)
    market_context_cache_ttl_hours: int = _int_env("MARKET_CONTEXT_CACHE_TTL_HOURS", 6, minimum=1)
    sector_context_cache_ttl_hours: int = _int_env("SECTOR_CONTEXT_CACHE_TTL_HOURS", 24, minimum=1)
    fred_api_key: str | None = os.getenv("FRED_API_KEY", "").strip() or None
    freshness_window_hours: int = _int_env("FRESHNESS_WINDOW_HOURS", 24, minimum=1)
    strict_official_mode: bool = _bool_env("STRICT_OFFICIAL_MODE", False)
    db_pool_size: int = _int_env("DB_POOL_SIZE", 10, minimum=1)
    db_max_overflow: int = _int_env("DB_MAX_OVERFLOW", 20, minimum=0)
    db_pool_timeout_seconds: int = _int_env("DB_POOL_TIMEOUT_SECONDS", 30, minimum=1)
    db_pool_recycle_seconds: int = _int_env("DB_POOL_RECYCLE_SECONDS", 1800, minimum=30)
    model_engine_max_financial_periods: int = _int_env("MODEL_ENGINE_MAX_FINANCIAL_PERIODS", 16, minimum=4)
    refresh_lock_timeout_seconds: int = _int_env("REFRESH_LOCK_TIMEOUT_SECONDS", 900, minimum=30)
    hot_response_cache_ttl_seconds: int = _int_env("HOT_RESPONSE_CACHE_TTL_SECONDS", 20, minimum=1)
    hot_response_cache_stale_ttl_seconds: int = _int_env("HOT_RESPONSE_CACHE_STALE_TTL_SECONDS", 120, minimum=1)
    performance_audit_enabled: bool = _bool_env("PERFORMANCE_AUDIT_ENABLED", False)
    performance_audit_max_records: int = _int_env("PERFORMANCE_AUDIT_MAX_RECORDS", 5000, minimum=100)
    dupont_mode: str = os.getenv("DUPONT_MODE", "auto").lower()
    valuation_workbench_enabled: bool = os.getenv("VALUATION_WORKBENCH_ENABLED", "true").strip().lower() not in {"0", "false", "no"}


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
