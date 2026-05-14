from __future__ import annotations

import sys
from typing import Any, Callable

from app.api.handlers import _shared as shared


def _sync_route_handler(handler: Callable[..., Any]) -> Callable[..., Any]:
    return getattr(handler, "__wrapped__", handler)


@shared.app.get("/api/companies/{ticker}/overview", response_model=shared.CompanyOverviewResponse)
def company_overview(
    ticker: str,
    request: shared.Request = None,
    http_response: shared.Response = None,
    financials_view: str | None = shared.Query(default=None, description="embedded financials shape: full|core_segments|core"),
    price_start_date: str | None = shared.Query(default=None, description="Optional price-history lower bound (YYYY-MM-DD)"),
    price_end_date: str | None = shared.Query(default=None, description="Optional price-history upper bound (YYYY-MM-DD)"),
    price_latest_n: int | None = shared.Query(default=None, ge=1, le=20000, description="Optional latest-N price points"),
    price_max_points: int | None = shared.Query(default=None, ge=2, le=5000, description="Optional decimation target points"),
    as_of: str | None = shared.Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: shared.Session = shared.Depends(shared.get_db_session),
) -> shared.CompanyOverviewResponse:
    normalized_ticker = shared._normalize_ticker(ticker)
    requested_as_of = shared._read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    requested_financials_view = shared._read_singleton_query_param_or_400(request, "financials_view", fallback=financials_view)
    parsed_as_of, normalized_financials_view, normalized_as_of = shared._normalize_company_financials_query_controls(
        requested_as_of=requested_as_of,
        view=requested_financials_view,
    )
    resolved_price_start_date, resolved_price_end_date, resolved_price_latest_n, resolved_price_max_points = shared._normalize_price_history_query_controls(
        price_start_date=price_start_date,
        price_end_date=price_end_date,
        price_latest_n=price_latest_n,
        price_max_points=price_max_points,
    )
    price_token = shared._price_history_cache_token(
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
    cached_hot = shared.shared_hot_response_cache.get_sync(hot_key, route="overview") if request is not None and http_response is not None else None
    if cached_hot is not None and cached_hot.is_fresh:
        return shared._hot_cache_json_response(request, http_response, cached_hot)

    snapshot = shared._resolve_company_brief_snapshot(session, normalized_ticker)
    financials = shared._build_company_financials_response(
        session,
        normalized_ticker,
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
        requested_as_of=requested_as_of,
        parsed_as_of=parsed_as_of,
        snapshot=snapshot,
    )
    response = shared.CompanyOverviewResponse(
        company=financials.company or brief.company,
        financials=financials,
        brief=brief,
    )
    shared._store_hot_cached_payload_sync(
        hot_key,
        response,
        tags=shared._build_hot_cache_tags(
            ticker=normalized_ticker,
            datasets=("financials", "prices", "company_research_brief"),
            schema_versions=(shared.HOT_CACHE_SCHEMA_VERSIONS["overview"],),
            as_of=normalized_as_of,
        ),
    )
    return response


@shared.app.get("/api/companies/{ticker}/workspace-bootstrap", response_model=shared.CompanyWorkspaceBootstrapResponse)
def company_workspace_bootstrap(
    ticker: str,
    request: shared.Request = None,
    http_response: shared.Response = None,
    include_overview_brief: bool = shared.Query(default=False),
    include_insiders: bool = shared.Query(default=False),
    include_institutional: bool = shared.Query(default=False),
    include_earnings_summary: bool = shared.Query(default=False),
    sections: str | None = shared.Query(default=None, description="Comma-separated list of sections: company_summary,latest_financials,recent_filings,recent_events,ownership_summary,source_freshness,warnings"),
    compact: bool = shared.Query(default=False, description="Enable compact mode to reduce payload size"),
    financials_view: str | None = shared.Query(default=None, description="embedded financials shape: full|core_segments|core"),
    price_start_date: str | None = shared.Query(default=None, description="Optional price-history lower bound (YYYY-MM-DD)"),
    price_end_date: str | None = shared.Query(default=None, description="Optional price-history upper bound (YYYY-MM-DD)"),
    price_latest_n: int | None = shared.Query(default=None, ge=1, le=20000, description="Optional latest-N price points"),
    price_max_points: int | None = shared.Query(default=None, ge=2, le=5000, description="Optional decimation target points"),
    as_of: str | None = shared.Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: shared.Session = shared.Depends(shared.get_db_session),
) -> shared.CompanyWorkspaceBootstrapResponse:
    normalized_ticker = shared._normalize_ticker(ticker)
    requested_as_of = shared._read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    requested_financials_view = shared._read_singleton_query_param_or_400(request, "financials_view", fallback=financials_view)
    requested_sections_str = shared._read_singleton_query_param_or_400(request, "sections", fallback=sections)
    requested_compact = shared._read_singleton_query_param_or_400(request, "compact", fallback=str(compact).lower())
    
    # Parse sections parameter and determine which sections to load
    requested_sections = _parse_bootstrap_sections(requested_sections_str)
    is_compact_mode = requested_compact in ("true", "1", "yes")
    
    # Legacy behavior: if no sections param, use include_* flags
    if not requested_sections:
        requested_sections = _build_sections_from_legacy_flags(
            include_overview_brief=include_overview_brief,
            include_insiders=include_insiders,
            include_institutional=include_institutional,
            include_earnings_summary=include_earnings_summary,
        )
    
    parsed_as_of, normalized_financials_view, normalized_as_of = shared._normalize_company_financials_query_controls(
        requested_as_of=requested_as_of,
        view=requested_financials_view,
    )
    resolved_price_start_date, resolved_price_end_date, resolved_price_latest_n, resolved_price_max_points = shared._normalize_price_history_query_controls(
        price_start_date=price_start_date,
        price_end_date=price_end_date,
        price_latest_n=price_latest_n,
        price_max_points=price_max_points,
    )
    price_token = shared._price_history_cache_token(
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
        sections=tuple(sorted(requested_sections)),
        compact=is_compact_mode,
    )
    cached_hot = (
        shared.shared_hot_response_cache.get_sync(hot_key, route="workspace_bootstrap")
        if request is not None and http_response is not None
        else None
    )
    if cached_hot is not None and cached_hot.is_fresh:
        cached_payload = shared._decode_hot_cache_payload(cached_hot)
        if not shared._is_company_missing_payload(cached_payload):
            return shared._hot_cache_json_response(request, http_response, cached_hot)

    brief: shared.CompanyResearchBriefResponse | None = None
    errors = shared.CompanyWorkspaceBootstrapErrorsPayload()
    main_module = sys.modules.get("app.main")
    resolve_company_brief_snapshot = getattr(
        main_module,
        "_resolve_company_brief_snapshot",
        shared._resolve_company_brief_snapshot,
    )
    build_company_financials_response = getattr(
        main_module,
        "_build_company_financials_response",
        shared._build_company_financials_response,
    )
    build_company_research_brief_response = getattr(
        main_module,
        "_build_company_research_brief_response",
        _build_company_research_brief_response,
    )

    # Determine which sections to actually load
    should_load_brief = "company_summary" in requested_sections or "recent_filings" in requested_sections or "recent_events" in requested_sections
    should_load_financials = "latest_financials" in requested_sections or (not requested_sections)  # financials always loaded if no sections specified
    should_load_insiders = "ownership_summary" in requested_sections
    should_load_institutional = "ownership_summary" in requested_sections
    should_load_earnings = "recent_events" in requested_sections

    if should_load_brief and not should_load_insiders and not should_load_institutional:
        snapshot = resolve_company_brief_snapshot(session, normalized_ticker)
        if should_load_financials:
            financials = build_company_financials_response(
                session,
                normalized_ticker,
                requested_as_of=requested_as_of,
                parsed_as_of=parsed_as_of,
                snapshot=snapshot,
                view=normalized_financials_view,
                price_start_date=resolved_price_start_date,
                price_end_date=resolved_price_end_date,
                price_latest_n=resolved_price_latest_n,
                price_max_points=resolved_price_max_points,
            )
        else:
            financials = build_company_financials_response(
                session,
                normalized_ticker,
                requested_as_of=requested_as_of,
                parsed_as_of=parsed_as_of,
                snapshot=snapshot,
                view=normalized_financials_view,
            )
        brief = build_company_research_brief_response(
            session,
            normalized_ticker,
            requested_as_of=requested_as_of,
            parsed_as_of=parsed_as_of,
            snapshot=snapshot,
        )
    else:
        if should_load_financials:
            financials = build_company_financials_response(
                session,
                normalized_ticker,
                requested_as_of=requested_as_of,
                parsed_as_of=parsed_as_of,
                view=normalized_financials_view,
                price_start_date=resolved_price_start_date,
                price_end_date=resolved_price_end_date,
                price_latest_n=resolved_price_latest_n,
                price_max_points=resolved_price_max_points,
            )
        else:
            # Return minimal financials
            financials = shared.CompanyFinancialsResponse(
                company=None,
                financials=[],
                price_history=[],
                refresh=shared.RefreshState(triggered=False, reason="none"),
            )

    insider_trades: shared.CompanyInsiderTradesResponse | None = None
    institutional_holdings: shared.CompanyInstitutionalHoldingsResponse | None = None
    earnings_summary: shared.CompanyEarningsSummaryResponse | None = None

    if should_load_insiders:
        try:
            insider_trades = _sync_route_handler(shared.company_insider_trades)(
                ticker=normalized_ticker,
                session=session,
            )
        except Exception as exc:
            errors.insider = str(exc) if str(exc) else "Unable to load insider trades"

    if should_load_institutional:
        try:
            institutional_holdings = _sync_route_handler(shared.company_institutional_holdings)(
                ticker=normalized_ticker,
                session=session,
            )
        except Exception as exc:
            errors.institutional = str(exc) if str(exc) else "Unable to load institutional holdings"

    if should_load_earnings:
        try:
            earnings_summary = _sync_route_handler(shared.company_earnings_summary)(
                ticker=normalized_ticker,
                session=session,
            )
        except Exception as exc:
            errors.earnings_summary = str(exc) if str(exc) else "Unable to load earnings summary"

    # Build source freshness and warnings payloads
    source_freshness = _build_bootstrap_source_freshness(brief, financials)
    warnings = _build_bootstrap_warnings(brief, financials)
    
    # Apply compact mode if requested
    if is_compact_mode and brief is not None:
        brief = _apply_compact_mode_to_brief(brief)

    response = shared.CompanyWorkspaceBootstrapResponse(
        company=financials.company or brief.company if brief is not None else financials.company,
        financials=financials,
        brief=brief,
        earnings_summary=earnings_summary,
        insider_trades=insider_trades,
        institutional_holdings=institutional_holdings,
        errors=errors,
        source_freshness=source_freshness,
        warnings=warnings,
        is_compact=is_compact_mode,
        requested_sections=requested_sections,
    )
    workspace_datasets = []
    if should_load_financials:
        workspace_datasets.extend(["financials", "prices"])
    if should_load_brief:
        workspace_datasets.append("company_research_brief")
    if should_load_insiders:
        workspace_datasets.append("insiders")
    if should_load_institutional:
        workspace_datasets.append("institutional")
    if should_load_earnings:
        workspace_datasets.append("earnings")
    shared._store_hot_cached_payload_sync(
        hot_key,
        response,
        tags=shared._build_hot_cache_tags(
            ticker=normalized_ticker,
            datasets=tuple(workspace_datasets),
            schema_versions=(shared.HOT_CACHE_SCHEMA_VERSIONS["workspace_bootstrap"],),
            as_of=normalized_as_of,
        ),
    )
    return response


@shared.app.get("/api/companies/{ticker}/brief", response_model=shared.CompanyResearchBriefResponse)
def company_brief(
    ticker: str,
    request: shared.Request = None,
    as_of: str | None = shared.Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: shared.Session = shared.Depends(shared.get_db_session),
) -> shared.CompanyResearchBriefResponse:
    normalized_ticker = shared._normalize_ticker(ticker)
    requested_as_of = shared._read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = shared._validated_as_of(requested_as_of)
    return _build_company_research_brief_response(
        session,
        normalized_ticker,
        requested_as_of=requested_as_of,
        parsed_as_of=parsed_as_of,
    )


def _build_company_research_brief_response(
    session: shared.Session,
    normalized_ticker: str,
    *,
    requested_as_of: str | None,
    parsed_as_of: shared.datetime | None,
    snapshot: shared.CompanyCacheSnapshot | None = None,
) -> shared.CompanyResearchBriefResponse:
    resolved_snapshot = snapshot or shared._resolve_company_brief_snapshot(session, normalized_ticker)
    if resolved_snapshot is None:
        refresh = shared._trigger_refresh(normalized_ticker, reason="missing")
        return shared._build_company_brief_bootstrap_for_missing_ticker(
            normalized_ticker,
            refresh=refresh,
            as_of=requested_as_of,
        )

    stored_snapshot, payload = shared._load_company_research_brief_snapshot_record(
        session,
        resolved_snapshot.company.id,
        as_of=parsed_as_of,
    )
    refresh = shared._refresh_for_company_brief(
        resolved_snapshot,
        stored_snapshot=stored_snapshot,
        as_of=parsed_as_of,
    )
    if payload is None:
        if not refresh.triggered:
            refresh = shared._trigger_refresh(resolved_snapshot.company.ticker, reason="missing")
        return shared._build_company_brief_bootstrap_for_snapshot(
            session,
            resolved_snapshot,
            refresh=refresh,
            as_of=requested_as_of,
        )

    return shared._augment_company_brief_response(
        session,
        resolved_snapshot,
        payload,
        refresh=refresh,
        as_of=requested_as_of,
    )


@shared.app.get("/api/companies/{ticker}/peers", response_model=shared.CompanyPeersResponse)
async def company_peers(
    request: shared.Request,
    http_response: shared.Response,
    ticker: str,
    peers: str | None = shared.Query(default=None),
    as_of: str | None = shared.Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
) -> shared.CompanyPeersResponse:
    normalized_ticker = shared._normalize_ticker(ticker)
    selected_tickers = shared._parse_csv_values(peers)
    requested_as_of = shared._read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = shared._validated_as_of(requested_as_of)
    normalized_as_of = shared._normalize_as_of(parsed_as_of) or "latest"
    hot_key = f"peers:{normalized_ticker}:selected={','.join(selected_tickers)}:asof={shared._normalize_as_of(parsed_as_of) or 'latest'}"
    hot_tags = shared._build_hot_cache_tags(
        ticker=normalized_ticker,
        tickers=tuple(selected_tickers),
        datasets=("financials", "prices", "derived_metrics"),
        schema_versions=(shared.HOT_CACHE_SCHEMA_VERSIONS["peers"],),
        as_of=normalized_as_of,
    )
    async with shared._session_scope() as session:
        cached_hot = await shared._get_hot_cached_payload(hot_key)
        if cached_hot is not None:
            if cached_hot.is_fresh:
                return shared._hot_cache_json_response(request, http_response, cached_hot)

            payload_data = shared._decode_hot_cache_payload(cached_hot)
            cached_response = shared.CompanyPeersResponse.model_validate(payload_data)
            if not cached_hot.is_fresh:
                stale_refresh = shared._trigger_refresh(normalized_ticker, reason="stale")
                cached_response = cached_response.model_copy(
                    update={
                        "refresh": stale_refresh,
                        "confidence_flags": sorted(set([*cached_response.confidence_flags, *shared._confidence_flags_from_refresh(stale_refresh)])),
                    }
                )

            not_modified = shared._apply_conditional_headers(
                request,
                http_response,
                cached_response,
                last_modified=cached_response.company.last_checked if cached_response.company else None,
            )
            if not_modified is not None:
                return not_modified  # type: ignore[return-value]
            return cached_response

        def build_peers_payload(sync_session: shared.Session) -> shared.CompanyPeersResponse:
            snapshot = shared._resolve_cached_company_snapshot(sync_session, normalized_ticker)
            if snapshot is None:
                payload = shared.CompanyPeersResponse(
                    company=None,
                    peer_basis="Cached peer universe",
                    available_companies=[],
                    selected_tickers=[],
                    peers=[],
                    notes={},
                    refresh=shared._trigger_refresh(normalized_ticker, reason="missing"),
                    **shared._empty_provenance_contract("company_missing"),
                )
                return shared._apply_requested_as_of(payload, requested_as_of)

            price_last_checked, price_cache_state = shared._visible_price_cache_status(sync_session, snapshot.company.id)
            financials = shared.get_company_financials(sync_session, snapshot.company.id)
            refresh = shared._refresh_for_financial_page(snapshot, price_cache_state, financials)
            payload = shared.build_peer_comparison(sync_session, snapshot.company.ticker, selected_tickers=selected_tickers, as_of=parsed_as_of)
            shared.logging.getLogger(__name__).info(
                "TELEMETRY peer_view ticker=%s selected=%s count=%s",
                snapshot.company.ticker,
                selected_tickers,
                len(payload.get("peers") or []) if payload else 0,
            )
            if payload is None:
                empty_payload = shared.CompanyPeersResponse(
                    company=None,
                    peer_basis="Cached peer universe",
                    available_companies=[],
                    selected_tickers=[],
                    peers=[],
                    notes={},
                    refresh=refresh,
                    **shared._empty_provenance_contract("peer_data_missing"),
                )
                return shared._apply_requested_as_of(empty_payload, requested_as_of)

            response_payload = shared.CompanyPeersResponse(
                company=shared._serialize_company(
                    payload["company"],
                    last_checked=shared._merge_last_checked(payload["company"].last_checked, price_last_checked),
                    last_checked_prices=price_last_checked,
                ),
                peer_basis=payload["peer_basis"],
                available_companies=[shared.PeerOptionPayload(**item) for item in payload["available_companies"]],
                selected_tickers=payload["selected_tickers"],
                peers=[shared.PeerMetricsPayload(**item) for item in payload["peers"]],
                notes=payload["notes"],
                refresh=refresh,
                **shared._peers_provenance_contract(payload, price_last_checked=price_last_checked, refresh=refresh),
            )
            return shared._apply_requested_as_of(response_payload, requested_as_of)

        response_payload = await shared._fill_hot_cached_payload(
            hot_key,
            model_type=shared.CompanyPeersResponse,
            tags=hot_tags,
            fill=lambda: shared._run_with_session_binding(session, build_peers_payload),
        )
        not_modified = shared._apply_conditional_headers(
            request,
            http_response,
            response_payload,
            last_modified=response_payload.company.last_checked if response_payload.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return response_payload


def _company_overview_hot_key(
    normalized_ticker: str,
    *,
    financials_view: str,
    as_of: str,
    price_token: str = "default",
) -> str:
    return f"overview:{normalized_ticker}:view={financials_view}:asof={as_of}:prices={price_token}"


def _parse_bootstrap_sections(sections_str: str | None) -> list[str]:
    """Parse the sections query parameter into a list of section names."""
    if not sections_str:
        return []
    
    # Split by comma and clean up
    sections = [s.strip().lower() for s in sections_str.split(",") if s.strip()]
    
    # Valid sections
    valid_sections = {
        "company_summary",
        "latest_financials",
        "recent_filings",
        "recent_events",
        "ownership_summary",
        "source_freshness",
        "warnings",
    }
    
    # Filter to only valid sections
    return [s for s in sections if s in valid_sections]


def _build_sections_from_legacy_flags(
    include_overview_brief: bool,
    include_insiders: bool,
    include_institutional: bool,
    include_earnings_summary: bool,
) -> list[str]:
    """Build sections list from legacy boolean flags."""
    sections = []
    
    if include_overview_brief:
        sections.extend(["company_summary", "recent_filings", "recent_events"])
    
    if include_insiders or include_institutional:
        sections.append("ownership_summary")
    
    if include_earnings_summary:
        sections.append("recent_events")
    
    return list(dict.fromkeys(sections))  # Remove duplicates while preserving order


def _build_bootstrap_source_freshness(
    brief: shared.CompanyResearchBriefResponse | None,
    financials: shared.CompanyFinancialsResponse,
) -> shared.CompanyBootstrapSourceFreshnessPayload:
    """Build source freshness payload from response data."""
    freshness = shared.CompanyBootstrapSourceFreshnessPayload()
    
    # Check financials freshness
    if financials.refresh and financials.refresh.triggered:
        freshness.financials_stale = True
        freshness.financials_message = f"Refresh triggered: {financials.refresh.reason or 'unknown'}"
    
    # Check brief freshness
    if brief:
        if brief.refresh and brief.refresh.triggered:
            freshness.brief_stale = True
            freshness.brief_message = f"Refresh triggered: {brief.refresh.reason or 'unknown'}"
        
        # Check capital and risk section for ownership and governance staleness
        if brief.capital_and_risk:
            ownership = brief.capital_and_risk.ownership_summary
            if ownership and ownership.refresh and ownership.refresh.triggered:
                freshness.ownership_stale = True
                freshness.ownership_message = f"Refresh triggered: {ownership.refresh.reason or 'unknown'}"
            
            governance = brief.capital_and_risk.governance_summary
            if governance and governance.refresh and governance.refresh.triggered:
                freshness.governance_stale = True
                freshness.governance_message = f"Refresh triggered: {governance.refresh.reason or 'unknown'}"
        
        freshness.last_updated = brief.generated_at
    
    return freshness


def _build_bootstrap_warnings(
    brief: shared.CompanyResearchBriefResponse | None,
    financials: shared.CompanyFinancialsResponse,
) -> list[shared.CompanyBootstrapWarningPayload]:
    """Build warnings payload from response data."""
    warnings: list[shared.CompanyBootstrapWarningPayload] = []
    
    # Check brief build state
    if brief:
        if brief.build_state == "building":
            warnings.append(
                shared.CompanyBootstrapWarningPayload(
                    severity="info",
                    code="brief_building",
                    title="Research brief still building",
                    detail=brief.build_status,
                    affected_sections=["company_summary", "recent_filings", "recent_events"],
                )
            )
        elif brief.build_state == "partial":
            warnings.append(
                shared.CompanyBootstrapWarningPayload(
                    severity="warning",
                    code="brief_partial",
                    title="Research brief incomplete",
                    detail="Some sections may not be fully available",
                    affected_sections=["company_summary", "recent_filings", "recent_events"],
                )
            )
        
        # Check stale summary cards
        if brief.stale_summary_cards:
            warnings.append(
                shared.CompanyBootstrapWarningPayload(
                    severity="warning",
                    code="stale_data_detected",
                    title=f"{len(brief.stale_summary_cards)} stale data card(s)",
                    detail="Some summary data may be outdated",
                    affected_sections=["company_summary"],
                )
            )
    
    # Check financials issues
    if not financials.financials:
        warnings.append(
            shared.CompanyBootstrapWarningPayload(
                severity="warning",
                code="no_financial_statements",
                title="No financial statements available",
                detail="Latest financial data is not available for this ticker",
                affected_sections=["latest_financials"],
            )
        )
    
    return warnings


def _apply_compact_mode_to_brief(
    brief: shared.CompanyResearchBriefResponse,
) -> shared.CompanyResearchBriefResponse:
    """Apply compact mode to research brief response to reduce payload size.
    
    In compact mode, we suppress large raw facts arrays and verbose details
    while keeping key summary data.
    """
    # Create a modified copy
    brief_copy = brief.model_copy(deep=True)
    
    # Clear large detail fields
    brief_copy.stale_summary_cards = []
    
    # Suppress section details while keeping summary data
    if brief_copy.what_changed:
        if brief_copy.what_changed.activity_overview:
            brief_copy.what_changed.activity_overview.facts = []
        if brief_copy.what_changed.changes:
            brief_copy.what_changed.changes.facts = []
    
    if brief_copy.capital_and_risk:
        if brief_copy.capital_and_risk.ownership_summary:
            brief_copy.capital_and_risk.ownership_summary.facts = []
        if brief_copy.capital_and_risk.governance_summary:
            brief_copy.capital_and_risk.governance_summary.facts = []
    
    if brief_copy.monitor:
        if brief_copy.monitor.activity_overview:
            brief_copy.monitor.activity_overview.facts = []
    
    return brief_copy


def _company_workspace_bootstrap_hot_key(
    normalized_ticker: str,
    *,
    financials_view: str,
    as_of: str,
    include_overview_brief: bool,
    include_insiders: bool,
    include_institutional: bool,
    include_earnings_summary: bool,
    price_token: str = "default",
    sections: tuple[str, ...] = (),
    compact: bool = False,
) -> str:
    sections_str = ",".join(sections) if sections else "all"
    return (
        f"workspace_bootstrap:{normalized_ticker}:view={financials_view}:asof={as_of}"
        f":overview={1 if include_overview_brief else 0}"
        f":insiders={1 if include_insiders else 0}"
        f":institutional={1 if include_institutional else 0}"
        f":earnings={1 if include_earnings_summary else 0}"
        f":prices={price_token}"
        f":sections={sections_str}"
        f":compact={1 if compact else 0}"
    )


_company_overview_sync = company_overview
_company_workspace_bootstrap_sync = company_workspace_bootstrap
_company_brief_sync = company_brief

company_overview = shared._wrap_db_handler(_company_overview_sync)
company_workspace_bootstrap = shared._wrap_db_handler(_company_workspace_bootstrap_sync)
company_brief = shared._wrap_db_handler(_company_brief_sync)


__all__ = [
    "company_brief",
    "company_overview",
    "company_peers",
    "company_workspace_bootstrap",
    "_build_company_research_brief_response",
    "_company_overview_hot_key",
    "_company_workspace_bootstrap_hot_key",
]
