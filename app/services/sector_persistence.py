"""Sector context persistence helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models.company_sector_snapshot import CompanySectorSnapshot

logger = logging.getLogger(__name__)

SECTOR_STALE_HOURS = settings.sector_context_cache_ttl_hours


def read_company_sector_snapshot_with_meta(
    session: Session, company_id: int
) -> tuple[dict[str, Any] | None, bool]:
    row = (
        session.execute(
            select(CompanySectorSnapshot)
            .where(CompanySectorSnapshot.company_id == company_id)
            .order_by(CompanySectorSnapshot.snapshot_date.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return None, True

    threshold = datetime.now(timezone.utc) - timedelta(hours=SECTOR_STALE_HOURS)
    is_stale = row.is_stale or row.fetched_at < threshold
    return dict(row.payload), is_stale


def upsert_company_sector_snapshot(
    session: Session,
    *,
    company_id: int,
    snapshot_date: datetime.date,
    payload: dict[str, Any],
    fetched_at: datetime,
) -> None:
    try:
        stmt = pg_insert(CompanySectorSnapshot.__table__).values(
            company_id=company_id,
            snapshot_date=snapshot_date,
            payload=payload,
            is_stale=False,
            fetched_at=fetched_at,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_company_sector_snapshots_company_date",
            set_={
                "payload": stmt.excluded.payload,
                "is_stale": stmt.excluded.is_stale,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
        session.execute(stmt)
        session.commit()
    except Exception:
        logger.warning(
            "Failed to upsert company sector snapshot for company_id=%s",
            company_id,
            exc_info=True,
        )
        session.rollback()