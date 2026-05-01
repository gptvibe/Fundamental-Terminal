from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
def company_governance(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyGovernanceResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyGovernanceResponse(
            company=None,
            filings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_governance(background_tasks, session, snapshot)
    cached_proxy = get_company_proxy_statements(session, snapshot.company.id)
    filings = [_serialize_cached_proxy_statement(statement) for statement in cached_proxy]
    return CompanyGovernanceResponse(
        company=_serialize_company(snapshot),
        filings=filings,
        refresh=refresh,
        diagnostics=_diagnostics_for_governance(filings, refresh),
        error=None,
    )


@main_bound
def company_governance_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyGovernanceSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyGovernanceSummaryResponse(
            company=None,
            summary=_empty_governance_summary(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_governance(background_tasks, session, snapshot)
    persisted_payload = _load_snapshot_backed_governance_summary_response(
        session,
        snapshot,
        refresh=refresh,
    )
    if persisted_payload is not None:
        return persisted_payload

    cached_proxy = get_company_proxy_statements(session, snapshot.company.id)
    filings = [_serialize_cached_proxy_statement(statement) for statement in cached_proxy]
    return CompanyGovernanceSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_governance_summary(filings),
        refresh=refresh,
        diagnostics=_diagnostics_for_governance(filings, refresh),
        error=None,
    )


@main_bound
def company_executive_compensation(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyExecutiveCompensationResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyExecutiveCompensationResponse(
            company=None,
            rows=[],
            fiscal_years=[],
            source="none",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_governance(background_tasks, session, snapshot)
    cached_rows = get_company_executive_compensation(session, snapshot.company.id)
    source = "cached" if cached_rows else "none"
    if cached_rows:
        serialized = [_serialize_exec_comp_row(row) for row in cached_rows]
    else:
        serialized = _load_live_exec_comp_rows(snapshot.company.cik)
        if serialized:
            source = "live"

    fiscal_years = sorted({row.fiscal_year for row in serialized if row.fiscal_year is not None}, reverse=True)
    return CompanyExecutiveCompensationResponse(
        company=_serialize_company(snapshot),
        rows=serialized,
        fiscal_years=fiscal_years,
        source=source,
        refresh=refresh,
        error=None,
    )


__all__ = ["company_executive_compensation", "company_governance", "company_governance_summary"]
