from __future__ import annotations

import logging
import os
from dataclasses import dataclass


DEFAULT_SEC_USER_AGENT = "FundamentalTerminal/1.0 (contact@example.com)"


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
        "postgresql+psycopg://user:password@localhost:5432/database_name",
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
    sec_filings_timeline_ttl_seconds: int = _int_env("SEC_FILINGS_TIMELINE_TTL_SECONDS", 300, minimum=30)
    sec_form4_max_filings_per_refresh: int = _int_env("SEC_FORM4_MAX_FILINGS_PER_REFRESH", 80, minimum=1)
    sec_13f_manager_limit: int = _int_env("SEC_13F_MANAGER_LIMIT", 8, minimum=1)
    sec_13f_history_quarters: int = _int_env("SEC_13F_HISTORY_QUARTERS", 4, minimum=2)
    sec_13f_universe_mode: str = os.getenv("SEC_13F_UNIVERSE_MODE", "curated").strip().lower()
    sec_13f_extra_managers: tuple[str, ...] = _csv_env("SEC_13F_EXTRA_MANAGERS")
    sec_max_retries: int = _int_env("SEC_MAX_RETRIES", 3, minimum=1)
    sec_retry_backoff_seconds: float = _float_env("SEC_RETRY_BACKOFF_SECONDS", 0.5)
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
    dupont_mode: str = os.getenv("DUPONT_MODE", "auto").lower()
    valuation_workbench_enabled: bool = os.getenv("VALUATION_WORKBENCH_ENABLED", "true").strip().lower() not in {"0", "false", "no"}


settings = Settings()
