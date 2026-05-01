from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
def watchlist_summary(
    payload: WatchlistSummaryRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> WatchlistSummaryResponse:
    normalized_tickers = _normalize_watchlist_tickers(payload.tickers)
    if len(normalized_tickers) > 50:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A maximum of 50 tickers is allowed")

    try:
        snapshots_by_ticker = get_company_snapshots_by_ticker(session, normalized_tickers)
        coverage_counts = get_company_coverage_counts(
            session,
            [snapshot.company.id for snapshot in snapshots_by_ticker.values()],
        )
    except Exception:
        logging.getLogger(__name__).exception("Unable to load watchlist summary snapshots")
        return WatchlistSummaryResponse(
            tickers=normalized_tickers,
            companies=[_build_missing_watchlist_summary_item(background_tasks, ticker) for ticker in normalized_tickers],
        )

    preload: dict[str, Any] | None = None
    try:
        preload = _load_watchlist_summary_preload(session, snapshots_by_ticker)
    except Exception:
        logging.getLogger(__name__).exception("Unable to batch watchlist summary preload data")

    companies: list[WatchlistSummaryItemPayload] = []
    preload_token = _watchlist_summary_preload_ctx.set(preload)
    try:
        for ticker in normalized_tickers:
            snapshot = snapshots_by_ticker.get(ticker)
            if snapshot is None:
                companies.append(_build_missing_watchlist_summary_item(background_tasks, ticker))
                continue
            try:
                companies.append(
                    _build_watchlist_summary_item(
                        session,
                        background_tasks,
                        ticker,
                        snapshot=snapshot,
                        coverage_counts=coverage_counts.get(snapshot.company.id),
                    )
                )
            except Exception:
                logging.getLogger(__name__).exception("Unable to build watchlist summary item for '%s'", ticker)
                companies.append(_build_missing_watchlist_summary_item(background_tasks, ticker))
    finally:
        _watchlist_summary_preload_ctx.reset(preload_token)
    logging.getLogger(__name__).info(
        "TELEMETRY watchlist_summary tickers=%s companies=%s",
        len(normalized_tickers),
        len(companies),
    )
    return WatchlistSummaryResponse(tickers=normalized_tickers, companies=companies)


@main_bound
def watchlist_calendar(
    tickers: list[str] = Query(default_factory=list),
    session: Session = Depends(get_db_session),
) -> WatchlistCalendarResponse:
    normalized_tickers = _normalize_watchlist_tickers(tickers)
    if len(normalized_tickers) > 50:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A maximum of 50 tickers is allowed")

    window_start = _watchlist_calendar_today()
    window_end = window_start + timedelta(days=WATCHLIST_CALENDAR_WINDOW_DAYS)
    snapshots_by_ticker = get_company_snapshots_by_ticker(session, normalized_tickers)

    events: list[WatchlistCalendarEventPayload] = []
    for ticker in normalized_tickers:
        snapshot = snapshots_by_ticker.get(ticker)
        if snapshot is None:
            continue
        try:
            events.extend(
                _build_watchlist_calendar_company_events(
                    session,
                    snapshot,
                    window_start=window_start,
                    window_end=window_end,
                )
            )
        except Exception:
            logging.getLogger(__name__).exception("Unable to build watchlist calendar events for '%s'", ticker)

    events.extend(_build_watchlist_13f_deadline_events(window_start=window_start, window_end=window_end))
    events.sort(key=lambda item: (item.date, item.ticker or "", item.title, item.id))
    logging.getLogger(__name__).info(
        "TELEMETRY watchlist_calendar tickers=%s events=%s",
        len(normalized_tickers),
        len(events),
    )
    return WatchlistCalendarResponse(
        tickers=normalized_tickers,
        window_start=window_start,
        window_end=window_end,
        events=events,
    )


__all__ = ["watchlist_calendar", "watchlist_summary"]
