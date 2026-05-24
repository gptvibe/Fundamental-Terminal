from __future__ import annotations

from dataclasses import dataclass
from datetime import date as DateType, datetime, timezone
from typing import Any, Callable, Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, CompanyWorkspaceBootstrapSnapshot, DatasetRefreshState
from app.services.refresh_state import build_payload_version_hash, cache_state_for_dataset, mark_dataset_checked
from app.source_registry import build_source_mix


BOOTSTRAP_SCHEMA_VERSION = "company_workspace_bootstrap_v1"
BOOTSTRAP_INPUT_FINGERPRINT_VERSION = "company-workspace-bootstrap-inputs-v1"
BOOTSTRAP_DATASET = "company_workspace_bootstrap"
DEFAULT_BOOTSTRAP_SECTIONS: tuple[str, ...] = (
    "company_summary",
    "latest_financials",
    "recent_filings",
    "recent_events",
    "source_freshness",
    "warnings",
)
DEFAULT_BOOTSTRAP_FINANCIALS_VIEW = "core_segments"
DEFAULT_BOOTSTRAP_PRICE_LATEST_N = 3200
DEFAULT_BOOTSTRAP_PRICE_MAX_POINTS = 480

FreshnessState = Literal["fresh", "stale", "missing", "building", "partial"]


@dataclass(frozen=True, slots=True)
class WorkspaceBootstrapSnapshotRead:
    record: CompanyWorkspaceBootstrapSnapshot
    payload: dict[str, Any]
    source_fingerprint: str
    freshness_state: FreshnessState
    is_current: bool

    @property
    def is_stale(self) -> bool:
        return not self.is_current or self.freshness_state != "fresh"


def normalize_bootstrap_sections(sections: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    normalized = tuple(sorted({str(section).strip().lower() for section in (sections or ()) if str(section).strip()}))
    return normalized or DEFAULT_BOOTSTRAP_SECTIONS


def is_default_compact_bootstrap_request(
    *,
    sections: tuple[str, ...] | list[str] | None,
    compact: bool,
    financials_view: str,
    price_start_date: DateType | None,
    price_end_date: DateType | None,
    price_latest_n: int | None,
    price_max_points: int | None,
) -> bool:
    return (
        compact
        and normalize_bootstrap_sections(sections) == tuple(sorted(DEFAULT_BOOTSTRAP_SECTIONS))
        and financials_view == DEFAULT_BOOTSTRAP_FINANCIALS_VIEW
        and price_start_date is None
        and price_end_date is None
        and (price_latest_n is None or price_latest_n == DEFAULT_BOOTSTRAP_PRICE_LATEST_N)
        and (price_max_points is None or price_max_points == DEFAULT_BOOTSTRAP_PRICE_MAX_POINTS)
    )


def build_company_workspace_bootstrap_source_fingerprint(
    session: Session,
    company_id: int,
    *,
    as_of: datetime | None = None,
    sections: tuple[str, ...] | list[str] | None = None,
    compact: bool = True,
    financials_view: str = DEFAULT_BOOTSTRAP_FINANCIALS_VIEW,
    price_token: str = "default",
    schema_version: str = BOOTSTRAP_SCHEMA_VERSION,
) -> str:
    company = session.get(Company, company_id)
    company_payload: dict[str, Any] = {}
    if company is not None:
        company_payload = {
            "ticker": company.ticker,
            "cik": company.cik,
            "name": company.name,
            "sector": company.sector,
            "market_sector": company.market_sector,
            "market_industry": company.market_industry,
        }

    dependencies = _dataset_dependency_fingerprints(session, company_id)
    return build_payload_version_hash(
        version=BOOTSTRAP_INPUT_FINGERPRINT_VERSION,
        payload={
            "schema_version": schema_version,
            "company": company_payload,
            "as_of_key": _as_of_key(as_of),
            "sections": normalize_bootstrap_sections(sections),
            "compact": bool(compact),
            "financials_view": financials_view,
            "price_token": price_token,
            "strict_official_mode": bool(settings.strict_official_mode),
            "dependencies": dependencies,
        },
    )


def get_company_workspace_bootstrap_snapshot_for_read(
    session: Session,
    company_id: int,
    *,
    as_of: datetime | None = None,
    source_fingerprint: str | None = None,
    schema_version: str = BOOTSTRAP_SCHEMA_VERSION,
) -> WorkspaceBootstrapSnapshotRead | None:
    current = None
    if source_fingerprint:
        current = _load_snapshot(
            session,
            company_id,
            as_of=as_of,
            schema_version=schema_version,
            source_fingerprint=source_fingerprint,
        )
    if current is not None:
        return _snapshot_read(session, current, source_fingerprint=source_fingerprint)

    latest = _load_snapshot(session, company_id, as_of=as_of, schema_version=schema_version)
    if latest is None:
        return None
    return _snapshot_read(session, latest, source_fingerprint=source_fingerprint)


def upsert_company_workspace_bootstrap_snapshot(
    session: Session,
    company_id: int,
    payload: dict[str, Any],
    *,
    checked_at: datetime | None = None,
    as_of: datetime | None = None,
    source_fingerprint: str | None = None,
    schema_version: str = BOOTSTRAP_SCHEMA_VERSION,
) -> CompanyWorkspaceBootstrapSnapshot:
    timestamp = _normalize_datetime(checked_at or datetime.now(timezone.utc))
    fingerprint = source_fingerprint or build_company_workspace_bootstrap_source_fingerprint(
        session,
        company_id,
        as_of=as_of,
        schema_version=schema_version,
    )
    metadata = _metadata_from_payload(payload, source_fingerprint=fingerprint, schema_version=schema_version, checked_at=timestamp)
    stored_payload = {**payload, **metadata}
    statement = insert(CompanyWorkspaceBootstrapSnapshot).values(
        company_id=company_id,
        as_of_key=_as_of_key(as_of),
        as_of_value=as_of,
        schema_version=schema_version,
        source_fingerprint=fingerprint,
        payload=stored_payload,
        provenance=metadata["provenance"],
        source_mix=metadata["source_mix"],
        freshness_state=metadata["freshness_state"],
        confidence_flags=metadata["confidence_flags"],
        fallback_flags=metadata["fallback_flags"],
        strict_official_eligible=metadata["strict_official_eligible"],
        last_updated=timestamp,
        last_checked=timestamp,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_cwbs_company_asof_schema_source",
        set_={
            "as_of_value": statement.excluded.as_of_value,
            "payload": statement.excluded.payload,
            "provenance": statement.excluded.provenance,
            "source_mix": statement.excluded.source_mix,
            "freshness_state": statement.excluded.freshness_state,
            "confidence_flags": statement.excluded.confidence_flags,
            "fallback_flags": statement.excluded.fallback_flags,
            "strict_official_eligible": statement.excluded.strict_official_eligible,
            "last_updated": statement.excluded.last_updated,
            "last_checked": statement.excluded.last_checked,
        },
    ).returning(CompanyWorkspaceBootstrapSnapshot)
    row = session.execute(statement).scalar_one()
    mark_dataset_checked(
        session,
        company_id,
        BOOTSTRAP_DATASET,
        checked_at=timestamp,
        success=True,
        payload_version_hash=fingerprint,
        invalidate_hot_cache=True,
    )
    return row


def recompute_and_persist_company_workspace_bootstrap_snapshot(
    session: Session,
    company_id: int,
    *,
    payload_builder: Callable[[], dict[str, Any]] | None = None,
    checked_at: datetime | None = None,
    as_of: datetime | None = None,
    source_fingerprint: str | None = None,
) -> dict[str, Any] | None:
    if payload_builder is None:
        return None
    timestamp = _normalize_datetime(checked_at or datetime.now(timezone.utc))
    payload = payload_builder()
    upsert_company_workspace_bootstrap_snapshot(
        session,
        company_id,
        payload,
        checked_at=timestamp,
        as_of=as_of,
        source_fingerprint=source_fingerprint,
    )
    return payload


def _load_snapshot(
    session: Session,
    company_id: int,
    *,
    as_of: datetime | None,
    schema_version: str,
    source_fingerprint: str | None = None,
) -> CompanyWorkspaceBootstrapSnapshot | None:
    statement = select(CompanyWorkspaceBootstrapSnapshot).where(
        CompanyWorkspaceBootstrapSnapshot.company_id == company_id,
        CompanyWorkspaceBootstrapSnapshot.as_of_key == _as_of_key(as_of),
        CompanyWorkspaceBootstrapSnapshot.schema_version == schema_version,
    )
    if source_fingerprint:
        statement = statement.where(CompanyWorkspaceBootstrapSnapshot.source_fingerprint == source_fingerprint)
    if settings.strict_official_mode:
        statement = statement.where(CompanyWorkspaceBootstrapSnapshot.strict_official_eligible.is_(True))
    statement = statement.order_by(CompanyWorkspaceBootstrapSnapshot.last_checked.desc(), CompanyWorkspaceBootstrapSnapshot.id.desc()).limit(1)
    return session.execute(statement).scalar_one_or_none()


def _snapshot_read(
    session: Session,
    record: CompanyWorkspaceBootstrapSnapshot,
    *,
    source_fingerprint: str | None,
) -> WorkspaceBootstrapSnapshotRead:
    payload = dict(record.payload or {})
    freshness_state = _freshness_state_for_record(session, record, source_fingerprint=source_fingerprint)
    return WorkspaceBootstrapSnapshotRead(
        record=record,
        payload={
            **payload,
            "schema_version": record.schema_version,
            "source_fingerprint": record.source_fingerprint,
            "freshness_state": freshness_state,
            "provenance": list(record.provenance or payload.get("provenance") or []),
            "source_mix": dict(record.source_mix or payload.get("source_mix") or {}),
            "confidence_flags": list(record.confidence_flags or payload.get("confidence_flags") or []),
            "fallback_flags": list(record.fallback_flags or payload.get("fallback_flags") or []),
            "strict_official_eligible": bool(record.strict_official_eligible),
        },
        source_fingerprint=record.source_fingerprint,
        freshness_state=freshness_state,
        is_current=bool(source_fingerprint and record.source_fingerprint == source_fingerprint and freshness_state == "fresh"),
    )


def _freshness_state_for_record(
    session: Session,
    record: CompanyWorkspaceBootstrapSnapshot,
    *,
    source_fingerprint: str | None,
) -> FreshnessState:
    if source_fingerprint and record.source_fingerprint != source_fingerprint:
        return "stale"
    _, dataset_state = cache_state_for_dataset(session, record.company_id, BOOTSTRAP_DATASET)
    if dataset_state in {"missing", "stale"}:
        return dataset_state
    value = str(record.freshness_state or "fresh").strip().lower()
    if value in {"fresh", "stale", "missing", "building", "partial"}:
        return value  # type: ignore[return-value]
    return "stale"


def _metadata_from_payload(
    payload: dict[str, Any],
    *,
    source_fingerprint: str,
    schema_version: str,
    checked_at: datetime,
) -> dict[str, Any]:
    provenance = _json_list(payload.get("provenance"))
    source_mix = _json_dict(payload.get("source_mix")) or build_source_mix(provenance)
    fallback_source_ids = source_mix.get("fallback_source_ids") if isinstance(source_mix, dict) else []
    fallback_source_ids = fallback_source_ids if isinstance(fallback_source_ids, list) else []
    fallback_flags = sorted(
        {
            *[str(flag) for flag in _json_list(payload.get("fallback_flags")) if str(flag)],
            *("commercial_fallback_present" for _ in fallback_source_ids or []),
        }
    )
    strict_official_eligible = not fallback_flags
    confidence_flags = sorted({str(flag) for flag in _json_list(payload.get("confidence_flags")) if str(flag)})
    freshness_state = str(payload.get("freshness_state") or "fresh").strip().lower()
    if freshness_state not in {"fresh", "stale", "missing", "building", "partial"}:
        freshness_state = "fresh"
    return {
        "schema_version": schema_version,
        "generated_at": payload.get("generated_at") or checked_at.isoformat(),
        "source_fingerprint": source_fingerprint,
        "source_mix": source_mix,
        "provenance": provenance,
        "freshness_state": freshness_state,
        "confidence_flags": confidence_flags,
        "fallback_flags": fallback_flags,
        "strict_official_eligible": strict_official_eligible,
    }


def _dataset_dependency_fingerprints(session: Session, company_id: int) -> dict[str, Any]:
    datasets = ["financials", "filings", "company_research_brief", "earnings"]
    if not settings.strict_official_mode:
        datasets.append("prices")

    statement = select(DatasetRefreshState).where(
        DatasetRefreshState.company_id == company_id,
        DatasetRefreshState.dataset.in_(datasets),
    )
    states = {state.dataset: state for state in session.execute(statement).scalars()}
    dependencies: dict[str, Any] = {}
    for dataset in datasets:
        state = states.get(dataset)
        dependencies[dataset] = {
            "payload_version_hash": getattr(state, "payload_version_hash", None),
            "last_success": _normalize_datetime_or_none(getattr(state, "last_success", None)),
            "freshness_deadline": _normalize_datetime_or_none(getattr(state, "freshness_deadline", None)),
            "active_job_id": getattr(state, "active_job_id", None),
        }
    return dependencies


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_datetime_or_none(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _normalize_datetime(value)


def _normalize_as_of(value: DateType | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _normalize_datetime(value).isoformat()
    if isinstance(value, DateType):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _as_of_key(as_of: datetime | None) -> str:
    return _normalize_as_of(as_of) or "latest"
