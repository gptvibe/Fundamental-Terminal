"""U.S. Treasury HQM Corporate Bond Yield Curve provider.

Primary source: U.S. Treasury HQM yield curve CSV
  https://home.treasury.gov/system/files/276/hqmYieldCurveData.csv

The HQM (High Quality Market) corporate yield curve is used for:
- Corporate bond discount rates for pension purposes
- HQM spread vs. Treasury benchmark (credit conditions proxy)
- DCF calibration for credit-sensitive sectors
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from io import StringIO

import httpx

from app.config import settings
from app.services.risk_free_rate import _request_with_retries

logger = logging.getLogger(__name__)

HQM_CSV_URL = (
    "https://home.treasury.gov/system/files/276/hqmYieldCurveData.csv"
)
HQM_SOURCE_NAME = "U.S. Treasury HQM Corporate Bond Yield Curve"
HQM_SOURCE_URL = "https://home.treasury.gov/resource-center/economic-policy/corporate-bond-yield-curve"

# Maturities to track (in years, as column headers in the CSV)
HQM_MATURITIES = ("0.5", "1", "2", "3", "5", "7", "10", "15", "20", "25", "30")
HQM_BENCHMARK_MATURITY = "30"  # primary HQM rate for model use


@dataclass(frozen=True, slots=True)
class HqmCurvePoint:
    maturity_label: str  # e.g. "30y"
    rate: float
    observation_date: date


@dataclass(frozen=True, slots=True)
class HqmSnapshot:
    status: str
    curve_points: tuple[HqmCurvePoint, ...]
    hqm_30y: float | None
    observation_date: date | None
    source_name: str
    source_url: str


def fetch_hqm_snapshot(http_client: httpx.Client | None = None) -> HqmSnapshot:
    """Fetch the latest HQM corporate yield curve snapshot."""
    own_client = http_client is None
    if own_client:
        http_client = httpx.Client(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept": "text/csv,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate",
            },
            follow_redirects=True,
            timeout=settings.sec_timeout_seconds,
        )

    try:
        response = _request_with_retries(
            http_client,
            HQM_CSV_URL,
            max_retries=settings.market_max_retries,
            backoff_seconds=settings.market_retry_backoff_seconds,
        )
        return _parse_hqm_csv(response.text)
    except Exception:
        logger.warning("HQM yield curve fetch failed; returning empty snapshot", exc_info=True)
        return HqmSnapshot(
            status="unavailable",
            curve_points=(),
            hqm_30y=None,
            observation_date=None,
            source_name=HQM_SOURCE_NAME,
            source_url=HQM_SOURCE_URL,
        )
    finally:
        if own_client:
            http_client.close()


def _parse_hqm_csv(content: str) -> HqmSnapshot:
    """Parse Treasury HQM CSV.

    The CSV has rows like:
      Date,0.5,1,1.5,2,...,100
    where values are annual percentage rates.
    """
    latest_date: date | None = None
    latest_row: dict[str, str] | None = None

    try:
        reader = csv.DictReader(StringIO(content))
        for row in reader:
            raw_date = (row.get("Date") or row.get("date") or "").strip()
            if not raw_date:
                continue
            for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
                try:
                    observed = datetime.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                continue
            if latest_date is None or observed > latest_date:
                latest_date = observed
                latest_row = row
    except Exception:
        logger.warning("HQM CSV parse failed", exc_info=True)
        return HqmSnapshot(
            status="unavailable",
            curve_points=(),
            hqm_30y=None,
            observation_date=None,
            source_name=HQM_SOURCE_NAME,
            source_url=HQM_SOURCE_URL,
        )

    if latest_row is None or latest_date is None:
        return HqmSnapshot(
            status="unavailable",
            curve_points=(),
            hqm_30y=None,
            observation_date=None,
            source_name=HQM_SOURCE_NAME,
            source_url=HQM_SOURCE_URL,
        )

    points: list[HqmCurvePoint] = []
    for maturity in HQM_MATURITIES:
        raw = (latest_row.get(maturity) or latest_row.get(f"{maturity} yr") or "").strip()
        if not raw:
            continue
        try:
            rate_pct = float(raw)
        except ValueError:
            continue
        label = f"{_maturity_label(maturity)}y"
        points.append(HqmCurvePoint(maturity_label=label, rate=rate_pct / 100.0, observation_date=latest_date))

    hqm_30y: float | None = None
    for point in points:
        if point.maturity_label == f"{_maturity_label(HQM_BENCHMARK_MATURITY)}y":
            hqm_30y = point.rate
            break

    status = "ok" if points else "unavailable"
    return HqmSnapshot(
        status=status,
        curve_points=tuple(points),
        hqm_30y=hqm_30y,
        observation_date=latest_date,
        source_name=HQM_SOURCE_NAME,
        source_url=HQM_SOURCE_URL,
    )


def _maturity_label(maturity_str: str) -> str:
    """Convert '0.5' -> '0.5', '1' -> '1', etc."""
    try:
        value = float(maturity_str)
        return str(int(value)) if value == int(value) else maturity_str
    except ValueError:
        return maturity_str
