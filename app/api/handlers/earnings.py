from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
def company_earnings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEarningsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEarningsResponse(
            company=None,
            earnings_releases=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
        )

    earnings_last_checked, earnings_cache_state = get_company_earnings_cache_status(session, snapshot.company)
    earnings_releases = get_company_earnings_releases(session, snapshot.company.id)
    refresh = _refresh_for_earnings(snapshot, earnings_cache_state)
    payload = [_serialize_earnings_release(release) for release in earnings_releases]
    return CompanyEarningsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, earnings_last_checked),
            last_checked_earnings=earnings_last_checked,
        ),
        earnings_releases=payload,
        refresh=refresh,
        diagnostics=_diagnostics_for_earnings_releases(payload, refresh),
    )


@main_bound
def company_earnings_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEarningsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEarningsSummaryResponse(
            company=None,
            summary=_build_earnings_summary([]),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
        )

    earnings_last_checked, earnings_cache_state = get_company_earnings_cache_status(session, snapshot.company)
    earnings_releases = get_company_earnings_releases(session, snapshot.company.id)
    refresh = _refresh_for_earnings(snapshot, earnings_cache_state)
    payload = [_serialize_earnings_release(release) for release in earnings_releases]
    return CompanyEarningsSummaryResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, earnings_last_checked),
            last_checked_earnings=earnings_last_checked,
        ),
        summary=_build_earnings_summary(payload),
        refresh=refresh,
        diagnostics=_diagnostics_for_earnings_releases(payload, refresh),
    )


@main_bound
def company_earnings_workspace(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEarningsWorkspaceResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEarningsWorkspaceResponse(
            company=None,
            earnings_releases=[],
            summary=_build_earnings_summary([]),
            model_points=[],
            backtests=EarningsBacktestPayload(
                window_sessions=3,
                quality_directional_consistency=None,
                quality_total_windows=0,
                quality_consistent_windows=0,
                eps_directional_consistency=None,
                eps_total_windows=0,
                eps_consistent_windows=0,
                windows=[],
            ),
            peer_context=EarningsPeerContextPayload(
                peer_group_basis="market_sector",
                peer_group_size=0,
                quality_percentile=None,
                eps_drift_percentile=None,
                sector_group_size=0,
                sector_quality_percentile=None,
                sector_eps_drift_percentile=None,
            ),
            alerts=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
        )

    earnings_last_checked, earnings_cache_state = get_company_earnings_cache_status(session, snapshot.company)
    model_last_checked, model_cache_state = get_company_earnings_model_cache_status(session, snapshot.company.id)
    earnings_releases = get_company_earnings_releases(session, snapshot.company.id)
    model_rows = get_company_earnings_model_points(session, snapshot.company.id)
    refresh = _refresh_for_earnings_workspace(snapshot, earnings_cache_state, model_cache_state)

    release_payload = [_serialize_earnings_release(release) for release in earnings_releases]
    model_payload = [_serialize_earnings_model_point(point) for point in model_rows]
    backtest_payload = EarningsBacktestPayload.model_validate(
        build_earnings_directional_backtest(
            model_rows,
            earnings_releases,
            _visible_price_history(session, snapshot.company.id),
        )
    )
    latest_point = model_rows[-1] if model_rows else None
    peer_payload = EarningsPeerContextPayload.model_validate(
        build_earnings_peer_percentiles(session, snapshot.company, latest_point)
    )
    alert_profile = build_sector_alert_profile(session, snapshot.company)
    alerts_payload = [EarningsAlertPayload.model_validate(item) for item in build_earnings_alerts(model_rows, profile=alert_profile)]

    return CompanyEarningsWorkspaceResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, _merge_last_checked(earnings_last_checked, model_last_checked)),
            last_checked_earnings=_merge_last_checked(earnings_last_checked, model_last_checked),
        ),
        earnings_releases=release_payload,
        summary=_build_earnings_summary(release_payload),
        model_points=model_payload,
        backtests=backtest_payload,
        peer_context=peer_payload,
        alerts=alerts_payload,
        refresh=refresh,
        diagnostics=_diagnostics_for_earnings_releases(release_payload, refresh, model_payload),
    )


__all__ = ["company_earnings", "company_earnings_summary", "company_earnings_workspace"]
