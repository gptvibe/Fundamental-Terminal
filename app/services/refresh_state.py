from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import Select, event, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, DatasetRefreshState
from app.services.hot_cache import shared_hot_response_cache

DatasetName = Literal[
    "financials",
    "prices",
    "insiders",
    "form144",
    "earnings",
    "earnings_models",
    "institutional",
    "beneficial_ownership",
    "filings",
    "capital_markets",
    "comment_letters",
    "proxy",
    "derived_metrics",
    "capital_structure",
    "company_research_brief",
    "charts_dashboard",
    "charts_forecast_accuracy",
    "oil_scenario_overlay",
    "company_refresh",
]

_SESSION_INVALIDATION_KEY = "shared_hot_cache_invalidations"


@dataclass(frozen=True, slots=True)
class _PendingHotCacheInvalidation:
    ticker: str | None
    dataset: str
    schema_version: str | None


@event.listens_for(Session, "after_commit")
def _flush_hot_cache_invalidations(session: Session) -> None:
    pending = session.info.pop(_SESSION_INVALIDATION_KEY, [])
    for invalidation in pending:
        shared_hot_response_cache.invalidate_sync(
            ticker=invalidation.ticker,
            dataset=invalidation.dataset,
            schema_version=invalidation.schema_version,
        )


@event.listens_for(Session, "after_rollback")
def _clear_hot_cache_invalidations(session: Session) -> None:
    session.info.pop(_SESSION_INVALIDATION_KEY, None)


def get_dataset_state(session: Session, company_id: int, dataset: DatasetName | str) -> DatasetRefreshState | None:
    statement: Select[tuple[DatasetRefreshState]] = select(DatasetRefreshState).where(
        DatasetRefreshState.company_id == company_id,
        DatasetRefreshState.dataset == str(dataset),
    )
    return session.execute(statement).scalar_one_or_none()


def get_dataset_last_checked(session: Session, company_id: int, dataset: DatasetName | str) -> datetime | None:
    state = get_dataset_state(session, company_id, dataset)
    if state is None:
        return None
    return _normalize_datetime(state.last_checked)


def cache_state_for_dataset(session: Session, company_id: int, dataset: DatasetName | str) -> tuple[datetime | None, str]:
    state = get_dataset_state(session, company_id, dataset)
    if state is None:
        return None, "missing"

    last_checked = _normalize_datetime(state.last_checked)
    deadline = _normalize_datetime(state.freshness_deadline)
    if last_checked is None:
        return None, "missing"
    if deadline is not None and deadline >= datetime.now(timezone.utc):
        return last_checked, "fresh"

    freshness_cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.freshness_window_hours)
    return last_checked, ("fresh" if last_checked >= freshness_cutoff else "stale")


def mark_dataset_checked(
    session: Session,
    company_id: int,
    dataset: DatasetName | str,
    *,
    checked_at: datetime,
    success: bool,
    job_id: str | None = None,
    payload_version_hash: str | None = None,
    error: str | None = None,
    invalidate_hot_cache: bool = False,
) -> None:
    normalized_checked_at = _normalize_datetime(checked_at)
    deadline = normalized_checked_at + timedelta(hours=settings.freshness_window_hours)
    statement = insert(DatasetRefreshState).values(
        company_id=company_id,
        dataset=str(dataset),
        last_checked=normalized_checked_at,
        last_success=normalized_checked_at if success else None,
        freshness_deadline=deadline if success else None,
        active_job_id=None,
        failure_count=0 if success else 1,
        last_error=None if success else (error or "refresh_failed"),
        payload_version_hash=payload_version_hash,
        updated_at=normalized_checked_at,
    )

    if success:
        set_values = {
            "last_checked": normalized_checked_at,
            "last_success": normalized_checked_at,
            "freshness_deadline": deadline,
            "active_job_id": None,
            "failure_count": 0,
            "last_error": None,
            "updated_at": normalized_checked_at,
        }
        if payload_version_hash is not None:
            set_values["payload_version_hash"] = payload_version_hash
    else:
        set_values = {
            "last_checked": normalized_checked_at,
            "active_job_id": None,
            "failure_count": DatasetRefreshState.failure_count + 1,
            "last_error": error or "refresh_failed",
            "updated_at": normalized_checked_at,
        }
        if payload_version_hash is not None:
            set_values["payload_version_hash"] = payload_version_hash
        if job_id is not None:
            set_values["active_job_id"] = None

    statement = statement.on_conflict_do_update(
        constraint="uq_dataset_refresh_state_company_dataset",
        set_=set_values,
    )
    session.execute(statement)
    if invalidate_hot_cache and success:
        _queue_hot_cache_invalidation(
            session,
            company_id=company_id,
            dataset=str(dataset),
            schema_version=payload_version_hash,
        )


def build_payload_version_hash(*, version: str, payload: Any) -> str:
    encoded = json.dumps(
        {
            "version": version,
            "payload": _json_fingerprint_value(payload),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]


def set_active_refresh_job(
    session: Session,
    *,
    company_id: int,
    dataset: DatasetName | str,
    job_id: str,
    updated_at: datetime | None = None,
) -> None:
    normalized_updated_at = _normalize_datetime(updated_at or datetime.now(timezone.utc))
    statement = insert(DatasetRefreshState).values(
        company_id=company_id,
        dataset=str(dataset),
        active_job_id=job_id,
        updated_at=normalized_updated_at,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_dataset_refresh_state_company_dataset",
        set_={
            "active_job_id": job_id,
            "updated_at": normalized_updated_at,
        },
    )
    session.execute(statement)


def acquire_refresh_lock(
    session: Session,
    *,
    company_id: int,
    dataset: DatasetName | str,
    job_id: str,
    now: datetime | None = None,
) -> str | None:
    current_time = _normalize_datetime(now or datetime.now(timezone.utc))
    state = get_dataset_state(session, company_id, dataset)
    if state is not None and state.active_job_id and state.last_checked is not None:
        lock_deadline = _normalize_datetime(state.last_checked) + timedelta(seconds=settings.refresh_lock_timeout_seconds)
        if lock_deadline > current_time:
            return state.active_job_id

    statement = insert(DatasetRefreshState).values(
        company_id=company_id,
        dataset=str(dataset),
        last_checked=current_time,
        active_job_id=job_id,
        updated_at=current_time,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_dataset_refresh_state_company_dataset",
        set_={
            "active_job_id": job_id,
            "last_checked": current_time,
            "updated_at": current_time,
        },
    )
    session.execute(statement)
    return None


def release_refresh_lock(
    session: Session,
    *,
    company_id: int,
    dataset: DatasetName | str,
    checked_at: datetime,
) -> None:
    mark_dataset_checked(
        session,
        company_id,
        dataset,
        checked_at=checked_at,
        success=True,
        invalidate_hot_cache=True,
    )


def release_refresh_lock_failed(
    session: Session,
    *,
    company_id: int,
    dataset: DatasetName | str,
    checked_at: datetime,
    error: str,
) -> None:
    mark_dataset_checked(
        session,
        company_id,
        dataset,
        checked_at=checked_at,
        success=False,
        error=error,
    )


def ensure_company(session: Session, ticker: str) -> Company | None:
    statement: Select[tuple[Company]] = select(Company).where(Company.ticker == ticker.strip().upper())
    return session.execute(statement).scalar_one_or_none()


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_fingerprint_value(value: Any) -> Any:
    if is_dataclass(value):
        return _json_fingerprint_value(asdict(value))
    if isinstance(value, datetime):
        normalized = _normalize_datetime(value)
        return normalized.isoformat() if normalized is not None else None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _json_fingerprint_value(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_fingerprint_value(item) for item in value]
    return value


def _queue_hot_cache_invalidation(
    session: Session,
    *,
    company_id: int,
    dataset: str,
    schema_version: str | None,
) -> None:
    ticker_statement: Select[tuple[str]] = select(Company.ticker).where(Company.id == company_id)
    ticker = session.execute(ticker_statement).scalar_one_or_none()
    pending = session.info.setdefault(_SESSION_INVALIDATION_KEY, [])
    invalidation = _PendingHotCacheInvalidation(ticker=ticker, dataset=dataset, schema_version=schema_version)
    if invalidation not in pending:
        pending.append(invalidation)
