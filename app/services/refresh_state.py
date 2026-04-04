from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, DatasetRefreshState

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
    "oil_scenario_overlay",
    "company_refresh",
]


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
            "payload_version_hash": payload_version_hash,
            "updated_at": normalized_checked_at,
        }
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
