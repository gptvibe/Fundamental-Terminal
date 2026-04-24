from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.company_charts import (
    CompanyChartsShareSnapshotPayload,
    CompanyChartsShareSnapshotRecordPayload,
)
from app.models.company_charts_share_snapshot import CompanyChartsShareSnapshot


def create_company_charts_share_snapshot(
    session: Session,
    *,
    company_id: int,
    payload: CompanyChartsShareSnapshotPayload,
) -> CompanyChartsShareSnapshot:
    normalized_payload = payload.model_dump(mode="json")
    snapshot_hash = _snapshot_hash(normalized_payload)
    existing = session.execute(
        select(CompanyChartsShareSnapshot).where(
            CompanyChartsShareSnapshot.company_id == company_id,
            CompanyChartsShareSnapshot.snapshot_hash == snapshot_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    snapshot = CompanyChartsShareSnapshot(
        id=str(uuid4()),
        company_id=company_id,
        snapshot_hash=snapshot_hash,
        schema_version=payload.schema_version,
        mode=payload.mode,
        payload=normalized_payload,
        created_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def get_company_charts_share_snapshot(
    session: Session,
    *,
    company_id: int,
    snapshot_id: str,
) -> CompanyChartsShareSnapshot | None:
    return session.execute(
        select(CompanyChartsShareSnapshot).where(
            CompanyChartsShareSnapshot.company_id == company_id,
            CompanyChartsShareSnapshot.id == snapshot_id,
        )
    ).scalar_one_or_none()


def serialize_company_charts_share_snapshot(
    snapshot: CompanyChartsShareSnapshot,
    *,
    ticker: str,
) -> CompanyChartsShareSnapshotRecordPayload:
    payload = CompanyChartsShareSnapshotPayload.model_validate(snapshot.payload)
    share_path = _build_company_charts_share_snapshot_path(ticker, snapshot.id)
    return CompanyChartsShareSnapshotRecordPayload(
        id=snapshot.id,
        ticker=ticker,
        mode=payload.mode,
        schema_version=payload.schema_version,
        share_path=share_path,
        image_path=f"{share_path}/image",
        created_at=snapshot.created_at,
        payload=payload,
    )


def _build_company_charts_share_snapshot_path(ticker: str, snapshot_id: str) -> str:
    return f"/company/{quote(ticker)}/charts/share/{quote(snapshot_id)}"


def _snapshot_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
