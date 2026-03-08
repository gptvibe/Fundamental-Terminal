from __future__ import annotations

import os
from dataclasses import dataclass


SEC_USER_AGENT = "MyFinanceApp/1.0 (KH; kh@example.com)"


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:password@localhost:5432/database_name",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    sec_user_agent: str = SEC_USER_AGENT
    sec_ticker_lookup_url: str = "https://www.sec.gov/files/company_tickers.json"
    sec_submissions_base_url: str = "https://data.sec.gov/submissions"
    sec_companyfacts_base_url: str = "https://data.sec.gov/api/xbrl/companyfacts"
    sec_search_base_url: str = "https://efts.sec.gov/LATEST/search-index"
    sec_timeout_seconds: float = float(os.getenv("SEC_TIMEOUT_SECONDS", "30"))
    sec_min_request_interval_seconds: float = float(
        os.getenv("SEC_MIN_REQUEST_INTERVAL_SECONDS", "0.2")
    )
    sec_form4_max_filings_per_refresh: int = int(os.getenv("SEC_FORM4_MAX_FILINGS_PER_REFRESH", "80"))
    sec_13f_manager_limit: int = int(os.getenv("SEC_13F_MANAGER_LIMIT", "8"))
    freshness_window_hours: int = int(os.getenv("FRESHNESS_WINDOW_HOURS", "24"))


settings = Settings()
