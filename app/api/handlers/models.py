from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
async def company_models(
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
    model: str | None = Query(default=None),
    expand: str | None = Query(default=None, description="optional expansions: input_periods, formula_details"),
    dupont_mode: str | None = Query(default=None, description="optional DuPont basis: auto|annual|ttm"),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
) -> CompanyModelsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = _read_singleton_query_param_or_400(request, "as_of", fallback=as_of)
    requested_expand = _read_singleton_query_param_or_400(request, "expand", fallback=expand)
    requested_dupont_mode = _read_singleton_query_param_or_400(request, "dupont_mode", fallback=dupont_mode)
    parsed_as_of, requested_expansions, normalized_mode, normalized_as_of = _normalize_company_models_query_controls(
        requested_as_of=requested_as_of,
        expand=requested_expand,
        dupont_mode=requested_dupont_mode,
    )
    requested_models = _parse_requested_models(model)
    include_input_periods = "input_periods" in requested_expansions
    include_formula_details = "formula_details" in requested_expansions
    if not settings.valuation_workbench_enabled:
        requested_models = [
            item
            for item in requested_models
            if item not in {"reverse_dcf", "roic", "capital_allocation"}
        ]
    normalized_expansions = ",".join(sorted(requested_expansions)) or "default"
    hot_key = (
        f"models:{normalized_ticker}:models={','.join(requested_models)}:dupont={normalized_mode or 'default'}"
        f":expand={normalized_expansions}:asof={normalized_as_of}"
    )
    hot_tags = _build_hot_cache_tags(
        ticker=normalized_ticker,
        datasets=("financials", "prices"),
        schema_versions=(HOT_CACHE_SCHEMA_VERSIONS["models"],),
        as_of=normalized_as_of,
    )
    token = None
    try:
        async with _session_scope() as session:
            cached_hot = await _get_hot_cached_payload(hot_key)
            if cached_hot is not None:
                if cached_hot.is_fresh:
                    return _hot_cache_json_response(request, http_response, cached_hot)

                payload_data = _decode_hot_cache_payload(cached_hot)
                cached_response = CompanyModelsResponse.model_validate(payload_data)
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

            def build_models_payload(sync_session: Session) -> CompanyModelsResponse:
                snapshot = _resolve_cached_company_snapshot(sync_session, normalized_ticker)
                if snapshot is None:
                    payload = CompanyModelsResponse(
                        company=None,
                        requested_models=requested_models,
                        models=[],
                        refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
                        diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
                        **_empty_provenance_contract("company_missing"),
                    )
                    return _apply_requested_as_of(payload, requested_as_of)

                refresh = _refresh_for_snapshot(background_tasks, snapshot)
                financials = get_company_financials(sync_session, snapshot.company.id)
                price_last_checked, _price_cache_state = _visible_price_cache_status(sync_session, snapshot.company.id)
                price_history: list[PriceHistory] = []
                if parsed_as_of is not None:
                    price_history = _visible_price_history(sync_session, snapshot.company.id)
                    financials = select_point_in_time_financials(financials, parsed_as_of)
                    price_history = filter_price_history_as_of(price_history, parsed_as_of)

                if parsed_as_of is None:
                    config_by_model = {"dupont": {"mode": dupont_model.get_mode()}}
                    models: list[ModelRun | dict[str, Any]] = get_company_models(
                        sync_session,
                        snapshot.company.id,
                        requested_models or None,
                        config_by_model=config_by_model,
                    )
                    available_model_names = {_model_name(model_run).lower() for model_run in models}
                    missing_requested_models = [
                        model_name for model_name in requested_models if model_name.lower() not in available_model_names
                    ]
                    if requested_models and (snapshot.cache_state == "fresh" or missing_requested_models):
                        model_names_to_compute = requested_models if snapshot.cache_state == "fresh" else missing_requested_models
                        model_job_results = ModelEngine(sync_session).compute_models(
                            snapshot.company.id,
                            model_names=model_names_to_compute,
                            force=False,
                        )
                        if any(not result.cached for result in model_job_results):
                            sync_session.commit()
                        models = get_company_models(
                            sync_session,
                            snapshot.company.id,
                            requested_models or None,
                            config_by_model=config_by_model,
                        )
                else:
                    latest_price = latest_price_as_of(price_history, parsed_as_of)
                    dataset = build_company_dataset(
                        snapshot.company,
                        financials,
                        build_market_snapshot(latest_price),
                        as_of_date=parsed_as_of,
                    )
                    models = ModelEngine(sync_session).evaluate_models(
                        dataset,
                        model_names=requested_models or None,
                        created_at=datetime.now(timezone.utc),
                    )
                company_context = _model_company_context(snapshot.company)
                status_counts: dict[str, int] = {}
                for model_run in models:
                    result = _model_result_payload(model_run, company_context=company_context)
                    model_status = str(result.get("model_status") or result.get("status") or "insufficient_data")
                    status_counts[model_status] = status_counts.get(model_status, 0) + 1
                logging.getLogger(__name__).info(
                    "TELEMETRY model_view ticker=%s models=%s status_counts=%s",
                    snapshot.company.ticker,
                    ",".join(requested_models) if requested_models else "all",
                    status_counts,
                )
                serialized_models = [
                    _serialize_model_payload(
                        model_run,
                        company_context=company_context,
                        include_input_periods=include_input_periods,
                        include_formula_details=include_formula_details,
                    )
                    for model_run in models
                ]
                diagnostics = _diagnostics_for_models(serialized_models, refresh)
                payload = CompanyModelsResponse(
                    company=_serialize_company(snapshot),
                    requested_models=requested_models,
                    models=serialized_models,
                    refresh=refresh,
                    diagnostics=diagnostics,
                    **_models_provenance_contract(
                        models,
                        financials,
                        price_last_checked=price_last_checked,
                        diagnostics=diagnostics,
                        refresh=refresh,
                    ),
                )
                return _apply_requested_as_of(payload, requested_as_of)

            if normalized_mode is not None:
                token = dupont_model.set_mode_override(normalized_mode)

            payload = await _fill_hot_cached_payload(
                hot_key,
                model_type=CompanyModelsResponse,
                tags=hot_tags,
                fill=lambda: _run_with_session_binding(session, build_models_payload),
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
    finally:
        if token is not None:
            dupont_model.reset_mode_override(token)


@main_bound
def list_formulas(
    ids: str | None = Query(default=None, description="Optional comma-separated formula ids"),
    include_details: bool = Query(default=False),
) -> FormulaListResponse:
    formula_ids = [item.strip() for item in (ids or "").split(",") if item.strip()] or None
    formulas = list_formula_metadata(formula_ids=formula_ids, include_details=include_details)
    return FormulaListResponse(
        schema_version=FORMULA_REGISTRY_VERSION,
        include_details=include_details,
        formulas=[
            FormulaMetadataPayload.model_validate(item) if include_details else FormulaSummaryPayload.model_validate(item)
            for item in formulas
        ],
    )


@main_bound
def get_formula(formula_id: str) -> FormulaMetadataPayload:
    metadata = get_formula_metadata(formula_id)
    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="formula not found")
    return FormulaMetadataPayload.model_validate(metadata.as_dict())


@main_bound
async def company_oil_scenario_overlay(
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
) -> CompanyOilScenarioOverlayResponse:
    normalized_ticker = _normalize_ticker(ticker)
    hot_key = f"oil_scenario_overlay:{normalized_ticker}"
    hot_tags = _build_hot_cache_tags(
        ticker=normalized_ticker,
        datasets=("oil_scenario_overlay", "financials", "prices"),
        schema_versions=(HOT_CACHE_SCHEMA_VERSIONS["oil_scenario_overlay"],),
    )
    async with _session_scope() as session:
        cached_hot = await _get_hot_cached_payload(hot_key)
        if cached_hot is not None:
            if cached_hot.is_fresh:
                return _hot_cache_json_response(request, http_response, cached_hot)

            payload_data = _decode_hot_cache_payload(cached_hot)
            cached_response = CompanyOilScenarioOverlayResponse.model_validate(payload_data)
            if not cached_hot.is_fresh:
                stale_refresh = _trigger_cached_company_refresh(background_tasks, normalized_ticker, reason="stale")
                cached_response = cached_response.model_copy(
                    update={
                        "refresh": stale_refresh,
                        "diagnostics": _with_stale_flags(cached_response.diagnostics, _stale_flags_from_refresh(stale_refresh)),
                        "confidence_flags": sorted(
                            set([*cached_response.confidence_flags, *_confidence_flags_from_refresh(stale_refresh)])
                        ),
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

        def build_oil_scenario_overlay_payload(sync_session: Session) -> CompanyOilScenarioOverlayResponse:
            snapshot = _resolve_cached_company_snapshot(sync_session, normalized_ticker)
            if snapshot is None:
                return CompanyOilScenarioOverlayResponse(
                    company=None,
                    status="insufficient_data",
                    fetched_at=datetime.now(timezone.utc),
                    strict_official_mode=settings.strict_official_mode,
                    exposure_profile=OilExposureProfilePayload(
                        profile_id="not_applicable",
                        label="Not Applicable",
                        hedging_signal="unknown",
                        pass_through_signal="unknown",
                    ),
                    benchmark_series=[],
                    scenarios=[],
                    sensitivity=None,
                    diagnostics=_build_data_quality_diagnostics(
                        coverage_ratio=0.0,
                        stale_flags=["company_missing", "oil_scenario_overlay_missing"],
                        missing_field_flags=["oil_scenario_overlay_missing"],
                    ),
                    refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
                    **_empty_provenance_contract("company_missing", "oil_scenario_overlay_missing"),
                )

            payload, cache_state = get_company_oil_scenario_overlay(sync_session, snapshot.company.id)
            last_checked = get_company_oil_scenario_overlay_last_checked(sync_session, snapshot.company.id)
            refresh = _refresh_for_oil_scenario_overlay(background_tasks, snapshot, cache_state)
            return _serialize_oil_scenario_overlay_response(
                company=_serialize_company(snapshot, last_checked=_merge_last_checked(snapshot.last_checked, last_checked)),
                payload=payload
                or build_company_oil_scenario_overlay_placeholder(
                    snapshot.company,
                    checked_at=last_checked or snapshot.last_checked or datetime.now(timezone.utc),
                ),
                refresh=refresh,
                default_checked_at=last_checked or snapshot.last_checked or datetime.now(timezone.utc),
                mark_missing=payload is None,
            )

        response = await _fill_hot_cached_payload(
            hot_key,
            model_type=CompanyOilScenarioOverlayResponse,
            tags=hot_tags,
            fill=lambda: _run_with_session_binding(session, build_oil_scenario_overlay_payload),
        )
        not_modified = _apply_conditional_headers(
            request,
            http_response,
            response,
            last_modified=response.company.last_checked if response.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return response


@main_bound
async def company_oil_scenario(
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
) -> CompanyOilScenarioResponse:
    normalized_ticker = _normalize_ticker(ticker)
    hot_key = f"oil_scenario:{normalized_ticker}"
    hot_tags = _build_hot_cache_tags(
        ticker=normalized_ticker,
        datasets=("oil_scenario_overlay", "financials", "prices"),
        schema_versions=(HOT_CACHE_SCHEMA_VERSIONS["oil_scenario"],),
    )
    async with _session_scope() as session:
        cached_hot = await _get_hot_cached_payload(hot_key)
        if cached_hot is not None:
            if cached_hot.is_fresh:
                return _hot_cache_json_response(request, http_response, cached_hot)

            payload_data = _decode_hot_cache_payload(cached_hot)
            cached_response = CompanyOilScenarioResponse.model_validate(payload_data)
            if not cached_hot.is_fresh:
                stale_refresh = _trigger_cached_company_refresh(background_tasks, normalized_ticker, reason="stale")
                cached_response = cached_response.model_copy(
                    update={
                        "refresh": stale_refresh,
                        "diagnostics": _with_stale_flags(cached_response.diagnostics, _stale_flags_from_refresh(stale_refresh)),
                        "confidence_flags": sorted(
                            set([*cached_response.confidence_flags, *_confidence_flags_from_refresh(stale_refresh)])
                        ),
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

        def build_oil_scenario_payload(sync_session: Session) -> CompanyOilScenarioResponse:
            snapshot = _resolve_cached_company_snapshot(sync_session, normalized_ticker)
            if snapshot is None:
                return CompanyOilScenarioResponse(
                    company=None,
                    status="insufficient_data",
                    fetched_at=datetime.now(timezone.utc),
                    strict_official_mode=settings.strict_official_mode,
                    exposure_profile=OilExposureProfilePayload(
                        profile_id="not_applicable",
                        label="Not Applicable",
                        hedging_signal="unknown",
                        pass_through_signal="unknown",
                    ),
                    eligibility=OilScenarioEligibilityPayload(eligible=False, status="unsupported", oil_exposure_type="non_oil", reasons=[]),
                    benchmark_series=[],
                    official_base_curve=OilScenarioOfficialBaseCurvePayload(),
                    user_editable_defaults=OilScenarioUserEditableDefaultsPayload(fade_years=2),
                    scenarios=[],
                    sensitivity=None,
                    sensitivity_source=OilScenarioSensitivitySourcePayload(kind="manual_override", value=None, metric_basis=None, status=None, confidence_flags=[]),
                    phase2_extensions=OilScenarioPhase2ExtensionsPayload(),
                    overlay_outputs=OilScenarioOverlayOutputsPayload(
                        status="insufficient_data",
                        model_status="insufficient_data",
                        reason="Company cache is missing.",
                    ),
                    requirements=OilScenarioRequirementsPayload(
                        strict_official_mode=settings.strict_official_mode,
                        manual_price_required=True,
                        manual_price_reason="Company cache is missing.",
                        manual_sensitivity_required=True,
                        manual_sensitivity_reason="Company cache is missing.",
                        price_input_mode="manual",
                    ),
                    direct_company_evidence=OilScenarioDirectCompanyEvidencePayload(
                        status="not_available",
                        parser_confidence_flags=["oil_company_evidence_not_available"],
                        disclosed_sensitivity=OilScenarioDisclosedSensitivityEvidencePayload(
                            status="not_available",
                            reason="Company cache is missing.",
                            confidence_flags=["oil_sensitivity_not_available"],
                            provenance_sources=["sec_edgar"],
                        ),
                        diluted_shares=OilScenarioDilutedSharesEvidencePayload(
                            status="not_available",
                            reason="Company cache is missing.",
                            confidence_flags=["diluted_shares_not_available"],
                            provenance_sources=["sec_companyfacts"],
                        ),
                        realized_price_comparison=OilScenarioRealizedPriceComparisonEvidencePayload(
                            status="not_available",
                            reason="Company cache is missing.",
                            benchmark=None,
                            rows=[],
                            confidence_flags=["realized_vs_benchmark_not_available"],
                            provenance_sources=["sec_edgar"],
                        ),
                    ),
                    diagnostics=_build_data_quality_diagnostics(
                        coverage_ratio=0.0,
                        stale_flags=["company_missing", "oil_scenario_missing"],
                        missing_field_flags=["oil_scenario_missing"],
                    ),
                    refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
                    **_empty_provenance_contract("company_missing", "oil_scenario_missing"),
                )

            payload, cache_state = get_company_oil_scenario_overlay(sync_session, snapshot.company.id)
            last_checked = get_company_oil_scenario_overlay_last_checked(sync_session, snapshot.company.id)
            refresh = _refresh_for_oil_scenario_overlay(background_tasks, snapshot, cache_state)
            default_checked_at = last_checked or snapshot.last_checked or datetime.now(timezone.utc)
            base_payload = payload or build_company_oil_scenario_overlay_placeholder(snapshot.company, checked_at=default_checked_at)
            public_payload = build_company_oil_scenario_public_payload(
                sync_session,
                snapshot.company,
                overlay_payload=base_payload,
                checked_at=default_checked_at,
            )
            return _serialize_oil_scenario_response(
                company=_serialize_company(snapshot, last_checked=_merge_last_checked(snapshot.last_checked, last_checked)),
                payload=public_payload,
                refresh=refresh,
                default_checked_at=default_checked_at,
                mark_missing=payload is None,
            )

        response = await _fill_hot_cached_payload(
            hot_key,
            model_type=CompanyOilScenarioResponse,
            tags=hot_tags,
            fill=lambda: _run_with_session_binding(session, build_oil_scenario_payload),
        )
        not_modified = _apply_conditional_headers(
            request,
            http_response,
            response,
            last_modified=response.company.last_checked if response.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return response


@main_bound
def latest_model_evaluation(
    request: Request,
    http_response: Response,
    suite_key: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> ModelEvaluationResponse:
    run = get_latest_model_evaluation_run(session, suite_key=suite_key)
    if run is None:
        payload = ModelEvaluationResponse(run=None, **_empty_provenance_contract("model_evaluation_missing"))
        return payload

    serialized_run = serialize_model_evaluation_run(run)
    summary = serialized_run.get("summary") if isinstance(serialized_run.get("summary"), dict) else {}
    provenance_mode = str(summary.get("provenance_mode") or "historical_cache")
    evaluation_focus = str(summary.get("evaluation_focus") or "general")
    as_of_value = summary.get("latest_as_of")
    last_refreshed_at = run.completed_at or run.created_at

    if provenance_mode == "synthetic_fixture":
        usages = [
            SourceUsage(
                source_id="ft_model_evaluation_fixture",
                role="derived",
                as_of=as_of_value,
                last_refreshed_at=last_refreshed_at,
            )
        ]
        confidence_flags = ["synthetic_fixture_suite"]
    elif evaluation_focus == "oil_overlay":
        usages = [
            SourceUsage(
                source_id="ft_model_evaluation_harness",
                role="derived",
                as_of=as_of_value,
                last_refreshed_at=last_refreshed_at,
            ),
            SourceUsage(
                source_id="ft_oil_scenario_overlay",
                role="derived",
                as_of=as_of_value,
                last_refreshed_at=last_refreshed_at,
            ),
            SourceUsage(
                source_id="ft_model_engine",
                role="supplemental",
                as_of=as_of_value,
                last_refreshed_at=last_refreshed_at,
            ),
            SourceUsage(
                source_id="sec_edgar",
                role="primary",
                as_of=as_of_value,
                last_refreshed_at=last_refreshed_at,
            ),
            SourceUsage(
                source_id="sec_companyfacts",
                role="primary",
                as_of=as_of_value,
                last_refreshed_at=last_refreshed_at,
            ),
            SourceUsage(
                source_id="eia_petroleum_spot_prices",
                role="primary",
                as_of=as_of_value,
                last_refreshed_at=last_refreshed_at,
            ),
            SourceUsage(
                source_id="eia_steo",
                role="primary",
                as_of=as_of_value,
                last_refreshed_at=last_refreshed_at,
            ),
            SourceUsage(
                source_id="yahoo_finance",
                role="fallback",
                as_of=summary.get("latest_future_as_of") or as_of_value,
                last_refreshed_at=last_refreshed_at,
            ),
        ]
        confidence_flags = []
    else:
        usages = [
            SourceUsage(
                source_id="ft_model_evaluation_harness",
                role="derived",
                as_of=as_of_value,
                last_refreshed_at=last_refreshed_at,
            ),
            SourceUsage(
                source_id="sec_companyfacts",
                role="primary",
                as_of=as_of_value,
                last_refreshed_at=last_refreshed_at,
            ),
            SourceUsage(
                source_id="yahoo_finance",
                role="fallback",
                as_of=summary.get("latest_future_as_of") or as_of_value,
                last_refreshed_at=last_refreshed_at,
            ),
        ]
        confidence_flags = []

    payload = ModelEvaluationResponse(
        run=ModelEvaluationRunPayload.model_validate(serialized_run),
        **_build_provenance_contract(
            usages,
            as_of=as_of_value,
            last_refreshed_at=last_refreshed_at,
            confidence_flags=confidence_flags,
        ),
    )
    not_modified = _apply_conditional_headers(
        request,
        http_response,
        payload,
        last_modified=last_refreshed_at,
    )
    if not_modified is not None:
        return not_modified  # type: ignore[return-value]
    return payload


__all__ = [
    "company_models",
    "list_formulas",
    "get_formula",
    "company_oil_scenario",
    "company_oil_scenario_overlay",
    "latest_model_evaluation",
]
