from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
def company_comment_letters(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCommentLettersResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyCommentLettersResponse(
            company=None,
            letters=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    comment_letters = get_company_comment_letters(session, snapshot.company.id)
    letters = [_serialize_comment_letter(letter) for letter in comment_letters]
    return CompanyCommentLettersResponse(
        company=_serialize_company(snapshot),
        letters=letters,
        refresh=refresh,
        diagnostics=_diagnostics_for_comment_letters(letters, refresh),
    )


@main_bound
def company_capital_raises(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCapitalRaisesResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyCapitalRaisesResponse(
            company=None,
            filings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    cached_events = get_company_capital_markets_events(session, snapshot.company.id)
    filings = [_serialize_cached_capital_markets_event(event) for event in cached_events]
    return CompanyCapitalRaisesResponse(
        company=_serialize_company(snapshot),
        filings=filings,
        refresh=refresh,
        diagnostics=_diagnostics_for_capital_markets(filings, refresh),
        error=None,
    )


@main_bound
def company_capital_markets(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCapitalRaisesResponse:
    main_module = __import__("sys").modules.get("app.main")
    if main_module is None:
        raise RuntimeError("app.main must be loaded before invoking company events handlers")
    return main_module.company_capital_raises(
        ticker=ticker,
        background_tasks=background_tasks,
        session=session,
    )


@main_bound
def company_capital_markets_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCapitalMarketsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyCapitalMarketsSummaryResponse(
            company=None,
            summary=_empty_capital_markets_summary(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    rows = [_serialize_cached_capital_markets_event(event) for event in get_company_capital_markets_events(session, snapshot.company.id)]
    return CompanyCapitalMarketsSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_capital_markets_summary(rows),
        refresh=refresh,
        diagnostics=_diagnostics_for_capital_markets(rows, refresh),
        error=None,
    )


@main_bound
def company_events(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEventsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEventsResponse(
            company=None,
            events=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    events = [_serialize_cached_filing_event(event) for event in get_company_filing_events(session, snapshot.company.id)]
    return CompanyEventsResponse(
        company=_serialize_company(snapshot),
        events=events,
        refresh=refresh,
        diagnostics=_diagnostics_for_filing_events(events, refresh),
        error=None,
    )


@main_bound
def company_filing_events(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEventsResponse:
    main_module = __import__("sys").modules.get("app.main")
    if main_module is None:
        raise RuntimeError("app.main must be loaded before invoking company events handlers")
    return main_module.company_events(
        ticker=ticker,
        background_tasks=background_tasks,
        session=session,
    )


@main_bound
def company_filing_events_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFilingEventsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyFilingEventsSummaryResponse(
            company=None,
            summary=_empty_filing_events_summary(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    rows = [_serialize_cached_filing_event(event) for event in get_company_filing_events(session, snapshot.company.id)]
    return CompanyFilingEventsSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_filing_events_summary(rows),
        refresh=refresh,
        diagnostics=_diagnostics_for_filing_events(rows, refresh),
        error=None,
    )


@main_bound
def company_activity_feed(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyActivityFeedResponse:
    overview = _build_company_activity_overview_response(ticker=ticker, background_tasks=background_tasks, session=session)
    return CompanyActivityFeedResponse(
        company=overview.company,
        entries=overview.entries,
        refresh=overview.refresh,
        error=overview.error,
    )


@main_bound
def company_alerts(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyAlertsResponse:
    overview = _build_company_activity_overview_response(ticker=ticker, background_tasks=background_tasks, session=session)
    return CompanyAlertsResponse(
        company=overview.company,
        alerts=overview.alerts,
        summary=overview.summary,
        refresh=overview.refresh,
        error=overview.error,
    )


@main_bound
def company_activity_overview(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyActivityOverviewResponse:
    return _build_company_activity_overview_response(ticker=ticker, background_tasks=background_tasks, session=session)


__all__ = [
    "company_activity_feed",
    "company_activity_overview",
    "company_alerts",
    "company_capital_markets",
    "company_capital_markets_summary",
    "company_comment_letters",
    "company_capital_raises",
    "company_events",
    "company_filing_events",
    "company_filing_events_summary",
]
