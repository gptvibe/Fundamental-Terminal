from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends
from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.api.endpoint_source_contract_manifest import USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS
from app.api.handlers import _shared as shared
from app.api.schemas.source_registry import (
    SourceRegistryEntryPayload,
    SourceRegistryErrorPayload,
    SourceRegistryHealthPayload,
    SourceRegistryResponse,
)
from app.db import get_db_session


def _main_module() -> Any:
    main_module = sys.modules.get("app.main")
    if main_module is None:
        raise RuntimeError("app.main must be loaded before invoking source registry handlers")
    return main_module


def _current_settings() -> Any:
    try:
        return _main_module().settings
    except Exception:
        return shared.settings


def _normalize_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return shared._normalize_utc_datetime(value)


async def source_registry(
    session: Any = Depends(get_db_session),
) -> SourceRegistryResponse:
    generated_at = datetime.now(timezone.utc)

    def invoke(sync_session: Session) -> SourceRegistryResponse:
        main_module = _main_module()
        try:
            status_by_source = _build_source_registry_status_by_source(sync_session, now=generated_at)
        except Exception:
            logging.getLogger(__name__).exception("Unable to build source registry status payloads")
            status_by_source = {}
        usage_paths_by_source = _build_source_registry_usage_paths()
        sources = [
            _build_source_registry_entry_payload(
                source_id,
                source_status=status_by_source.get(source_id),
                used_by_paths=usage_paths_by_source.get(source_id, ()),
            )
            for source_id in _sorted_source_registry_ids()
        ]
        try:
            health = main_module._build_source_registry_health_payload(sync_session, now=generated_at)
        except Exception:
            logging.getLogger(__name__).exception("Unable to build source registry health payload")
            health = main_module._empty_source_registry_health_payload()
        settings = _current_settings()
        return SourceRegistryResponse(
            strict_official_mode=bool(getattr(settings, "strict_official_mode", False)),
            generated_at=generated_at,
            sources=sources,
            health=health,
        )

    return await shared._run_with_session_binding(session, invoke)


def _sorted_source_registry_ids() -> list[str]:
    return sorted(
        shared.SOURCE_REGISTRY.keys(),
        key=lambda source_id: (
            shared.SOURCE_REGISTRY_TIER_ORDER.get(shared.SOURCE_REGISTRY[source_id].tier, 99),
            shared.SOURCE_REGISTRY[source_id].display_label,
            source_id,
        ),
    )


def _build_source_registry_usage_paths() -> dict[str, list[str]]:
    usage_paths: dict[str, set[str]] = {}
    for (_method, path), contract in USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS.items():
        if path == "/api/source-registry":
            continue
        for source_id in contract.allowed_source_ids:
            usage_paths.setdefault(source_id, set()).add(path)

    return {
        source_id: sorted(paths)
        for source_id, paths in usage_paths.items()
    }


def _build_source_registry_status_by_source(
    session: Session,
    *,
    now: datetime,
) -> dict[str, dict[str, Any]]:
    statement: Select[Any] = shared.select(
        shared.DatasetRefreshState.dataset,
        shared.DatasetRefreshState.last_success,
        shared.DatasetRefreshState.freshness_deadline,
        shared.DatasetRefreshState.last_error,
        shared.DatasetRefreshState.updated_at,
    )
    rows = session.execute(statement).all()

    statuses: dict[str, dict[str, Any]] = {}
    for dataset_id, last_success, freshness_deadline, last_error, updated_at in rows:
        mapped_source_ids = shared.SOURCE_REGISTRY_DATASET_SOURCE_IDS.get(str(dataset_id), ())
        if not mapped_source_ids:
            continue

        normalized_last_success = _normalize_utc_datetime(last_success)
        normalized_deadline = _normalize_utc_datetime(freshness_deadline)
        normalized_updated_at = _normalize_utc_datetime(updated_at)
        is_stale = normalized_deadline is not None and normalized_deadline < now

        for source_id in mapped_source_ids:
            status = statuses.setdefault(
                source_id,
                {
                    "last_success_at": None,
                    "last_error": None,
                    "last_error_at": None,
                    "is_stale": False,
                },
            )

            if normalized_last_success is not None:
                existing_last_success = status["last_success_at"]
                if existing_last_success is None or normalized_last_success > existing_last_success:
                    status["last_success_at"] = normalized_last_success

            status["is_stale"] = bool(status["is_stale"] or is_stale)

            if last_error and normalized_updated_at is not None:
                existing_last_error_at = status["last_error_at"]
                if existing_last_error_at is None or normalized_updated_at >= existing_last_error_at:
                    status["last_error"] = str(last_error)
                    status["last_error_at"] = normalized_updated_at

    return statuses


def _build_source_registry_entry_payload(
    source_id: str,
    *,
    source_status: dict[str, Any] | None = None,
    used_by_paths: list[str] | tuple[str, ...] = (),
) -> SourceRegistryEntryPayload:
    definition = shared.SOURCE_REGISTRY[source_id]
    settings = _current_settings()
    disabled_in_current_mode = bool(getattr(settings, "strict_official_mode", False)) and definition.tier in shared.STRICT_OFFICIAL_DISABLED_SOURCE_TIERS
    if disabled_in_current_mode:
        strict_note = "Strict official mode is enabled, so this fallback source is currently suppressed."
    elif bool(getattr(settings, "strict_official_mode", False)):
        strict_note = "Strict official mode is enabled and this source remains available because it is official/public or derived from official inputs."
    else:
        strict_note = "Strict official mode is disabled, so this source is currently available."
    return SourceRegistryEntryPayload(
        source_id=definition.source_id,
        source_tier=definition.tier,
        display_label=definition.display_label,
        url=definition.url,
        default_freshness_ttl_seconds=definition.default_freshness_ttl_seconds,
        disclosure_note=definition.disclosure_note,
        strict_official_mode_state="disabled" if disabled_in_current_mode else "available",
        strict_official_mode_note=strict_note,
        last_success_at=source_status.get("last_success_at") if source_status else None,
        last_error=source_status.get("last_error") if source_status else None,
        last_error_at=source_status.get("last_error_at") if source_status else None,
        is_stale=bool(source_status.get("is_stale")) if source_status else False,
        used_by_paths=list(used_by_paths),
    )


def _build_source_registry_health_payload(
    session: Session,
    *,
    now: datetime,
) -> SourceRegistryHealthPayload:
    cached_company_checks = [
        last_checked
        for last_checked in session.execute(shared.select(_source_registry_latest_checks_subquery().c.last_checked)).scalars()
        if last_checked is not None
    ]
    normalized_checks = [shared._normalize_utc_datetime(last_checked) for last_checked in cached_company_checks]
    ages = [max((now - last_checked).total_seconds(), 0.0) for last_checked in normalized_checks if last_checked is not None]
    return SourceRegistryHealthPayload(
        total_companies_cached=len(ages),
        average_data_age_seconds=(sum(ages) / len(ages)) if ages else None,
        recent_error_window_hours=shared.SOURCE_REGISTRY_RECENT_ERROR_WINDOW_HOURS,
        sources_with_recent_errors=_main_module()._build_source_registry_error_payloads(session, now=now),
    )


def _empty_source_registry_health_payload() -> SourceRegistryHealthPayload:
    return SourceRegistryHealthPayload(
        total_companies_cached=0,
        average_data_age_seconds=None,
        recent_error_window_hours=shared.SOURCE_REGISTRY_RECENT_ERROR_WINDOW_HOURS,
        sources_with_recent_errors=[],
    )


def _build_source_registry_error_payloads(
    session: Session,
    *,
    now: datetime,
) -> list[SourceRegistryErrorPayload]:
    cutoff = now - timedelta(hours=shared.SOURCE_REGISTRY_RECENT_ERROR_WINDOW_HOURS)
    rows = session.execute(
        shared.select(
            shared.DatasetRefreshState.dataset,
            shared.DatasetRefreshState.company_id,
            shared.DatasetRefreshState.failure_count,
            shared.DatasetRefreshState.last_error,
            shared.DatasetRefreshState.updated_at,
        ).where(
            shared.DatasetRefreshState.last_error.is_not(None),
            shared.DatasetRefreshState.updated_at >= cutoff,
        )
    ).all()

    aggregates: dict[str, dict[str, Any]] = {}
    for dataset_id, company_id, failure_count, last_error, updated_at in rows:
        for source_id in shared.SOURCE_REGISTRY_DATASET_SOURCE_IDS.get(str(dataset_id), ()):
            definition = shared.get_source_definition(source_id)
            if definition is None or not last_error:
                continue
            aggregate = aggregates.setdefault(
                source_id,
                {
                    "source_id": source_id,
                    "source_tier": definition.tier,
                    "display_label": definition.display_label,
                    "affected_dataset_ids": set(),
                    "affected_company_ids": set(),
                    "failure_count": 0,
                    "last_error": str(last_error),
                    "last_error_at": shared._normalize_utc_datetime(updated_at),
                },
            )
            aggregate["affected_dataset_ids"].add(str(dataset_id))
            aggregate["affected_company_ids"].add(int(company_id))
            aggregate["failure_count"] += int(failure_count or 1)
            normalized_updated_at = shared._normalize_utc_datetime(updated_at)
            if normalized_updated_at >= aggregate["last_error_at"]:
                aggregate["last_error_at"] = normalized_updated_at
                aggregate["last_error"] = str(last_error)

    return [
        SourceRegistryErrorPayload(
            source_id=str(aggregate["source_id"]),
            source_tier=aggregate["source_tier"],
            display_label=str(aggregate["display_label"]),
            affected_dataset_ids=sorted(str(item) for item in aggregate["affected_dataset_ids"]),
            affected_company_count=len(aggregate["affected_company_ids"]),
            failure_count=int(aggregate["failure_count"]),
            last_error=str(aggregate["last_error"]),
            last_error_at=aggregate["last_error_at"],
        )
        for aggregate in sorted(
            aggregates.values(),
            key=lambda item: (
                -item["last_error_at"].timestamp(),
                str(item["display_label"]),
            ),
        )
    ]


def _source_registry_latest_checks_subquery():
    statement_checks = (
        shared.select(
            shared.FinancialStatement.company_id.label("company_id"),
            shared.func.max(shared.FinancialStatement.last_checked).label("last_checked"),
        )
        .where(shared.FinancialStatement.statement_type == shared.CANONICAL_STATEMENT_TYPE)
        .group_by(shared.FinancialStatement.company_id)
        .subquery()
    )

    refresh_checks = (
        shared.select(
            shared.DatasetRefreshState.company_id.label("company_id"),
            shared.func.max(shared.DatasetRefreshState.last_checked).label("last_checked"),
        )
        .where(shared.DatasetRefreshState.dataset == "financials")
        .group_by(shared.DatasetRefreshState.company_id)
        .subquery()
    )

    return (
        shared.select(
            statement_checks.c.company_id.label("company_id"),
            shared.func.coalesce(refresh_checks.c.last_checked, statement_checks.c.last_checked).label("last_checked"),
        )
        .outerjoin(refresh_checks, refresh_checks.c.company_id == statement_checks.c.company_id)
        .subquery()
    )


__all__ = [
    "_build_source_registry_entry_payload",
    "_build_source_registry_error_payloads",
    "_build_source_registry_health_payload",
    "_build_source_registry_status_by_source",
    "_build_source_registry_usage_paths",
    "_empty_source_registry_health_payload",
    "_sorted_source_registry_ids",
    "_source_registry_latest_checks_subquery",
    "source_registry",
]
