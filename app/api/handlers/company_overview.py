from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
def company_overview(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    http_response: Response = None,
    financials_view: str | None = Query(default=None, description="embedded financials shape: full|core_segments|core"),
    price_start_date: str | None = Query(default=None, description="Optional price-history lower bound (YYYY-MM-DD)"),
    price_end_date: str | None = Query(default=None, description="Optional price-history upper bound (YYYY-MM-DD)"),
    price_latest_n: int | None = Query(default=None, ge=1, le=20000, description="Optional latest-N price points"),
    price_max_points: int | None = Query(default=None, ge=2, le=5000, description="Optional decimation target points"),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyOverviewResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    requested_financials_view = _read_singleton_query_param_or_400(request, "financials_view", fallback=financials_view)
    parsed_as_of, normalized_financials_view, normalized_as_of = _normalize_company_financials_query_controls(
        requested_as_of=requested_as_of,
        view=requested_financials_view,
    )
    resolved_price_start_date, resolved_price_end_date, resolved_price_latest_n, resolved_price_max_points = _normalize_price_history_query_controls(
        price_start_date=price_start_date,
        price_end_date=price_end_date,
        price_latest_n=price_latest_n,
        price_max_points=price_max_points,
    )
    price_token = _price_history_cache_token(
        start_date=resolved_price_start_date,
        end_date=resolved_price_end_date,
        latest_n=resolved_price_latest_n,
        max_points=resolved_price_max_points,
    )
    hot_key = _company_overview_hot_key(
        normalized_ticker,
        financials_view=normalized_financials_view,
        as_of=normalized_as_of,
        price_token=price_token,
    )
    cached_hot = shared_hot_response_cache.get_sync(hot_key, route="overview") if request is not None and http_response is not None else None
    if (
        cached_hot is not None
        and cached_hot.is_fresh
        and not _is_company_missing_payload(_decode_hot_cache_payload(cached_hot))
    ):
        return _hot_cache_json_response(request, http_response, cached_hot)

    snapshot = _resolve_company_brief_snapshot(session, normalized_ticker)
    financials = _build_company_financials_response(
        session,
        normalized_ticker,
        background_tasks,
        requested_as_of=requested_as_of,
        parsed_as_of=parsed_as_of,
        snapshot=snapshot,
        view=normalized_financials_view,
        price_start_date=resolved_price_start_date,
        price_end_date=resolved_price_end_date,
        price_latest_n=resolved_price_latest_n,
        price_max_points=resolved_price_max_points,
    )
    brief = _build_company_research_brief_response(
        session,
        normalized_ticker,
        background_tasks,
        requested_as_of=requested_as_of,
        parsed_as_of=parsed_as_of,
        snapshot=snapshot,
    )
    response = CompanyOverviewResponse(
        company=financials.company or brief.company,
        financials=financials,
        brief=brief,
    )
    _store_hot_cached_payload_sync(
        hot_key,
        response,
        tags=_build_hot_cache_tags(
            ticker=normalized_ticker,
            datasets=("financials", "prices", "company_research_brief"),
            schema_versions=(HOT_CACHE_SCHEMA_VERSIONS["overview"],),
            as_of=normalized_as_of,
        ),
    )
    return response


@main_bound
def company_workspace_bootstrap(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    http_response: Response = None,
    include_overview_brief: bool = Query(default=False),
    include_insiders: bool = Query(default=False),
    include_institutional: bool = Query(default=False),
    include_earnings_summary: bool = Query(default=False),
    financials_view: str | None = Query(default=None, description="embedded financials shape: full|core_segments|core"),
    price_start_date: str | None = Query(default=None, description="Optional price-history lower bound (YYYY-MM-DD)"),
    price_end_date: str | None = Query(default=None, description="Optional price-history upper bound (YYYY-MM-DD)"),
    price_latest_n: int | None = Query(default=None, ge=1, le=20000, description="Optional latest-N price points"),
    price_max_points: int | None = Query(default=None, ge=2, le=5000, description="Optional decimation target points"),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyWorkspaceBootstrapResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    requested_financials_view = _read_singleton_query_param_or_400(request, "financials_view", fallback=financials_view)
    parsed_as_of, normalized_financials_view, normalized_as_of = _normalize_company_financials_query_controls(
        requested_as_of=requested_as_of,
        view=requested_financials_view,
    )
    resolved_price_start_date, resolved_price_end_date, resolved_price_latest_n, resolved_price_max_points = _normalize_price_history_query_controls(
        price_start_date=price_start_date,
        price_end_date=price_end_date,
        price_latest_n=price_latest_n,
        price_max_points=price_max_points,
    )
    price_token = _price_history_cache_token(
        start_date=resolved_price_start_date,
        end_date=resolved_price_end_date,
        latest_n=resolved_price_latest_n,
        max_points=resolved_price_max_points,
    )
    hot_key = _company_workspace_bootstrap_hot_key(
        normalized_ticker,
        financials_view=normalized_financials_view,
        as_of=normalized_as_of,
        include_overview_brief=include_overview_brief,
        include_insiders=include_insiders,
        include_institutional=include_institutional,
        include_earnings_summary=include_earnings_summary,
        price_token=price_token,
    )
    cached_hot = (
        shared_hot_response_cache.get_sync(hot_key, route="workspace_bootstrap")
        if request is not None and http_response is not None
        else None
    )
    if (
        cached_hot is not None
        and cached_hot.is_fresh
        and not _is_company_missing_payload(_decode_hot_cache_payload(cached_hot))
    ):
        return _hot_cache_json_response(request, http_response, cached_hot)

    brief: CompanyResearchBriefResponse | None = None
    errors = CompanyWorkspaceBootstrapErrorsPayload()

    if include_overview_brief and not include_insiders and not include_institutional:
        try:
            main_module = __import__("sys").modules.get("app.main")
            if main_module is None:
                raise RuntimeError("app.main must be loaded before invoking company overview handlers")
            overview = main_module.company_overview(
                ticker=normalized_ticker,
                background_tasks=background_tasks,
                request=request,
                financials_view=normalized_financials_view,
                price_start_date=resolved_price_start_date.isoformat() if resolved_price_start_date is not None else None,
                price_end_date=resolved_price_end_date.isoformat() if resolved_price_end_date is not None else None,
                price_latest_n=resolved_price_latest_n,
                price_max_points=resolved_price_max_points,
                as_of=requested_as_of,
                session=session,
            )
            financials = overview.financials
            brief = overview.brief
        except Exception:
            financials = _build_company_financials_response(
                session,
                normalized_ticker,
                background_tasks,
                requested_as_of=requested_as_of,
                parsed_as_of=parsed_as_of,
                view=normalized_financials_view,
                price_start_date=resolved_price_start_date,
                price_end_date=resolved_price_end_date,
                price_latest_n=resolved_price_latest_n,
                price_max_points=resolved_price_max_points,
            )
    else:
        financials = _build_company_financials_response(
            session,
            normalized_ticker,
            background_tasks,
            requested_as_of=requested_as_of,
            parsed_as_of=parsed_as_of,
            view=normalized_financials_view,
            price_start_date=resolved_price_start_date,
            price_end_date=resolved_price_end_date,
            price_latest_n=resolved_price_latest_n,
            price_max_points=resolved_price_max_points,
        )

    insider_trades: CompanyInsiderTradesResponse | None = None
    institutional_holdings: CompanyInstitutionalHoldingsResponse | None = None
    earnings_summary: CompanyEarningsSummaryResponse | None = None

    if include_insiders:
        try:
            insider_trades = company_insider_trades(
                ticker=normalized_ticker,
                background_tasks=background_tasks,
                session=session,
            )
        except Exception as exc:
            errors.insider = str(exc) if str(exc) else "Unable to load insider trades"

    if include_institutional:
        try:
            institutional_holdings = company_institutional_holdings(
                ticker=normalized_ticker,
                background_tasks=background_tasks,
                session=session,
            )
        except Exception as exc:
            errors.institutional = str(exc) if str(exc) else "Unable to load institutional holdings"

    if include_earnings_summary:
        try:
            earnings_summary = company_earnings_summary(
                ticker=normalized_ticker,
                background_tasks=background_tasks,
                session=session,
            )
        except Exception as exc:
            errors.earnings_summary = str(exc) if str(exc) else "Unable to load earnings summary"

    response = CompanyWorkspaceBootstrapResponse(
        company=financials.company or brief.company if brief is not None else financials.company,
        financials=financials,
        brief=brief,
        earnings_summary=earnings_summary,
        insider_trades=insider_trades,
        institutional_holdings=institutional_holdings,
        errors=errors,
    )
    workspace_datasets = ["financials", "prices"]
    if include_overview_brief:
        workspace_datasets.append("company_research_brief")
    if include_insiders:
        workspace_datasets.append("insiders")
    if include_institutional:
        workspace_datasets.append("institutional")
    if include_earnings_summary:
        workspace_datasets.append("earnings")
    _store_hot_cached_payload_sync(
        hot_key,
        response,
        tags=_build_hot_cache_tags(
            ticker=normalized_ticker,
            datasets=tuple(workspace_datasets),
            schema_versions=(HOT_CACHE_SCHEMA_VERSIONS["workspace_bootstrap"],),
            as_of=normalized_as_of,
        ),
    )
    return response


@main_bound
def company_brief(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyResearchBriefResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    return _build_company_research_brief_response(
        session,
        normalized_ticker,
        background_tasks,
        requested_as_of=requested_as_of,
        parsed_as_of=parsed_as_of,
    )


@main_bound
async def company_peers(
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
    peers: str | None = Query(default=None),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
) -> CompanyPeersResponse:
    normalized_ticker = _normalize_ticker(ticker)
    selected_tickers = _parse_csv_values(peers)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    normalized_as_of = _normalize_as_of(parsed_as_of) or "latest"
    hot_key = f"peers:{normalized_ticker}:selected={','.join(selected_tickers)}:asof={_normalize_as_of(parsed_as_of) or 'latest'}"
    hot_tags = _build_hot_cache_tags(
        ticker=normalized_ticker,
        tickers=tuple(selected_tickers),
        datasets=("financials", "prices", "derived_metrics"),
        schema_versions=(HOT_CACHE_SCHEMA_VERSIONS["peers"],),
        as_of=normalized_as_of,
    )
    async with _session_scope() as session:
        cached_hot = await _get_hot_cached_payload(hot_key)
        if cached_hot is not None:
            if cached_hot.is_fresh:
                return _hot_cache_json_response(request, http_response, cached_hot)

            payload_data = _decode_hot_cache_payload(cached_hot)
            cached_response = CompanyPeersResponse.model_validate(payload_data)
            if not cached_hot.is_fresh:
                stale_refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="stale")
                cached_response = cached_response.model_copy(
                    update={
                        "refresh": stale_refresh,
                        "confidence_flags": sorted(set([*cached_response.confidence_flags, *_confidence_flags_from_refresh(stale_refresh)])),
                    }
                )

            not_modified = _apply_conditional_headers(
                request,
                http_response,
                cached_response,
                last_modified=cached_response.company.last_checked if cached_response.company else None,
            )
            if not_modified is not None:
                return not_modified  # type: ignore[return-value]
            return cached_response

        def build_peers_payload(sync_session: Session) -> CompanyPeersResponse:
            snapshot = _resolve_cached_company_snapshot(sync_session, normalized_ticker)
            if snapshot is None:
                payload = CompanyPeersResponse(
                    company=None,
                    peer_basis="Cached peer universe",
                    available_companies=[],
                    selected_tickers=[],
                    peers=[],
                    notes={},
                    refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
                    **_empty_provenance_contract("company_missing"),
                )
                return _apply_requested_as_of(payload, requested_as_of)

            price_last_checked, price_cache_state = _visible_price_cache_status(sync_session, snapshot.company.id)
            financials = get_company_financials(sync_session, snapshot.company.id)
            refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)
            payload = build_peer_comparison(sync_session, snapshot.company.ticker, selected_tickers=selected_tickers, as_of=parsed_as_of)
            logging.getLogger(__name__).info(
                "TELEMETRY peer_view ticker=%s selected=%s count=%s",
                snapshot.company.ticker,
                selected_tickers,
                len(payload.get("peers") or []) if payload else 0,
            )
            if payload is None:
                empty_payload = CompanyPeersResponse(
                    company=None,
                    peer_basis="Cached peer universe",
                    available_companies=[],
                    selected_tickers=[],
                    peers=[],
                    notes={},
                    refresh=refresh,
                    **_empty_provenance_contract("peer_data_missing"),
                )
                return _apply_requested_as_of(empty_payload, requested_as_of)

            response_payload = CompanyPeersResponse(
                company=_serialize_company(
                    payload["company"],
                    last_checked=_merge_last_checked(payload["company"].last_checked, price_last_checked),
                    last_checked_prices=price_last_checked,
                ),
                peer_basis=payload["peer_basis"],
                available_companies=[PeerOptionPayload(**item) for item in payload["available_companies"]],
                selected_tickers=payload["selected_tickers"],
                peers=[PeerMetricsPayload(**item) for item in payload["peers"]],
                notes=payload["notes"],
                refresh=refresh,
                **_peers_provenance_contract(payload, price_last_checked=price_last_checked, refresh=refresh),
            )
            return _apply_requested_as_of(response_payload, requested_as_of)

        response_payload = await _fill_hot_cached_payload(
            hot_key,
            model_type=CompanyPeersResponse,
            tags=hot_tags,
            fill=lambda: _run_with_session_binding(session, build_peers_payload),
        )
        not_modified = _apply_conditional_headers(
            request,
            http_response,
            response_payload,
            last_modified=response_payload.company.last_checked if response_payload.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return response_payload


__all__ = [
    "company_brief",
    "company_overview",
    "company_peers",
    "company_workspace_bootstrap",
]
