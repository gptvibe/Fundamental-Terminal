from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
def official_screener_filters() -> OfficialScreenerMetadataResponse:
    payload = build_official_screener_filter_catalog()
    source_hints = dict(payload.pop("source_hints", None) or {})
    confidence_flags = list(payload.pop("confidence_flags", None) or [])
    return OfficialScreenerMetadataResponse(
        **payload,
        **_official_screener_provenance_contract(
            source_hints=source_hints,
            as_of=None,
            last_refreshed_at=None,
            confidence_flags=confidence_flags,
        ),
    )


@main_bound
def official_screener_search(
    payload: OfficialScreenerSearchRequest,
    session: Session = Depends(get_db_session),
) -> OfficialScreenerSearchResponse:
    result = run_official_screener(session, payload.model_dump(mode="python"))
    source_hints = dict(result.pop("source_hints", None) or {})
    confidence_flags = list(result.pop("confidence_flags", None) or [])
    provenance_as_of = result.pop("as_of", None)
    provenance_last_refreshed_at = result.pop("last_refreshed_at", None)
    return OfficialScreenerSearchResponse(
        **result,
        **_official_screener_provenance_contract(
            source_hints=source_hints,
            as_of=provenance_as_of,
            last_refreshed_at=provenance_last_refreshed_at,
            confidence_flags=confidence_flags,
        ),
    )


@main_bound
def sec_frames_screener(
    ciks: str = Query(default="", description="Comma-separated CIK list; omit for all."),
    fiscal_year: int | None = Query(default=None),
    fiscal_quarter: int | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> SecFramesScreenerResponse:
    import datetime as _dt
    from datetime import timezone
    from app.services.sec.frames import ALL_SCREENER_CONCEPT_KEYS
    from app.services.sec_frames_screener import (
        get_latest_snapshot_summary,
        query_sec_frames_screener,
    )

    cik_list = [c.strip().zfill(10) for c in ciks.split(",") if c.strip()] or None
    raw = query_sec_frames_screener(
        session,
        cik_list=cik_list,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
    )
    snapshots = get_latest_snapshot_summary(session)
    covered = {s["concept_key"] for s in snapshots}
    companies = [
        SecFrameCompanyPayload(
            cik=cik,
            entity_name=entry.get("entity_name", ""),
            facts={
                k: SecFrameFactPayload(**v)
                for k, v in entry.get("facts", {}).items()
            },
        )
        for cik, entry in raw.items()
    ]
    return SecFramesScreenerResponse(
        snapshots=[SecFramesSnapshotSummaryPayload(**s) for s in snapshots],
        companies=companies,
        total_companies=len(companies),
        covered_concepts=sorted(covered),
        missing_concepts=sorted(set(ALL_SCREENER_CONCEPT_KEYS) - covered),
        as_of=_dt.datetime.now(tz=timezone.utc).isoformat(),
        last_refreshed_at=None,
        confidence_flags=["sec_xbrl_frames_official_only"],
    )


__all__ = ["official_screener_filters", "official_screener_search", "sec_frames_screener"]
