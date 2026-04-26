from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.workspace import (
    LocalImportNotePayload,
    LocalImportWatchlistItemPayload,
    ResearchWorkspaceDeleteResponse,
    ResearchWorkspaceNotePayload,
    ResearchWorkspaceImportLocalRequest,
    ResearchWorkspacePayload,
    ResearchWorkspaceSavedCompanyPayload,
    ResearchWorkspaceUpsertRequest,
)
from app.db import get_db_session
from app.models.research_workspace import ResearchWorkspace


DEFAULT_WORKSPACE_KEY = "default"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _empty_workspace_payload(workspace_key: str) -> ResearchWorkspacePayload:
    now = _utc_now()
    return ResearchWorkspacePayload(
        workspace_key=workspace_key,
        saved_companies=[],
        notes=[],
        pinned_metrics=[],
        pinned_charts=[],
        compare_baskets=[],
        memo_draft=None,
        updated_at=now,
    )


async def _load_workspace_row(session: AsyncSession, workspace_key: str) -> ResearchWorkspace | None:
    statement = select(ResearchWorkspace).where(ResearchWorkspace.workspace_key == workspace_key)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


def _workspace_row_to_payload(row: ResearchWorkspace) -> ResearchWorkspacePayload:
    return ResearchWorkspacePayload(
        workspace_key=row.workspace_key,
        saved_companies=row.saved_companies or [],
        notes=list((row.notes or {}).values()),
        pinned_metrics=row.pinned_metrics or [],
        pinned_charts=row.pinned_charts or [],
        compare_baskets=row.compare_baskets or [],
        memo_draft=row.memo_draft,
        updated_at=row.updated_at,
    )


async def get_research_workspace(
    workspace_key: str = Query(DEFAULT_WORKSPACE_KEY, min_length=1, max_length=120),
    session: AsyncSession = Depends(get_db_session),
) -> ResearchWorkspacePayload:
    row = await _load_workspace_row(session, workspace_key)
    if row is None:
        return _empty_workspace_payload(workspace_key)
    return _workspace_row_to_payload(row)


async def upsert_research_workspace(
    payload: ResearchWorkspaceUpsertRequest,
    workspace_key: str = Query(DEFAULT_WORKSPACE_KEY, min_length=1, max_length=120),
    session: AsyncSession = Depends(get_db_session),
) -> ResearchWorkspacePayload:
    now = _utc_now()
    row = await _load_workspace_row(session, workspace_key)

    next_notes = {item.ticker: item.model_dump(mode="json") for item in payload.notes}
    next_saved_companies = [item.model_dump(mode="json") for item in payload.saved_companies]
    next_pinned_metrics = [item.model_dump(mode="json") for item in payload.pinned_metrics]
    next_pinned_charts = [item.model_dump(mode="json") for item in payload.pinned_charts]
    next_compare_baskets = [item.model_dump(mode="json") for item in payload.compare_baskets]

    if row is None:
        row = ResearchWorkspace(
            workspace_key=workspace_key,
            saved_companies=next_saved_companies,
            notes=next_notes,
            pinned_metrics=next_pinned_metrics,
            pinned_charts=next_pinned_charts,
            compare_baskets=next_compare_baskets,
            memo_draft=payload.memo_draft,
            updated_at=now,
        )
        session.add(row)
    else:
        row.saved_companies = next_saved_companies
        row.notes = next_notes
        row.pinned_metrics = next_pinned_metrics
        row.pinned_charts = next_pinned_charts
        row.compare_baskets = next_compare_baskets
        row.memo_draft = payload.memo_draft
        row.updated_at = now

    await session.commit()
    await session.refresh(row)
    return _workspace_row_to_payload(row)


async def delete_research_workspace(
    workspace_key: str = Query(DEFAULT_WORKSPACE_KEY, min_length=1, max_length=120),
    session: AsyncSession = Depends(get_db_session),
) -> ResearchWorkspaceDeleteResponse:
    row = await _load_workspace_row(session, workspace_key)
    now = _utc_now()
    if row is not None:
        await session.delete(row)
        await session.commit()

    return ResearchWorkspaceDeleteResponse(workspace_key=workspace_key, deleted=True, updated_at=now)


def _parse_datetime_or_now(value: datetime | None) -> datetime:
    return value or _utc_now()


def _merge_saved_companies(
    existing: list[dict[str, Any]],
    incoming: list[LocalImportWatchlistItemPayload],
) -> list[dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {item.get("ticker", ""): dict(item) for item in existing if item.get("ticker")}

    for item in incoming:
        candidate = ResearchWorkspaceSavedCompanyPayload(
            ticker=item.ticker,
            name=item.name,
            sector=item.sector,
            saved_at=_parse_datetime_or_now(item.savedAt),
            updated_at=_parse_datetime_or_now(item.savedAt),
        )
        current = by_ticker.get(candidate.ticker)
        if current is None:
            by_ticker[candidate.ticker] = candidate.model_dump(mode="json")
            continue

        current_updated_at = _parse_datetime_or_now(ResearchWorkspaceSavedCompanyPayload.model_validate(current).updated_at)
        if candidate.updated_at >= current_updated_at:
            by_ticker[candidate.ticker] = candidate.model_dump(mode="json")

    merged = list(by_ticker.values())
    merged.sort(key=lambda item: (item.get("updated_at") or "", item.get("ticker") or ""), reverse=True)
    return merged


def _merge_notes(
    existing: dict[str, dict[str, Any]],
    incoming: dict[str, LocalImportNotePayload],
) -> dict[str, dict[str, Any]]:
    by_ticker = {ticker: dict(value) for ticker, value in existing.items()}

    for note in incoming.values():
        candidate = note.model_copy(update={"updatedAt": _parse_datetime_or_now(note.updatedAt)})
        normalized = candidate.ticker
        current = by_ticker.get(normalized)
        if current is None:
            by_ticker[normalized] = {
                "ticker": normalized,
                "name": candidate.name,
                "sector": candidate.sector,
                "note": candidate.note,
                "updated_at": candidate.updatedAt.isoformat(),
            }
            continue

        current_payload = ResearchWorkspaceNotePayload.model_validate(current)
        current_updated = current_payload.updated_at
        if candidate.updatedAt >= current_updated:
            by_ticker[normalized] = {
                "ticker": normalized,
                "name": candidate.name,
                "sector": candidate.sector,
                "note": candidate.note,
                "updated_at": candidate.updatedAt.isoformat(),
            }

    return by_ticker


async def import_local_research_workspace(
    payload: ResearchWorkspaceImportLocalRequest,
    workspace_key: str = Query(DEFAULT_WORKSPACE_KEY, min_length=1, max_length=120),
    session: AsyncSession = Depends(get_db_session),
) -> ResearchWorkspacePayload:
    now = _utc_now()
    row = await _load_workspace_row(session, workspace_key)

    if row is None:
        row = ResearchWorkspace(
            workspace_key=workspace_key,
            saved_companies=[],
            notes={},
            pinned_metrics=[],
            pinned_charts=[],
            compare_baskets=[],
            memo_draft=None,
            updated_at=now,
        )
        session.add(row)

    if payload.mode == "replace":
        row.saved_companies = _merge_saved_companies([], payload.watchlist)
        row.notes = _merge_notes({}, payload.notes)
    else:
        row.saved_companies = _merge_saved_companies(row.saved_companies or [], payload.watchlist)
        row.notes = _merge_notes(row.notes or {}, payload.notes)

    row.updated_at = now
    await session.commit()
    await session.refresh(row)
    return _workspace_row_to_payload(row)
