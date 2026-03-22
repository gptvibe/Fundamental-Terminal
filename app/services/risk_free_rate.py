from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TREASURY_SOURCE_NAME = "U.S. Treasury Daily Par Yield Curve"
TREASURY_TENOR = "10y"
TREASURY_FALLBACK_SOURCE_NAME = "U.S. Treasury FiscalData Average Interest Rates"
TREASURY_FALLBACK_TENOR = "10y_proxy"
TREASURY_FALLBACK_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/"
    "accounting/od/avg_interest_rates?sort=-record_date&page[number]=1&page[size]=50"
)


@dataclass(frozen=True, slots=True)
class RiskFreeRateSnapshot:
    source_name: str
    tenor: str
    observation_date: date
    rate_used: float
    fetched_at: datetime


class RiskFreeRateClient:
    def __init__(self, cache_file: Path | None = None) -> None:
        default_cache = Path(__file__).resolve().parents[2] / "data" / "market_cache" / "risk_free_rate.json"
        self._cache_file = cache_file or default_cache
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._http = httpx.Client(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept": "text/csv,application/xml,text/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate",
            },
            follow_redirects=True,
            timeout=settings.sec_timeout_seconds,
        )

    def close(self) -> None:
        self._http.close()

    def get_latest_10y_rate(self) -> RiskFreeRateSnapshot:
        cached = self._read_cache()
        now = datetime.now(timezone.utc)
        if cached is not None and now - cached.fetched_at < timedelta(hours=24):
            return cached

        try:
            fresh = self._fetch_treasury_10y_rate()
            self._write_cache(fresh)
            return fresh
        except Exception:
            if cached is not None:
                logger.warning("Treasury rate unavailable, using cached value from %s", cached.observation_date.isoformat())
                return cached
            raise

    def _fetch_treasury_10y_rate(self) -> RiskFreeRateSnapshot:
        try:
            response = _request_with_retries(
                self._http,
                settings.treasury_yield_curve_csv_url,
                max_retries=settings.treasury_max_retries,
                backoff_seconds=settings.treasury_retry_backoff_seconds,
            )
            return _parse_treasury_csv_snapshot(response.text)
        except Exception as exc:
            logger.warning("Treasury CSV source unavailable (%s). Falling back to FiscalData proxy rate.", exc)
            response = _request_with_retries(
                self._http,
                TREASURY_FALLBACK_URL,
                max_retries=settings.treasury_max_retries,
                backoff_seconds=settings.treasury_retry_backoff_seconds,
            )
            return _parse_fiscaldata_proxy_snapshot(response.text)

    def _read_cache(self) -> RiskFreeRateSnapshot | None:
        if not self._cache_file.exists():
            return None
        try:
            payload = json.loads(self._cache_file.read_text(encoding="utf-8"))
            return RiskFreeRateSnapshot(
                source_name=str(payload["source_name"]),
                tenor=str(payload["tenor"]),
                observation_date=date.fromisoformat(str(payload["observation_date"])),
                rate_used=float(payload["rate_used"]),
                fetched_at=_parse_datetime_utc(str(payload["fetched_at"])),
            )
        except Exception:
            return None

    def _write_cache(self, snapshot: RiskFreeRateSnapshot) -> None:
        payload = asdict(snapshot)
        payload["observation_date"] = snapshot.observation_date.isoformat()
        payload["fetched_at"] = snapshot.fetched_at.isoformat()
        tmp = self._cache_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp.replace(self._cache_file)


def get_latest_risk_free_rate() -> RiskFreeRateSnapshot:
    client = RiskFreeRateClient()
    try:
        return client.get_latest_10y_rate()
    finally:
        client.close()


def _parse_datetime_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_treasury_csv_snapshot(content: str) -> RiskFreeRateSnapshot:
    latest_date: date | None = None
    latest_rate: float | None = None
    for row in csv.DictReader(StringIO(content)):
        raw_date = (row.get("Date") or row.get("date") or "").strip()
        raw_10y = (row.get("10 Yr") or row.get("10 yr") or row.get("10YR") or row.get("10-year") or "").strip()
        if not raw_date or not raw_10y:
            continue
        try:
            observed = datetime.strptime(raw_date, "%m/%d/%Y").date()
            rate_percent = float(raw_10y)
        except ValueError:
            continue
        if latest_date is None or observed > latest_date:
            latest_date = observed
            latest_rate = rate_percent / 100.0

    if latest_date is None or latest_rate is None:
        raise ValueError("Treasury CSV did not contain a usable 10-year yield")

    return RiskFreeRateSnapshot(
        source_name=TREASURY_SOURCE_NAME,
        tenor=TREASURY_TENOR,
        observation_date=latest_date,
        rate_used=latest_rate,
        fetched_at=datetime.now(timezone.utc),
    )


def _parse_fiscaldata_proxy_snapshot(content: str) -> RiskFreeRateSnapshot:
    payload = json.loads(content)
    records = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        raise ValueError("FiscalData response did not contain records")

    # The avg_interest_rates dataset does not expose the 10Y point directly.
    # Use the latest Treasury Bonds average rate as a stable no-key proxy.
    for record in records:
        if not isinstance(record, dict):
            continue
        security_desc = str(record.get("security_desc") or "").lower()
        if "treasury bonds" not in security_desc:
            continue
        record_date = str(record.get("record_date") or "")
        rate_text = str(record.get("avg_interest_rate_amt") or "")
        try:
            observed = date.fromisoformat(record_date)
            rate_percent = float(rate_text)
        except ValueError:
            continue
        return RiskFreeRateSnapshot(
            source_name=TREASURY_FALLBACK_SOURCE_NAME,
            tenor=TREASURY_FALLBACK_TENOR,
            observation_date=observed,
            rate_used=rate_percent / 100.0,
            fetched_at=datetime.now(timezone.utc),
        )

    raise ValueError("FiscalData response did not contain Treasury Bonds proxy rate")


def _request_with_retries(
    client: httpx.Client,
    url: str,
    *,
    max_retries: int,
    backoff_seconds: float,
) -> httpx.Response:
    response: httpx.Response | None = None
    for attempt in range(max_retries):
        response = client.get(url)
        if response.status_code in {429, 500, 502, 503, 504} and attempt < max_retries - 1:
            retry_after = response.headers.get("retry-after")
            try:
                wait = float(retry_after) if retry_after else backoff_seconds * (2**attempt)
            except ValueError:
                wait = backoff_seconds * (2**attempt)
            response.close()
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response

    assert response is not None
    response.raise_for_status()
    return response
