from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timezone
from threading import Lock
import re
import time
from typing import Any

import httpx
from sqlalchemy import Select, case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, PriceHistory
from app.services.refresh_state import build_payload_version_hash, cache_state_for_dataset, mark_dataset_checked
from app.services.shared_upstream_cache import shared_upstream_cache


PRICE_SOURCE = "yahoo_finance_chart"
PRICE_HISTORY_PAYLOAD_VERSION = "price-history-v1"
DEFAULT_MARKET_PROFILE_CACHE_TTL_SECONDS = 21600
DEFAULT_PRICE_HISTORY_SHARED_CACHE_BUCKET_SECONDS = 10
_market_profile_cache: dict[str, tuple[float, MarketProfile]] = {}
_market_profile_cache_lock = Lock()


class MarketDataUnavailableError(RuntimeError):
    def __init__(self, symbol: str, message: str) -> None:
        self.symbol = symbol
        super().__init__(message)


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

    def get_price_history(self, ticker: str, *, start_date: date | None = None) -> list[PriceBar]:
        if settings.strict_official_mode:
            return []

        symbol = _normalize_market_symbol(ticker)
        period_start = 0
        if start_date is not None:
            period_start = max(0, int(datetime.combine(start_date, datetime_time.min, tzinfo=timezone.utc).timestamp()))
        period_end = int(time.time())
        cache_key = _price_history_shared_cache_key(
            symbol,
            start_date=start_date,
            period_end=period_end,
        )

        payload = shared_upstream_cache.fill_json(
            cache_key,
            fill=lambda: self._fetch_price_history_payload(
                symbol,
                period_start=period_start,
                period_end=period_end,
            ),
        )
        return _deserialize_price_history_payload(payload)

    def get_market_profile(self, ticker: str) -> MarketProfile:
        if settings.strict_official_mode:
            return MarketProfile(sector=None, industry=None)

        symbol = _normalize_market_symbol(ticker)
        cached = _get_cached_market_profile(symbol)
        if cached is not None:
            return cached

        shared_payload = shared_upstream_cache.fill_json(
            _market_profile_shared_cache_key(symbol),
            fill=lambda: self._fetch_market_profile_payload(symbol),
        )
        profile = _deserialize_market_profile_payload(shared_payload)
        _store_cached_market_profile(symbol, profile)
        return profile

    def _fetch_market_profile_payload(self, symbol: str) -> tuple[dict[str, Any], float]:
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
        profile = _market_profile_from_search_payload(symbol, payload)
        ttl_seconds = _shared_cache_ttl_from_response(
            response,
            maximum_seconds=_get_market_profile_cache_ttl_seconds(),
        )
        return (
            {
                "sector": profile.sector,
                "industry": profile.industry,
            },
            ttl_seconds if profile.sector or profile.industry else 0.0,
        )

    def _fetch_price_history_payload(
        self,
        symbol: str,
        *,
        period_start: int,
        period_end: int,
    ) -> tuple[dict[str, Any], float]:
        try:
            response = _request_with_retries(
                self._http,
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={
                    "period1": period_start,
                    "period2": period_end,
                    "interval": "1d",
                    "includeAdjustedClose": "true",
                },
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                raise MarketDataUnavailableError(symbol, f"Yahoo Finance has no chart history for {symbol}.") from exc
            raise

        price_bars = _parse_price_history_payload(symbol, response.json())
        return (
            {
                "bars": [
                    {
                        "trade_date": bar.trade_date.isoformat(),
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in price_bars
                ]
            },
            _shared_cache_ttl_from_response(response),
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


def get_company_latest_trade_date(session: Session, company_id: int) -> date | None:
    statement = select(func.max(PriceHistory.trade_date)).where(PriceHistory.company_id == company_id)
    return session.execute(statement).scalar_one_or_none()


def get_company_price_history_tail(
    session: Session,
    company_id: int,
    *,
    start_date: date,
) -> list[PriceBar]:
    statement: Select[tuple[PriceHistory]] = (
        select(PriceHistory)
        .where(
            PriceHistory.company_id == company_id,
            PriceHistory.source == PRICE_SOURCE,
            PriceHistory.trade_date >= start_date,
        )
        .order_by(PriceHistory.trade_date.asc())
    )
    return [
        PriceBar(trade_date=row.trade_date, close=row.close, volume=row.volume)
        for row in session.execute(statement).scalars()
    ]


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
            "fetch_timestamp": checked_at,
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
                "fetch_timestamp": statement.excluded.fetch_timestamp,
                "last_checked": statement.excluded.last_checked,
            },
        )
        session.execute(statement)
        total_rows += len(batch)

    return total_rows


def build_price_history_payload_hash(price_bars: list[PriceBar]) -> str:
    payload = [
        {
            "trade_date": bar.trade_date,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in sorted(price_bars, key=lambda item: item.trade_date)
    ]
    return build_payload_version_hash(version=PRICE_HISTORY_PAYLOAD_VERSION, payload=payload)


def touch_company_price_history(
    session: Session,
    company_id: int,
    checked_at: datetime,
    *,
    payload_version_hash: str | None = None,
    touch_rows: bool = True,
    invalidate_hot_cache: bool = True,
) -> None:
    if touch_rows:
        statement = (
            update(PriceHistory)
            .where(PriceHistory.company_id == company_id)
            .values(last_checked=checked_at)
        )
        session.execute(statement)
    mark_dataset_checked(
        session,
        company_id,
        "prices",
        checked_at=checked_at,
        success=True,
        payload_version_hash=payload_version_hash,
        invalidate_hot_cache=invalidate_hot_cache,
    )


def price_bar_windows_match(expected: list[PriceBar], observed: list[PriceBar]) -> bool:
    if len(expected) != len(observed):
        return False
    return all(
        expected_bar.trade_date == observed_bar.trade_date
        and expected_bar.close == observed_bar.close
        and expected_bar.volume == observed_bar.volume
        for expected_bar, observed_bar in zip(expected, observed, strict=True)
    )


def _get_market_profile_cache_ttl_seconds() -> int:
    ttl_seconds = int(getattr(settings, "market_profile_cache_ttl_seconds", DEFAULT_MARKET_PROFILE_CACHE_TTL_SECONDS))
    return max(0, ttl_seconds)


def _get_cached_market_profile(symbol: str) -> MarketProfile | None:
    ttl_seconds = _get_market_profile_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return None

    try:
        cached = None
        now = time.monotonic()
        with _market_profile_cache_lock:
            cached = _market_profile_cache.get(symbol)
            if cached is None:
                return None
            expires_at, profile = cached
            if not isinstance(expires_at, (int, float)) or expires_at <= now or not isinstance(profile, MarketProfile):
                _market_profile_cache.pop(symbol, None)
                return None
            return profile
    except Exception:
        return None


def _store_cached_market_profile(symbol: str, profile: MarketProfile) -> None:
    ttl_seconds = _get_market_profile_cache_ttl_seconds()
    if ttl_seconds <= 0 or not (profile.sector or profile.industry):
        return

    try:
        with _market_profile_cache_lock:
            _market_profile_cache[symbol] = (time.monotonic() + ttl_seconds, profile)
    except Exception:
        return


def _clear_market_profile_cache() -> None:
    with _market_profile_cache_lock:
        _market_profile_cache.clear()


def _clear_market_shared_cache() -> None:
    shared_upstream_cache.clear_local()


def _normalize_market_symbol(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-").replace("/", "-")


def _market_profile_shared_cache_key(symbol: str) -> str:
    return f"market-profile:{symbol}"


def _price_history_shared_cache_key(symbol: str, *, start_date: date | None, period_end: int) -> str:
    start_token = start_date.isoformat() if start_date is not None else "full"
    bucket = _bucket_price_history_period_end(period_end)
    return f"price-history:{symbol}:{start_token}:{bucket}"


def _bucket_price_history_period_end(period_end: int) -> int:
    bucket_seconds = DEFAULT_PRICE_HISTORY_SHARED_CACHE_BUCKET_SECONDS
    if bucket_seconds <= 1:
        return period_end
    return period_end - (period_end % bucket_seconds)


def _deserialize_market_profile_payload(payload: Any) -> MarketProfile:
    if not isinstance(payload, dict):
        return MarketProfile(sector=None, industry=None)
    return MarketProfile(
        sector=_string_or_none(payload.get("sector")),
        industry=_string_or_none(payload.get("industry")),
    )


def _deserialize_price_history_payload(payload: Any) -> list[PriceBar]:
    if not isinstance(payload, dict):
        return []
    bars = payload.get("bars")
    if not isinstance(bars, list):
        return []
    parsed: list[PriceBar] = []
    for item in bars:
        if not isinstance(item, dict):
            continue
        trade_date_text = _string_or_none(item.get("trade_date"))
        if trade_date_text is None:
            continue
        try:
            trade_date = date.fromisoformat(trade_date_text)
        except ValueError:
            continue
        close = _coerce_float(item.get("close"))
        if close is None:
            continue
        parsed.append(
            PriceBar(
                trade_date=trade_date,
                close=close,
                volume=_coerce_int(item.get("volume")),
            )
        )
    parsed.sort(key=lambda bar: bar.trade_date)
    return parsed


def _market_profile_from_search_payload(symbol: str, payload: dict[str, Any]) -> MarketProfile:
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


def _parse_price_history_payload(symbol: str, payload: dict[str, Any]) -> list[PriceBar]:
    chart_root = payload.get("chart", {})
    if chart_root.get("error"):
        error_payload = chart_root["error"]
        if isinstance(error_payload, dict):
            description = _string_or_none(error_payload.get("description")) or _string_or_none(error_payload.get("code"))
            if description and any(token in description.lower() for token in ("not found", "no data", "no price")):
                raise MarketDataUnavailableError(symbol, f"Yahoo Finance has no chart history for {symbol}.")
        raise ValueError(str(error_payload))

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


def _shared_cache_ttl_from_response(response: httpx.Response, *, maximum_seconds: int | None = None) -> float:
    response_headers = getattr(response, "headers", {}) or {}
    cache_control = str(response_headers.get("cache-control") or "")
    match = re.search(r"(?:^|,)\s*max-age\s*=\s*(\d+)\s*(?:,|$)", cache_control, flags=re.IGNORECASE)
    if match is None:
        return 0.0
    ttl_seconds = float(int(match.group(1)))
    if maximum_seconds is not None:
        ttl_seconds = min(ttl_seconds, float(maximum_seconds))
    return max(0.0, ttl_seconds)


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
