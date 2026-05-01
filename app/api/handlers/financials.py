from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
def company_compare(
    tickers: str = Query(..., description="Comma-separated tickers to compare"),
    background_tasks: BackgroundTasks = None,
    request: Request = None,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyCompareResponse:
    tickers = _read_singleton_query_param_or_400(request, "tickers", fallback=tickers) or ""
    normalized_tickers = _normalize_compare_tickers(tickers)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshots_by_ticker = get_company_snapshots_by_ticker(session, normalized_tickers)
    companies = [
        _build_company_compare_item(
            session=session,
            ticker=ticker,
            requested_as_of=requested_as_of,
            parsed_as_of=parsed_as_of,
            snapshot=snapshots_by_ticker.get(ticker),
        )
        for ticker in normalized_tickers
    ]
    return CompanyCompareResponse(tickers=normalized_tickers, companies=companies)


@main_bound
async def company_financials(
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
    view: str | None = Query(default=None, description="response shape: full|core_segments|core"),
    price_start_date: str | None = Query(default=None, description="Optional price-history lower bound (YYYY-MM-DD)"),
    price_end_date: str | None = Query(default=None, description="Optional price-history upper bound (YYYY-MM-DD)"),
    price_latest_n: int | None = Query(default=None, ge=1, le=20000, description="Optional latest-N price points"),
    price_max_points: int | None = Query(default=None, ge=2, le=5000, description="Optional decimation target points"),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
) -> CompanyFinancialsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    requested_view = _read_singleton_query_param_or_400(request, "view", fallback=view)
    parsed_as_of, normalized_view, normalized_as_of = _normalize_company_financials_query_controls(
        requested_as_of=requested_as_of,
        view=requested_view,
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
    hot_key = f"financials:{normalized_ticker}:view={normalized_view}:asof={normalized_as_of}:prices={price_token}"
    legacy_hot_key = f"financials:{normalized_ticker}:asof={normalized_as_of}" if normalized_view == "full" else None
    hot_tags = _build_hot_cache_tags(
        ticker=normalized_ticker,
        datasets=("financials", "prices"),
        schema_versions=(HOT_CACHE_SCHEMA_VERSIONS["financials"],),
        as_of=normalized_as_of,
    )
    async with _session_scope() as session:
        cached_hot = await _get_hot_cached_payload(hot_key)
        if cached_hot is None and legacy_hot_key is not None:
            cached_hot = await _get_hot_cached_payload(legacy_hot_key)
        if cached_hot is not None:
            if cached_hot.is_fresh:
                return _hot_cache_json_response(request, http_response, cached_hot)

            payload_data = _decode_hot_cache_payload(cached_hot)
            cached_response = CompanyFinancialsResponse.model_validate(payload_data)
            if not cached_hot.is_fresh:
                stale_refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="stale")
                cached_response = cached_response.model_copy(
                    update={
                        "refresh": stale_refresh,
                        "diagnostics": _with_stale_flags(cached_response.diagnostics, _stale_flags_from_refresh(stale_refresh)),
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

        def build_financials_payload(sync_session: Session) -> CompanyFinancialsResponse:
            return _build_company_financials_response(
                sync_session,
                normalized_ticker,
                requested_as_of=requested_as_of,
                parsed_as_of=parsed_as_of,
                view=normalized_view,
                price_start_date=resolved_price_start_date,
                price_end_date=resolved_price_end_date,
                price_latest_n=resolved_price_latest_n,
                price_max_points=resolved_price_max_points,
            )

        payload = await _fill_hot_cached_payload(
            hot_key,
            model_type=CompanyFinancialsResponse,
            tags=hot_tags,
            fill=lambda: _run_with_session_binding(session, build_financials_payload),
        )
        not_modified = _apply_conditional_headers(
            request,
            http_response,
            payload,
            last_modified=payload.company.last_checked if payload.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return payload


@main_bound
def company_segment_history(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    years: int = Query(default=5, ge=1, le=20),
    kind: Literal["business", "geographic"] = Query(default="business"),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanySegmentHistoryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)

    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanySegmentHistoryResponse(
            company=None,
            kind=kind,
            years=years,
            periods=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(
                stale_flags=["company_missing"],
                missing_field_flags=["segment_history_empty"],
            ),
            **_empty_provenance_contract("company_missing"),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    financials = _visible_financials_for_company(session, snapshot.company)
    if parsed_as_of is not None:
        financials = select_point_in_time_financials(financials, parsed_as_of)

    history_result = build_segment_history(financials, kind=kind, years=years)
    refresh = _refresh_for_segment_history(snapshot, financials)
    periods = [_serialize_segment_history_period(period) for period in history_result.periods]
    diagnostics = _diagnostics_for_segment_history_response(periods, requested_years=years, refresh=refresh)
    last_refreshed_at = _merge_last_checked(*(statement.last_checked for statement in history_result.provenance_statements))
    latest_period_end = periods[0].period_end if periods else None
    payload = CompanySegmentHistoryResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, last_refreshed_at),
            regulated_entity=_regulated_entity_payload(snapshot.company, financials),
        ),
        kind=kind,
        years=years,
        periods=periods,
        refresh=refresh,
        diagnostics=diagnostics,
        **_segment_history_provenance_contract(
            history_result.provenance_statements,
            latest_period_end=latest_period_end,
            last_refreshed_at=last_refreshed_at,
            periods=periods,
            diagnostics=diagnostics,
            refresh=refresh,
        ),
    )
    return _apply_requested_as_of(payload, requested_as_of)


@main_bound
async def company_capital_structure(
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    max_periods: int = Query(default=8, ge=1, le=40),
) -> CompanyCapitalStructureResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    normalized_as_of = _normalize_as_of(parsed_as_of) or "latest"
    hot_key = f"capital_structure:{normalized_ticker}:periods={max_periods}:asof={_normalize_as_of(parsed_as_of) or 'latest'}"
    hot_tags = _build_hot_cache_tags(
        ticker=normalized_ticker,
        datasets=("capital_structure", "financials"),
        schema_versions=(HOT_CACHE_SCHEMA_VERSIONS["capital_structure"],),
        as_of=normalized_as_of,
    )
    async with _session_scope() as session:
        cached_hot = await _get_hot_cached_payload(hot_key)
        if cached_hot is not None:
            if cached_hot.is_fresh:
                return _hot_cache_json_response(request, http_response, cached_hot)

            payload_data = _decode_hot_cache_payload(cached_hot)
            cached_response = CompanyCapitalStructureResponse.model_validate(payload_data)
            if not cached_hot.is_fresh:
                stale_refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="stale")
                cached_response = cached_response.model_copy(
                    update={
                        "refresh": stale_refresh,
                        "diagnostics": _with_stale_flags(cached_response.diagnostics, _stale_flags_from_refresh(stale_refresh)),
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

        def build_capital_structure_payload(sync_session: Session) -> CompanyCapitalStructureResponse:
            snapshot = _resolve_cached_company_snapshot(sync_session, normalized_ticker)
            if snapshot is None:
                payload = CompanyCapitalStructureResponse(
                    company=None,
                    latest=None,
                    history=[],
                    last_capital_structure_check=None,
                    refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
                    diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing", "capital_structure_missing"]),
                    **_empty_provenance_contract("company_missing", "capital_structure_missing"),
                )
                return _apply_requested_as_of(payload, requested_as_of)

            history = get_company_capital_structure_snapshots(sync_session, snapshot.company.id, limit=max(48, max_periods * 6))
            last_capital_structure_check = get_company_capital_structure_last_checked(sync_session, snapshot.company.id)
            if parsed_as_of is not None:
                floor = datetime.min.replace(tzinfo=timezone.utc)
                history = [item for item in history if (snapshot_effective_at(item) or floor) <= parsed_as_of]
            history = history[:max_periods]
            refresh = _refresh_for_capital_structure(snapshot, last_capital_structure_check, history)
            serialized_history = [_serialize_capital_structure_snapshot(item) for item in history]
            latest = serialized_history[0] if serialized_history else None
            diagnostics = _diagnostics_for_capital_structure(serialized_history, refresh)
            payload = CompanyCapitalStructureResponse(
                company=_serialize_company(snapshot, last_checked=_merge_last_checked(snapshot.last_checked, last_capital_structure_check)),
                latest=latest,
                history=serialized_history,
                last_capital_structure_check=last_capital_structure_check,
                refresh=refresh,
                diagnostics=diagnostics,
                **_capital_structure_provenance_contract(
                    history,
                    latest=latest,
                    last_capital_structure_check=last_capital_structure_check,
                    diagnostics=diagnostics,
                    refresh=refresh,
                ),
            )
            return _apply_requested_as_of(payload, requested_as_of)

        payload = await _fill_hot_cached_payload(
            hot_key,
            model_type=CompanyCapitalStructureResponse,
            tags=hot_tags,
            fill=lambda: _run_with_session_binding(session, build_capital_structure_payload),
        )
        not_modified = _apply_conditional_headers(
            request,
            http_response,
            payload,
            last_modified=payload.company.last_checked if payload.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return payload


@main_bound
def company_equity_claim_risk(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyEquityClaimRiskResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyEquityClaimRiskResponse(
            company=None,
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing", "equity_claim_risk_missing"], missing_field_flags=["financials_missing", "capital_structure_missing", "capital_markets_missing", "filing_events_missing"]),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    payload = build_company_equity_claim_risk_response(
        session,
        snapshot.company.id,
        company=_serialize_company(snapshot),
        refresh=refresh,
        as_of=parsed_as_of,
    )
    return _apply_requested_as_of(payload, requested_as_of)


@main_bound
def company_filing_insights(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFilingInsightsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyFilingInsightsResponse(
            company=None,
            insights=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
        )

    insights = get_company_filing_insights(session, snapshot.company.id)
    insights_last_checked = max((item.last_checked for item in insights if item.last_checked is not None), default=None)
    refresh = _refresh_for_filing_insights(background_tasks, snapshot)
    serialized_insights = [_serialize_filing_parser_insight(item) for item in insights]
    return CompanyFilingInsightsResponse(
        company=_serialize_company(snapshot, last_checked=insights_last_checked),
        insights=serialized_insights,
        refresh=refresh,
        diagnostics=_diagnostics_for_filing_insights(serialized_insights, refresh),
    )


@main_bound
def company_changes_since_last_filing(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyChangesSinceLastFilingResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyChangesSinceLastFilingResponse(
            company=None,
            summary=ChangesSinceLastFilingSummaryPayload(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            **_empty_provenance_contract("company_missing"),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    persisted_payload = _load_snapshot_backed_changes_since_last_filing_response(
        session,
        snapshot,
        refresh=refresh,
        requested_as_of=requested_as_of,
        parsed_as_of=parsed_as_of,
    )
    if persisted_payload is not None:
        return persisted_payload

    financials = _visible_financials_for_company(session, snapshot.company)
    if parsed_as_of is not None:
        financials = select_point_in_time_financials(financials, parsed_as_of)
    restatements = get_company_financial_restatements(session, snapshot.company.id)
    if parsed_as_of is not None:
        restatements = [record for record in restatements if _financial_restatement_effective_at(record) <= parsed_as_of]
    parsed_filings = get_company_filing_insights(session, snapshot.company.id, limit=12)
    if parsed_as_of is not None:
        parsed_filings = select_point_in_time_financials(parsed_filings, parsed_as_of)
    comment_letters = get_company_comment_letters(session, snapshot.company.id, limit=24)
    if parsed_as_of is not None:
        comment_letters = [letter for letter in comment_letters if _effective_at(letter.filing_date) <= parsed_as_of]

    comparison = build_changes_since_last_filing(
        financials,
        restatements,
        parsed_filings=parsed_filings,
        comment_letters=comment_letters,
    )
    diagnostics = _diagnostics_for_changes_since_last_filing(comparison, refresh)
    comparison_as_of = requested_as_of or _latest_as_of(
        (comparison.get("current_filing") or {}).get("filing_acceptance_at"),
        (comparison.get("current_filing") or {}).get("period_end"),
    )

    usages: list[SourceUsage] = [
        SourceUsage(
            source_id="ft_changes_since_last_filing",
            role="derived",
            as_of=comparison_as_of,
            last_refreshed_at=_merge_last_checked(
                snapshot.last_checked,
                (comparison.get("current_filing") or {}).get("last_checked"),
                (comparison.get("previous_filing") or {}).get("last_checked"),
            ),
        )
    ]
    companyfacts_usage = _source_usage_from_hint(
        "https://data.sec.gov/api/xbrl/companyfacts/",
        role="primary",
        as_of=comparison_as_of,
        last_refreshed_at=snapshot.last_checked,
        default_source_id="sec_companyfacts",
    )
    if companyfacts_usage is not None:
        usages.append(companyfacts_usage)
    if any(
        str(source or "").startswith("https://www.sec.gov/Archives/")
        for source in [
            (comparison.get("current_filing") or {}).get("source"),
            (comparison.get("previous_filing") or {}).get("source"),
            *(item.get("source") for item in comparison.get("amended_prior_values", [])),
            *(
                evidence.get("source")
                for item in comparison.get("high_signal_changes", [])
                if isinstance(item, dict)
                for evidence in item.get("evidence", [])
                if isinstance(evidence, dict)
            ),
        ]
    ):
        filing_usage = _source_usage_from_hint(
            "https://www.sec.gov/Archives/",
            role="supplemental",
            as_of=comparison_as_of,
            last_refreshed_at=_merge_last_checked(
                snapshot.last_checked,
                *(item.last_checked for item in restatements),
                *(getattr(item, "last_checked", None) for item in parsed_filings),
                *(getattr(item, "last_checked", None) for item in comment_letters),
            ),
            default_source_id="sec_edgar",
        )
        if filing_usage is not None:
            usages.append(filing_usage)

    confidence_flags = set(_confidence_flags_from_refresh(refresh))
    confidence_flags.update(str(flag) for flag in comparison.get("confidence_flags", []))
    confidence_flags.update(
        str(item.get("indicator_key") or "")
        for item in comparison.get("new_risk_indicators", [])
        if str(item.get("severity") or "") == "high"
    )
    confidence_flags.discard("")

    payload = CompanyChangesSinceLastFilingResponse(
        company=_serialize_company(snapshot),
        current_filing=comparison.get("current_filing"),
        previous_filing=comparison.get("previous_filing"),
        summary=comparison.get("summary") or ChangesSinceLastFilingSummaryPayload(),
        metric_deltas=comparison.get("metric_deltas") or [],
        new_risk_indicators=comparison.get("new_risk_indicators") or [],
        segment_shifts=comparison.get("segment_shifts") or [],
        share_count_changes=comparison.get("share_count_changes") or [],
        capital_structure_changes=comparison.get("capital_structure_changes") or [],
        amended_prior_values=comparison.get("amended_prior_values") or [],
        high_signal_changes=comparison.get("high_signal_changes") or [],
        comment_letter_history=comparison.get("comment_letter_history") or {},
        refresh=refresh,
        diagnostics=diagnostics,
        **_build_provenance_contract(
            usages,
            as_of=comparison_as_of,
            last_refreshed_at=_merge_last_checked(
                snapshot.last_checked,
                (comparison.get("current_filing") or {}).get("last_checked"),
                (comparison.get("previous_filing") or {}).get("last_checked"),
                *(item.last_checked for item in restatements),
                *(getattr(item, "last_checked", None) for item in parsed_filings),
                *(getattr(item, "last_checked", None) for item in comment_letters),
            ),
            confidence_flags=sorted(confidence_flags),
        ),
    )
    return _apply_requested_as_of(payload, requested_as_of)


@main_bound
def company_metrics_timeseries(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    cadence: Literal["quarterly", "annual", "ttm"] | None = Query(default=None),
    max_points: int = Query(default=24, ge=1, le=200),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyMetricsTimeseriesResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyMetricsTimeseriesResponse(
            company=None,
            series=[],
            last_financials_check=None,
            last_price_check=None,
            staleness_reason="company_missing",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            **_empty_provenance_contract("company_missing"),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    financials = _visible_financials_for_company(session, snapshot.company)
    price_last_checked, price_cache_state = _visible_price_cache_status(session, snapshot.company.id)
    staleness_reason = _metrics_staleness_reason(snapshot, price_cache_state, financials)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)
    price_history = _visible_price_history(session, snapshot.company.id)
    if parsed_as_of is not None:
        financials = select_point_in_time_financials(financials, parsed_as_of)
        price_history = filter_price_history_as_of(price_history, parsed_as_of)
    series = build_metrics_timeseries(financials, price_history, cadence=cadence, max_points=max_points)
    point_payload = _sanitize_metrics_timeseries_points_for_strict_official_mode(
        [MetricsTimeseriesPointPayload.model_validate(point) for point in series]
    )
    diagnostics = _diagnostics_for_metrics_timeseries(point_payload, refresh, staleness_reason)
    payload = CompanyMetricsTimeseriesResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
            regulated_entity=_regulated_entity_payload(snapshot.company, financials),
        ),
        series=point_payload,
        last_financials_check=snapshot.last_checked,
        last_price_check=price_last_checked,
        staleness_reason=staleness_reason,
        refresh=refresh,
        diagnostics=diagnostics,
        **_metrics_timeseries_provenance_contract(
            point_payload,
            last_financials_check=snapshot.last_checked,
            last_price_check=price_last_checked,
            diagnostics=diagnostics,
            refresh=refresh,
        ),
    )
    return _apply_requested_as_of(payload, requested_as_of)


@main_bound
def company_derived_metrics(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    period_type: Literal["quarterly", "annual", "ttm"] = Query(default="ttm"),
    max_periods: int = Query(default=24, ge=1, le=200),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyDerivedMetricsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyDerivedMetricsResponse(
            company=None,
            period_type=period_type,
            periods=[],
            available_metric_keys=[],
            last_metrics_check=None,
            last_financials_check=None,
            last_price_check=None,
            staleness_reason="company_missing",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            **_empty_provenance_contract("company_missing"),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    price_last_checked, price_cache_state = _visible_price_cache_status(session, snapshot.company.id)
    financials = _visible_financials_for_company(session, snapshot.company)
    staleness_reason = _metrics_staleness_reason(snapshot, price_cache_state, financials)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)

    if parsed_as_of is None:
        rows = get_company_derived_metric_points(
            session,
            snapshot.company.id,
            period_type=period_type,
            max_periods=max_periods,
        )
        last_metrics_check = get_company_derived_metrics_last_checked(session, snapshot.company.id)
        if not rows:
            refresh = _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
            if staleness_reason == "fresh":
                staleness_reason = "metrics_missing"

        period_payload = _sanitize_derived_metric_periods_for_strict_official_mode(
            [DerivedMetricPeriodPayload.model_validate(item) for item in to_period_payload(rows)]
        )
        available_metric_keys = sorted({item.metric_key for item in rows})
        metric_values = [metric for period in period_payload for metric in period.metrics]
        latest_period_end = max((period.period_end for period in period_payload), default=None)
        diagnostics = _diagnostics_for_derived_metrics_periods(period_payload, refresh, staleness_reason)
        payload = CompanyDerivedMetricsResponse(
            company=_serialize_company(
                snapshot,
                last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
                last_checked_prices=price_last_checked,
                regulated_entity=_regulated_entity_payload(snapshot.company, financials),
            ),
            period_type=period_type,
            periods=period_payload,
            available_metric_keys=available_metric_keys,
            last_metrics_check=last_metrics_check,
            last_financials_check=snapshot.last_checked,
            last_price_check=price_last_checked,
            staleness_reason=staleness_reason,
            refresh=refresh,
            diagnostics=diagnostics,
            **_derived_metrics_provenance_contract(
                metric_values,
                as_of=latest_period_end,
                derived_source_id="ft_derived_metrics_mart",
                last_metrics_check=last_metrics_check,
                last_financials_check=snapshot.last_checked,
                last_price_check=price_last_checked,
                diagnostics=diagnostics,
                refresh=refresh,
            ),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    filtered_financials = select_point_in_time_financials(financials, parsed_as_of)
    filtered_price_history = filter_price_history_as_of(_visible_price_history(session, snapshot.company.id), parsed_as_of)
    point_rows = [
        row
        for row in build_derived_metric_points(filtered_financials, filtered_price_history)
        if row.get("period_type") == period_type
    ]
    period_rows = to_period_payload_from_points(point_rows)
    if len(period_rows) > max_periods:
        period_rows = period_rows[-max_periods:]
    period_payload = _sanitize_derived_metric_periods_for_strict_official_mode(
        [DerivedMetricPeriodPayload.model_validate(item) for item in period_rows]
    )
    available_metric_keys = sorted({str(item.get("metric_key") or "") for item in point_rows if item.get("metric_key")})
    last_metrics_check = None
    diagnostics = _diagnostics_for_derived_metrics_periods(period_payload, refresh, staleness_reason)
    metric_values = [metric for period in period_payload for metric in period.metrics]
    latest_period_end = max((period.period_end for period in period_payload), default=None)
    payload = CompanyDerivedMetricsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
            regulated_entity=_regulated_entity_payload(snapshot.company, financials),
        ),
        period_type=period_type,
        periods=period_payload,
        available_metric_keys=available_metric_keys,
        last_metrics_check=last_metrics_check,
        last_financials_check=snapshot.last_checked,
        last_price_check=price_last_checked,
        staleness_reason=staleness_reason,
        refresh=refresh,
        diagnostics=diagnostics,
        **_derived_metrics_provenance_contract(
            metric_values,
            as_of=requested_as_of or latest_period_end,
            derived_source_id="ft_derived_metrics_engine",
            last_metrics_check=last_metrics_check,
            last_financials_check=snapshot.last_checked,
            last_price_check=price_last_checked,
            diagnostics=diagnostics,
            refresh=refresh,
        ),
    )
    return _apply_requested_as_of(payload, requested_as_of)


@main_bound
def company_derived_metrics_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    period_type: Literal["quarterly", "annual", "ttm"] = Query(default="ttm"),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyDerivedMetricsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyDerivedMetricsSummaryResponse(
            company=None,
            period_type=period_type,
            latest_period_end=None,
            metrics=[],
            last_metrics_check=None,
            last_financials_check=None,
            last_price_check=None,
            staleness_reason="company_missing",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            **_empty_provenance_contract("company_missing"),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    price_last_checked, price_cache_state = _visible_price_cache_status(session, snapshot.company.id)
    financials = _visible_financials_for_company(session, snapshot.company)
    staleness_reason = _metrics_staleness_reason(snapshot, price_cache_state, financials)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)

    if parsed_as_of is None:
        rows = get_company_derived_metric_points(session, snapshot.company.id, max_periods=24)
        last_metrics_check = get_company_derived_metrics_last_checked(session, snapshot.company.id)
        if not rows:
            refresh = _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
            if staleness_reason == "fresh":
                staleness_reason = "metrics_missing"

        summary = build_summary_payload(rows, period_type)
        metric_payload = _sanitize_derived_metric_values_for_strict_official_mode(
            [DerivedMetricValuePayload.model_validate(item) for item in summary["metrics"]]
        )
        diagnostics = _diagnostics_for_derived_metrics_values(metric_payload, refresh, staleness_reason)
        payload = CompanyDerivedMetricsSummaryResponse(
            company=_serialize_company(
                snapshot,
                last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
                last_checked_prices=price_last_checked,
                regulated_entity=_regulated_entity_payload(snapshot.company, financials),
            ),
            period_type=summary["period_type"],
            latest_period_end=summary["latest_period_end"],
            metrics=metric_payload,
            last_metrics_check=last_metrics_check,
            last_financials_check=snapshot.last_checked,
            last_price_check=price_last_checked,
            staleness_reason=staleness_reason,
            refresh=refresh,
            diagnostics=diagnostics,
            **_derived_metrics_provenance_contract(
                metric_payload,
                as_of=summary["latest_period_end"],
                derived_source_id="ft_derived_metrics_mart",
                last_metrics_check=last_metrics_check,
                last_financials_check=snapshot.last_checked,
                last_price_check=price_last_checked,
                diagnostics=diagnostics,
                refresh=refresh,
            ),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    filtered_financials = select_point_in_time_financials(financials, parsed_as_of)
    filtered_price_history = filter_price_history_as_of(_visible_price_history(session, snapshot.company.id), parsed_as_of)
    point_rows = build_derived_metric_points(filtered_financials, filtered_price_history)
    summary = build_summary_payload_from_points(point_rows, period_type)
    last_metrics_check = None
    metric_payload = _sanitize_derived_metric_values_for_strict_official_mode(
        [DerivedMetricValuePayload.model_validate(item) for item in summary["metrics"]]
    )
    diagnostics = _diagnostics_for_derived_metrics_values(metric_payload, refresh, staleness_reason)
    payload = CompanyDerivedMetricsSummaryResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
            regulated_entity=_regulated_entity_payload(snapshot.company, financials),
        ),
        period_type=summary["period_type"],
        latest_period_end=summary["latest_period_end"],
        metrics=metric_payload,
        last_metrics_check=last_metrics_check,
        last_financials_check=snapshot.last_checked,
        last_price_check=price_last_checked,
        staleness_reason=staleness_reason,
        refresh=refresh,
        diagnostics=diagnostics,
        **_derived_metrics_provenance_contract(
            metric_payload,
            as_of=requested_as_of or summary["latest_period_end"],
            derived_source_id="ft_derived_metrics_engine",
            last_metrics_check=last_metrics_check,
            last_financials_check=snapshot.last_checked,
            last_price_check=price_last_checked,
            diagnostics=diagnostics,
            refresh=refresh,
        ),
    )
    return _apply_requested_as_of(payload, requested_as_of)


@main_bound
def company_charts(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyChartsDashboardResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    return _build_company_charts_response(
        session,
        normalized_ticker,
        background_tasks,
        requested_as_of=requested_as_of,
        parsed_as_of=parsed_as_of,
    )


@main_bound
def company_charts_what_if(
    ticker: str,
    background_tasks: BackgroundTasks,
    payload: CompanyChartsWhatIfRequest | None = Body(default=None),
    request: Request = None,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyChartsDashboardResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    return _build_company_charts_what_if_response(
        session,
        normalized_ticker,
        background_tasks,
        requested_as_of=requested_as_of,
        parsed_as_of=parsed_as_of,
        payload=payload or CompanyChartsWhatIfRequest(),
    )


@main_bound
def company_charts_forecast_accuracy(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyChartsForecastAccuracyResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    normalized_as_of = _normalize_as_of(parsed_as_of) or "latest"
    hot_key = f"charts-forecast-accuracy:{normalized_ticker}:asof={normalized_as_of}"
    cached_hot = shared_hot_response_cache.get_sync(hot_key, route="charts")
    if cached_hot is not None and cached_hot.is_fresh:
        return CompanyChartsForecastAccuracyResponse.model_validate(_decode_hot_cache_payload(cached_hot))

    snapshot = _resolve_company_brief_snapshot(session, normalized_ticker)
    if snapshot is None:
        refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="missing")
        return CompanyChartsForecastAccuracyResponse(
            company=None,
            status="insufficient_history",
            insufficient_history_reason="No persisted company snapshot is available yet.",
            max_backtests=6,
            metrics=[],
            aggregate=CompanyChartsForecastAccuracyAggregatePayload(),
            samples=[],
            refresh=refresh,
            diagnostics=_build_data_quality_diagnostics(missing_field_flags=["company_missing", "forecast_accuracy_insufficient_history"]),
            **_empty_provenance_contract(),
        )

    stored_snapshot, payload = _load_company_charts_forecast_accuracy_snapshot_record(
        session,
        snapshot.company.id,
        as_of=parsed_as_of,
    )
    refresh = _refresh_for_company_charts_forecast_accuracy(
        background_tasks,
        session,
        snapshot,
        stored_snapshot=stored_snapshot,
        as_of=parsed_as_of,
    )
    if payload is None:
        if hasattr(session, "execute") and hasattr(session, "commit"):
            generated = recompute_and_persist_company_charts_forecast_accuracy(
                session,
                snapshot.company.id,
                as_of=parsed_as_of,
            )
            if generated is not None:
                session.commit()
                response = generated.model_copy(
                    update={
                        "refresh": RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None),
                    }
                )
                shared_hot_response_cache.store_sync(
                    hot_key,
                    route="charts",
                    payload=response.model_dump(mode="json"),
                    tags=_build_hot_cache_tags(
                        ticker=snapshot.company.ticker,
                        datasets=("charts_forecast_accuracy",),
                        schema_versions=(CHARTS_FORECAST_ACCURACY_SCHEMA_VERSION,),
                        as_of=normalized_as_of,
                    ),
                )
                return response
        if not refresh.triggered:
            refresh = _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
        return CompanyChartsForecastAccuracyResponse(
            company=_serialize_company(snapshot),
            status="insufficient_history",
            insufficient_history_reason="Forecast accuracy payload is still building for this company.",
            max_backtests=6,
            metrics=[],
            aggregate=CompanyChartsForecastAccuracyAggregatePayload(),
            samples=[],
            refresh=refresh,
            diagnostics=_build_data_quality_diagnostics(stale_flags=["forecast_accuracy_missing"], missing_field_flags=["forecast_accuracy_unavailable"]),
            **_empty_provenance_contract(),
        )

    response = payload.model_copy(update={"refresh": refresh})
    shared_hot_response_cache.store_sync(
        hot_key,
        route="charts",
        payload=response.model_dump(mode="json"),
        tags=_build_hot_cache_tags(
            ticker=snapshot.company.ticker,
            datasets=("charts_forecast_accuracy",),
            schema_versions=(CHARTS_FORECAST_ACCURACY_SCHEMA_VERSION,),
            as_of=normalized_as_of,
        ),
    )
    return response


@main_bound
def company_charts_scenarios(
    ticker: str,
    request: Request = None,
    session: Session = Depends(get_db_session),
) -> CompanyChartsScenarioListResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_company_brief_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    viewer_key, viewer = _resolve_projection_studio_viewer(request)
    scenarios = [
        serialize_company_charts_scenario(
            scenario,
            ticker=snapshot.company.ticker,
            viewer_key=viewer_key,
        )
        for scenario in list_company_charts_scenarios(
            session,
            company_id=snapshot.company.id,
            viewer_key=viewer_key,
        )
    ]
    return CompanyChartsScenarioListResponse(viewer=viewer, scenarios=scenarios)


@main_bound
def company_charts_scenario_create(
    ticker: str,
    payload: CompanyChartsScenarioUpsertRequest,
    request: Request = None,
    session: Session = Depends(get_db_session),
) -> CompanyChartsScenarioDetailPayload:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_company_brief_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    viewer_key, viewer = _resolve_projection_studio_viewer(request)
    if payload.visibility == "private" and not viewer.can_create_private:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Private Projection Studio scenarios require a local viewer or signed-in identity.",
        )

    scenario = create_company_charts_scenario(
        session,
        company_id=snapshot.company.id,
        payload=payload,
        viewer_key=viewer_key,
    )
    if hasattr(session, "commit"):
        session.commit()
    return CompanyChartsScenarioDetailPayload(
        viewer=viewer,
        scenario=serialize_company_charts_scenario(
            scenario,
            ticker=snapshot.company.ticker,
            viewer_key=viewer_key,
        ),
    )


@main_bound
def company_charts_scenario_detail(
    ticker: str,
    scenario_id: str,
    request: Request = None,
    session: Session = Depends(get_db_session),
) -> CompanyChartsScenarioDetailPayload:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_company_brief_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    viewer_key, viewer = _resolve_projection_studio_viewer(request)
    scenario = get_company_charts_scenario(
        session,
        company_id=snapshot.company.id,
        scenario_id=scenario_id,
    )
    if scenario is None or not viewer_can_access_company_charts_scenario(scenario, viewer_key=viewer_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projection Studio scenario not found.")

    return CompanyChartsScenarioDetailPayload(
        viewer=viewer,
        scenario=serialize_company_charts_scenario(
            scenario,
            ticker=snapshot.company.ticker,
            viewer_key=viewer_key,
        ),
    )


@main_bound
def company_charts_scenario_update(
    ticker: str,
    scenario_id: str,
    payload: CompanyChartsScenarioUpsertRequest,
    request: Request = None,
    session: Session = Depends(get_db_session),
) -> CompanyChartsScenarioDetailPayload:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_company_brief_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    viewer_key, viewer = _resolve_projection_studio_viewer(request)
    scenario = get_company_charts_scenario(
        session,
        company_id=snapshot.company.id,
        scenario_id=scenario_id,
    )
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projection Studio scenario not found.")
    if not viewer_can_edit_company_charts_scenario(scenario, viewer_key=viewer_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot update this Projection Studio scenario.")
    if payload.visibility == "private" and not viewer.can_create_private:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Private Projection Studio scenarios require a local viewer or signed-in identity.",
        )

    updated = update_company_charts_scenario(session, scenario=scenario, payload=payload)
    if hasattr(session, "commit"):
        session.commit()
    return CompanyChartsScenarioDetailPayload(
        viewer=viewer,
        scenario=serialize_company_charts_scenario(
            updated,
            ticker=snapshot.company.ticker,
            viewer_key=viewer_key,
        ),
    )


@main_bound
def company_charts_scenario_clone(
    ticker: str,
    scenario_id: str,
    payload: CompanyChartsScenarioCloneRequest,
    request: Request = None,
    session: Session = Depends(get_db_session),
) -> CompanyChartsScenarioDetailPayload:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_company_brief_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    viewer_key, viewer = _resolve_projection_studio_viewer(request)
    source_scenario = get_company_charts_scenario(
        session,
        company_id=snapshot.company.id,
        scenario_id=scenario_id,
    )
    if source_scenario is None or not viewer_can_access_company_charts_scenario(source_scenario, viewer_key=viewer_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projection Studio scenario not found.")

    requested_visibility = payload.visibility or source_scenario.visibility
    if requested_visibility == "private" and not viewer.can_create_private:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Private Projection Studio scenarios require a local viewer or signed-in identity.",
        )

    cloned = clone_company_charts_scenario(
        session,
        company_id=snapshot.company.id,
        source_scenario=source_scenario,
        payload=payload,
        viewer_key=viewer_key,
    )
    if hasattr(session, "commit"):
        session.commit()
    return CompanyChartsScenarioDetailPayload(
        viewer=viewer,
        scenario=serialize_company_charts_scenario(
            cloned,
            ticker=snapshot.company.ticker,
            viewer_key=viewer_key,
        ),
    )


@main_bound
def company_charts_share_snapshot_create(
    ticker: str,
    payload: CompanyChartsShareSnapshotPayload,
    session: Session = Depends(get_db_session),
) -> CompanyChartsShareSnapshotRecordPayload:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_company_brief_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    created = create_company_charts_share_snapshot(
        session,
        company_id=snapshot.company.id,
        payload=payload.model_copy(update={"ticker": snapshot.company.ticker}),
    )
    if hasattr(session, "commit"):
        session.commit()
    return serialize_company_charts_share_snapshot(created, ticker=snapshot.company.ticker)


@main_bound
def company_charts_share_snapshot_detail(
    ticker: str,
    snapshot_id: str,
    session: Session = Depends(get_db_session),
) -> CompanyChartsShareSnapshotRecordPayload:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_company_brief_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    record = get_company_charts_share_snapshot(
        session,
        company_id=snapshot.company.id,
        snapshot_id=snapshot_id,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charts share snapshot not found.")

    return serialize_company_charts_share_snapshot(record, ticker=snapshot.company.ticker)


@main_bound
def company_financial_restatements(
    ticker: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyFinancialRestatementsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyFinancialRestatementsResponse(
            company=None,
            summary=_empty_financial_restatements_summary(),
            restatements=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            **_empty_provenance_contract("company_missing"),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    records = get_company_financial_restatements(session, snapshot.company.id)
    if parsed_as_of is not None:
        records = [record for record in records if _financial_restatement_effective_at(record) <= parsed_as_of]

    serialized = [_serialize_financial_restatement(record) for record in records]
    confidence_flags = set(_confidence_flags_from_refresh(refresh))
    for record in serialized:
        confidence_flags.update(record.confidence_impact.flags)

    usages: list[SourceUsage] = []
    companyfacts_usage = _source_usage_from_hint(
        "https://data.sec.gov/api/xbrl/companyfacts/",
        role="primary",
        as_of=requested_as_of or _latest_financial_restatement_as_of(records),
        last_refreshed_at=snapshot.last_checked,
        default_source_id="sec_companyfacts",
    )
    if companyfacts_usage is not None:
        usages.append(companyfacts_usage)
    if any(record.source.startswith("https://www.sec.gov/Archives/") for record in records):
        filing_usage = _source_usage_from_hint(
            "https://www.sec.gov/Archives/",
            role="supplemental",
            as_of=requested_as_of or _latest_financial_restatement_as_of(records),
            last_refreshed_at=snapshot.last_checked,
            default_source_id="sec_edgar",
        )
        if filing_usage is not None:
            usages.append(filing_usage)

    payload = CompanyFinancialRestatementsResponse(
        company=_serialize_company(snapshot),
        summary=_build_financial_restatements_summary(serialized),
        restatements=serialized,
        refresh=refresh,
        **_build_provenance_contract(
            usages,
            as_of=requested_as_of or _latest_financial_restatement_as_of(records),
            last_refreshed_at=_merge_last_checked(snapshot.last_checked, *(record.last_checked for record in records)),
            confidence_flags=sorted(confidence_flags),
        ),
    )
    return _apply_requested_as_of(payload, requested_as_of)


@main_bound
def company_financial_history(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> CompanyFactsResponse:
    normalized = _normalize_search_query(ticker)
    resolved_cik = _normalize_cik_query(normalized)
    if resolved_cik:
        cik = resolved_cik
    else:
        snapshot = _resolve_cached_company_snapshot(session, _normalize_ticker(ticker))
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown ticker")
        cik = snapshot.company.cik

    client = EdgarClient()
    try:
        facts = client.get_companyfacts(cik)
        if not isinstance(facts, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unexpected SEC companyfacts payload")
        return CompanyFactsResponse(facts=facts.get("facts", {}))
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to load SEC companyfacts for '%s'", cik)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to load SEC companyfacts")
    finally:
        client.close()


__all__ = [
    "company_capital_structure",
    "company_charts",
    "company_charts_forecast_accuracy",
    "company_charts_scenario_clone",
    "company_charts_scenario_create",
    "company_charts_scenario_detail",
    "company_charts_scenario_update",
    "company_charts_scenarios",
    "company_charts_share_snapshot_create",
    "company_charts_share_snapshot_detail",
    "company_charts_what_if",
    "company_changes_since_last_filing",
    "company_compare",
    "company_derived_metrics",
    "company_derived_metrics_summary",
    "company_equity_claim_risk",
    "company_filing_insights",
    "company_financial_history",
    "company_financial_restatements",
    "company_financials",
    "company_metrics_timeseries",
    "company_segment_history",
]
