from __future__ import annotations

import sys

from app.api.handlers import _shared as shared
from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


def _main_or_shared_attr(name: str):
    main_module = sys.modules.get("app.main")
    if main_module is not None and hasattr(main_module, name):
        return getattr(main_module, name)
    return getattr(shared, name)


def _build_company_capital_raises_response(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session,
) -> CompanyCapitalRaisesResponse:
    normalize_ticker = _main_or_shared_attr("_normalize_ticker")
    resolve_snapshot = _main_or_shared_attr("_resolve_cached_company_snapshot")
    trigger_refresh = _main_or_shared_attr("_trigger_refresh")
    refresh_for_snapshot = _main_or_shared_attr("_refresh_for_snapshot")
    serialize_company = _main_or_shared_attr("_serialize_company")
    diagnostics_for_capital_markets = _main_or_shared_attr("_diagnostics_for_capital_markets")
    build_data_quality_diagnostics = _main_or_shared_attr("_build_data_quality_diagnostics")
    get_capital_markets_events = _main_or_shared_attr("get_company_capital_markets_events")
    serialize_cached_capital_markets_event = _main_or_shared_attr("_serialize_cached_capital_markets_event")

    normalized_ticker = normalize_ticker(ticker)
    snapshot = resolve_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyCapitalRaisesResponse(
            company=None,
            filings=[],
            refresh=trigger_refresh(normalized_ticker, reason="missing"),
            diagnostics=build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = refresh_for_snapshot(snapshot)
    cached_events = get_capital_markets_events(session, snapshot.company.id)
    filings = [serialize_cached_capital_markets_event(event) for event in cached_events]
    return CompanyCapitalRaisesResponse(
        company=serialize_company(snapshot),
        filings=filings,
        refresh=refresh,
        diagnostics=diagnostics_for_capital_markets(filings, refresh),
        error=None,
    )


def _build_company_events_response(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session,
) -> CompanyEventsResponse:
    normalize_ticker = _main_or_shared_attr("_normalize_ticker")
    resolve_snapshot = _main_or_shared_attr("_resolve_cached_company_snapshot")
    trigger_refresh = _main_or_shared_attr("_trigger_refresh")
    refresh_for_snapshot = _main_or_shared_attr("_refresh_for_snapshot")
    serialize_company = _main_or_shared_attr("_serialize_company")
    diagnostics_for_filing_events = _main_or_shared_attr("_diagnostics_for_filing_events")
    build_data_quality_diagnostics = _main_or_shared_attr("_build_data_quality_diagnostics")
    get_filing_events = _main_or_shared_attr("get_company_filing_events")
    serialize_cached_filing_event = _main_or_shared_attr("_serialize_cached_filing_event")

    normalized_ticker = normalize_ticker(ticker)
    snapshot = resolve_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEventsResponse(
            company=None,
            events=[],
            refresh=trigger_refresh(normalized_ticker, reason="missing"),
            diagnostics=build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = refresh_for_snapshot(snapshot)
    events = [serialize_cached_filing_event(event) for event in get_filing_events(session, snapshot.company.id)]
    return CompanyEventsResponse(
        company=serialize_company(snapshot),
        events=events,
        refresh=refresh,
        diagnostics=diagnostics_for_filing_events(events, refresh),
        error=None,
    )


@main_bound
def company_comment_letters(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCommentLettersResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        refresh = _trigger_refresh(normalized_ticker, reason="missing")
        return CompanyCommentLettersResponse(
            company=None,
            letters=[],
            refresh=refresh,
            **_empty_provenance_contract("company_missing"),
        )

    letters_last_checked, letters_cache_state = get_company_comment_letters_cache_status(session, snapshot.company)
    letters = [_serialize_comment_letter(letter) for letter in get_company_comment_letters(session, snapshot.company.id)]
    refresh = (
        _trigger_refresh(snapshot.company.ticker, reason=letters_cache_state)
        if letters_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    merged_last_checked = _merge_last_checked(snapshot.last_checked, letters_last_checked)
    return CompanyCommentLettersResponse(
        company=_serialize_company(snapshot, last_checked=merged_last_checked),
        letters=letters,
        refresh=refresh,
        **_comment_letters_provenance_contract(letters, last_refreshed_at=merged_last_checked, refresh=refresh),
    )


@main_bound
def company_capital_raises(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCapitalRaisesResponse:
    return _build_company_capital_raises_response(ticker, background_tasks, session)


@main_bound
def company_capital_markets(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCapitalRaisesResponse:
    return _build_company_capital_raises_response(ticker, background_tasks, session)


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
            refresh=_trigger_refresh(normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(snapshot)
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
    return _build_company_events_response(ticker, background_tasks, session)


@main_bound
def company_filing_events(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEventsResponse:
    return _build_company_events_response(ticker, background_tasks, session)


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
            refresh=_trigger_refresh(normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(snapshot)
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
    overview = _build_company_activity_overview_response(ticker=ticker, session=session)
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
    overview = _build_company_activity_overview_response(ticker=ticker, session=session)
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
    return _build_company_activity_overview_response(ticker=ticker, session=session)


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
