"""SEC XBRL frames screener - ingestion and query service.

Provides two public entry points:

  ingest_sec_frame_snapshots(session, fiscal_year, fiscal_quarter)
      Fetches frames for all configured concept keys and persists them.

  query_sec_frames_screener(session, cik_list)
      Returns a dict keyed by CIK with the latest known value per concept.
      Missing facts are represented as None so the UI can clearly mark them.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import func as sa_func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.sec_frame_company_fact import SecFrameCompanyFact
from app.models.sec_frame_snapshot import SecFrameSnapshot
from app.services.sec.frames import ALL_SCREENER_CONCEPT_KEYS, SecFramesClient

logger = logging.getLogger(__name__)

CONCEPT_LABELS: dict[str, str] = {
    "revenue": "Revenue",
    "operating_income": "Operating income",
    "net_income": "Net income",
    "assets": "Total assets",
    "liabilities": "Total liabilities",
    "operating_cash_flow": "Operating cash flow",
    "capex": "Capital expenditures",
    "diluted_shares": "Diluted shares",
}

CONCEPT_UNITS: dict[str, str] = {
    "revenue": "USD",
    "operating_income": "USD",
    "net_income": "USD",
    "assets": "USD",
    "liabilities": "USD",
    "operating_cash_flow": "USD",
    "capex": "USD",
    "diluted_shares": "shares",
}


def ingest_sec_frame_snapshots(
    session: Session,
    fiscal_year: int,
    fiscal_quarter: int | None = None,
    *,
    concept_keys: tuple[str, ...] | None = None,
    user_agent: str = "Fundamental-Terminal research@example.com",
) -> dict[str, Any]:
    """Fetch frames from SEC and persist them."""
    keys_to_fetch = concept_keys or ALL_SCREENER_CONCEPT_KEYS
    new_snapshots = 0
    skipped_snapshots = 0
    facts_upserted = 0

    with SecFramesClient(user_agent=user_agent) as client:
        for concept_key in keys_to_fetch:
            frame = client.fetch_concept_frame(concept_key, fiscal_year, fiscal_quarter)
            if frame is None:
                logger.info(
                    "No frame found for %s fy=%s q=%s", concept_key, fiscal_year, fiscal_quarter
                )
                skipped_snapshots += 1
                continue

            period_type = _derive_period_type(frame.period_label)

            stmt = (
                pg_insert(SecFrameSnapshot)
                .values(
                    concept_key=frame.concept_key,
                    taxonomy=frame.taxonomy,
                    tag=frame.tag,
                    unit=frame.unit,
                    period_label=frame.period_label,
                    period_type=period_type,
                    fiscal_year=fiscal_year,
                    fiscal_quarter=fiscal_quarter,
                    pts=frame.pts,
                    fetched_at=frame.fetched_at,
                )
                .on_conflict_do_update(
                    constraint="uq_sec_frame_snapshots_concept_period_tag",
                    set_={
                        "pts": pg_insert(SecFrameSnapshot).excluded.pts,
                        "fetched_at": pg_insert(SecFrameSnapshot).excluded.fetched_at,
                    },
                )
                .returning(SecFrameSnapshot.id)
            )
            snapshot_id: int = session.execute(stmt).scalar_one()
            new_snapshots += 1

            if frame.data:
                fact_rows = [
                    {
                        "snapshot_id": snapshot_id,
                        "cik": str(dp.cik).zfill(10),
                        "entity_name": dp.entity_name[:255],
                        "end_date": _parse_date(dp.end),
                        "value": dp.val,
                        "accession_number": dp.accn[:30] if dp.accn else "",
                    }
                    for dp in frame.data
                ]
                facts_stmt = (
                    pg_insert(SecFrameCompanyFact)
                    .values(fact_rows)
                    .on_conflict_do_update(
                        constraint="uq_sec_frame_company_facts_snapshot_cik",
                        set_={
                            "value": pg_insert(SecFrameCompanyFact).excluded.value,
                            "end_date": pg_insert(SecFrameCompanyFact).excluded.end_date,
                            "accession_number": pg_insert(
                                SecFrameCompanyFact
                            ).excluded.accession_number,
                        },
                    )
                )
                session.execute(facts_stmt)
                facts_upserted += len(fact_rows)

            session.commit()
            logger.info(
                "Ingested %s: %d facts for %s %s",
                concept_key,
                len(frame.data),
                frame.period_label,
                frame.tag,
            )

    return {
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "new_snapshots": new_snapshots,
        "skipped_snapshots": skipped_snapshots,
        "facts_upserted": facts_upserted,
    }


def query_sec_frames_screener(
    session: Session,
    cik_list: list[str] | None = None,
    fiscal_year: int | None = None,
    fiscal_quarter: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Return the latest known SEC frame values per CIK for all concept keys."""
    snapshot_ids = _latest_snapshot_ids(session, fiscal_year, fiscal_quarter)

    if not snapshot_ids:
        return {}

    fact_q = (
        select(
            SecFrameCompanyFact.cik,
            SecFrameCompanyFact.entity_name,
            SecFrameCompanyFact.end_date,
            SecFrameCompanyFact.value,
            SecFrameCompanyFact.accession_number,
            SecFrameSnapshot.concept_key,
            SecFrameSnapshot.period_label,
            SecFrameSnapshot.unit,
        )
        .join(SecFrameSnapshot, SecFrameCompanyFact.snapshot_id == SecFrameSnapshot.id)
        .where(SecFrameCompanyFact.snapshot_id.in_(list(snapshot_ids.values())))
    )
    if cik_list:
        fact_q = fact_q.where(SecFrameCompanyFact.cik.in_(cik_list))

    fact_rows = session.execute(fact_q).all()

    result: dict[str, dict[str, Any]] = {}
    for row in fact_rows:
        cik = row.cik
        if cik not in result:
            result[cik] = {"entity_name": row.entity_name, "facts": {}}
        result[cik]["facts"][row.concept_key] = {
            "value": row.value,
            "end_date": row.end_date.isoformat() if row.end_date else None,
            "period_label": row.period_label,
            "unit": row.unit,
            "label": CONCEPT_LABELS.get(row.concept_key, row.concept_key),
            "missing": row.value is None,
            "accession_number": row.accession_number,
        }

    if cik_list:
        for cik in cik_list:
            entry = result.setdefault(cik, {"entity_name": "", "facts": {}})
            for concept_key in ALL_SCREENER_CONCEPT_KEYS:
                entry["facts"].setdefault(
                    concept_key,
                    {
                        "value": None,
                        "end_date": None,
                        "period_label": None,
                        "unit": CONCEPT_UNITS.get(concept_key, ""),
                        "label": CONCEPT_LABELS.get(concept_key, concept_key),
                        "missing": True,
                        "accession_number": "",
                    },
                )

    return result


def get_latest_snapshot_summary(session: Session) -> list[dict[str, Any]]:
    """Return metadata for the most recently fetched snapshot per concept key."""
    snapshot_ids = _latest_snapshot_ids(session, None, None)
    if not snapshot_ids:
        return []

    rows = (
        session.execute(
            select(SecFrameSnapshot).where(SecFrameSnapshot.id.in_(list(snapshot_ids.values())))
        )
        .scalars()
        .all()
    )

    return [
        {
            "concept_key": row.concept_key,
            "label": CONCEPT_LABELS.get(row.concept_key, row.concept_key),
            "period_label": row.period_label,
            "fiscal_year": row.fiscal_year,
            "fiscal_quarter": row.fiscal_quarter,
            "pts": row.pts,
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        }
        for row in rows
    ]


def _latest_snapshot_ids(
    session: Session,
    fiscal_year: int | None,
    fiscal_quarter: int | None,
) -> dict[str, int]:
    """Return the most recently fetched snapshot id per concept_key."""
    max_subq = (
        select(
            SecFrameSnapshot.concept_key,
            sa_func.max(SecFrameSnapshot.fetched_at).label("max_fetched"),
        ).group_by(SecFrameSnapshot.concept_key)
    )
    if fiscal_year is not None:
        max_subq = max_subq.where(SecFrameSnapshot.fiscal_year == fiscal_year)
    if fiscal_quarter is not None:
        max_subq = max_subq.where(SecFrameSnapshot.fiscal_quarter == fiscal_quarter)
    max_subq = max_subq.subquery()

    rows = session.execute(
        select(SecFrameSnapshot.concept_key, SecFrameSnapshot.id).join(
            max_subq,
            (SecFrameSnapshot.concept_key == max_subq.c.concept_key)
            & (SecFrameSnapshot.fetched_at == max_subq.c.max_fetched),
        )
    ).all()
    return {row.concept_key: row.id for row in rows}


def _derive_period_type(period_label: str) -> str:
    if period_label.endswith("I"):
        return "instant"
    if "Q" in period_label:
        return "quarterly"
    return "annual"


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


__all__ = [
    "ALL_SCREENER_CONCEPT_KEYS",
    "CONCEPT_LABELS",
    "CONCEPT_UNITS",
    "ingest_sec_frame_snapshots",
    "query_sec_frames_screener",
    "get_latest_snapshot_summary",
]
