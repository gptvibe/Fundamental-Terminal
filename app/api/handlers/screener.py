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


__all__ = ["official_screener_filters", "official_screener_search"]
