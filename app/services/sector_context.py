from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.services.sector_persistence import (
    read_company_sector_snapshot_with_meta,
    upsert_company_sector_snapshot,
)
from app.services.sector_plugins import SECTOR_PLUGINS
from app.source_registry import SourceUsage, build_provenance_entries, build_source_mix

if False:  # pragma: no cover
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_company_sector_context(
    session: "Session",
    company_id: int,
    *,
    sector: str | None = None,
    market_sector: str | None = None,
    market_industry: str | None = None,
) -> dict[str, Any]:
    cached_payload, is_stale = read_company_sector_snapshot_with_meta(session, company_id)
    if cached_payload is not None and not is_stale:
        return cached_payload

    now = datetime.now(timezone.utc)
    plugins: list[dict[str, Any]] = []
    usages: list[SourceUsage] = []
    confidence_flags: list[str] = []
    matched_plugin_ids: list[str] = []

    for plugin in SECTOR_PLUGINS:
        relevance_reasons = plugin.relevance_reasons(
            sector=sector,
            market_sector=market_sector,
            market_industry=market_industry,
        )
        if not relevance_reasons:
            continue
        matched_plugin_ids.append(plugin.plugin_id)
        try:
            result = plugin.fetch()
        except Exception:
            logger.warning("Sector plugin %s failed", plugin.plugin_id, exc_info=True)
            plugins.append(
                {
                    "plugin_id": plugin.plugin_id,
                    "title": plugin.title,
                    "description": plugin.description,
                    "status": "unavailable",
                    "relevance_reasons": relevance_reasons,
                    "source_ids": [],
                    "refresh_policy": {
                        "cadence_label": plugin.refresh_policy.cadence_label,
                        "ttl_seconds": plugin.refresh_policy.ttl_seconds,
                        "notes": list(plugin.refresh_policy.notes),
                    },
                    "summary_metrics": [],
                    "charts": [],
                    "detail_view": {"title": "Current snapshot unavailable", "rows": []},
                    "confidence_flags": ["sector_plugin_fetch_failed"],
                    "as_of": None,
                    "last_refreshed_at": now.isoformat(),
                }
            )
            confidence_flags.append(f"{plugin.plugin_id}_unavailable")
            continue

        usages.extend(result.source_usages)
        confidence_flags.extend(result.confidence_flags)
        plugins.append(
            {
                "plugin_id": result.plugin_id,
                "title": result.title,
                "description": result.description,
                "status": result.status,
                "relevance_reasons": relevance_reasons,
                "source_ids": [usage.source_id for usage in result.source_usages],
                "refresh_policy": {
                    "cadence_label": plugin.refresh_policy.cadence_label,
                    "ttl_seconds": plugin.refresh_policy.ttl_seconds,
                    "notes": list(plugin.refresh_policy.notes),
                },
                "summary_metrics": [
                    {
                        "metric_id": item.metric_id,
                        "label": item.label,
                        "unit": item.unit,
                        "value": item.value,
                        "previous_value": item.previous_value,
                        "change": item.change,
                        "change_percent": item.change_percent,
                        "as_of": item.as_of,
                        "status": item.status,
                    }
                    for item in result.summary_metrics
                ],
                "charts": [
                    {
                        "chart_id": chart.chart_id,
                        "title": chart.title,
                        "subtitle": chart.subtitle,
                        "unit": chart.unit,
                        "series": [
                            {
                                "series_key": series.series_key,
                                "label": series.label,
                                "unit": series.unit,
                                "points": [
                                    {"label": point.label, "value": point.value}
                                    for point in series.points
                                ],
                            }
                            for series in chart.series
                        ],
                    }
                    for chart in result.charts
                ],
                "detail_view": {
                    "title": result.detail_view.title if result.detail_view else "Detail view unavailable",
                    "rows": [
                        {
                            "label": row.label,
                            "unit": row.unit,
                            "current_value": row.current_value,
                            "prior_value": row.prior_value,
                            "change": row.change,
                            "change_percent": row.change_percent,
                            "as_of": row.as_of,
                            "note": row.note,
                        }
                        for row in (result.detail_view.rows if result.detail_view else ())
                    ],
                },
                "confidence_flags": list(result.confidence_flags),
                "as_of": result.as_of,
                "last_refreshed_at": result.last_refreshed_at.isoformat(),
            }
        )

    provenance_entries = build_provenance_entries(usages)
    source_mix = build_source_mix(provenance_entries)
    as_of = max((entry.get("as_of") for entry in provenance_entries if entry.get("as_of")), default=None)
    last_refreshed_at = max(
        (
            entry.get("last_refreshed_at").isoformat()
            for entry in provenance_entries
            if entry.get("last_refreshed_at") is not None
        ),
        default=now.isoformat(),
    )

    if not matched_plugin_ids:
        status = "not_applicable"
        confidence_flags.append("no_relevant_sector_plugins")
    elif plugins and all(plugin.get("status") == "ok" for plugin in plugins):
        status = "ok"
    elif any(plugin.get("status") == "ok" for plugin in plugins):
        status = "partial"
    else:
        status = "unavailable"

    payload = {
        "status": status,
        "matched_plugin_ids": matched_plugin_ids,
        "plugins": plugins,
        "fetched_at": now.isoformat(),
        "provenance": provenance_entries,
        "as_of": as_of,
        "last_refreshed_at": last_refreshed_at,
        "source_mix": source_mix,
        "confidence_flags": sorted(set(confidence_flags)),
    }
    upsert_company_sector_snapshot(
        session,
        company_id=company_id,
        snapshot_date=now.date(),
        payload=payload,
        fetched_at=now,
    )
    return payload