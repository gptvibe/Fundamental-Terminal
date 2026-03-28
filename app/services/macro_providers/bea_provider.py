"""Official Bureau of Economic Analysis provider.

Uses the BEA API when a registered API key is configured.
Tracked series:
- Personal consumption expenditures (NIPA)
- GDP by industry for broad company relevance buckets
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
import calendar

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BEA_API_URL = settings.bea_api_base_url
BEA_SOURCE_NAME = "Bureau of Economic Analysis"
BEA_NIPA_SOURCE_URL = "https://www.bea.gov/data/consumer-spending/main"
BEA_GDP_BY_INDUSTRY_SOURCE_URL = "https://www.bea.gov/data/gdp/gdp-industry"


@dataclass(frozen=True, slots=True)
class BeaSeriesSpec:
    series_id: str
    label: str
    units: str
    section: str
    dataset: str
    table_name: str | None = None
    line_number: str | None = None
    table_id: str | None = None
    industry_keywords: tuple[str, ...] = ()


BEA_SERIES_SPECS: tuple[BeaSeriesSpec, ...] = (
    BeaSeriesSpec(
        series_id="bea_pce_total",
        label="Personal Consumption Expenditures",
        units="billions_usd",
        section="growth_activity",
        dataset="NIPA",
        table_name=settings.bea_pce_table_name,
        line_number=settings.bea_pce_line_number,
    ),
    BeaSeriesSpec(
        series_id="bea_gdp_manufacturing",
        label="GDP by Industry: Manufacturing",
        units="billions_usd",
        section="cyclical_demand",
        dataset="GDPByIndustry",
        table_id=settings.bea_gdp_by_industry_table_id,
        industry_keywords=("manufacturing",),
    ),
    BeaSeriesSpec(
        series_id="bea_gdp_retail_trade",
        label="GDP by Industry: Retail Trade",
        units="billions_usd",
        section="cyclical_demand",
        dataset="GDPByIndustry",
        table_id=settings.bea_gdp_by_industry_table_id,
        industry_keywords=("retail trade",),
    ),
    BeaSeriesSpec(
        series_id="bea_gdp_information",
        label="GDP by Industry: Information",
        units="billions_usd",
        section="cyclical_demand",
        dataset="GDPByIndustry",
        table_id=settings.bea_gdp_by_industry_table_id,
        industry_keywords=("information",),
    ),
    BeaSeriesSpec(
        series_id="bea_gdp_professional_services",
        label="GDP by Industry: Professional Services",
        units="billions_usd",
        section="cyclical_demand",
        dataset="GDPByIndustry",
        table_id=settings.bea_gdp_by_industry_table_id,
        industry_keywords=("professional, scientific, and technical services",),
    ),
    BeaSeriesSpec(
        series_id="bea_gdp_health_care",
        label="GDP by Industry: Health Care",
        units="billions_usd",
        section="cyclical_demand",
        dataset="GDPByIndustry",
        table_id=settings.bea_gdp_by_industry_table_id,
        industry_keywords=("health care", "social assistance"),
    ),
    BeaSeriesSpec(
        series_id="bea_gdp_accommodation_food",
        label="GDP by Industry: Accommodation & Food Services",
        units="billions_usd",
        section="cyclical_demand",
        dataset="GDPByIndustry",
        table_id=settings.bea_gdp_by_industry_table_id,
        industry_keywords=("accommodation and food services",),
    ),
    BeaSeriesSpec(
        series_id="bea_gdp_transportation_warehousing",
        label="GDP by Industry: Transportation & Warehousing",
        units="billions_usd",
        section="cyclical_demand",
        dataset="GDPByIndustry",
        table_id=settings.bea_gdp_by_industry_table_id,
        industry_keywords=("transportation and warehousing",),
    ),
)


@dataclass(frozen=True, slots=True)
class BeaSeriesPoint:
    observation_date: date
    value: float


@dataclass(frozen=True, slots=True)
class BeaSeriesResult:
    series_id: str
    label: str
    units: str
    section: str
    status: str
    value: float | None
    previous_value: float | None
    observation_date: date | None
    history: tuple[BeaSeriesPoint, ...]
    source_name: str
    source_url: str


def fetch_bea_series(http_client: httpx.Client | None = None) -> tuple[BeaSeriesResult, ...]:
    """Fetch BEA series using the official BEA API."""
    own_client = http_client is None
    if own_client:
        http_client = httpx.Client(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept": "application/json",
            },
            follow_redirects=True,
            timeout=settings.bea_timeout_seconds,
        )

    try:
        return _fetch_all(http_client)
    finally:
        if own_client:
            http_client.close()


def _fetch_all(http_client: httpx.Client) -> tuple[BeaSeriesResult, ...]:
    if not settings.bea_api_key:
        return tuple(_unavailable_result(spec) for spec in BEA_SERIES_SPECS)

    nipa_rows: list[dict[str, str]] = []
    gdp_rows: list[dict[str, str]] = []
    try:
        nipa_rows = _fetch_nipa_rows(http_client)
    except Exception:
        logger.warning("BEA NIPA fetch failed", exc_info=True)
    try:
        gdp_rows = _fetch_gdp_by_industry_rows(http_client)
    except Exception:
        logger.warning("BEA GDP by industry fetch failed", exc_info=True)

    results: list[BeaSeriesResult] = []
    for spec in BEA_SERIES_SPECS:
        if spec.dataset == "NIPA":
            results.append(_build_nipa_result(spec, nipa_rows))
        else:
            results.append(_build_gdp_by_industry_result(spec, gdp_rows))
    return tuple(results)


def _fetch_nipa_rows(http_client: httpx.Client) -> list[dict[str, str]]:
    years = ",".join(str(year) for year in range(datetime.now(timezone.utc).year - 2, datetime.now(timezone.utc).year + 1))
    response = http_client.get(
        BEA_API_URL,
        params={
            "UserID": settings.bea_api_key,
            "method": "GetData",
            "datasetname": "NIPA",
            "TableName": settings.bea_pce_table_name,
            "LineNumber": settings.bea_pce_line_number,
            "Frequency": "M",
            "Year": years,
            "ResultFormat": "json",
        },
    )
    response.raise_for_status()
    payload = response.json()
    return _extract_bea_rows(payload)


def _fetch_gdp_by_industry_rows(http_client: httpx.Client) -> list[dict[str, str]]:
    years = ",".join(str(year) for year in range(datetime.now(timezone.utc).year - 4, datetime.now(timezone.utc).year + 1))
    response = http_client.get(
        BEA_API_URL,
        params={
            "UserID": settings.bea_api_key,
            "method": "GetData",
            "datasetname": "GDPByIndustry",
            "TableID": settings.bea_gdp_by_industry_table_id,
            "Frequency": "A",
            "Industry": "ALL",
            "Year": years,
            "ResultFormat": "json",
        },
    )
    response.raise_for_status()
    payload = response.json()
    return _extract_bea_rows(payload)


def _extract_bea_rows(payload: dict[str, object]) -> list[dict[str, str]]:
    api_payload = payload.get("BEAAPI") if isinstance(payload, dict) else None
    results = api_payload.get("Results") if isinstance(api_payload, dict) else None
    data = results.get("Data") if isinstance(results, dict) else None
    if not isinstance(data, list):
        return []
    return [{str(key): str(value) for key, value in row.items()} for row in data if isinstance(row, dict)]


def _build_nipa_result(spec: BeaSeriesSpec, rows: list[dict[str, str]]) -> BeaSeriesResult:
    parsed: list[tuple[date, float]] = []
    for row in rows:
        time_period = row.get("TimePeriod") or row.get("Timeperiod")
        value = _parse_bea_number(row.get("DataValue"))
        observation_date = _parse_bea_time_period(time_period)
        if observation_date is None or value is None:
            continue
        parsed.append((observation_date, value))
    return _result_from_parsed(spec, parsed, BEA_SOURCE_NAME, BEA_NIPA_SOURCE_URL)


def _build_gdp_by_industry_result(spec: BeaSeriesSpec, rows: list[dict[str, str]]) -> BeaSeriesResult:
    matched_rows = [
        row
        for row in rows
        if any(keyword in (row.get("IndustrYDescription") or row.get("IndustryDescription") or "").lower() for keyword in spec.industry_keywords)
    ]
    parsed: list[tuple[date, float]] = []
    for row in matched_rows:
        time_period = row.get("TimePeriod") or row.get("Year")
        value = _parse_bea_number(row.get("DataValue"))
        observation_date = _parse_bea_time_period(time_period)
        if observation_date is None or value is None:
            continue
        parsed.append((observation_date, value))
    return _result_from_parsed(spec, parsed, BEA_SOURCE_NAME, BEA_GDP_BY_INDUSTRY_SOURCE_URL)


def _result_from_parsed(spec: BeaSeriesSpec, parsed: list[tuple[date, float]], source_name: str, source_url: str) -> BeaSeriesResult:
    parsed.sort(key=lambda item: item[0])
    if not parsed:
        return _unavailable_result(spec, source_name=source_name, source_url=source_url)
    history = tuple(BeaSeriesPoint(observation_date=obs_date, value=value) for obs_date, value in parsed[-13:])
    latest_date, latest_value = parsed[-1]
    previous_value = parsed[-2][1] if len(parsed) >= 2 else None
    return BeaSeriesResult(
        series_id=spec.series_id,
        label=spec.label,
        units=spec.units,
        section=spec.section,
        status="ok",
        value=latest_value,
        previous_value=previous_value,
        observation_date=latest_date,
        history=history,
        source_name=source_name,
        source_url=source_url,
    )


def _unavailable_result(
    spec: BeaSeriesSpec,
    *,
    source_name: str = BEA_SOURCE_NAME,
    source_url: str | None = None,
) -> BeaSeriesResult:
    if source_url is None:
        source_url = BEA_NIPA_SOURCE_URL if spec.dataset == "NIPA" else BEA_GDP_BY_INDUSTRY_SOURCE_URL
    return BeaSeriesResult(
        series_id=spec.series_id,
        label=spec.label,
        units=spec.units,
        section=spec.section,
        status="unavailable",
        value=None,
        previous_value=None,
        observation_date=None,
        history=(),
        source_name=source_name,
        source_url=source_url,
    )


def _parse_bea_number(raw_value: str | None) -> float | None:
    if raw_value in {None, "", "(NA)", "--"}:
        return None
    try:
        return float(str(raw_value).replace(",", ""))
    except ValueError:
        return None


def _parse_bea_time_period(raw_value: str | None) -> date | None:
    if not raw_value:
        return None
    value = str(raw_value).strip()
    try:
        if "M" in value:
            year_text, month_text = value.split("M", 1)
            year = int(year_text)
            month = int(month_text)
            day = calendar.monthrange(year, month)[1]
            return date(year, month, day)
        if "Q" in value:
            year_text, quarter_text = value.split("Q", 1)
            year = int(year_text)
            quarter = int(quarter_text)
            month = quarter * 3
            day = calendar.monthrange(year, month)[1]
            return date(year, month, day)
        year = int(value)
        return date(year, 12, 31)
    except (ValueError, TypeError):
        return None
