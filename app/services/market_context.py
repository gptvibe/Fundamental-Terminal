from __future__ import annotations

import csv
import html
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path

import httpx

from app.config import settings
from app.services.risk_free_rate import TREASURY_SOURCE_NAME, _request_with_retries, get_latest_risk_free_rate

logger = logging.getLogger(__name__)

TREASURY_CSV_SOURCE_URL = settings.treasury_yield_curve_csv_url
TREASURY_TEXTVIEW_URL_TEMPLATE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value_month={year_month}"
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

TREASURY_CURVE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("1 Mo", "1m"),
    ("2 Mo", "2m"),
    ("3 Mo", "3m"),
    ("4 Mo", "4m"),
    ("6 Mo", "6m"),
    ("1 Yr", "1y"),
    ("2 Yr", "2y"),
    ("3 Yr", "3y"),
    ("5 Yr", "5y"),
    ("7 Yr", "7y"),
    ("10 Yr", "10y"),
    ("20 Yr", "20y"),
    ("30 Yr", "30y"),
)

THREE_M_EQUIVALENTS = ("3m", "6m", "1y", "2m", "1m")

FRED_CURVE_SERIES: tuple[tuple[str, str, str], ...] = (
    ("RRPONTSYAWARD", "rrp", "Reverse Repo Facility Award Rate"),
    ("DGS1MO", "1m", "1 Month Treasury"),
    ("DGS2MO", "2m", "2 Month Treasury"),
    ("DGS3MO", "3m", "3 Month Treasury"),
    ("DGS4MO", "4m", "4 Month Treasury"),
    ("DGS6MO", "6m", "6 Month Treasury"),
    ("DGS1", "1y", "1 Year Treasury"),
    ("DGS2", "2y", "2 Year Treasury"),
    ("DGS3", "3y", "3 Year Treasury"),
    ("DGS5", "5y", "5 Year Treasury"),
    ("DGS7", "7y", "7 Year Treasury"),
    ("DGS10", "10y", "10 Year Treasury"),
    ("DGS20", "20y", "20 Year Treasury"),
    ("DGS30", "30y", "30 Year Treasury"),
)

FRED_SERIES = (
    {
        "series_id": "BAA10Y",
        "label": "Credit Spread (BAA-10Y)",
        "category": "credit_spread",
        "units": "spread",
    },
    {
        "series_id": "USREC",
        "label": "NBER Recession Indicator",
        "category": "regime",
        "units": "index",
    },
    {
        "series_id": "T10YIE",
        "label": "10Y Breakeven Inflation",
        "category": "inflation",
        "units": "percent",
    },
    {
        "series_id": "CPIAUCSL",
        "label": "Headline CPI (YoY)",
        "category": "inflation",
        "units": "percent",
        "fred_units": "pc1",
    },
    {
        "series_id": "CPILFESL",
        "label": "Core CPI (YoY)",
        "category": "inflation_core",
        "units": "percent",
        "fred_units": "pc1",
    },
    {
        "series_id": "PCEPI",
        "label": "PCE Price Index (YoY)",
        "category": "inflation_pce",
        "units": "percent",
        "fred_units": "pc1",
    },
    {
        "series_id": "PCEPILFE",
        "label": "Core PCE (YoY)",
        "category": "inflation_core_pce",
        "units": "percent",
        "fred_units": "pc1",
    },
    {
        "series_id": "UNRATE",
        "label": "Unemployment Rate",
        "category": "unemployment",
        "units": "percent",
    },
)


@dataclass(frozen=True, slots=True)
class MarketCurvePoint:
    tenor: str
    rate: float
    observation_date: date


@dataclass(frozen=True, slots=True)
class MarketSlope:
    label: str
    value: float | None
    long_tenor: str
    short_tenor: str
    observation_date: date | None


@dataclass(frozen=True, slots=True)
class MarketFredSeries:
    series_id: str
    label: str
    category: str
    units: str
    value: float | None
    observation_date: date | None
    state: str


@dataclass(frozen=True, slots=True)
class MarketContextSnapshot:
    status: str
    curve_points: tuple[MarketCurvePoint, ...]
    slope_2s10s: MarketSlope
    slope_3m10y: MarketSlope
    fred_series: tuple[MarketFredSeries, ...] = field(default_factory=tuple)
    provenance: dict[str, object] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MarketContextClient:
    def __init__(self, cache_file: Path | None = None) -> None:
        default_cache = Path(__file__).resolve().parents[2] / "data" / "market_cache" / "market_context.json"
        self._cache_file = cache_file or default_cache
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._http = httpx.Client(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept": "application/json,text/csv,text/plain;q=0.8,*/*;q=0.7",
                "Accept-Encoding": "gzip, deflate",
            },
            follow_redirects=True,
            timeout=settings.sec_timeout_seconds,
        )

    def close(self) -> None:
        self._http.close()

    def get_market_context(self) -> MarketContextSnapshot:
        cached = self._read_cache()
        now = datetime.now(timezone.utc)
        if cached is not None and cached.fetched_at.astimezone(timezone.utc).date() == now.date():
            return cached

        try:
            fresh = self._fetch_market_context()
            self._write_cache(fresh)
            return fresh
        except Exception:
            if cached is not None:
                logger.warning("Market context refresh failed; serving cached market context.", exc_info=True)
                return cached
            raise

    def get_cached_status(self) -> dict[str, object]:
        cached = self._read_cache()
        if cached is None:
            return {
                "state": "missing",
                "label": "Market context unavailable",
                "observation_date": None,
                "source": "none",
            }

        treasury = cached.provenance.get("treasury") if isinstance(cached.provenance, dict) else {}
        treasury_status = "ok"
        if isinstance(treasury, dict):
            treasury_status = str(treasury.get("status") or "ok")

        return {
            "state": cached.status,
            "label": "Treasury + FRED" if cached.fred_series else "Treasury only",
            "observation_date": _latest_observation_date(cached.curve_points),
            "source": TREASURY_SOURCE_NAME,
            "treasury_status": treasury_status,
        }

    def _fetch_market_context(self) -> MarketContextSnapshot:
        treasury_points, treasury_obs_date, treasury_meta = self._fetch_treasury_curve()
        slope_2s10s = _build_slope("2s10s", treasury_points, short_tenor="2y", long_tenor="10y")
        slope_3m10y = _build_three_m_ten_y_slope(treasury_points)

        fred_payload: tuple[MarketFredSeries, ...] = ()
        fred_provenance: dict[str, object] = {
            "enabled": bool(settings.fred_api_key),
            "series": [],
            "status": "missing_api_key" if not settings.fred_api_key else "ok",
        }

        if settings.fred_api_key:
            fred_payload, fred_provenance = self._fetch_fred_series()

        status = "ok"
        if not treasury_points:
            status = "insufficient_data"
        elif not settings.fred_api_key or any(series.state != "ok" for series in fred_payload):
            status = "partial"

        return MarketContextSnapshot(
            status=status,
            curve_points=tuple(treasury_points),
            slope_2s10s=slope_2s10s,
            slope_3m10y=slope_3m10y,
            fred_series=fred_payload,
            provenance={
                "treasury": {
                    "source_name": treasury_meta["source_name"],
                    "source_url": treasury_meta["source_url"],
                    "observation_date": treasury_obs_date.isoformat() if treasury_obs_date is not None else None,
                    "status": treasury_meta["status"],
                    "fallback_used": bool(treasury_meta.get("fallback_used")),
                },
                "fred": fred_provenance,
            },
            fetched_at=datetime.now(timezone.utc),
        )

    def _fetch_treasury_curve(self) -> tuple[list[MarketCurvePoint], date | None, dict[str, object]]:
        try:
            response = _request_with_retries(
                self._http,
                TREASURY_CSV_SOURCE_URL,
                max_retries=settings.treasury_max_retries,
                backoff_seconds=settings.treasury_retry_backoff_seconds,
            )
            points, obs_date = _parse_treasury_curve(response.text)
            if points:
                points = self._augment_curve_with_rrp(points)
                return points, obs_date, {
                    "source_name": TREASURY_SOURCE_NAME,
                    "source_url": TREASURY_CSV_SOURCE_URL,
                    "status": "ok",
                    "fallback_used": False,
                }
        except Exception:
            logger.warning("Treasury curve CSV unavailable. Falling back to latest risk-free snapshot.")

        try:
            textview_url = _build_treasury_textview_url()
            response = _request_with_retries(
                self._http,
                textview_url,
                max_retries=settings.treasury_max_retries,
                backoff_seconds=settings.treasury_retry_backoff_seconds,
            )
            points, obs_date = _parse_treasury_curve_textview(response.text)
            if points:
                points = self._augment_curve_with_rrp(points)
                return points, obs_date, {
                    "source_name": f"{TREASURY_SOURCE_NAME} (TextView)",
                    "source_url": textview_url,
                    "status": "partial",
                    "fallback_used": True,
                }
        except Exception:
            logger.warning("Treasury TextView fallback unavailable. Falling back to FRED curve data.")

        if settings.fred_api_key:
            fred_points, fred_obs_date = self._fetch_fred_curve_points()
            if fred_points:
                return fred_points, fred_obs_date, {
                    "source_name": "Federal Reserve Economic Data (FRED)",
                    "source_url": FRED_BASE_URL,
                    "status": "partial",
                    "fallback_used": True,
                }

        snapshot = get_latest_risk_free_rate()
        points = [
            MarketCurvePoint(
                tenor="10y",
                rate=float(snapshot.rate_used),
                observation_date=snapshot.observation_date,
            )
        ]
        return points, snapshot.observation_date, {
            "source_name": str(snapshot.source_name),
            "source_url": TREASURY_CSV_SOURCE_URL,
            "status": "partial",
            "fallback_used": True,
        }

    def _augment_curve_with_rrp(self, points: list[MarketCurvePoint]) -> list[MarketCurvePoint]:
        if not settings.fred_api_key:
            return points

        try:
            response = _request_with_retries(
                self._http,
                f"{FRED_BASE_URL}?series_id=RRPONTSYAWARD&api_key={settings.fred_api_key}&file_type=json&sort_order=desc&limit=10",
                max_retries=settings.market_max_retries,
                backoff_seconds=settings.market_retry_backoff_seconds,
            )
            value, observation_date = _parse_latest_fred_numeric_observation(response.text, units="percent")
        except Exception:
            logger.warning("Unable to fetch FRED RRP award-rate series for Treasury curve augmentation.", exc_info=True)
            return points

        if value is None or observation_date is None:
            return points

        filtered = [point for point in points if point.tenor != "rrp"]
        filtered.append(MarketCurvePoint(tenor="rrp", rate=value, observation_date=observation_date))
        return filtered

    def _fetch_fred_curve_points(self) -> tuple[list[MarketCurvePoint], date | None]:
        points: list[MarketCurvePoint] = []
        latest_observation: date | None = None

        for series_id, tenor, label in FRED_CURVE_SERIES:
            try:
                response = _request_with_retries(
                    self._http,
                    f"{FRED_BASE_URL}?series_id={series_id}&api_key={settings.fred_api_key}&file_type=json&sort_order=desc&limit=10",
                    max_retries=settings.market_max_retries,
                    backoff_seconds=settings.market_retry_backoff_seconds,
                )
                value, observation_date = _parse_latest_fred_numeric_observation(response.text, units="percent")
            except Exception:
                logger.warning("Unable to fetch FRED Treasury curve series %s (%s)", series_id, label, exc_info=True)
                continue

            if value is None or observation_date is None:
                continue

            points.append(MarketCurvePoint(tenor=tenor, rate=value, observation_date=observation_date))
            if latest_observation is None or observation_date > latest_observation:
                latest_observation = observation_date

        return points, latest_observation

    def _fetch_fred_series(self) -> tuple[tuple[MarketFredSeries, ...], dict[str, object]]:
        items: list[MarketFredSeries] = []
        series_provenance: list[dict[str, object]] = []

        for series in FRED_SERIES:
            series_id = str(series["series_id"])
            label = str(series["label"])
            category = str(series["category"])
            units = str(series["units"])
            fred_units = str(series.get("fred_units") or "").strip()
            units_param = f"&units={fred_units}" if fred_units else ""

            try:
                response = _request_with_retries(
                    self._http,
                    f"{FRED_BASE_URL}?series_id={series_id}&api_key={settings.fred_api_key}&file_type=json&sort_order=desc&limit=1{units_param}",
                    max_retries=settings.market_max_retries,
                    backoff_seconds=settings.market_retry_backoff_seconds,
                )
                item = _parse_fred_observation(series_id, label, category, units, response.text)
                items.append(item)
                series_provenance.append({
                    "series_id": series_id,
                    "state": item.state,
                    "observation_date": item.observation_date.isoformat() if item.observation_date else None,
                })
            except Exception:
                logger.warning("Unable to fetch FRED series %s", series_id, exc_info=True)
                items.append(
                    MarketFredSeries(
                        series_id=series_id,
                        label=label,
                        category=category,
                        units=units,
                        value=None,
                        observation_date=None,
                        state="unavailable",
                    )
                )
                series_provenance.append({"series_id": series_id, "state": "unavailable", "observation_date": None})

        status = "ok" if all(item["state"] == "ok" for item in series_provenance) else "partial"
        return tuple(items), {
            "enabled": True,
            "status": status,
            "series": series_provenance,
            "source": "Federal Reserve Economic Data (FRED)",
        }

    def _read_cache(self) -> MarketContextSnapshot | None:
        if not self._cache_file.exists():
            return None
        try:
            payload = json.loads(self._cache_file.read_text(encoding="utf-8"))
            return _snapshot_from_payload(payload)
        except Exception:
            return None

    def _write_cache(self, snapshot: MarketContextSnapshot) -> None:
        payload = _snapshot_to_payload(snapshot)
        tmp = self._cache_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp.replace(self._cache_file)


def get_market_context_snapshot() -> MarketContextSnapshot:
    client = MarketContextClient()
    try:
        return client.get_market_context()
    finally:
        client.close()


def get_cached_market_context_status() -> dict[str, object]:
    client = MarketContextClient()
    try:
        return client.get_cached_status()
    finally:
        client.close()


def _parse_treasury_curve(content: str) -> tuple[list[MarketCurvePoint], date | None]:
    latest_row: dict[str, str] | None = None
    latest_date: date | None = None

    for row in csv.DictReader(StringIO(content)):
        raw_date = (row.get("Date") or row.get("date") or "").strip()
        if not raw_date:
            continue
        try:
            observed = datetime.strptime(raw_date, "%m/%d/%Y").date()
        except ValueError:
            continue
        if latest_date is None or observed > latest_date:
            latest_date = observed
            latest_row = row

    if latest_row is None or latest_date is None:
        return [], None

    points: list[MarketCurvePoint] = []
    for source_key, tenor in TREASURY_CURVE_COLUMNS:
        raw = (latest_row.get(source_key) or "").strip()
        if not raw:
            continue
        try:
            rate_percent = float(raw)
        except ValueError:
            continue
        points.append(MarketCurvePoint(tenor=tenor, rate=rate_percent / 100.0, observation_date=latest_date))

    return points, latest_date


def _parse_treasury_curve_textview(content: str) -> tuple[list[MarketCurvePoint], date | None]:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", content, flags=re.IGNORECASE | re.DOTALL)
    header: list[str] | None = None
    latest_row: list[str] | None = None
    latest_date: date | None = None

    for row_html in rows:
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, flags=re.IGNORECASE | re.DOTALL)
        if not cells:
            continue

        cleaned = [_clean_html_cell(cell) for cell in cells]
        if not cleaned:
            continue

        if header is None and any(cell.lower() == "date" for cell in cleaned):
            header = cleaned
            continue

        if header is None or len(cleaned) != len(header):
            continue

        raw_date = cleaned[0]
        try:
            observed = datetime.strptime(raw_date, "%m/%d/%Y").date()
        except ValueError:
            continue

        if latest_date is None or observed > latest_date:
            latest_date = observed
            latest_row = cleaned

    if header is None or latest_row is None or latest_date is None:
        return [], None

    row_by_header = {column: value for column, value in zip(header, latest_row, strict=True)}
    points: list[MarketCurvePoint] = []
    for source_key, tenor in TREASURY_CURVE_COLUMNS:
        raw = (row_by_header.get(source_key) or "").strip()
        if not raw or raw.upper() == "N/A":
            continue
        try:
            rate_percent = float(raw)
        except ValueError:
            continue
        points.append(MarketCurvePoint(tenor=tenor, rate=rate_percent / 100.0, observation_date=latest_date))

    return points, latest_date


def _clean_html_cell(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    normalized = html.unescape(without_tags)
    return re.sub(r"\s+", " ", normalized).strip()


def _build_treasury_textview_url(reference_time: datetime | None = None) -> str:
    current = reference_time or datetime.now(timezone.utc)
    return TREASURY_TEXTVIEW_URL_TEMPLATE.format(year_month=current.strftime("%Y%m"))


def _build_slope(label: str, points: list[MarketCurvePoint], *, short_tenor: str, long_tenor: str) -> MarketSlope:
    by_tenor = {point.tenor: point for point in points}
    short = by_tenor.get(short_tenor)
    long = by_tenor.get(long_tenor)

    if short is None or long is None:
        return MarketSlope(
            label=label,
            value=None,
            short_tenor=short_tenor,
            long_tenor=long_tenor,
            observation_date=None,
        )

    observation = long.observation_date if long.observation_date >= short.observation_date else short.observation_date
    return MarketSlope(
        label=label,
        value=long.rate - short.rate,
        short_tenor=short_tenor,
        long_tenor=long_tenor,
        observation_date=observation,
    )


def _build_three_m_ten_y_slope(points: list[MarketCurvePoint]) -> MarketSlope:
    by_tenor = {point.tenor: point for point in points}
    long = by_tenor.get("10y")
    if long is None:
        return MarketSlope(label="3m10y", value=None, short_tenor="3m", long_tenor="10y", observation_date=None)

    for candidate in THREE_M_EQUIVALENTS:
        short = by_tenor.get(candidate)
        if short is None:
            continue
        observation = long.observation_date if long.observation_date >= short.observation_date else short.observation_date
        return MarketSlope(
            label="3m10y",
            value=long.rate - short.rate,
            short_tenor=candidate,
            long_tenor="10y",
            observation_date=observation,
        )

    return MarketSlope(label="3m10y", value=None, short_tenor="3m", long_tenor="10y", observation_date=None)


def _parse_fred_observation(series_id: str, label: str, category: str, units: str, payload_text: str) -> MarketFredSeries:
    value, observation_date = _parse_latest_fred_numeric_observation(payload_text, units=units)
    if value is not None and observation_date is not None:
        return MarketFredSeries(
            series_id=series_id,
            label=label,
            category=category,
            units=units,
            value=value,
            observation_date=observation_date,
            state="ok",
        )

    payload = json.loads(payload_text)
    observations = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(observations, list) or not observations:
        return MarketFredSeries(
            series_id=series_id,
            label=label,
            category=category,
            units=units,
            value=None,
            observation_date=None,
            state="insufficient_data",
        )

    for item in observations:
        if not isinstance(item, dict):
            continue
        value_raw = str(item.get("value") or "").strip()
        date_raw = str(item.get("date") or "").strip()
        if not date_raw:
            continue
        try:
            observed = date.fromisoformat(date_raw)
        except ValueError:
            continue

        if value_raw in {"", "."}:
            continue

        try:
            value = float(value_raw)
        except ValueError:
            continue

        if units == "percent":
            value /= 100.0

        return MarketFredSeries(
            series_id=series_id,
            label=label,
            category=category,
            units=units,
            value=value,
            observation_date=observed,
            state="ok",
        )

    return MarketFredSeries(
        series_id=series_id,
        label=label,
        category=category,
        units=units,
        value=None,
        observation_date=None,
        state="insufficient_data",
    )


def _parse_latest_fred_numeric_observation(payload_text: str, *, units: str) -> tuple[float | None, date | None]:
    payload = json.loads(payload_text)
    observations = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(observations, list):
        return None, None

    for item in observations:
        if not isinstance(item, dict):
            continue

        value_raw = str(item.get("value") or "").strip()
        date_raw = str(item.get("date") or "").strip()
        if not date_raw or value_raw in {"", "."}:
            continue

        try:
            observed = date.fromisoformat(date_raw)
            value = float(value_raw)
        except ValueError:
            continue

        if units == "percent":
            value /= 100.0

        return value, observed

    return None, None


def _snapshot_to_payload(snapshot: MarketContextSnapshot) -> dict[str, object]:
    return {
        "status": snapshot.status,
        "curve_points": [
            {
                "tenor": item.tenor,
                "rate": item.rate,
                "observation_date": item.observation_date.isoformat(),
            }
            for item in snapshot.curve_points
        ],
        "slope_2s10s": _slope_to_payload(snapshot.slope_2s10s),
        "slope_3m10y": _slope_to_payload(snapshot.slope_3m10y),
        "fred_series": [
            {
                "series_id": item.series_id,
                "label": item.label,
                "category": item.category,
                "units": item.units,
                "value": item.value,
                "observation_date": item.observation_date.isoformat() if item.observation_date else None,
                "state": item.state,
            }
            for item in snapshot.fred_series
        ],
        "provenance": snapshot.provenance,
        "fetched_at": snapshot.fetched_at.isoformat(),
    }


def _snapshot_from_payload(payload: dict[str, object]) -> MarketContextSnapshot:
    curve_points = tuple(
        MarketCurvePoint(
            tenor=str(item.get("tenor")),
            rate=float(item.get("rate")),
            observation_date=date.fromisoformat(str(item.get("observation_date"))),
        )
        for item in payload.get("curve_points", [])
        if isinstance(item, dict)
    )

    fred_series = tuple(
        MarketFredSeries(
            series_id=str(item.get("series_id")),
            label=str(item.get("label")),
            category=str(item.get("category")),
            units=str(item.get("units")),
            value=float(item.get("value")) if item.get("value") is not None else None,
            observation_date=date.fromisoformat(str(item.get("observation_date"))) if item.get("observation_date") else None,
            state=str(item.get("state") or "unknown"),
        )
        for item in payload.get("fred_series", [])
        if isinstance(item, dict)
    )

    return MarketContextSnapshot(
        status=str(payload.get("status") or "partial"),
        curve_points=curve_points,
        slope_2s10s=_slope_from_payload(payload.get("slope_2s10s")),
        slope_3m10y=_slope_from_payload(payload.get("slope_3m10y")),
        fred_series=fred_series,
        provenance=payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {},
        fetched_at=_parse_datetime_utc(str(payload.get("fetched_at"))),
    )


def _slope_to_payload(slope: MarketSlope) -> dict[str, object]:
    return {
        "label": slope.label,
        "value": slope.value,
        "long_tenor": slope.long_tenor,
        "short_tenor": slope.short_tenor,
        "observation_date": slope.observation_date.isoformat() if slope.observation_date else None,
    }


def _slope_from_payload(value: object) -> MarketSlope:
    if not isinstance(value, dict):
        return MarketSlope(label="unknown", value=None, long_tenor="10y", short_tenor="unknown", observation_date=None)

    raw_obs = value.get("observation_date")
    obs = date.fromisoformat(str(raw_obs)) if raw_obs else None
    slope_value = value.get("value")
    slope_number = float(slope_value) if slope_value is not None else None
    return MarketSlope(
        label=str(value.get("label") or "unknown"),
        value=slope_number,
        long_tenor=str(value.get("long_tenor") or "10y"),
        short_tenor=str(value.get("short_tenor") or "unknown"),
        observation_date=obs,
    )


def _latest_observation_date(points: tuple[MarketCurvePoint, ...]) -> str | None:
    if not points:
        return None
    latest = max(point.observation_date for point in points)
    return latest.isoformat()


def _parse_datetime_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
