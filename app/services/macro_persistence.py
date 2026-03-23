"""Macro data persistence helpers.

Implements DB-first / cache-first read paths for:
- market_context_snapshots (global)
- company_macro_snapshots (per-company)

Write helpers persist fresh payloads atomically (upsert by date).
Read helpers return the latest snapshot with stale detection.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models.company_macro_snapshot import CompanyMacroSnapshot
from app.models.market_context_snapshot import MarketContextSnapshot

logger = logging.getLogger(__name__)

# How old a snapshot can be before it is considered stale (hours)
GLOBAL_STALE_HOURS = settings.market_context_cache_ttl_hours
COMPANY_STALE_HOURS = settings.market_context_cache_ttl_hours


# ---------------------------------------------------------------------------
# Global snapshot helpers
# ---------------------------------------------------------------------------


def read_global_macro_snapshot(session: Session) -> dict[str, Any] | None:
    """Return the latest global macro snapshot payload, or None if missing."""
    row = (
        session.execute(
            select(MarketContextSnapshot)
            .order_by(MarketContextSnapshot.snapshot_date.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    return dict(row.payload)


def read_global_macro_snapshot_with_meta(session: Session) -> tuple[dict[str, Any] | None, bool]:
    """Return (payload, is_stale) for the latest global snapshot."""
    row = (
        session.execute(
            select(MarketContextSnapshot)
            .order_by(MarketContextSnapshot.snapshot_date.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return None, True

    threshold = datetime.now(timezone.utc) - timedelta(hours=GLOBAL_STALE_HOURS)
    is_stale = row.is_stale or row.fetched_at < threshold
    return dict(row.payload), is_stale


def upsert_global_macro_snapshot(
    session: Session,
    *,
    snapshot_date: date,
    status: str,
    payload: dict[str, Any],
    provenance: dict[str, Any] | None,
    fetched_at: datetime,
) -> None:
    """Upsert global snapshot, replacing any existing row for the same date."""
    try:
        stmt = pg_insert(MarketContextSnapshot.__table__).values(
            snapshot_date=snapshot_date,
            status=status,
            payload=payload,
            provenance=provenance,
            is_stale=False,
            fetched_at=fetched_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["snapshot_date"],
            set_={
                "status": stmt.excluded.status,
                "payload": stmt.excluded.payload,
                "provenance": stmt.excluded.provenance,
                "is_stale": stmt.excluded.is_stale,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
        session.execute(stmt)
        session.commit()
    except Exception:
        logger.warning("Failed to upsert global macro snapshot for %s", snapshot_date, exc_info=True)
        session.rollback()


def mark_global_snapshot_stale(session: Session) -> None:
    """Mark all global snapshots as stale (triggers background refresh on next read)."""
    try:
        session.execute(
            text("UPDATE market_context_snapshots SET is_stale = true")
        )
        session.commit()
    except Exception:
        logger.warning("Failed to mark global snapshots stale", exc_info=True)
        session.rollback()


# ---------------------------------------------------------------------------
# Company snapshot helpers
# ---------------------------------------------------------------------------


def read_company_macro_snapshot(session: Session, company_id: int) -> dict[str, Any] | None:
    """Return the latest company macro snapshot payload, or None if missing."""
    row = (
        session.execute(
            select(CompanyMacroSnapshot)
            .where(CompanyMacroSnapshot.company_id == company_id)
            .order_by(CompanyMacroSnapshot.snapshot_date.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    return dict(row.payload)


def read_company_macro_snapshot_with_meta(
    session: Session, company_id: int
) -> tuple[dict[str, Any] | None, bool]:
    """Return (payload, is_stale) for the latest company macro snapshot."""
    row = (
        session.execute(
            select(CompanyMacroSnapshot)
            .where(CompanyMacroSnapshot.company_id == company_id)
            .order_by(CompanyMacroSnapshot.snapshot_date.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return None, True

    threshold = datetime.now(timezone.utc) - timedelta(hours=COMPANY_STALE_HOURS)
    is_stale = row.is_stale or row.fetched_at < threshold
    return dict(row.payload), is_stale


def upsert_company_macro_snapshot(
    session: Session,
    *,
    company_id: int,
    snapshot_date: date,
    payload: dict[str, Any],
    fetched_at: datetime,
) -> None:
    """Upsert company macro snapshot, replacing any existing row for the same company+date."""
    try:
        stmt = pg_insert(CompanyMacroSnapshot.__table__).values(
            company_id=company_id,
            snapshot_date=snapshot_date,
            payload=payload,
            is_stale=False,
            fetched_at=fetched_at,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_company_macro_snapshots_company_date",
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
            "Failed to upsert company macro snapshot for company_id=%s", company_id, exc_info=True
        )
        session.rollback()
