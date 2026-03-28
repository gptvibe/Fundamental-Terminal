"""Official Census economic indicator provider.

Tracked series:
- M3 manufacturing shipments, new orders, backlog, and inventories
- Monthly retail and food services sales
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CENSUS_SOURCE_NAME = "U.S. Census Bureau Economic Indicators"
M3_SOURCE_URL = "https://api.census.gov/data/timeseries/eits/m3"
RETAIL_SOURCE_URL = "https://api.census.gov/data/timeseries/eits/marts"
_HISTORY_MONTHS = 13

_M3_SERIES: tuple[tuple[str, str, str], ...] = (
    ("VS", "Manufacturing Shipments (M3)", "census_m3_shipments_total"),
    ("NO", "Manufacturing New Orders (M3)", "census_m3_new_orders_total"),
    ("UO", "Manufacturing Backlog (M3)", "census_m3_backlog_total"),
    ("TI", "Manufacturing Inventories (M3)", "census_m3_inventories_total"),
)


@dataclass(frozen=True, slots=True)
class CensusSeriesPoint:
    observation_date: date
    value: float


@dataclass(frozen=True, slots=True)
class CensusSeriesResult:
    series_id: str
    label: str
    units: str
    section: str
    status: str
    value: float | None
    previous_value: float | None
    observation_date: date | None
    history: tuple[CensusSeriesPoint, ...]
    source_name: str
    source_url: str


def fetch_census_series(http_client: httpx.Client | None = None) -> tuple[CensusSeriesResult, ...]:
    own_client = http_client is None
    if own_client:
        http_client = httpx.Client(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept": "application/json",
            },
            follow_redirects=True,
            timeout=settings.census_timeout_seconds,
        )

    try:
        return _fetch_all(http_client)
    finally:
        if own_client:
            http_client.close()


def _fetch_all(http_client: httpx.Client) -> tuple[CensusSeriesResult, ...]:
    start_month, end_month = _history_window(_HISTORY_MONTHS)

    results: list[CensusSeriesResult] = []
    try:
        m3_rows = _fetch_rows(
            http_client,
            f"{settings.census_api_base_url.rstrip('/')}/m3",
            params={
                "get": "data_type_code,category_code,time_slot_id,seasonally_adj,cell_value",
                "for": "us:1",
                "seasonally_adj": "yes",
                "category_code": "MTM",
                "time_slot_id": "0",
                "time": f"from {start_month} to {end_month}",
            },
        )
    except Exception:
        logger.warning("Census M3 fetch failed", exc_info=True)
        m3_rows = []

    for data_type_code, label, series_id in _M3_SERIES:
        results.append(
            _build_result(
                rows=m3_rows,
                source_url=M3_SOURCE_URL,
                label=label,
                series_id=series_id,
                data_type_code=data_type_code,
                units="millions_usd",
                section="cyclical_demand",
            )
        )

    try:
        retail_rows = _fetch_rows(
            http_client,
            f"{settings.census_api_base_url.rstrip('/')}/marts",
            params={
                "get": "data_type_code,category_code,seasonally_adj,cell_value",
                "for": "us:1",
                "seasonally_adj": "yes",
                "category_code": "44X72",
                "data_type_code": "SM",
                "time": f"from {start_month} to {end_month}",
            },
        )
    except Exception:
        logger.warning("Census retail sales fetch failed", exc_info=True)
        retail_rows = []

    results.append(
        _build_result(
            rows=retail_rows,
            source_url=RETAIL_SOURCE_URL,
            label="Retail & Food Services Sales",
            series_id="census_retail_sales_total",
            data_type_code="SM",
            units="millions_usd",
            section="cyclical_demand",
        )
    )

    return tuple(results)


def _fetch_rows(http_client: httpx.Client, url: str, *, params: dict[str, str]) -> list[dict[str, str]]:
    request_params = dict(params)
    if settings.census_api_key:
        request_params["key"] = settings.census_api_key
    response = http_client.get(url, params=request_params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        return []
    header = payload[0]
    if not isinstance(header, list):
        return []

    rows: list[dict[str, str]] = []
    for raw_row in payload[1:]:
        if not isinstance(raw_row, list):
            continue
        rows.append({str(key): str(value) for key, value in zip(header, raw_row, strict=False)})
    return rows


def _build_result(
    *,
    rows: list[dict[str, str]],
    source_url: str,
    label: str,
    series_id: str,
    data_type_code: str,
    units: str,
    section: str,
) -> CensusSeriesResult:
    parsed: list[tuple[date, float]] = []
    for row in rows:
        if str(row.get("data_type_code") or "") != data_type_code:
            continue
        parsed_date = _parse_month(row.get("time"))
        raw_value = row.get("cell_value")
        if parsed_date is None or raw_value in {None, "", "."}:
            continue
        try:
            parsed_value = float(str(raw_value).replace(",", ""))
        except ValueError:
            continue
        parsed.append((parsed_date, parsed_value))

    parsed.sort(key=lambda item: item[0])
    if not parsed:
        return CensusSeriesResult(
            series_id=series_id,
            label=label,
            units=units,
            section=section,
            status="unavailable",
            value=None,
            previous_value=None,
            observation_date=None,
            history=(),
            source_name=CENSUS_SOURCE_NAME,
            source_url=source_url,
        )

    history = tuple(CensusSeriesPoint(observation_date=obs_date, value=value) for obs_date, value in parsed[-13:])
    latest_date, latest_value = parsed[-1]
    previous_value = parsed[-2][1] if len(parsed) >= 2 else None
    return CensusSeriesResult(
        series_id=series_id,
        label=label,
        units=units,
        section=section,
        status="ok",
        value=latest_value,
        previous_value=previous_value,
        observation_date=latest_date,
        history=history,
        source_name=CENSUS_SOURCE_NAME,
        source_url=source_url,
    )


def _history_window(months: int) -> tuple[str, str]:
    current = datetime.now(timezone.utc)
    end_month = f"{current.year:04d}-{current.month:02d}"
    start_year = current.year
    start_month = current.month - (months - 1)
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    return f"{start_year:04d}-{start_month:02d}", end_month


def _parse_month(value: str | None) -> date | None:
    if not value:
        return None
    try:
        year_text, month_text = value.split("-", 1)
        year = int(year_text)
        month = int(month_text)
        day = calendar.monthrange(year, month)[1]
        return date(year, month, day)
    except (ValueError, TypeError):
        return None