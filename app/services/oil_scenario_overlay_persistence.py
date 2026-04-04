"""Persistence helpers for company oil scenario overlay snapshots."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models.company_oil_scenario_overlay_snapshot import CompanyOilScenarioOverlaySnapshot

logger = logging.getLogger(__name__)

OIL_SCENARIO_STALE_HOURS = settings.freshness_window_hours


def read_company_oil_scenario_overlay_snapshot_with_meta(
    session: Session,
    company_id: int,
) -> tuple[dict[str, Any] | None, bool]:
    row = (
        session.execute(
            select(CompanyOilScenarioOverlaySnapshot)
            .where(CompanyOilScenarioOverlaySnapshot.company_id == company_id)
            .order_by(CompanyOilScenarioOverlaySnapshot.snapshot_date.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return None, True

    threshold = datetime.now(timezone.utc) - timedelta(hours=OIL_SCENARIO_STALE_HOURS)
    is_stale = row.is_stale or row.fetched_at < threshold
    return dict(row.payload), is_stale


def upsert_company_oil_scenario_overlay_snapshot(
    session: Session,
    *,
    company_id: int,
    snapshot_date: date,
    payload: dict[str, Any],
    fetched_at: datetime,
) -> None:
    stmt = pg_insert(CompanyOilScenarioOverlaySnapshot.__table__).values(
        company_id=company_id,
        snapshot_date=snapshot_date,
        payload=payload,
        is_stale=False,
        fetched_at=fetched_at,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_company_oil_overlay_snapshots_company_date",
        set_={
            "payload": stmt.excluded.payload,
            "is_stale": stmt.excluded.is_stale,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )
    session.execute(stmt)


def mark_company_oil_scenario_overlay_stale(session: Session, company_id: int) -> None:
    row = (
        session.execute(
            select(CompanyOilScenarioOverlaySnapshot)
            .where(CompanyOilScenarioOverlaySnapshot.company_id == company_id)
            .order_by(CompanyOilScenarioOverlaySnapshot.snapshot_date.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return

    try:
        row.is_stale = True
        session.flush()
    except Exception:
        logger.warning(
            "Failed to mark oil scenario overlay snapshot stale for company_id=%s",
            company_id,
            exc_info=True,
        )
        session.rollback()