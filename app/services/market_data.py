from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import time
from typing import Any

import httpx
from sqlalchemy import Select, case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, PriceHistory
from app.services.refresh_state import cache_state_for_dataset, mark_dataset_checked


PRICE_SOURCE = "yahoo_finance_chart"


@dataclass(slots=True)
class PriceBar:
    trade_date: date
    close: float
    volume: int | None


@dataclass(slots=True)
class MarketProfile:
    sector: str | None
    industry: str | None


class MarketDataClient:
    def __init__(self) -> None:
        self._http = httpx.Client(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
            follow_redirects=True,
            timeout=settings.sec_timeout_seconds,
        )

    def close(self) -> None:
        self._http.close()

    def get_price_history(self, ticker: str) -> list[PriceBar]:
        symbol = _normalize_market_symbol(ticker)
        period_end = int(time.time())
        response = _request_with_retries(
            self._http,
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={
                "period1": 0,
                "period2": period_end,
                "interval": "1d",
                "includeAdjustedClose": "true",
            },
        )

        payload = response.json()
        chart_root = payload.get("chart", {})
        if chart_root.get("error"):
            raise ValueError(str(chart_root["error"]))

        results = chart_root.get("result") or []
        if not results:
            return []

        result = results[0]
        timestamps = result.get("timestamp") or []
        indicators = result.get("indicators") or {}
        quote = ((indicators.get("quote") or [{}])[0]) if isinstance(indicators.get("quote"), list) else {}
        adjclose_root = ((indicators.get("adjclose") or [{}])[0]) if isinstance(indicators.get("adjclose"), list) else {}
        close_values = adjclose_root.get("adjclose") or quote.get("close") or []
        volume_values = quote.get("volume") or []

        bars: list[PriceBar] = []
        for index, timestamp in enumerate(timestamps):
            close = _coerce_float(_value_at(close_values, index))
            if close is None:
                continue

            trade_date = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date()
            volume = _coerce_int(_value_at(volume_values, index))
            bars.append(PriceBar(trade_date=trade_date, close=close, volume=volume))

        bars.sort(key=lambda bar: bar.trade_date)
        return bars

    def get_market_profile(self, ticker: str) -> MarketProfile:
        symbol = _normalize_market_symbol(ticker)
        response = _request_with_retries(
            self._http,
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={
                "q": symbol,
                "quotesCount": 12,
                "newsCount": 0,
                "listsCount": 0,
                "enableFuzzyQuery": "false",
            },
        )
        payload = response.json()
        quotes = payload.get("quotes") or []
        exact_match = next(
            (
                item
                for item in quotes
                if isinstance(item, dict)
                and str(item.get("symbol", "")).upper() == symbol
                and str(item.get("quoteType", "")).upper() == "EQUITY"
            ),
            None,
        )
        if exact_match is None:
            exact_match = next(
                (
                    item
                    for item in quotes
                    if isinstance(item, dict) and str(item.get("quoteType", "")).upper() == "EQUITY"
                ),
                None,
            )

        if exact_match is None:
            return MarketProfile(sector=None, industry=None)

        return MarketProfile(
            sector=_string_or_none(exact_match.get("sectorDisp") or exact_match.get("sector")),
            industry=_string_or_none(exact_match.get("industryDisp") or exact_match.get("industry")),
        )


def get_company_price_history(session: Session, company_id: int) -> list[PriceHistory]:
    statement: Select[tuple[PriceHistory]] = (
        select(PriceHistory)
        .where(PriceHistory.company_id == company_id)
        .order_by(PriceHistory.trade_date.asc())
    )
    return list(session.execute(statement).scalars())


def get_company_price_last_checked(session: Session, company_id: int) -> datetime | None:
    state_last_checked, state_cache = cache_state_for_dataset(session, company_id, "prices")
    if state_cache != "missing":
        return state_last_checked

    statement = select(func.max(PriceHistory.last_checked)).where(PriceHistory.company_id == company_id)
    scanned = session.execute(statement).scalar_one_or_none()
    if scanned is not None:
        mark_dataset_checked(session, company_id, "prices", checked_at=scanned, success=True)
    return scanned


def upsert_price_history(
    session: Session,
    company: Company,
    price_bars: list[PriceBar],
    checked_at: datetime,
) -> int:
    if not price_bars:
        return 0

    payload = [
        {
            "company_id": company.id,
            "trade_date": bar.trade_date,
            "close": bar.close,
            "volume": bar.volume,
            "source": PRICE_SOURCE,
            "last_updated": checked_at,
            "last_checked": checked_at,
        }
        for bar in price_bars
    ]

    # Keep only one row per unique conflict key to avoid PostgreSQL cardinality violations.
    deduplicated_payload: dict[tuple[int, Any, str], dict[str, Any]] = {}
    for row in payload:
        key = (row["company_id"], row["trade_date"], row["source"])
        deduplicated_payload[key] = row

    unique_payload = list(deduplicated_payload.values())

    total_rows = 0
    for batch in _chunked(unique_payload, size=5000):
        statement = insert(PriceHistory).values(batch)
        data_changed = or_(
            PriceHistory.close.is_distinct_from(statement.excluded.close),
            PriceHistory.volume.is_distinct_from(statement.excluded.volume),
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_price_history_company_date_source",
            set_={
                "close": statement.excluded.close,
                "volume": statement.excluded.volume,
                "last_updated": case(
                    (data_changed, statement.excluded.last_updated),
                    else_=PriceHistory.last_updated,
                ),
                "last_checked": statement.excluded.last_checked,
            },
        )
        session.execute(statement)
        total_rows += len(batch)

    return total_rows


def touch_company_price_history(session: Session, company_id: int, checked_at: datetime) -> None:
    statement = (
        update(PriceHistory)
        .where(PriceHistory.company_id == company_id)
        .values(last_checked=checked_at)
    )
    session.execute(statement)
    mark_dataset_checked(session, company_id, "prices", checked_at=checked_at, success=True)


def _normalize_market_symbol(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-").replace("/", "-")


def _value_at(values: list[Any] | None, index: int) -> Any:
    if values is None or index >= len(values):
        return None
    return values[index]


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    coerced = float(value)
    if not coerced == coerced:
        return None
    return coerced


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    coerced = int(value)
    return coerced if coerced >= 0 else None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def _request_with_retries(client: httpx.Client, url: str, *, params: dict[str, Any]) -> httpx.Response:
    max_retries = settings.market_max_retries
    backoff = settings.market_retry_backoff_seconds
    for attempt in range(max_retries):
        response = client.get(url, params=params)
        if response.status_code in {429, 500, 502, 503, 504} and attempt < max_retries - 1:
            retry_after = response.headers.get("retry-after")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff * (2 ** attempt)
            response.close()
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response
    response.raise_for_status()
    return response
