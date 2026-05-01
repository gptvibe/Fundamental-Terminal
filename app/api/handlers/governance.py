from __future__ import annotations

from app.api.handlers import _shared as shared


@shared.app.get("/api/companies/{ticker}/governance", response_model=shared.CompanyGovernanceResponse)
def company_governance(
    ticker: str,
    session: shared.Session = shared.Depends(shared.get_db_session),
) -> shared.CompanyGovernanceResponse:
    normalized_ticker = shared._normalize_ticker(ticker)
    snapshot = shared._resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return shared.CompanyGovernanceResponse(
            company=None,
            filings=[],
            refresh=shared._trigger_refresh(normalized_ticker, reason="missing"),
            diagnostics=shared._build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = shared._refresh_for_governance(session, snapshot)
    cached_proxy = shared.get_company_proxy_statements(session, snapshot.company.id)
    filings = [shared._serialize_cached_proxy_statement(statement) for statement in cached_proxy]
    return shared.CompanyGovernanceResponse(
        company=shared._serialize_company(snapshot),
        filings=filings,
        refresh=refresh,
        diagnostics=shared._diagnostics_for_governance(filings, refresh),
        error=None,
    )


@shared.app.get("/api/companies/{ticker}/governance/summary", response_model=shared.CompanyGovernanceSummaryResponse)
def company_governance_summary(
    ticker: str,
    session: shared.Session = shared.Depends(shared.get_db_session),
) -> shared.CompanyGovernanceSummaryResponse:
    normalized_ticker = shared._normalize_ticker(ticker)
    snapshot = shared._resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return shared.CompanyGovernanceSummaryResponse(
            company=None,
            summary=shared._empty_governance_summary(),
            refresh=shared._trigger_refresh(normalized_ticker, reason="missing"),
            diagnostics=shared._build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = shared._refresh_for_governance(session, snapshot)
    persisted_payload = shared._load_snapshot_backed_governance_summary_response(
        session,
        snapshot,
        refresh=refresh,
    )
    if persisted_payload is not None:
        return persisted_payload

    cached_proxy = shared.get_company_proxy_statements(session, snapshot.company.id)
    filings = [shared._serialize_cached_proxy_statement(statement) for statement in cached_proxy]
    return shared.CompanyGovernanceSummaryResponse(
        company=shared._serialize_company(snapshot),
        summary=shared._build_governance_summary(filings),
        refresh=refresh,
        diagnostics=shared._diagnostics_for_governance(filings, refresh),
        error=None,
    )


@shared.app.get("/api/companies/{ticker}/executive-compensation", response_model=shared.CompanyExecutiveCompensationResponse)
def company_executive_compensation(
    ticker: str,
    session: shared.Session = shared.Depends(shared.get_db_session),
) -> shared.CompanyExecutiveCompensationResponse:
    normalized_ticker = shared._normalize_ticker(ticker)
    snapshot = shared._resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return shared.CompanyExecutiveCompensationResponse(
            company=None,
            rows=[],
            fiscal_years=[],
            source="none",
            refresh=shared._trigger_refresh(normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = shared._refresh_for_governance(session, snapshot)
    cached_rows = shared.get_company_executive_compensation(session, snapshot.company.id)
    source = "cached" if cached_rows else "none"
    if cached_rows:
        serialized = [shared._serialize_exec_comp_row(row) for row in cached_rows]
    else:
        serialized = shared._load_live_exec_comp_rows(snapshot.company.cik)
        if serialized:
            source = "live"

    fiscal_years = sorted({row.fiscal_year for row in serialized if row.fiscal_year is not None}, reverse=True)
    return shared.CompanyExecutiveCompensationResponse(
        company=shared._serialize_company(snapshot),
        rows=serialized,
        fiscal_years=fiscal_years,
        source=source,
        refresh=refresh,
        error=None,
    )


company_governance = shared._wrap_db_handler(company_governance)
company_governance_summary = shared._wrap_db_handler(company_governance_summary)
company_executive_compensation = shared._wrap_db_handler(company_executive_compensation)


__all__ = ["company_executive_compensation", "company_governance", "company_governance_summary"]
