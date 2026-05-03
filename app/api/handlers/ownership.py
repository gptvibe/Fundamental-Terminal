from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
def company_insider_trades(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyInsiderTradesResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyInsiderTradesResponse(
            company=None,
            insider_trades=[],
            summary=_serialize_insider_activity_summary(build_insider_activity_summary([])),
            refresh=_trigger_refresh(normalized_ticker, reason="missing"),
        )

    insider_last_checked, insider_cache_state = get_company_insider_trade_cache_status(session, snapshot.company)
    insider_trades = get_company_insider_trades(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(snapshot.company.ticker, reason=insider_cache_state)
        if insider_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    return CompanyInsiderTradesResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, insider_last_checked),
            last_checked_insiders=insider_last_checked,
        ),
        insider_trades=[_serialize_insider_trade(trade) for trade in insider_trades],
        summary=_serialize_insider_activity_summary(build_insider_activity_summary(insider_trades)),
        refresh=refresh,
    )


@main_bound
def company_institutional_holdings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyInstitutionalHoldingsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyInstitutionalHoldingsResponse(
            company=None,
            institutional_holdings=[],
            refresh=_trigger_refresh(normalized_ticker, reason="missing"),
        )

    holdings_last_checked, holdings_cache_state = get_company_institutional_holdings_cache_status(session, snapshot.company)
    holdings = get_company_institutional_holdings(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(snapshot.company.ticker, reason=holdings_cache_state)
        if holdings_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    return CompanyInstitutionalHoldingsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, holdings_last_checked),
            last_checked_institutional=holdings_last_checked,
        ),
        institutional_holdings=[_serialize_institutional_holding(holding) for holding in holdings],
        refresh=refresh,
    )


@main_bound
def company_institutional_holdings_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyInstitutionalHoldingsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyInstitutionalHoldingsSummaryResponse(
            company=None,
            summary=InstitutionalHoldingsSummaryPayload(total_rows=0, unique_managers=0, amended_rows=0, latest_reporting_date=None),
            refresh=_trigger_refresh(normalized_ticker, reason="missing"),
        )

    holdings_last_checked, holdings_cache_state = get_company_institutional_holdings_cache_status(session, snapshot.company)
    holdings = get_company_institutional_holdings(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(snapshot.company.ticker, reason=holdings_cache_state)
        if holdings_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    rows = [_serialize_institutional_holding(holding) for holding in holdings]
    return CompanyInstitutionalHoldingsSummaryResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, holdings_last_checked),
            last_checked_institutional=holdings_last_checked,
        ),
        summary=_build_institutional_holdings_summary(rows),
        refresh=refresh,
    )


@main_bound
def company_form144_filings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyForm144Response:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyForm144Response(
            company=None,
            filings=[],
            refresh=_trigger_refresh(normalized_ticker, reason="missing"),
        )

    form144_last_checked, form144_cache_state = get_company_form144_cache_status(session, snapshot.company)
    filings = get_company_form144_filings(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(snapshot.company.ticker, reason=form144_cache_state)
        if form144_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    return CompanyForm144Response(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, form144_last_checked),
        ),
        filings=[_serialize_form144_filing(filing) for filing in filings],
        refresh=refresh,
    )


@main_bound
def insider_analytics(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> InsiderAnalyticsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    trades = get_company_insider_trades(session, snapshot.company.id, limit=400)
    return _serialize_insider_analytics(build_insider_analytics(trades))


@main_bound
def ownership_analytics(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> OwnershipAnalyticsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    holdings = get_company_institutional_holdings(session, snapshot.company.id, limit=600)
    analytics = build_ownership_analytics(holdings)
    return _serialize_ownership_analytics(analytics)


@main_bound
def company_beneficial_ownership(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyBeneficialOwnershipResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyBeneficialOwnershipResponse(
            company=None,
            filings=[],
            refresh=_trigger_refresh(normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(snapshot)
    cached_reports = get_company_beneficial_ownership_reports(session, snapshot.company.id)
    filings = _enrich_beneficial_ownership_amendment_history(
        [_serialize_cached_beneficial_ownership_report(report) for report in cached_reports]
    )
    return CompanyBeneficialOwnershipResponse(
        company=_serialize_company(snapshot),
        filings=filings,
        refresh=refresh,
        error=None,
    )


@main_bound
def company_beneficial_ownership_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyBeneficialOwnershipSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyBeneficialOwnershipSummaryResponse(
            company=None,
            summary=_empty_beneficial_ownership_summary(),
            refresh=_trigger_refresh(normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(snapshot)
    cached_reports = get_company_beneficial_ownership_reports(session, snapshot.company.id)
    filings = _enrich_beneficial_ownership_amendment_history(
        [_serialize_cached_beneficial_ownership_report(report) for report in cached_reports]
    )
    return CompanyBeneficialOwnershipSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_beneficial_ownership_summary(filings),
        refresh=refresh,
        error=None,
    )


__all__ = [
    "company_beneficial_ownership",
    "company_beneficial_ownership_summary",
    "company_form144_filings",
    "company_insider_trades",
    "company_institutional_holdings",
    "company_institutional_holdings_summary",
    "insider_analytics",
    "ownership_analytics",
]

