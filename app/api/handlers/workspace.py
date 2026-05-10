from __future__ import annotations

from datetime import datetime, timezone

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403
from app.services.watchlist_alerts import get_active_alerts, detect_and_create_alerts
from app.source_registry import SourceUsage, build_provenance_entries, build_source_mix


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
            companies=[_build_missing_watchlist_summary_item(ticker) for ticker in normalized_tickers],
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
                companies.append(_build_missing_watchlist_summary_item(ticker))
                continue
            try:
                companies.append(
                    _build_watchlist_summary_item(
                        session,
                        ticker,
                        snapshot=snapshot,
                        coverage_counts=coverage_counts.get(snapshot.company.id),
                    )
                )
            except Exception:
                logging.getLogger(__name__).exception("Unable to build watchlist summary item for '%s'", ticker)
                companies.append(_build_missing_watchlist_summary_item(ticker))
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


@main_bound
def watchlist_alerts(
    payload: WatchlistSummaryRequest,
    alert_types: list[str] | None = Query(None),
    session: Session = Depends(get_db_session),
) -> WatchlistAlertsResponse:
    """Get active watchlist alerts for the specified tickers."""
    normalized_tickers = _normalize_watchlist_tickers(payload.tickers)
    if len(normalized_tickers) > 50:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A maximum of 50 tickers is allowed")

    # Fetch companies by ticker
    companies_by_ticker = {}
    for ticker in normalized_tickers:
        company = session.query(Company).filter(Company.ticker == ticker).first()
        if company:
            companies_by_ticker[ticker] = company

    # Generate new alerts for each company
    all_alerts: list[WatchlistAlertPayload] = []
    for ticker, company in companies_by_ticker.items():
        try:
            # Detect and create new alerts (will be deduped by the service)
            detect_and_create_alerts(session, company.id)
        except Exception:
            logging.getLogger(__name__).exception("Unable to detect alerts for company_id=%s ticker=%s", company.id, ticker)

        # Get active alerts for this company
        try:
            db_alerts = get_active_alerts(session, company.id, alert_types=alert_types)
            for alert in db_alerts:
                title, detail = _build_alert_title_detail(alert.alert_type, alert.source_filing_form)
                all_alerts.append(
                    WatchlistAlertPayload(
                        id=alert.id,
                        ticker=ticker,
                        alert_type=alert.alert_type,
                        title=title,
                        detail=detail,
                        source_filing_accession=alert.source_filing_accession,
                        source_filing_form=alert.source_filing_form,
                        created_at=alert.created_at,
                        dismissed_at=alert.dismissed_at,
                    )
                )
        except Exception:
            logging.getLogger(__name__).exception("Unable to load alerts for company_id=%s ticker=%s", company.id, ticker)

    # Sort by created_at descending (most recent first)
    all_alerts.sort(key=lambda a: a.created_at, reverse=True)

    # Count unread (not dismissed)
    unread_count = sum(1 for alert in all_alerts if alert.dismissed_at is None)

    logging.getLogger(__name__).info(
        "TELEMETRY watchlist_alerts tickers=%s alerts=%s unread=%s",
        len(normalized_tickers),
        len(all_alerts),
        unread_count,
    )

    return WatchlistAlertsResponse(
        tickers=normalized_tickers,
        alerts=all_alerts,
        total_count=len(all_alerts),
        unread_count=unread_count,
        **_build_watchlist_alerts_provenance(datetime.now(timezone.utc)),
    )


def _build_alert_title_detail(alert_type: str, form: str | None) -> tuple[str, str]:
    """Build human-readable title and detail for an alert."""
    if alert_type == "10-K":
        return "New annual report (10-K) filed", f"Company filed Form 10-K"
    elif alert_type == "10-Q":
        return "New quarterly report (10-Q) filed", f"Company filed Form 10-Q"
    elif alert_type == "8-K":
        return "Current report (8-K) filed", f"Company filed Form 8-K for current event"
    elif alert_type == "proxy":
        return "New proxy statement filed", f"Company filed proxy statement (PROXY DEF 14A or similar)"
    elif alert_type == "form-4":
        return "Insider transaction (Form 4) filed", f"Insider filed Form 4 transaction"
    elif alert_type == "amendment":
        return f"Amended filing (Form {form or 'N/A'}/A)", f"Company filed an amendment to a previous filing"
    elif alert_type == "late-filing":
        return f"Late filing notice (NT {form or 'N/A'})", f"Company filed late notice (NT 10-K, NT 10-Q, etc.)"
    elif alert_type == "stale-data":
        return "Filing data is stale", "SEC filing data hasn't been refreshed in over 30 days"
    else:
        return "New watchlist alert", f"Alert type: {alert_type}"


def _build_watchlist_alerts_provenance(generated_at: datetime) -> dict[str, object]:
    provenance = build_provenance_entries(
        [
            SourceUsage("sec_edgar", role="primary", as_of=generated_at.date(), last_refreshed_at=generated_at),
            SourceUsage("sec_companyfacts", role="supplemental", as_of=generated_at.date(), last_refreshed_at=generated_at),
            SourceUsage("ft_watchlist_alerts", role="derived", as_of=generated_at.date(), last_refreshed_at=generated_at),
        ]
    )
    return {
        "provenance": provenance,
        "as_of": generated_at.date().isoformat(),
        "last_refreshed_at": generated_at,
        "source_mix": build_source_mix(provenance),
        "confidence_flags": [],
    }


__all__ = ["watchlist_alerts", "watchlist_calendar", "watchlist_summary"]
