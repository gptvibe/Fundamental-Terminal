"""Bureau of Economic Analysis (BEA) / growth & activity provider.

Primary sources (with BEA API key): BEA NIPA tables
Fallback (no BEA key): Federal Reserve Economic Data (FRED) supplemental

Series tracked (growth_activity section):
- GDPC1 / A191RL1Q225SBEA  Real GDP (QoQ annualized rate)
- PI                        Personal Income (monthly, level)
- PCE / DPCERX1Q020SBEA    Personal Consumption Expenditures (% change)
- CP                        Corporate Profits After Tax (FRED: CP)

All via FRED when no BEA key is set. FRED is explicit supplemental here.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
BEA_SOURCE_NAME = "Bureau of Economic Analysis (NIPA)"
BEA_SOURCE_URL = "https://www.bea.gov/data/gdp/"
FRED_SOURCE_NAME = "Federal Reserve Economic Data (FRED)"
FRED_SOURCE_URL = "https://fred.stlouisfed.org/"

# Series: (series_id, label, units, section, fred_units_transform)
# fred_units_transform: None = level, "pc1" = YoY %, "pch" = period-over-period %
GROWTH_SERIES: tuple[tuple[str, str, str, str, str | None], ...] = (
    ("A191RL1Q225SBEA", "Real GDP (QoQ annualized)", "percent", "growth_activity", None),
    ("PI", "Personal Income", "billions_usd", "growth_activity", None),
    ("PCE", "Personal Consumption Expenditures", "billions_usd", "growth_activity", None),
    ("CP", "Corporate Profits After Tax", "billions_usd", "growth_activity", None),
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
    """Fetch all growth/activity series. Uses FRED as source when FRED key is available."""
    own_client = http_client is None
    if own_client:
        http_client = httpx.Client(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept": "application/json",
            },
            follow_redirects=True,
            timeout=settings.sec_timeout_seconds,
        )

    try:
        return _fetch_via_fred(http_client)
    finally:
        if own_client:
            http_client.close()


def _fetch_via_fred(http_client: httpx.Client) -> tuple[BeaSeriesResult, ...]:
    """Fetch all series via FRED API. Requires a FRED API key."""
    if not settings.fred_api_key:
        # No FRED key - return empty stubs so the rest of the system can continue
        logger.debug("No FRED API key configured; BEA/growth series unavailable")
        return tuple(
            BeaSeriesResult(
                series_id=sid,
                label=label,
                units=units,
                section=section,
                status="unavailable",
                value=None,
                previous_value=None,
                observation_date=None,
                history=(),
                source_name=FRED_SOURCE_NAME,
                source_url=FRED_SOURCE_URL,
            )
            for sid, label, units, section, _ in GROWTH_SERIES
        )

    results: list[BeaSeriesResult] = []
    for series_id, label, units, section, fred_units in GROWTH_SERIES:
        result = _fetch_single_fred(http_client, series_id, label, units, section, fred_units)
        results.append(result)

    return tuple(results)


def _fetch_single_fred(
    http_client: httpx.Client,
    series_id: str,
    label: str,
    units: str,
    section: str,
    fred_units: str | None,
) -> BeaSeriesResult:
    units_param = f"&units={fred_units}" if fred_units else ""
    url = (
        f"{FRED_BASE_URL}?series_id={series_id}"
        f"&api_key={settings.fred_api_key}"
        f"&file_type=json&sort_order=desc&limit=20{units_param}"
    )
    try:
        for attempt in range(settings.market_max_retries):
            response = http_client.get(url)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < settings.market_max_retries - 1:
                time.sleep(settings.market_retry_backoff_seconds * (attempt + 1))
                continue
            break

        payload = response.json()
        observations = payload.get("observations") if isinstance(payload, dict) else None
        if not isinstance(observations, list) or not observations:
            raise ValueError("No observations in FRED response")

        parsed: list[tuple[date, float]] = []
        for obs in observations:
            raw_date = str(obs.get("date") or "")
            raw_value = str(obs.get("value") or "")
            if not raw_date or raw_value in (".", ""):
                continue
            try:
                obs_date = date.fromisoformat(raw_date)
                obs_value = float(raw_value)
            except (ValueError, TypeError):
                continue
            parsed.append((obs_date, obs_value))

        # Observations come desc from FRED; reverse for chronological
        parsed.sort(key=lambda x: x[0])

        if not parsed:
            raise ValueError("No valid observations parsed")

        history = tuple(BeaSeriesPoint(observation_date=d, value=v) for d, v in parsed[-13:])
        latest_date, latest_value = parsed[-1]
        prev_value = parsed[-2][1] if len(parsed) >= 2 else None

        return BeaSeriesResult(
            series_id=series_id,
            label=label,
            units=units,
            section=section,
            status="ok",
            value=latest_value,
            previous_value=prev_value,
            observation_date=latest_date,
            history=history,
            source_name=FRED_SOURCE_NAME,
            source_url=FRED_SOURCE_URL,
        )
    except Exception:
        logger.warning("FRED fetch failed for %s", series_id, exc_info=True)
        return BeaSeriesResult(
            series_id=series_id,
            label=label,
            units=units,
            section=section,
            status="unavailable",
            value=None,
            previous_value=None,
            observation_date=None,
            history=(),
            source_name=FRED_SOURCE_NAME,
            source_url=FRED_SOURCE_URL,
        )
