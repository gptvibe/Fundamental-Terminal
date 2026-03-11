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


def _load_sec_user_agent() -> str:
    raw_value = os.getenv("SEC_USER_AGENT", "").strip()
    value = raw_value or DEFAULT_SEC_USER_AGENT
    if "@" not in value and "http://" not in value and "https://" not in value:
        logging.getLogger(__name__).warning(
            "SEC_USER_AGENT should include a contact email or URL (for example: 'FundamentalTerminal/1.0 (contact@example.com)')."
        )
    return value


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
    sec_max_retries: int = _int_env("SEC_MAX_RETRIES", 3, minimum=1)
    sec_retry_backoff_seconds: float = _float_env("SEC_RETRY_BACKOFF_SECONDS", 0.5)
    market_max_retries: int = _int_env("MARKET_MAX_RETRIES", 3, minimum=1)
    market_retry_backoff_seconds: float = _float_env("MARKET_RETRY_BACKOFF_SECONDS", 0.5)
    freshness_window_hours: int = _int_env("FRESHNESS_WINDOW_HOURS", 24, minimum=1)
    dupont_mode: str = os.getenv("DUPONT_MODE", "auto").lower()


settings = Settings()
