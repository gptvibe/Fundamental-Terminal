from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.config import settings
from app.services.sector_plugins.base import build_http_client, parse_float
from app.source_registry import SourceUsage, build_provenance_entries, build_source_mix


OfficialOilInputsStatus = Literal["ok", "partial", "unavailable"]
FreshnessStatus = Literal["fresh", "stale", "missing"]

_SPOT_SOURCE_ID = "eia_petroleum_spot_prices"
_STEO_SOURCE_ID = "eia_steo"
_UNITS = "usd_per_barrel"
_SPOT_PATH = "petroleum/pri/spt/data/"
_STEO_PATH = "steo/data/"
_SPOT_POINT_LIMIT = 365
_BASELINE_POINT_LIMIT = 36
_OBSERVATION_RE = (
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{4}-\d{2}$"),
    re.compile(r"^\d{8}$"),
    re.compile(r"^\d{6}$"),
)


@dataclass(frozen=True, slots=True)
class OfficialOilPointDTO:
    label: str
    value: float | None
    units: str
    observation_date: str | None = None


@dataclass(frozen=True, slots=True)
class OfficialOilSeriesDTO:
    series_id: str
    label: str
    source_id: str
    cadence: str
    units: str
    status: str
    points: tuple[OfficialOilPointDTO, ...] = field(default_factory=tuple)
    latest_value: float | None = None
    latest_observation_date: str | None = None
    confidence_flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OfficialOilInputsDTO:
    status: OfficialOilInputsStatus
    fetched_at: datetime
    as_of: str | None
    last_refreshed_at: datetime
    strict_official_mode: bool
    strict_official_compatible: bool
    spot_history: tuple[OfficialOilSeriesDTO, ...] = field(default_factory=tuple)
    short_term_baseline: tuple[OfficialOilSeriesDTO, ...] = field(default_factory=tuple)
    long_term_anchor: dict[str, Any] = field(default_factory=dict)
    freshness: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    confidence_flags: tuple[str, ...] = field(default_factory=tuple)
    provenance: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    source_mix: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "fetched_at": self.fetched_at.isoformat(),
            "as_of": self.as_of,
            "last_refreshed_at": self.last_refreshed_at.isoformat(),
            "strict_official_mode": self.strict_official_mode,
            "strict_official_compatible": self.strict_official_compatible,
            "spot_history": [_series_to_payload(item) for item in self.spot_history],
            "short_term_baseline": [_series_to_payload(item) for item in self.short_term_baseline],
            "long_term_anchor": self.long_term_anchor,
            "freshness": self.freshness,
            "diagnostics": self.diagnostics,
            "confidence_flags": list(self.confidence_flags),
            "provenance": list(self.provenance),
            "source_mix": self.source_mix,
        }


@dataclass(frozen=True, slots=True)
class _DatasetDefinition:
    dataset_id: str
    source_id: str
    path: str
    frequency: str
    length: int


@dataclass(frozen=True, slots=True)
class _SeriesDefinition:
    series_id: str
    label: str
    source_id: str
    cadence: str
    max_points: int
    tokens: tuple[str, ...]


_SPOT_DATASET = _DatasetDefinition(
    dataset_id="spot_prices",
    source_id=_SPOT_SOURCE_ID,
    path=_SPOT_PATH,
    frequency="daily",
    length=5000,
)

_STEO_DATASET = _DatasetDefinition(
    dataset_id="steo_baseline",
    source_id=_STEO_SOURCE_ID,
    path=_STEO_PATH,
    frequency="monthly",
    length=5000,
)

_SPOT_SERIES = (
    _SeriesDefinition(
        series_id="wti_spot_history",
        label="WTI spot history",
        source_id=_SPOT_SOURCE_ID,
        cadence="daily",
        max_points=_SPOT_POINT_LIMIT,
        tokens=("wti", "west texas intermediate", "rwtc"),
    ),
    _SeriesDefinition(
        series_id="brent_spot_history",
        label="Brent spot history",
        source_id=_SPOT_SOURCE_ID,
        cadence="daily",
        max_points=_SPOT_POINT_LIMIT,
        tokens=("brent", "rbrte"),
    ),
)

_STEO_SERIES = (
    _SeriesDefinition(
        series_id="wti_short_term_baseline",
        label="WTI short-term official baseline",
        source_id=_STEO_SOURCE_ID,
        cadence="monthly",
        max_points=_BASELINE_POINT_LIMIT,
        tokens=("wti", "west texas intermediate", "rwtc"),
    ),
    _SeriesDefinition(
        series_id="brent_short_term_baseline",
        label="Brent short-term official baseline",
        source_id=_STEO_SOURCE_ID,
        cadence="monthly",
        max_points=_BASELINE_POINT_LIMIT,
        tokens=("brent", "rbrte"),
    ),
)


def fetch_official_oil_inputs(*, now: datetime | None = None) -> OfficialOilInputsDTO:
    checked_at = _normalize_datetime(now) or datetime.now(timezone.utc)
    base_flags: set[str] = {"long_term_anchor_user_editable"}
    if settings.strict_official_mode:
        base_flags.add("strict_official_mode")

    usages = [
        SourceUsage(source_id=_SPOT_SOURCE_ID, role="primary", last_refreshed_at=checked_at),
        SourceUsage(source_id=_STEO_SOURCE_ID, role="primary", last_refreshed_at=checked_at),
    ]

    if not settings.eia_api_key:
        return _build_empty_response(
            checked_at=checked_at,
            usages=usages,
            confidence_flags=tuple(sorted(base_flags | {"eia_api_key_missing"})),
            diagnostics={
                "failed_dataset_ids": ["spot_prices", "steo_baseline"],
                "missing_series_ids": [item.series_id for item in (*_SPOT_SERIES, *_STEO_SERIES)],
                "dataset_errors": {
                    "spot_prices": "EIA_API_KEY is not configured",
                    "steo_baseline": "EIA_API_KEY is not configured",
                },
                "pending_extensions": ["eia_aeo_long_term_cases"],
            },
        )

    dataset_rows: dict[str, list[dict[str, Any]]] = {}
    dataset_errors: dict[str, str] = {}

    with build_http_client(timeout_seconds=settings.eia_timeout_seconds) as client:
        for dataset in (_SPOT_DATASET, _STEO_DATASET):
            try:
                dataset_rows[dataset.dataset_id] = _fetch_dataset_rows(client, dataset)
            except Exception as exc:
                dataset_errors[dataset.dataset_id] = str(exc)
                dataset_rows[dataset.dataset_id] = []

    spot_history = _normalize_series_group(
        dataset=_SPOT_DATASET,
        definitions=_SPOT_SERIES,
        rows=dataset_rows[_SPOT_DATASET.dataset_id],
        dataset_error=dataset_errors.get(_SPOT_DATASET.dataset_id),
    )
    short_term_baseline = _normalize_series_group(
        dataset=_STEO_DATASET,
        definitions=_STEO_SERIES,
        rows=dataset_rows[_STEO_DATASET.dataset_id],
        dataset_error=dataset_errors.get(_STEO_DATASET.dataset_id),
    )

    all_series = (*spot_history, *short_term_baseline)
    successful_series = tuple(series for series in all_series if series.status == "ok")
    missing_series_ids = [series.series_id for series in all_series if series.status != "ok"]
    status: OfficialOilInputsStatus
    if len(successful_series) == len(all_series):
        status = "ok"
    elif successful_series:
        status = "partial"
    else:
        status = "unavailable"

    if status == "partial":
        base_flags.add("official_oil_partial_data")
    if status == "unavailable":
        base_flags.add("official_oil_unavailable")

    latest_by_source = {
        _SPOT_SOURCE_ID: _latest_observation_for_group(spot_history),
        _STEO_SOURCE_ID: _latest_observation_for_group(short_term_baseline),
    }
    provenance = tuple(
        build_provenance_entries(
            [
                SourceUsage(
                    source_id=usage.source_id,
                    role=usage.role,
                    as_of=latest_by_source.get(usage.source_id),
                    last_refreshed_at=usage.last_refreshed_at,
                )
                for usage in usages
            ]
        )
    )
    source_mix = build_source_mix(provenance)
    as_of = _latest_observation_for_group(all_series)
    freshness = build_official_oil_inputs_freshness(
        last_refreshed_at=checked_at,
        now=checked_at,
        has_data=bool(successful_series),
    )
    diagnostics = {
        "failed_dataset_ids": sorted(dataset_errors),
        "missing_series_ids": missing_series_ids,
        "dataset_errors": dataset_errors,
        "pending_extensions": ["eia_aeo_long_term_cases"],
    }

    return OfficialOilInputsDTO(
        status=status,
        fetched_at=checked_at,
        as_of=as_of,
        last_refreshed_at=checked_at,
        strict_official_mode=settings.strict_official_mode,
        strict_official_compatible=bool(source_mix.get("official_only", False)),
        spot_history=spot_history,
        short_term_baseline=short_term_baseline,
        long_term_anchor=_build_long_term_anchor(),
        freshness=freshness,
        diagnostics=diagnostics,
        confidence_flags=tuple(sorted(base_flags)),
        provenance=provenance,
        source_mix=source_mix,
    )


def get_official_oil_inputs_payload(*, now: datetime | None = None) -> dict[str, Any]:
    return fetch_official_oil_inputs(now=now).to_payload()


def build_official_oil_inputs_freshness(
    *,
    last_refreshed_at: datetime | None,
    now: datetime | None = None,
    has_data: bool,
) -> dict[str, Any]:
    current_time = _normalize_datetime(now) or datetime.now(timezone.utc)
    normalized_last_refreshed_at = _normalize_datetime(last_refreshed_at)
    freshness_window_hours = int(settings.freshness_window_hours)
    if not has_data or normalized_last_refreshed_at is None:
        return {
            "status": "missing",
            "is_stale": True,
            "freshness_window_hours": freshness_window_hours,
            "freshness_deadline": None,
            "age_seconds": None,
            "stale_flags": ["official_oil_inputs_missing"],
        }

    freshness_deadline = normalized_last_refreshed_at + timedelta(hours=freshness_window_hours)
    age_seconds = max(0.0, (current_time - normalized_last_refreshed_at).total_seconds())
    is_stale = current_time > freshness_deadline
    return {
        "status": "stale" if is_stale else "fresh",
        "is_stale": is_stale,
        "freshness_window_hours": freshness_window_hours,
        "freshness_deadline": freshness_deadline.isoformat(),
        "age_seconds": age_seconds,
        "stale_flags": ["official_oil_inputs_stale"] if is_stale else [],
    }


def _build_empty_response(
    *,
    checked_at: datetime,
    usages: list[SourceUsage],
    confidence_flags: tuple[str, ...],
    diagnostics: dict[str, Any],
) -> OfficialOilInputsDTO:
    provenance = tuple(build_provenance_entries(usages))
    source_mix = build_source_mix(provenance)
    return OfficialOilInputsDTO(
        status="unavailable",
        fetched_at=checked_at,
        as_of=None,
        last_refreshed_at=checked_at,
        strict_official_mode=settings.strict_official_mode,
        strict_official_compatible=bool(source_mix.get("official_only", False)),
        spot_history=tuple(_unavailable_series(item, "eia_api_key_missing") for item in _SPOT_SERIES),
        short_term_baseline=tuple(_unavailable_series(item, "eia_api_key_missing") for item in _STEO_SERIES),
        long_term_anchor=_build_long_term_anchor(),
        freshness=build_official_oil_inputs_freshness(last_refreshed_at=checked_at, now=checked_at, has_data=False),
        diagnostics=diagnostics,
        confidence_flags=confidence_flags,
        provenance=provenance,
        source_mix=source_mix,
    )


def _build_long_term_anchor() -> dict[str, Any]:
    return {
        "mode": "user_editable",
        "status": "not_set",
        "label": "Long-term anchor",
        "units": _UNITS,
        "value": None,
        "available_case_ids": [],
        "future_source_id": "eia_aeo",
        "strict_official_compatible": True,
        "notes": [
            "v1 intentionally leaves the long-term anchor unset and user-editable.",
            "Official AEO cases can be attached later without changing the surrounding payload shape.",
        ],
    }


def _fetch_dataset_rows(client: Any, dataset: _DatasetDefinition) -> list[dict[str, Any]]:
    params = {
        "api_key": settings.eia_api_key,
        "frequency": dataset.frequency,
        "data[0]": "value",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "offset": 0,
        "length": dataset.length,
    }
    response = client.get(f"{settings.eia_api_base_url}/{dataset.path}", params=params)
    response.raise_for_status()
    payload = response.json()
    body = payload.get("response") if isinstance(payload, dict) else None
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"Unexpected EIA payload shape for {dataset.dataset_id}")
    return [row for row in rows if isinstance(row, dict)]


def _normalize_series_group(
    *,
    dataset: _DatasetDefinition,
    definitions: tuple[_SeriesDefinition, ...],
    rows: list[dict[str, Any]],
    dataset_error: str | None,
) -> tuple[OfficialOilSeriesDTO, ...]:
    if dataset_error:
        flag = f"{dataset.dataset_id}_fetch_failed"
        return tuple(_unavailable_series(definition, flag) for definition in definitions)
    return tuple(_normalize_series(definition, rows) for definition in definitions)


def _normalize_series(definition: _SeriesDefinition, rows: list[dict[str, Any]]) -> OfficialOilSeriesDTO:
    matched_rows = [row for row in rows if _row_matches_definition(row, definition)]
    normalized_points: dict[str, OfficialOilPointDTO] = {}
    for row in matched_rows:
        observation_date = _extract_observation_date(row)
        value = _extract_numeric_value(row)
        if observation_date is None or value is None:
            continue
        normalized_points[observation_date] = OfficialOilPointDTO(
            label=observation_date,
            value=value,
            units=_UNITS,
            observation_date=observation_date,
        )

    ordered_points = tuple(
        normalized_points[key]
        for key in sorted(normalized_points, key=_observation_sort_key)[-definition.max_points:]
    )
    if not ordered_points:
        return _unavailable_series(definition, f"{definition.series_id}_missing")

    latest_point = ordered_points[-1]
    return OfficialOilSeriesDTO(
        series_id=definition.series_id,
        label=definition.label,
        source_id=definition.source_id,
        cadence=definition.cadence,
        units=_UNITS,
        status="ok",
        points=ordered_points,
        latest_value=latest_point.value,
        latest_observation_date=latest_point.observation_date,
        confidence_flags=(),
    )


def _unavailable_series(definition: _SeriesDefinition, flag: str) -> OfficialOilSeriesDTO:
    return OfficialOilSeriesDTO(
        series_id=definition.series_id,
        label=definition.label,
        source_id=definition.source_id,
        cadence=definition.cadence,
        units=_UNITS,
        status="unavailable",
        points=(),
        latest_value=None,
        latest_observation_date=None,
        confidence_flags=(flag,),
    )


def _row_matches_definition(row: dict[str, Any], definition: _SeriesDefinition) -> bool:
    descriptor = " ".join(
        str(value).strip().lower()
        for value in row.values()
        if isinstance(value, str) and str(value).strip()
    )
    return any(token in descriptor for token in definition.tokens)


def _extract_numeric_value(row: dict[str, Any]) -> float | None:
    for key in ("value", "price", "close", "series-value"):
        if key in row:
            parsed = parse_float(row.get(key))
            if parsed is not None:
                return parsed
    return None


def _extract_observation_date(row: dict[str, Any]) -> str | None:
    for key in ("period", "date", "observation_date", "forecast_period", "forecast_date"):
        if key not in row:
            continue
        normalized = _normalize_observation(str(row.get(key) or "").strip())
        if normalized:
            return normalized
    return None


def _normalize_observation(value: str) -> str | None:
    if not value:
        return None
    if _OBSERVATION_RE[0].match(value) or _OBSERVATION_RE[1].match(value):
        return value
    if _OBSERVATION_RE[2].match(value):
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    if _OBSERVATION_RE[3].match(value):
        return f"{value[:4]}-{value[4:6]}"
    return value


def _latest_observation_for_group(series_group: tuple[OfficialOilSeriesDTO, ...] | tuple[OfficialOilSeriesDTO, ...] | tuple[Any, ...]) -> str | None:
    latest: str | None = None
    for series in series_group:
        candidate = getattr(series, "latest_observation_date", None)
        if candidate is None:
            continue
        if latest is None or _observation_sort_key(candidate) > _observation_sort_key(latest):
            latest = candidate
    return latest


def _observation_sort_key(value: str | None) -> tuple[int, str]:
    if value is None:
        return (0, "")
    normalized = _normalize_observation(value)
    if normalized is None:
        return (0, "")
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return (1, datetime.strptime(normalized, fmt).isoformat())
        except ValueError:
            continue
    return (1, normalized)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _series_to_payload(series: OfficialOilSeriesDTO) -> dict[str, Any]:
    return {
        "series_id": series.series_id,
        "label": series.label,
        "source_id": series.source_id,
        "cadence": series.cadence,
        "units": series.units,
        "status": series.status,
        "points": [
            {
                "label": point.label,
                "value": point.value,
                "units": point.units,
                "observation_date": point.observation_date,
            }
            for point in series.points
        ],
        "latest_value": series.latest_value,
        "latest_observation_date": series.latest_observation_date,
        "confidence_flags": list(series.confidence_flags),
    }