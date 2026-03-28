"""Bureau of Labor Statistics (BLS) official-source provider.

Primary source: BLS Public Data API v2.

Series tracked:
- CPI, core CPI, PPI, unemployment, payrolls
- ECI total compensation
- JOLTS job openings, hires, quits, and total separations
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

BLS_SOURCE_NAME = "U.S. Bureau of Labor Statistics"
BLS_SOURCE_URL = "https://www.bls.gov/data/"

# Series definitions: (series_id, label, units, section, compute_yoy)
BLS_SERIES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("CUSR0000SA0", "CPI (Urban, All Items)", "percent", "inflation_labor", True),
    ("CUSR0000SA0L1E", "Core CPI (ex Food & Energy)", "percent", "inflation_labor", True),
    ("WPSFD4", "PPI Final Demand", "percent", "cyclical_costs", True),
    ("LNS14000000", "Unemployment Rate", "percent", "inflation_labor", False),
    ("CES0000000001", "Nonfarm Payrolls", "thousands", "inflation_labor", False),
    ("CIU1010000000000I", "Employment Cost Index (Total Compensation)", "percent", "cyclical_costs", True),
    ("JTS000000000000000JOL", "JOLTS Job Openings", "thousands", "cyclical_costs", False),
    ("JTS000000000000000HIL", "JOLTS Hires", "thousands", "cyclical_costs", False),
    ("JTS000000000000000QUL", "JOLTS Quits", "thousands", "cyclical_costs", False),
    ("JTS000000000000000TSL", "JOLTS Total Separations", "thousands", "cyclical_costs", False),
)

HISTORY_MONTHS = 13  # request enough history to compute YoY and 12m sparkline


@dataclass(frozen=True, slots=True)
class BlsSeriesPoint:
    observation_date: date
    value: float


@dataclass(frozen=True, slots=True)
class BlsSeriesResult:
    series_id: str
    label: str
    units: str
    section: str
    status: str
    value: float | None
    previous_value: float | None
    observation_date: date | None
    history: tuple[BlsSeriesPoint, ...]
    source_name: str
    source_url: str


def fetch_bls_series(http_client: httpx.Client | None = None) -> tuple[BlsSeriesResult, ...]:
    """Fetch all tracked BLS series in one batch request."""
    own_client = http_client is None
    if own_client:
        http_client = httpx.Client(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            follow_redirects=True,
            timeout=settings.bls_timeout_seconds,
        )

    try:
        return _fetch_all(http_client)
    finally:
        if own_client:
            http_client.close()


def _fetch_all(http_client: httpx.Client) -> tuple[BlsSeriesResult, ...]:
    now = datetime.now(timezone.utc)
    start_year = str(now.year - 2)
    end_year = str(now.year)

    series_ids = [s[0] for s in BLS_SERIES]
    request_payload = {"seriesid": series_ids, "startyear": start_year, "endyear": end_year}
    if settings.bls_api_key:
        request_payload["registrationkey"] = settings.bls_api_key
    request_body = json.dumps(request_payload)

    raw_data: dict[str, list[dict]] = {}
    try:
        for attempt in range(settings.market_max_retries):
            try:
                response = http_client.post(settings.bls_api_base_url, content=request_body)
            except Exception as exc:
                # Transient network failures are common; retry before falling back.
                is_last = attempt >= settings.market_max_retries - 1
                if not is_last:
                    time.sleep(settings.market_retry_backoff_seconds * (attempt + 1))
                    continue
                logger.warning("BLS batch fetch failed after retries: %s", exc)
                break
            if response.status_code in {429, 500, 502, 503, 504} and attempt < settings.market_max_retries - 1:
                time.sleep(settings.market_retry_backoff_seconds * (attempt + 1))
                continue
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, dict) and payload.get("status") == "REQUEST_SUCCEEDED":
                    for series_data in payload.get("Results", {}).get("series", []):
                        sid = str(series_data.get("seriesID") or "")
                        observations = series_data.get("data") or []
                        if sid and isinstance(observations, list):
                            raw_data[sid] = observations
                break
            break
    except Exception:
            logger.warning("BLS batch fetch failed", exc_info=True)

    results: list[BlsSeriesResult] = []
    for series_id, label, units, section, compute_yoy in BLS_SERIES:
        observations = raw_data.get(series_id) or []
        result = _build_series_result(series_id, label, units, section, compute_yoy, observations)
        results.append(result)

    return tuple(results)


def _build_series_result(
    series_id: str,
    label: str,
    units: str,
    section: str,
    compute_yoy: bool,
    raw_observations: list[dict],
) -> BlsSeriesResult:
    """Parse raw BLS observations into a typed result."""
    if not raw_observations:
        return BlsSeriesResult(
            series_id=series_id,
            label=label,
            units=units,
            section=section,
            status="unavailable",
            value=None,
            previous_value=None,
            observation_date=None,
            history=(),
            source_name=BLS_SOURCE_NAME,
            source_url=BLS_SOURCE_URL,
        )

    # Parse and sort ascending by date
    parsed: list[tuple[date, float]] = []
    for obs in raw_observations:
        value_str = str(obs.get("value") or "")
        year_str = str(obs.get("year") or "")
        period_str = str(obs.get("period") or "")  # M01..M12 or A01
        if not value_str or value_str == "-" or not year_str:
            continue
        try:
            value = float(value_str)
        except ValueError:
            continue
        # Decode period: M01 = January
        obs_date: date | None = _decode_period(year_str, period_str)
        if obs_date is None:
            continue
        parsed.append((obs_date, value))

    parsed.sort(key=lambda x: x[0])

    if not parsed:
        return BlsSeriesResult(
            series_id=series_id,
            label=label,
            units=units,
            section=section,
            status="unavailable",
            value=None,
            previous_value=None,
            observation_date=None,
            history=(),
            source_name=BLS_SOURCE_NAME,
            source_url=BLS_SOURCE_URL,
        )

    history_points = tuple(BlsSeriesPoint(observation_date=d, value=v) for d, v in parsed[-13:])

    latest_date, latest_raw = parsed[-1]

    if compute_yoy:
        # Find the value 12 months prior
        prior_value: float | None = None
        for obs_date, obs_value in reversed(parsed[:-1]):
            if abs((latest_date.year - obs_date.year) * 12 + (latest_date.month - obs_date.month) - 12) <= 1:
                prior_value = obs_value
                break

        if prior_value is not None and prior_value != 0:
            yoy_pct = (latest_raw - prior_value) / abs(prior_value) * 100.0
        else:
            yoy_pct = None

        previous_date, previous_raw = parsed[-2] if len(parsed) >= 2 else (None, None)
        prev_yoy: float | None = None
        if previous_date is not None and previous_raw is not None:
            prev_prior: float | None = None
            for obs_date, obs_value in reversed(parsed[:-2]):
                if abs((previous_date.year - obs_date.year) * 12 + (previous_date.month - obs_date.month) - 12) <= 1:
                    prev_prior = obs_value
                    break
            if prev_prior is not None and prev_prior != 0 and previous_raw is not None:
                prev_yoy = (previous_raw - prev_prior) / abs(prev_prior) * 100.0

        return BlsSeriesResult(
            series_id=series_id,
            label=label,
            units=units,
            section=section,
            status="ok",
            value=yoy_pct,
            previous_value=prev_yoy,
            observation_date=latest_date,
            history=history_points,
            source_name=BLS_SOURCE_NAME,
            source_url=BLS_SOURCE_URL,
        )
    else:
        # Return level value directly
        prev_level = parsed[-2][1] if len(parsed) >= 2 else None
        return BlsSeriesResult(
            series_id=series_id,
            label=label,
            units=units,
            section=section,
            status="ok",
            value=latest_raw,
            previous_value=prev_level,
            observation_date=latest_date,
            history=history_points,
            source_name=BLS_SOURCE_NAME,
            source_url=BLS_SOURCE_URL,
        )


def _decode_period(year: str, period: str) -> date | None:
    """Decode BLS year/period into a date. Period is 'M01'..'M12' or 'A01' (annual)."""
    try:
        year_int = int(year)
        if period.startswith("M") and len(period) == 3:
            month_int = int(period[1:])
            if 1 <= month_int <= 12:
                return date(year_int, month_int, 28)
        elif period.startswith("Q") and len(period) == 3:
            quarter = int(period[1:])
            month = quarter * 3
            if 1 <= month <= 12:
                return date(year_int, month, 28)
        elif period == "A01":
            return date(year_int, 12, 31)
    except (ValueError, TypeError):
        pass
    return None
