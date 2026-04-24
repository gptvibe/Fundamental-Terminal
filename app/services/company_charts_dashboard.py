from __future__ import annotations

from datetime import date as DateType, datetime, time as TimeType, timezone
from math import isfinite
from statistics import fmean
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.contracts.common import CompanyPayload, DataQualityDiagnosticsPayload, RefreshState
from app.contracts.company_charts import (
    CompanyChartsAssumptionItemPayload,
    CompanyChartsAssumptionsCardPayload,
    CompanyChartsCardPayload,
    CompanyChartsCardsPayload,
    CompanyChartsComparisonCardPayload,
    CompanyChartsComparisonItemPayload,
    CompanyChartsDashboardResponse,
    CompanyChartsDriverControlMetadataPayload,
    CompanyChartsDriverCardPayload,
    CompanyChartsEventOverlayPayload,
    CompanyChartsEventPayload,
    CompanyChartsFactorValuePayload,
    CompanyChartsFactorsPayload,
    CompanyChartsForecastDiagnosticsPayload,
    CompanyChartsFormulaInputPayload,
    CompanyChartsFormulaTracePayload,
    CompanyChartsForecastAccuracyAggregatePayload,
    CompanyChartsForecastAccuracyMetricPayload,
    CompanyChartsForecastAccuracyResponse,
    CompanyChartsForecastAccuracySamplePayload,
    CompanyChartsLegendItemPayload,
    CompanyChartsLegendPayload,
    CompanyChartsMethodologyPayload,
    CompanyChartsProjectedRowPayload,
    CompanyChartsProjectionStudioPayload,
    CompanyChartsQuarterChangeItemPayload,
    CompanyChartsQuarterChangePayload,
    CompanyChartsScheduleSectionPayload,
    CompanyChartsScoreComponentPayload,
    CompanyChartsScoreBadgePayload,
    CompanyChartsSensitivityCellPayload,
    CompanyChartsSeriesPayload,
    CompanyChartsSeriesPointPayload,
    CompanyChartsSummaryPayload,
    CompanyChartsWhatIfImpactMetricPayload,
    CompanyChartsWhatIfImpactSummaryPayload,
    CompanyChartsWhatIfOverridePayload,
    CompanyChartsWhatIfPayload,
    CompanyChartsWhatIfRequest,
)
from app.models import Company, CompanyChartsDashboardSnapshot
from app.source_registry import SourceUsage, build_provenance_entries, build_source_mix
from app.services.cache_queries import (
    get_company_capital_markets_events,
    get_company_earnings_model_points,
    get_company_earnings_releases,
    get_company_financials,
    get_company_financial_restatements,
    get_company_snapshot,
    select_point_in_time_financials,
)
from app.services.company_charts_driver_model import build_driver_forecast_bundle
from app.services.refresh_state import mark_dataset_checked


CHARTS_DASHBOARD_SCHEMA_VERSION = "company_charts_dashboard_v9"
CHARTS_FORECAST_ACCURACY_SCHEMA_VERSION = "charts_forecast_accuracy_v1"
CHARTS_DASHBOARD_INPUT_FINGERPRINT_VERSION = "company-charts-dashboard-inputs-v9"
ANNUAL_FILING_TYPES = {"10-K", "20-F", "40-F"}
FORECAST_STABILITY_MIN_SCORE = 20
FORECAST_STABILITY_MAX_SCORE = 90
FORECAST_STABILITY_BASE_SCORE = 52
FORECAST_STABILITY_TARGET_HISTORY_PERIODS = 5
FORECAST_STABILITY_THIN_HISTORY_PERIODS = 3
FORECAST_STABILITY_HISTORY_GAP_PENALTY = 6
FORECAST_STABILITY_VOLATILITY_WINDOW = 4
FORECAST_STABILITY_MISSING_REVENUE_POINT_PENALTY = 4
FORECAST_STABILITY_MISSING_QUALITY_SIGNAL_PENALTY = 6
FORECAST_STABILITY_LOW_QUALITY_PENALTY = 4
FORECAST_STABILITY_BACKTEST_HORIZONS = (1, 2, 3)
FORECAST_STABILITY_BACKTEST_WEIGHTS = {1: 0.5, 2: 0.3, 3: 0.2}
FORECAST_STABILITY_BACKTEST_METRIC_WEIGHTS = {
    "revenue": 0.5,
    "operating_income": 0.2,
    "eps": 0.15,
    "free_cash_flow": 0.15,
}
FORECAST_STABILITY_BACKTEST_METRIC_LABELS = {
    "revenue": "Revenue",
    "operating_income": "EBIT",
    "eps": "EPS",
    "free_cash_flow": "FCF",
}
FORECAST_STABILITY_VOLATILITY_BANDS = (
    (0.08, "stable"),
    (0.18, "moderate"),
    (0.3, "elevated"),
)
FORECAST_STABILITY_SECTOR_TEMPLATES = {
    "technology": {"label": "Technology", "tight": 0.10, "moderate": 0.18, "wide": 0.30},
    "communication services": {"label": "Communication Services", "tight": 0.11, "moderate": 0.20, "wide": 0.32},
    "consumer cyclical": {"label": "Consumer Cyclical", "tight": 0.12, "moderate": 0.22, "wide": 0.35},
    "consumer defensive": {"label": "Consumer Defensive", "tight": 0.09, "moderate": 0.17, "wide": 0.28},
    "industrials": {"label": "Industrials", "tight": 0.11, "moderate": 0.20, "wide": 0.32},
    "energy": {"label": "Energy", "tight": 0.16, "moderate": 0.28, "wide": 0.42},
    "materials": {"label": "Materials", "tight": 0.14, "moderate": 0.25, "wide": 0.38},
    "financial services": {"label": "Financial Services", "tight": 0.10, "moderate": 0.18, "wide": 0.29},
    "real estate": {"label": "Real Estate", "tight": 0.10, "moderate": 0.19, "wide": 0.30},
    "healthcare": {"label": "Healthcare", "tight": 0.10, "moderate": 0.18, "wide": 0.30},
    "utilities": {"label": "Utilities", "tight": 0.08, "moderate": 0.15, "wide": 0.25},
    "default": {"label": "General", "tight": 0.11, "moderate": 0.20, "wide": 0.32},
}
REVENUE_FORECAST_GROWTH_FLOOR = -0.18
REVENUE_FORECAST_GROWTH_CAP = 0.30
REVENUE_FORECAST_TERMINAL_GROWTH = 0.03
REVENUE_FORECAST_REVERSION_SPEED = 0.45
REVENUE_FORECAST_RECENT_WEIGHTS = (0.2, 0.3, 0.5)
REVENUE_FORECAST_RECENT_BLEND_WEIGHT = 0.65
REVENUE_FORECAST_CAGR_BLEND_WEIGHT = 0.35
MARGIN_FORECAST_NORMALIZATION_WINDOW = 3
MARGIN_FORECAST_PROFILES = {
    "operating": {"floor": -0.15, "cap": 0.45, "normalized_recent_weight": 0.35, "reversion_weights": (0.35, 0.65, 0.85)},
    "net_income": {"floor": -0.18, "cap": 0.25, "normalized_recent_weight": 0.25, "reversion_weights": (0.45, 0.75, 0.9)},
    "cash_flow": {"floor": -0.2, "cap": 0.3, "normalized_recent_weight": 0.3, "reversion_weights": (0.4, 0.65, 0.85)},
    "capex": {"floor": -0.02, "cap": 0.18, "normalized_recent_weight": 0.3, "reversion_weights": (0.3, 0.55, 0.75)},
}
DILUTED_SHARE_FORECAST_CHANGE_FLOOR = -0.05
DILUTED_SHARE_FORECAST_CHANGE_CAP = 0.06
DILUTED_SHARE_FORECAST_REVERSION_SPEED = 0.5
PROJECTION_STUDIO_REPORTED_PERIODS = 3
PROJECTION_STUDIO_SENSITIVITY_DELTAS = (-0.04, -0.02, 0.0, 0.02, 0.04)
FORECAST_ACCURACY_MAX_BACKTESTS = 6
FORECAST_ACCURACY_MIN_SAMPLE_COUNT = 2
FORECAST_ACCURACY_METRICS: tuple[tuple[str, str, str], ...] = (
    ("revenue", "Revenue", "usd"),
    ("operating_income", "Operating Income", "usd"),
    ("eps", "Diluted EPS", "usd_per_share"),
    ("free_cash_flow", "Free Cash Flow", "usd"),
)
CHART_EVENT_TYPES: tuple[str, ...] = (
    "earnings",
    "guidance",
    "buyback",
    "major_m_and_a",
    "restatement",
)
DEFAULT_ENABLED_CHART_EVENT_TYPES: tuple[str, ...] = (
    "earnings",
    "guidance",
    "restatement",
)
MAX_CHART_EVENTS = 18


def get_company_charts_dashboard_snapshot(session: Session, company_id: int, *, as_of: datetime | None = None, schema_version: str = CHARTS_DASHBOARD_SCHEMA_VERSION) -> CompanyChartsDashboardSnapshot | None:
    statement = select(CompanyChartsDashboardSnapshot).where(
        CompanyChartsDashboardSnapshot.company_id == company_id,
        CompanyChartsDashboardSnapshot.as_of_key == _as_of_key(as_of),
        CompanyChartsDashboardSnapshot.schema_version == schema_version,
    )
    return session.execute(statement).scalar_one_or_none()


def get_company_charts_forecast_accuracy_snapshot(
    session: Session,
    company_id: int,
    *,
    as_of: datetime | None = None,
    schema_version: str = CHARTS_FORECAST_ACCURACY_SCHEMA_VERSION,
) -> CompanyChartsDashboardSnapshot | None:
    statement = select(CompanyChartsDashboardSnapshot).where(
        CompanyChartsDashboardSnapshot.company_id == company_id,
        CompanyChartsDashboardSnapshot.as_of_key == _as_of_key(as_of),
        CompanyChartsDashboardSnapshot.schema_version == schema_version,
    )
    return session.execute(statement).scalar_one_or_none()


def build_company_charts_dashboard_response(
    session: Session,
    company_id: int,
    *,
    as_of: datetime | None = None,
    generated_at: datetime | None = None,
    payload_version: str | None = None,
    what_if_request: CompanyChartsWhatIfRequest | None = None,
) -> CompanyChartsDashboardResponse | None:
    company = session.get(Company, company_id)
    if company is None:
        return None

    snapshot = get_company_snapshot(session, company.ticker)
    financials = get_company_financials(session, company_id)
    if as_of is not None:
        financials = select_point_in_time_financials(financials, as_of)
    annuals = _annual_statements(financials)
    # No-lookahead rule: every earnings-model diagnostic used by charts must honor
    # the same `as_of` cutoff as statement history.
    earnings_points = get_company_earnings_model_points(session, company_id, limit=8, as_of=as_of)
    earnings_releases = get_company_earnings_releases(session, company_id, limit=24, as_of=as_of)
    restatements = get_company_financial_restatements(session, company_id, limit=200, as_of=as_of)
    capital_markets_events = _load_capital_markets_events(session, company_id, as_of=as_of)
    baseline_driver_bundle = build_driver_forecast_bundle(annuals, earnings_releases, company=company)
    requested_overrides = dict(what_if_request.overrides) if what_if_request is not None else {}
    driver_bundle = (
        build_driver_forecast_bundle(annuals, earnings_releases, overrides=requested_overrides, company=company)
        if requested_overrides
        else baseline_driver_bundle
    )
    timestamp = generated_at or datetime.now(timezone.utc)
    source_inputs_last_refreshed_at = _merge(
        _latest_checked(annuals),
        _latest_checked(earnings_points),
        _latest_checked(earnings_releases),
        _latest_checked(restatements),
        _latest_checked(capital_markets_events),
    )

    revenue_actual = _actual_series(annuals, "revenue")
    growth_actual = _growth_series(revenue_actual, "actual")
    hist_3y = _cagr([_point_value(point) for point in revenue_actual[-4:]]) if len(revenue_actual) >= 4 else None
    forecast_state = _build_forecast_state(annuals, revenue_actual, growth_actual, hist_3y, driver_bundle, company.name)
    exp_1y = forecast_state["exp_1y"]
    exp_3y = forecast_state["exp_3y"]
    profit_series = forecast_state["profit_series"]
    cash_series = forecast_state["cash_series"]
    eps_actual = forecast_state["eps_actual"]
    revenue_outlook_bridge_card = _build_revenue_outlook_bridge_card(revenue_actual, driver_bundle)
    margin_path_card = _build_margin_path_card(annuals, forecast_state["revenue_card"], profit_series, driver_bundle)
    fcf_outlook_card = _build_fcf_outlook_card(annuals, profit_series, cash_series, driver_bundle)

    quality_score = _score(
        _blend(
            _safe_divide(_statement_value(annuals[-1], "operating_income") if annuals else None, _statement_value(annuals[-1], "revenue") if annuals else None),
            _safe_divide(_statement_value(annuals[-1], "free_cash_flow") if annuals else None, _statement_value(annuals[-1], "revenue") if annuals else None),
        ),
        -0.05,
        0.35,
    )
    momentum_score = _score(_blend(exp_1y, getattr(earnings_points[-1], "earnings_momentum_drift", None) if earnings_points else None), -0.1, 0.3)
    growth_score = _score(_blend(hist_3y, exp_1y), -0.1, 0.35)
    forecast_stability = _forecast_stability_profile(
        session,
        company,
        annuals,
        revenue_actual,
        earnings_points,
        earnings_releases,
        restatements,
        driver_bundle,
    )
    confidence_score = int(forecast_stability.final_score or 0)

    factors = CompanyChartsFactorsPayload(
        primary=CompanyChartsFactorValuePayload(key="growth", label="Growth", score=growth_score, normalized_score=_norm(growth_score), tone=_tone(growth_score), detail=str(forecast_state["growth_detail"])),
        supporting=[
            CompanyChartsFactorValuePayload(key="quality", label="Quality", score=quality_score, normalized_score=_norm(quality_score), tone=_tone(quality_score), detail="Margins and cash conversion from reported periods."),
            CompanyChartsFactorValuePayload(key="momentum", label="Momentum", score=momentum_score, normalized_score=_norm(momentum_score), tone=_tone(momentum_score), detail=str(forecast_state["momentum_detail"])),
            CompanyChartsFactorValuePayload(key="value", label="Value", score=None, normalized_score=None, tone="unavailable", unavailable_reason="Hidden until a trustworthy valuation input set is available."),
            CompanyChartsFactorValuePayload(
                key=forecast_stability.score_key,
                label=forecast_stability.score_name,
                score=confidence_score,
                normalized_score=_norm(confidence_score),
                tone=_tone(confidence_score),
                detail=forecast_stability.summary,
            ),
        ],
    )

    diagnostics = DataQualityDiagnosticsPayload(
        coverage_ratio=round(sum(1 for item in [revenue_actual, profit_series, cash_series, eps_actual] if item) / 4, 3),
        fallback_ratio=0.0,
        stale_flags=(["limited_annual_history"] if len(annuals) < 3 else []),
        parser_confidence=round(float(getattr(earnings_points[-1], "quality_score", 0)), 3) if earnings_points and getattr(earnings_points[-1], "quality_score", None) is not None else None,
        missing_field_flags=[flag for flag, present in [("revenue_history_missing", bool(revenue_actual)), ("profit_history_missing", bool(profit_series)), ("cash_flow_history_missing", bool(cash_series)), ("eps_history_missing", bool(eps_actual))] if not present],
        reconciliation_penalty=None,
        reconciliation_disagreement_count=0,
    )

    latest_period = annuals[-1].period_end if annuals else None
    company_payload = CompanyPayload(
        ticker=company.ticker,
        cik=company.cik,
        name=company.name,
        sector=company.sector,
        market_sector=company.market_sector,
        market_industry=company.market_industry,
        strict_official_mode=True,
        last_checked=getattr(snapshot, "last_checked", None),
        cache_state=getattr(snapshot, "cache_state", "fresh") if snapshot is not None else "fresh",
    )
    provenance = build_provenance_entries(
        [
            usage
            for usage in [
                SourceUsage(
                    "ft_company_charts_dashboard",
                    role="derived",
                    as_of=latest_period or as_of,
                    last_refreshed_at=source_inputs_last_refreshed_at or timestamp,
                ),
                SourceUsage("sec_companyfacts", role="primary", as_of=latest_period or as_of, last_refreshed_at=_latest_checked(annuals)) if annuals else None,
                SourceUsage("sec_edgar", role="primary", as_of=latest_period or as_of, last_refreshed_at=_latest_checked(earnings_releases)) if earnings_releases else None,
                SourceUsage("ft_model_engine", role="derived", as_of=latest_period or as_of, last_refreshed_at=_latest_checked(earnings_points)) if earnings_points else None,
            ]
            if usage is not None
        ]
    )
    title = "Growth Outlook"
    thesis = str(forecast_state["thesis"])
    secondary_badges = [
        CompanyChartsScoreBadgePayload(key=item.key, label=item.label, score=item.score, tone=item.tone, detail=item.detail, unavailable_reason=item.unavailable_reason)
        for item in factors.supporting
    ]
    stability_label = f"Forecast stability: {_stability_label(confidence_score)}"
    forecast_methodology = CompanyChartsMethodologyPayload(
        version=CHARTS_DASHBOARD_SCHEMA_VERSION,
        label=str(forecast_state["methodology_label"]),
        summary=str(forecast_state["methodology_summary"]),
        disclaimer=str(forecast_state["methodology_disclaimer"]),
        score_name=forecast_stability.score_name,
        heuristic=bool(forecast_state["methodology_heuristic"]),
        score_components=[component.label for component in forecast_stability.components],
        stability_label=stability_label,
        confidence_label=stability_label,
    )
    projection_studio = _build_projection_studio_payload(annuals, driver_bundle, forecast_methodology)
    event_overlay = _build_chart_event_overlay(
        earnings_releases=earnings_releases,
        restatements=restatements,
        capital_markets_events=capital_markets_events,
        annuals=annuals,
    )
    quarter_change = _build_quarter_change_payload(
        annuals=annuals,
        event_overlay=event_overlay,
        forecast_state=forecast_state,
    )
    what_if_payload = (
        _build_company_charts_what_if_payload(baseline_driver_bundle, driver_bundle)
        if what_if_request is not None
        else None
    )

    return CompanyChartsDashboardResponse(
        company=company_payload,
        title=title,
        build_state="ready",
        build_status="Charts dashboard ready.",
        summary=CompanyChartsSummaryPayload(
            headline=title,
            primary_score=CompanyChartsScoreBadgePayload(key="growth", label="Growth", score=growth_score, tone=_tone(growth_score), detail=factors.primary.detail if factors.primary else None),
            secondary_badges=secondary_badges,
            thesis=thesis,
            unavailable_notes=[
                "Forecast values are dashed or muted and never presented as reported results.",
                "Forecast stability is calibrated from point-in-time revenue, EBIT, EPS, and FCF walk-forward errors plus explicit risk penalties, not a probability or confidence interval.",
                "Value stays explicitly unavailable until a trustworthy valuation input set exists.",
            ],
            freshness_badges=[
                f"Updated {(source_inputs_last_refreshed_at or timestamp).date().isoformat()}",
                f"Reported through FY{latest_period.year}" if latest_period is not None else "Awaiting annual history",
            ],
            source_badges=list(forecast_state["source_badges"]),
        ),
        factors=factors,
        legend=CompanyChartsLegendPayload(title="Actual vs Forecast", items=[
            CompanyChartsLegendItemPayload(key="actual", label="Reported", style="solid", tone="actual", description="Historical official filings."),
            CompanyChartsLegendItemPayload(key="forecast", label="Forecast", style="dashed", tone="forecast", description="Internal projection, not reported results."),
        ]),
        cards=CompanyChartsCardsPayload(
            revenue=forecast_state["revenue_card"],
            revenue_growth=forecast_state["growth_card"],
            profit_metric=CompanyChartsCardPayload(key="profit_metric", title="Profit Metrics", subtitle=str(forecast_state["profit_subtitle"]), metric_label="Profit", unit_label="USD", empty_state="Profit history is unavailable for the selected periods." if not profit_series else None, series=profit_series),
            cash_flow_metric=CompanyChartsCardPayload(key="cash_flow_metric", title="Cash Flow Metrics", subtitle=str(forecast_state["cash_subtitle"]), metric_label="Cash Flow", unit_label="USD", empty_state="Cash flow history is unavailable for the selected periods." if not cash_series else None, series=cash_series),
            eps=forecast_state["eps_card"],
            growth_summary=forecast_state["growth_summary_card"],
            forecast_assumptions=forecast_state["assumptions_card"],
            forecast_calculations=forecast_state["calculations_card"],
            revenue_outlook_bridge=revenue_outlook_bridge_card,
            margin_path=margin_path_card,
            fcf_outlook=fcf_outlook_card,
        ),
        event_overlay=event_overlay,
        quarter_change=quarter_change,
        forecast_methodology=forecast_methodology,
        forecast_diagnostics=forecast_stability,
        projection_studio=projection_studio,
        what_if=what_if_payload,
        payload_version=payload_version or CHARTS_DASHBOARD_SCHEMA_VERSION,
        refresh=RefreshState(triggered=False, reason="fresh", ticker=company.ticker, job_id=None),
        diagnostics=diagnostics,
        provenance=provenance,
        as_of=_as_of_text(as_of, latest_period),
        last_refreshed_at=source_inputs_last_refreshed_at or timestamp,
        source_mix=build_source_mix(provenance),
        confidence_flags=sorted(set(list(diagnostics.stale_flags) + list(diagnostics.missing_field_flags) + (["reduced_forecast_stability"] if confidence_score < 60 else []))),
    )


def recompute_and_persist_company_charts_dashboard(session: Session, company_id: int, *, checked_at: datetime | None = None, as_of: datetime | None = None, payload_version_hash: str | None = None) -> CompanyChartsDashboardResponse | None:
    timestamp = checked_at or datetime.now(timezone.utc)
    payload = build_company_charts_dashboard_response(session, company_id, as_of=as_of, generated_at=timestamp)
    if payload is None:
        mark_dataset_checked(session, company_id, "charts_dashboard", checked_at=timestamp, success=True, payload_version_hash=payload_version_hash or CHARTS_DASHBOARD_SCHEMA_VERSION, invalidate_hot_cache=True)
        return None
    statement = insert(CompanyChartsDashboardSnapshot).values(company_id=company_id, as_of_key=_as_of_key(as_of), as_of_value=as_of, schema_version=CHARTS_DASHBOARD_SCHEMA_VERSION, payload=payload.model_dump(mode="json"), last_updated=timestamp, last_checked=timestamp)
    statement = statement.on_conflict_do_update(
        constraint="uq_company_charts_dashboard_snapshots_company_asof_schema",
        set_={"as_of_value": statement.excluded.as_of_value, "payload": statement.excluded.payload, "last_updated": statement.excluded.last_updated, "last_checked": statement.excluded.last_checked},
    )
    session.execute(statement)
    mark_dataset_checked(session, company_id, "charts_dashboard", checked_at=timestamp, success=True, payload_version_hash=payload_version_hash or payload.payload_version, invalidate_hot_cache=True)
    return payload


def recompute_and_persist_company_charts_forecast_accuracy(
    session: Session,
    company_id: int,
    *,
    checked_at: datetime | None = None,
    as_of: datetime | None = None,
    payload_version_hash: str | None = None,
    max_backtests: int = FORECAST_ACCURACY_MAX_BACKTESTS,
) -> CompanyChartsForecastAccuracyResponse | None:
    timestamp = checked_at or datetime.now(timezone.utc)
    payload = build_company_charts_forecast_accuracy_response(
        session,
        company_id,
        as_of=as_of,
        generated_at=timestamp,
        max_backtests=max_backtests,
    )
    if payload is None:
        mark_dataset_checked(
            session,
            company_id,
            "charts_forecast_accuracy",
            checked_at=timestamp,
            success=True,
            payload_version_hash=payload_version_hash or CHARTS_FORECAST_ACCURACY_SCHEMA_VERSION,
            invalidate_hot_cache=True,
        )
        return None

    statement = insert(CompanyChartsDashboardSnapshot).values(
        company_id=company_id,
        as_of_key=_as_of_key(as_of),
        as_of_value=as_of,
        schema_version=CHARTS_FORECAST_ACCURACY_SCHEMA_VERSION,
        payload=payload.model_dump(mode="json"),
        last_updated=timestamp,
        last_checked=timestamp,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_company_charts_dashboard_snapshots_company_asof_schema",
        set_={
            "as_of_value": statement.excluded.as_of_value,
            "payload": statement.excluded.payload,
            "last_updated": statement.excluded.last_updated,
            "last_checked": statement.excluded.last_checked,
        },
    )
    session.execute(statement)
    mark_dataset_checked(
        session,
        company_id,
        "charts_forecast_accuracy",
        checked_at=timestamp,
        success=True,
        payload_version_hash=payload_version_hash or CHARTS_FORECAST_ACCURACY_SCHEMA_VERSION,
        invalidate_hot_cache=True,
    )
    return payload


def build_company_charts_forecast_accuracy_response(
    session: Session,
    company_id: int,
    *,
    as_of: datetime | None = None,
    generated_at: datetime | None = None,
    max_backtests: int = FORECAST_ACCURACY_MAX_BACKTESTS,
) -> CompanyChartsForecastAccuracyResponse | None:
    company = session.get(Company, company_id)
    if company is None:
        return None

    snapshot = get_company_snapshot(session, company.ticker)
    timestamp = generated_at or datetime.now(timezone.utc)
    financials = get_company_financials(session, company_id)
    if as_of is not None:
        financials = select_point_in_time_financials(financials, as_of)
    annuals = _annual_statements(financials)
    earnings_releases = get_company_earnings_releases(session, company_id, limit=36, as_of=as_of)

    samples = _build_forecast_accuracy_samples(
        company,
        financials,
        earnings_releases,
        max_backtests=max_backtests,
    )
    metric_payloads = _build_forecast_accuracy_metric_payloads(samples)
    aggregate_payload = _build_forecast_accuracy_aggregate_payload(samples)
    insufficient_reason = _forecast_accuracy_insufficient_reason(annuals, aggregate_payload.sample_count)
    status = "ok" if insufficient_reason is None else "insufficient_history"

    source_inputs_last_refreshed_at = _merge(
        _latest_checked(annuals),
        _latest_checked(earnings_releases),
    )
    company_payload = CompanyPayload(
        ticker=company.ticker,
        cik=company.cik,
        name=company.name,
        sector=company.sector,
        market_sector=company.market_sector,
        market_industry=company.market_industry,
        strict_official_mode=True,
        last_checked=getattr(snapshot, "last_checked", None),
        cache_state=getattr(snapshot, "cache_state", "fresh") if snapshot is not None else "fresh",
    )
    latest_period = annuals[-1].period_end if annuals else None
    provenance = build_provenance_entries(
        [
            usage
            for usage in [
                SourceUsage(
                    "ft_company_charts_dashboard",
                    role="derived",
                    as_of=latest_period or as_of,
                    last_refreshed_at=source_inputs_last_refreshed_at or timestamp,
                ),
                SourceUsage("sec_companyfacts", role="primary", as_of=latest_period or as_of, last_refreshed_at=_latest_checked(annuals)) if annuals else None,
                SourceUsage("sec_edgar", role="primary", as_of=latest_period or as_of, last_refreshed_at=_latest_checked(earnings_releases)) if earnings_releases else None,
            ]
            if usage is not None
        ]
    )

    diagnostics = DataQualityDiagnosticsPayload(
        coverage_ratio=_round(float(aggregate_payload.sample_count) / max(1, max_backtests * len(FORECAST_ACCURACY_METRICS)), 3),
        fallback_ratio=0.0,
        stale_flags=[],
        parser_confidence=None,
        missing_field_flags=[] if status == "ok" else ["forecast_accuracy_insufficient_history"],
        reconciliation_penalty=None,
        reconciliation_disagreement_count=0,
    )

    return CompanyChartsForecastAccuracyResponse(
        company=company_payload,
        status=status,
        insufficient_history_reason=insufficient_reason,
        max_backtests=max_backtests,
        metrics=metric_payloads,
        aggregate=aggregate_payload,
        samples=samples,
        refresh=RefreshState(triggered=False, reason="fresh", ticker=company.ticker, job_id=None),
        diagnostics=diagnostics,
        provenance=provenance,
        as_of=_as_of_text(as_of, latest_period),
        last_refreshed_at=source_inputs_last_refreshed_at or timestamp,
        source_mix=build_source_mix(provenance),
        confidence_flags=(["forecast_accuracy_insufficient_history"] if status != "ok" else []),
    )


def _build_forecast_accuracy_samples(
    company: Company,
    financials: list[Any],
    earnings_releases: list[Any],
    *,
    max_backtests: int,
) -> list[CompanyChartsForecastAccuracySamplePayload]:
    annuals = _annual_statements(financials)
    if len(annuals) < 3:
        return []

    metric_actuals_by_year = {
        metric: {
            statement.period_end.year: value
            for statement in annuals
            if getattr(statement, "period_end", None) is not None
            for value in [_actual_metric_value(statement, metric)]
            if value is not None
        }
        for metric, _label, _unit in FORECAST_ACCURACY_METRICS
    }

    samples: list[CompanyChartsForecastAccuracySamplePayload] = []
    realized_snapshot_count = 0
    for cutoff_index in range(len(annuals) - 2, 0, -1):
        if realized_snapshot_count >= max_backtests:
            break

        anchor_statement = annuals[cutoff_index]
        cutoff_as_of = _statement_effective_at(anchor_statement)
        if cutoff_as_of is None:
            continue

        visible_financials = select_point_in_time_financials(financials, cutoff_as_of)
        visible_annuals = _annual_statements(visible_financials)
        if len(visible_annuals) < 2:
            continue

        anchor_year = visible_annuals[-1].period_end.year
        target_year = anchor_year + 1
        visible_releases = _visible_releases_as_of(earnings_releases, cutoff_as_of)
        revenue_actual = _actual_series(visible_annuals, "revenue")
        if len(revenue_actual) < 2:
            continue

        driver_bundle = build_driver_forecast_bundle(visible_annuals, visible_releases, company=company)
        growth_actual = _growth_series(revenue_actual, "actual")
        hist_3y = _cagr([_point_value(point) for point in revenue_actual[-4:]]) if len(revenue_actual) >= 4 else None
        forecast_state = _build_forecast_state(visible_annuals, revenue_actual, growth_actual, hist_3y, driver_bundle, company.name)

        realized_snapshot = False
        cutoff_as_of_text = cutoff_as_of.isoformat()
        for metric, label, unit in FORECAST_ACCURACY_METRICS:
            predicted_value = _forecast_metric_value_for_year(forecast_state, metric, target_year)
            actual_value = metric_actuals_by_year[metric].get(target_year)
            if predicted_value is None or actual_value is None:
                continue

            anchor_actual_value = _actual_metric_value(visible_annuals[-1], metric)
            absolute_error = abs(float(predicted_value) - float(actual_value))
            absolute_percentage_error = _absolute_percentage_error(predicted_value, actual_value)
            directionally_correct = _directional_accuracy_sample(predicted_value, actual_value, anchor_actual_value)
            samples.append(
                CompanyChartsForecastAccuracySamplePayload(
                    metric_key=metric,
                    metric_label=label,
                    unit=unit,
                    anchor_fiscal_year=anchor_year,
                    target_fiscal_year=target_year,
                    cutoff_as_of=cutoff_as_of_text,
                    predicted_value=_round(predicted_value, 6),
                    actual_value=_round(actual_value, 6),
                    absolute_error=_round(absolute_error, 6),
                    absolute_percentage_error=_round(absolute_percentage_error, 6),
                    directionally_correct=directionally_correct,
                )
            )
            realized_snapshot = True

        if realized_snapshot:
            realized_snapshot_count += 1

    return samples


def _forecast_metric_value_for_year(forecast_state: dict[str, Any], metric: str, fiscal_year: int) -> float | None:
    points = _forecast_metric_points(forecast_state, metric)
    for point in points:
        if point.fiscal_year != fiscal_year:
            continue
        return _point_value(point)
    return None


def _directional_accuracy_sample(predicted: float, actual: float, anchor_actual: float | None) -> bool | None:
    if anchor_actual is None:
        return None
    predicted_delta = float(predicted) - float(anchor_actual)
    actual_delta = float(actual) - float(anchor_actual)
    if predicted_delta == 0 and actual_delta == 0:
        return True
    if predicted_delta == 0 or actual_delta == 0:
        return None
    return (predicted_delta > 0 and actual_delta > 0) or (predicted_delta < 0 and actual_delta < 0)


def _build_forecast_accuracy_metric_payloads(
    samples: list[CompanyChartsForecastAccuracySamplePayload],
) -> list[CompanyChartsForecastAccuracyMetricPayload]:
    payloads: list[CompanyChartsForecastAccuracyMetricPayload] = []
    for metric, label, unit in FORECAST_ACCURACY_METRICS:
        metric_samples = [sample for sample in samples if sample.metric_key == metric]
        abs_errors = [float(sample.absolute_error) for sample in metric_samples if sample.absolute_error is not None]
        ape_values = [float(sample.absolute_percentage_error) for sample in metric_samples if sample.absolute_percentage_error is not None]
        directional_values = [sample.directionally_correct for sample in metric_samples if sample.directionally_correct is not None]
        directional_correct = sum(1 for value in directional_values if value)
        payloads.append(
            CompanyChartsForecastAccuracyMetricPayload(
                key=metric,
                label=label,
                unit=unit,
                sample_count=len(metric_samples),
                directional_sample_count=len(directional_values),
                mean_absolute_error=_round(sum(abs_errors) / len(abs_errors), 6) if abs_errors else None,
                mean_absolute_percentage_error=_round(sum(ape_values) / len(ape_values), 6) if ape_values else None,
                directional_accuracy=_round(float(directional_correct) / len(directional_values), 6) if directional_values else None,
            )
        )
    return payloads


def _build_forecast_accuracy_aggregate_payload(
    samples: list[CompanyChartsForecastAccuracySamplePayload],
) -> CompanyChartsForecastAccuracyAggregatePayload:
    snapshot_keys = {
        (sample.anchor_fiscal_year, sample.target_fiscal_year, sample.cutoff_as_of)
        for sample in samples
    }
    ape_values = [float(sample.absolute_percentage_error) for sample in samples if sample.absolute_percentage_error is not None]
    directional_values = [sample.directionally_correct for sample in samples if sample.directionally_correct is not None]
    directional_correct = sum(1 for value in directional_values if value)
    return CompanyChartsForecastAccuracyAggregatePayload(
        snapshot_count=len(snapshot_keys),
        sample_count=len(samples),
        directional_sample_count=len(directional_values),
        mean_absolute_percentage_error=_round(sum(ape_values) / len(ape_values), 6) if ape_values else None,
        directional_accuracy=_round(float(directional_correct) / len(directional_values), 6) if directional_values else None,
    )


def _forecast_accuracy_insufficient_reason(annuals: list[Any], sample_count: int) -> str | None:
    if len(annuals) < 3:
        return "Need at least three annual periods to evaluate one-year-forward forecast accuracy without lookahead."
    if sample_count < FORECAST_ACCURACY_MIN_SAMPLE_COUNT:
        return "Insufficient realized one-year-forward samples for a stable forecast-accuracy estimate."
    return None


def _build_forecast_state(
    annuals: list[Any],
    revenue_actual: list[CompanyChartsSeriesPointPayload],
    growth_actual: list[CompanyChartsSeriesPointPayload],
    hist_3y: float | None,
    driver_bundle: Any | None,
    company_name: str,
) -> dict[str, Any]:
    engine_mode = getattr(driver_bundle, "engine_mode", None) if driver_bundle is not None else None
    if driver_bundle is not None and engine_mode == "driver":
        base = driver_bundle.scenarios["base"]
        bull = driver_bundle.scenarios["bull"]
        bear = driver_bundle.scenarios["bear"]
        revenue_base = _driver_line_points(base.revenue, digits=2)
        revenue_bull = _driver_line_points(bull.revenue, digits=2)
        revenue_bear = _driver_line_points(bear.revenue, digits=2)
        profit_series = [
            _series("operating_income_actual", "EBIT Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "operating_income")),
            _series("net_income_actual", "Net Income Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "net_income")),
            _series("ebitda_actual", "EBITDA Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "ebitda_proxy")),
            _driver_series("operating_income_forecast", "EBIT Base", "usd", "line", "dashed", base.operating_income, 2),
            _driver_series("net_income_forecast", "Net Income Base", "usd", "line", "dashed", base.net_income, 2),
            _driver_series("ebitda_forecast", "EBITDA Base", "usd", "line", "dashed", base.ebitda, 2),
            _driver_series("net_income_bull", "Net Income Bull", "usd", "line", "muted", bull.net_income, 2),
            _driver_series("net_income_bear", "Net Income Bear", "usd", "line", "muted", bear.net_income, 2),
        ]
        cash_series = [
            _series("operating_cash_flow_actual", "Operating CF Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "operating_cash_flow")),
            _series("free_cash_flow_actual", "Free CF Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "free_cash_flow")),
            _series("capex_actual", "Capex Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "capex")),
            _driver_series("operating_cash_flow_forecast", "Operating CF Base", "usd", "line", "dashed", base.operating_cash_flow, 2),
            _driver_series("free_cash_flow_forecast", "Free CF Base", "usd", "line", "dashed", base.free_cash_flow, 2),
            _driver_series("capex_forecast", "Capex Base", "usd", "line", "dashed", base.capex, 2),
            _driver_series("free_cash_flow_bull", "Free CF Bull", "usd", "line", "muted", bull.free_cash_flow, 2),
            _driver_series("free_cash_flow_bear", "Free CF Bear", "usd", "line", "muted", bear.free_cash_flow, 2),
        ]
        eps_actual, _ = _eps_series(annuals, [])
        exp_1y = driver_bundle.base_next_year_growth
        exp_3y = driver_bundle.base_three_year_cagr
        return {
            "exp_1y": exp_1y,
            "exp_3y": exp_3y,
            "profit_series": profit_series,
            "cash_series": cash_series,
            "eps_actual": eps_actual,
            "growth_detail": f"Hist 3Y CAGR {_pct(hist_3y)}; base 1Y {_pct(exp_1y)}; bull / bear {_pct(driver_bundle.bull_next_year_growth)} / {_pct(driver_bundle.bear_next_year_growth)}.",
            "momentum_detail": "Base next-year growth and latest earnings drift.",
            "thesis": (
                f"{company_name} reported {_pct(hist_3y)} 3Y revenue CAGR; the driver-based base case implies {_pct(exp_1y)} next-year growth, "
                f"with bull / bear cases of {_pct(driver_bundle.bull_next_year_growth)} and {_pct(driver_bundle.bear_next_year_growth)}."
                if hist_3y is not None and exp_1y is not None
                else "Historical official filings are normalized first, forecast paths stay clearly labeled, and the driver engine separates assumptions from calculations for auditability."
            ),
            "source_badges": ["Official filings", "Driver-based integrated forecast", "Base / bull / bear scenarios", "Empirical stability overlay"],
            "revenue_card": CompanyChartsCardPayload(
                key="revenue",
                title="Revenue",
                subtitle="Reported history with driver-based base / bull / bear scenarios",
                metric_label="Revenue",
                unit_label="USD",
                empty_state="Reported revenue history is unavailable." if not revenue_actual else None,
                series=[
                    _series("revenue_actual", "Reported", "usd", "line", "actual", "solid", revenue_actual),
                    _series("revenue_base", "Base Forecast", "usd", "line", "forecast", "dashed", revenue_base),
                    _series("revenue_bull", "Bull Forecast", "usd", "line", "forecast", "muted", revenue_bull),
                    _series("revenue_bear", "Bear Forecast", "usd", "line", "forecast", "muted", revenue_bear),
                ],
                highlights=[item for item in [f"Hist 3Y CAGR {_pct(hist_3y)}" if hist_3y is not None else None, *driver_bundle.highlights] if item],
            ),
            "growth_card": CompanyChartsCardPayload(
                key="revenue_growth",
                title="Revenue Growth",
                subtitle="Reported growth with scenario sensitivities",
                metric_label="Revenue Growth",
                unit_label="Percent",
                empty_state="Revenue growth requires at least two annual periods." if not growth_actual else None,
                series=[
                    _series("revenue_growth_actual", "Reported", "percent", "bar", "actual", "solid", growth_actual),
                    _series("revenue_growth_base", "Base Forecast", "percent", "bar", "forecast", "muted", _driver_line_points(base.revenue_growth, digits=4)),
                    _series("revenue_growth_bull", "Bull Forecast", "percent", "bar", "forecast", "muted", _driver_line_points(bull.revenue_growth, digits=4)),
                    _series("revenue_growth_bear", "Bear Forecast", "percent", "bar", "forecast", "muted", _driver_line_points(bear.revenue_growth, digits=4)),
                ],
            ),
            "eps_card": CompanyChartsCardPayload(
                key="eps",
                title="EPS",
                subtitle="Diluted EPS with explicit SBC and buyback dilution logic",
                metric_label="EPS",
                unit_label="USD / share",
                empty_state="EPS history is unavailable for the selected periods." if not eps_actual else None,
                series=[
                    _series("eps_actual", "Reported", "usd_per_share", "bar", "actual", "solid", eps_actual),
                    _series("eps_base", "Base Forecast", "usd_per_share", "bar", "forecast", "muted", _driver_line_points(base.eps, digits=3)),
                    _series("eps_bull", "Bull Forecast", "usd_per_share", "bar", "forecast", "muted", _driver_line_points(bull.eps, digits=3)),
                    _series("eps_bear", "Bear Forecast", "usd_per_share", "bar", "forecast", "muted", _driver_line_points(bear.eps, digits=3)),
                ],
            ),
            "growth_summary_card": CompanyChartsComparisonCardPayload(
                subtitle="Scenario outputs are shown without benchmark overlays until a trustworthy comparable series is available.",
                comparisons=[
                    CompanyChartsComparisonItemPayload(key="historical_3y", label="Hist 3Y CAGR", company_value=_round(hist_3y, 4), benchmark_label="Benchmark hidden", benchmark_available=False, unit="percent", company_label="Company"),
                    CompanyChartsComparisonItemPayload(key="base_1y", label="Base 1Y", company_value=_round(driver_bundle.base_next_year_growth, 4), benchmark_label="Benchmark hidden", benchmark_available=False, unit="percent", company_label="Company"),
                    CompanyChartsComparisonItemPayload(key="bull_1y", label="Bull 1Y", company_value=_round(driver_bundle.bull_next_year_growth, 4), benchmark_label="Benchmark hidden", benchmark_available=False, unit="percent", company_label="Company"),
                    CompanyChartsComparisonItemPayload(key="bear_1y", label="Bear 1Y", company_value=_round(driver_bundle.bear_next_year_growth, 4), benchmark_label="Benchmark hidden", benchmark_available=False, unit="percent", company_label="Company"),
                    CompanyChartsComparisonItemPayload(key="base_3y", label="Base 3Y CAGR", company_value=_round(driver_bundle.base_three_year_cagr, 4), benchmark_label="Benchmark hidden", benchmark_available=False, unit="percent", company_label="Company"),
                ],
                empty_state="Growth summary requires a few annual revenue periods." if hist_3y is None and exp_1y is None else None,
            ),
            "assumptions_card": CompanyChartsAssumptionsCardPayload(items=_rows_to_assumption_items(driver_bundle.assumption_rows)),
            "calculations_card": CompanyChartsAssumptionsCardPayload(key="forecast_calculations", title="Forecast Calculations", items=_rows_to_assumption_items(driver_bundle.calculation_rows + driver_bundle.sensitivity_rows)),
            "profit_subtitle": "Explicit cost and below-the-line schedules drive the base case.",
            "cash_subtitle": "Operating working-capital schedules reconcile balance-sheet movement into cash flow.",
            "methodology_label": "Driver-based integrated forecast",
            "methodology_summary": "Revenue is modeled from a pricing proxy, residual-implied demand growth, and share or mix proxies, then layered with segment rollups, guidance, and backlog or capacity overlays when available. EBIT flows from explicit variable, semi-variable, and fixed cost schedules; operating working capital is forecast through receivables, inventory, payables, deferred revenue, and accrued operating-liability days while excluding cash and financing items; pretax income then bridges through debt-funded interest expense, cash yield, and other income or expense; operating cash flow subtracts delta operating working capital, capex covers maintenance capital plus positive-growth fixed-capital reinvestment from sales-to-capital, and free cash flow and diluted EPS are layered on top with disclosed cash, debt, SBC, buybacks, acquisition dilution, and convert dilution where available. Forecast Stability is then calibrated against point-in-time walk-forward backtests for revenue, EBIT, EPS, and FCF before conservative penalties are applied. When disclosure is sparse, the engine uses conservative component-level fallbacks before dropping all the way back to the older guarded heuristic path.",
            "methodology_disclaimer": "Scenario outputs are internally derived from official inputs and remain explicitly labeled as forecast rather than reported results or analyst consensus.",
            "methodology_heuristic": False,
        }
    if driver_bundle is not None and engine_mode == "regulated_financial_separate":
        return _build_regulated_financial_forecast_state(annuals, revenue_actual, growth_actual, hist_3y, driver_bundle, company_name)

    return _build_heuristic_forecast_state(annuals, revenue_actual, growth_actual, hist_3y, driver_bundle, company_name)


def _build_heuristic_assumption_items(
    annuals: list[Any],
    exp_1y: float | None,
    routing_rows: list[CompanyChartsAssumptionItemPayload] | None = None,
) -> list[CompanyChartsAssumptionItemPayload]:
    items = list(routing_rows or [])
    items.extend(
        [
            CompanyChartsAssumptionItemPayload(key="horizon", label="Forecast Horizon", value="3 fiscal years", detail="Annual-only forecast surface."),
            CompanyChartsAssumptionItemPayload(key="growth_guardrails", label="Growth Guardrails", value="-18% to +30%", detail="Forecast revenue growth is clipped."),
            CompanyChartsAssumptionItemPayload(key="history_depth", label="History Depth", value=f"{len(annuals)} annual periods", detail="Shorter annual history makes deterministic extrapolation less stable."),
            CompanyChartsAssumptionItemPayload(key="growth_volatility_band", label="Growth Volatility Band", value="Heuristic", detail="The fallback heuristic engine uses revenue volatility to dampen extrapolation."),
            CompanyChartsAssumptionItemPayload(key="fallback_mode", label="Forecast Mode", value="Heuristic fallback", detail="The driver engine is bypassed when statement coverage is too thin for explicit cost, reinvestment, or dilution schedules."),
            CompanyChartsAssumptionItemPayload(key="base_case_next_year", label="Base-Case Next Year", value=_pct(exp_1y), detail="Implied next-year revenue growth."),
        ]
    )
    return items


def _build_heuristic_forecast_state(
    annuals: list[Any],
    revenue_actual: list[CompanyChartsSeriesPointPayload],
    growth_actual: list[CompanyChartsSeriesPointPayload],
    hist_3y: float | None,
    routing_bundle: Any | None,
    company_name: str,
) -> dict[str, Any]:
    revenue_forecast, growth_curve = _forecast_revenue(revenue_actual)
    growth_forecast = _forecast_growth_series(revenue_forecast, growth_curve)
    profit_series = _margin_projected_series(annuals, revenue_actual, revenue_forecast, [("operating_income", "EBIT"), ("net_income", "Net Income"), ("ebitda_proxy", "EBITDA")])
    cash_series = _margin_projected_series(annuals, revenue_actual, revenue_forecast, [("operating_cash_flow", "Operating CF"), ("free_cash_flow", "Free CF"), ("capex", "Capex")])
    net_income_forecast = _series_points_by_key(profit_series, "net_income_forecast")
    eps_actual, eps_forecast = _eps_series(annuals, net_income_forecast.points if net_income_forecast is not None else [])
    exp_1y = _growth_rate(_point_value(revenue_forecast[0]) if revenue_forecast else None, _point_value(revenue_actual[-1]) if revenue_actual else None)
    exp_3y = _cagr([_point_value(revenue_actual[-1])] + [_point_value(point) for point in revenue_forecast[:3]]) if revenue_actual and len(revenue_forecast) >= 3 else None
    routing_assumption_items = _rows_to_assumption_items(getattr(routing_bundle, "assumption_rows", [])) if routing_bundle is not None else []
    calculations_card = None
    if routing_bundle is not None and getattr(routing_bundle, "calculation_rows", None):
        calculations_card = CompanyChartsAssumptionsCardPayload(key="forecast_calculations", title="Forecast Calculations", items=_rows_to_assumption_items(routing_bundle.calculation_rows))
    methodology_label = "Deterministic projection with empirical stability overlay"
    methodology_summary = "Annual historical official filings are normalized into a deterministic three-year projection, then paired with a point-in-time walk-forward stability score calibrated to realized revenue, EBIT, EPS, and FCF error bands plus explicit penalties for cyclicality, structural breaks, M&A, restatements, and share-count instability."
    methodology_disclaimer = "Forecast stability is a conservative communication aid grounded in historical multi-metric walk-forward error, not a probability, prediction interval, or statistical confidence measure. Forecast values remain projections rather than reported results or analyst consensus."
    if routing_bundle is not None and getattr(routing_bundle, "entity_routing", None) == "UNSURE_REQUIRE_CONSERVATIVE_FALLBACK":
        methodology_label = "Conservative fallback after routing gate"
        methodology_summary = "The forecast entrypoint identified a financial-sector-adjacent issuer without a confirmed non-financial routing, so the industrial driver engine was withheld and the dashboard stayed on a guarded heuristic fallback instead of applying DSO/DIO/DPO, sales-to-capital, or industrial capex heuristics as primary schedules."
        methodology_disclaimer = "This view is intentionally conservative: it avoids asserting an industrial IB-style schedule until the issuer is clearly classified as non-financial or routed to a dedicated regulated-financial path."
    return {
        "exp_1y": exp_1y,
        "exp_3y": exp_3y,
        "profit_series": profit_series,
        "cash_series": cash_series,
        "eps_actual": eps_actual,
        "growth_detail": f"Hist 3Y CAGR {_pct(hist_3y)}; forecast 1Y {_pct(exp_1y)}.",
        "momentum_detail": "Recent growth and earnings drift.",
        "thesis": (
            f"{company_name} reported {_pct(hist_3y)} 3Y revenue CAGR; the base-case projection implies {_pct(exp_1y)} next-year growth with heuristic guardrails."
            if hist_3y is not None and exp_1y is not None
            else "Historical official filings are normalized first, projected values remain explicitly labeled as forecast, and forecast stability remains guarded when multi-metric empirical history is thin."
        ),
        "source_badges": ["Official filings", "Deterministic forecast v3", "Empirical stability overlay", "Benchmark hidden unless trustworthy"],
        "revenue_card": CompanyChartsCardPayload(key="revenue", title="Revenue", subtitle="Reported history with guarded projection", metric_label="Revenue", unit_label="USD", empty_state="Reported revenue history is unavailable." if not revenue_actual else None, series=[_series("revenue_actual", "Reported", "usd", "line", "actual", "solid", revenue_actual), _series("revenue_forecast", "Forecast", "usd", "line", "forecast", "dashed", revenue_forecast)], highlights=[item for item in [f"Hist 3Y CAGR {_pct(hist_3y)}" if hist_3y is not None else None, f"Base-case next year {_pct(exp_1y)}" if exp_1y is not None else None] if item]),
        "growth_card": CompanyChartsCardPayload(key="revenue_growth", title="Revenue Growth", subtitle="Year-over-year reported and projected growth", metric_label="Revenue Growth", unit_label="Percent", empty_state="Revenue growth requires at least two annual periods." if not growth_actual else None, series=[_series("revenue_growth_actual", "Reported", "percent", "bar", "actual", "solid", growth_actual), _series("revenue_growth_forecast", "Forecast", "percent", "bar", "forecast", "muted", growth_forecast)]),
        "eps_card": CompanyChartsCardPayload(key="eps", title="EPS", subtitle="Diluted EPS with guarded share-count trend", metric_label="EPS", unit_label="USD / share", empty_state="EPS history is unavailable for the selected periods." if not eps_actual else None, series=[_series("eps_actual", "Reported", "usd_per_share", "bar", "actual", "solid", eps_actual), _series("eps_forecast", "Forecast", "usd_per_share", "bar", "forecast", "muted", eps_forecast)]),
        "growth_summary_card": CompanyChartsComparisonCardPayload(subtitle="Benchmark comparison stays hidden until a trustworthy series is available.", comparisons=[
            CompanyChartsComparisonItemPayload(key="historical_3y", label="Hist 3Y CAGR", company_value=_round(hist_3y, 4), benchmark_label="Benchmark hidden", benchmark_available=False, unit="percent", company_label="Company"),
            CompanyChartsComparisonItemPayload(key="expected_1y", label="Exp 1Y", company_value=_round(exp_1y, 4), benchmark_label="Benchmark hidden", benchmark_available=False, unit="percent", company_label="Company"),
            CompanyChartsComparisonItemPayload(key="expected_3y", label="Exp 3Y CAGR", company_value=_round(exp_3y, 4), benchmark_label="Benchmark hidden", benchmark_available=False, unit="percent", company_label="Company"),
        ], empty_state="Growth summary requires a few annual revenue periods." if hist_3y is None and exp_1y is None and exp_3y is None else None),
        "assumptions_card": CompanyChartsAssumptionsCardPayload(items=_build_heuristic_assumption_items(annuals, exp_1y, routing_assumption_items)),
        "calculations_card": calculations_card,
        "profit_subtitle": "Margin-based projections with guardrails",
        "cash_subtitle": "Cash generation stays visually distinct from projections",
        "methodology_label": methodology_label,
        "methodology_summary": methodology_summary,
        "methodology_disclaimer": methodology_disclaimer,
        "methodology_heuristic": True,
    }


def _build_regulated_financial_forecast_state(
    annuals: list[Any],
    revenue_actual: list[CompanyChartsSeriesPointPayload],
    growth_actual: list[CompanyChartsSeriesPointPayload],
    hist_3y: float | None,
    routing_bundle: Any,
    company_name: str,
) -> dict[str, Any]:
    eps_actual, _ = _eps_series(annuals, [])
    profit_series = [
        _series("operating_income_actual", "EBIT Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "operating_income")),
        _series("net_income_actual", "Net Income Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "net_income")),
        _series("ebitda_actual", "EBITDA Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "ebitda_proxy")),
    ]
    cash_series = [
        _series("operating_cash_flow_actual", "Operating CF Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "operating_cash_flow")),
        _series("free_cash_flow_actual", "Free CF Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "free_cash_flow")),
        _series("capex_actual", "Capex Reported", "usd", "line", "actual", "solid", _actual_series(annuals, "capex")),
    ]
    return {
        "exp_1y": None,
        "exp_3y": None,
        "profit_series": profit_series,
        "cash_series": cash_series,
        "eps_actual": eps_actual,
        "growth_detail": f"Hist 3Y CAGR {_pct(hist_3y)}; forecast withheld pending regulated-financial routing.",
        "momentum_detail": "Regulated-financial routing gate blocked industrial forecast schedules.",
        "thesis": f"{company_name} is routed away from the industrial driver engine because bank / broker / regulated-financial issuers need a separate forecast path built around balance-sheet and regulatory drivers.",
        "source_badges": ["Official filings", "Routing gate active", "Regulated-financial separate path", "No industrial driver forecast applied"],
        "revenue_card": CompanyChartsCardPayload(
            key="revenue",
            title="Revenue",
            subtitle="Reported history only while the issuer is routed to the regulated-financial path",
            metric_label="Revenue",
            unit_label="USD",
            empty_state="Reported revenue history is unavailable." if not revenue_actual else None,
            series=[_series("revenue_actual", "Reported", "usd", "line", "actual", "solid", revenue_actual)],
            highlights=["Industrial revenue-driver forecasts are withheld for regulated-financial routing."],
        ),
        "growth_card": CompanyChartsCardPayload(
            key="revenue_growth",
            title="Revenue Growth",
            subtitle="Reported growth only while industrial forecast logic is bypassed",
            metric_label="Revenue Growth",
            unit_label="Percent",
            empty_state="Revenue growth requires at least two annual periods." if not growth_actual else None,
            series=[_series("revenue_growth_actual", "Reported", "percent", "bar", "actual", "solid", growth_actual)],
        ),
        "eps_card": CompanyChartsCardPayload(
            key="eps",
            title="EPS",
            subtitle="Reported diluted EPS while the regulated-financial path is required",
            metric_label="EPS",
            unit_label="USD / share",
            empty_state="EPS history is unavailable for the selected periods." if not eps_actual else None,
            series=[_series("eps_actual", "Reported", "usd_per_share", "bar", "actual", "solid", eps_actual)],
        ),
        "growth_summary_card": CompanyChartsComparisonCardPayload(
            subtitle="Forecast comparison is withheld until the regulated-financial path is used.",
            comparisons=[
                CompanyChartsComparisonItemPayload(key="historical_3y", label="Hist 3Y CAGR", company_value=_round(hist_3y, 4), benchmark_label="Forecast withheld", benchmark_available=False, unit="percent", company_label="Company"),
            ],
            empty_state="Growth summary requires a few annual revenue periods." if hist_3y is None else None,
        ),
        "assumptions_card": CompanyChartsAssumptionsCardPayload(items=_rows_to_assumption_items(getattr(routing_bundle, "assumption_rows", []))),
        "calculations_card": CompanyChartsAssumptionsCardPayload(key="forecast_calculations", title="Forecast Calculations", items=_rows_to_assumption_items(getattr(routing_bundle, "calculation_rows", []))),
        "profit_subtitle": "Reported profit only while regulated-financial routing is active",
        "cash_subtitle": "Reported cash-flow history only while industrial forecast logic is bypassed",
        "methodology_label": "Regulated-financial separate path required",
        "methodology_summary": "The charts forecast gate classified the issuer as regulated financial before industrial schedules were built, so the dashboard does not apply industrial DSO/DIO/DPO, sales-to-capital, PP&E-led capex heuristics, or generic cash-debt sweeps as the primary modeling framework.",
        "methodology_disclaimer": "Use the regulated-financial path for banks, brokers, and similarly regulated issuers. This charts surface intentionally withholds the industrial forecast rather than silently stretching it across bank-style balance sheets.",
        "methodology_heuristic": False,
    }


def _annual_statements(financials: list[Any]) -> list[Any]:
    seen: dict[DateType, Any] = {}
    for statement in financials:
        if getattr(statement, "filing_type", None) in ANNUAL_FILING_TYPES and statement.period_end not in seen:
            seen[statement.period_end] = statement
    ordered = sorted(seen.values(), key=lambda item: item.period_end)
    return ordered[-8:]


def _load_capital_markets_events(session: Session, company_id: int, *, as_of: datetime | None) -> list[Any]:
    try:
        events = get_company_capital_markets_events(session, company_id, limit=120)
    except (AttributeError, TypeError):
        # Unit tests often pass a lightweight session double without SQL methods.
        return []
    if as_of is None:
        return events
    filtered: list[Any] = []
    for event in events:
        effective_at = _capital_markets_event_effective_at(event)
        if effective_at is None or effective_at > as_of:
            continue
        filtered.append(event)
    return filtered


def _build_chart_event_overlay(
    *,
    earnings_releases: list[Any],
    restatements: list[Any],
    capital_markets_events: list[Any],
    annuals: list[Any],
) -> CompanyChartsEventOverlayPayload:
    events: list[CompanyChartsEventPayload] = []
    has_guidance = False
    has_buyback = False
    has_m_and_a = False

    for release in earnings_releases:
        event_date = _release_event_date(release)
        if event_date is None:
            continue
        period_end = getattr(release, "reported_period_end", None)
        period_label = f"FY{period_end.year}" if period_end is not None else None
        source_url = _to_str_or_none(getattr(release, "source_url", None))
        filing_date = getattr(release, "filing_date", None)
        events.append(
            CompanyChartsEventPayload(
                key=f"earnings-{getattr(release, 'id', event_date.isoformat())}",
                event_type="earnings",
                label="Earnings release",
                event_date=event_date,
                period_label=period_label,
                detail=(f"Filed {filing_date.isoformat()}" if filing_date is not None else "Filed with SEC"),
                source_label="SEC earnings release",
                source_url=source_url,
            )
        )
        if _release_has_guidance(release):
            has_guidance = True
            events.append(
                CompanyChartsEventPayload(
                    key=f"guidance-{getattr(release, 'id', event_date.isoformat())}",
                    event_type="guidance",
                    label="Guidance update",
                    event_date=event_date,
                    period_label=period_label,
                    detail=_release_guidance_detail(release),
                    source_label="SEC earnings release",
                    source_url=source_url,
                )
            )
        if _release_has_buyback(release):
            has_buyback = True
            events.append(
                CompanyChartsEventPayload(
                    key=f"buyback-release-{getattr(release, 'id', event_date.isoformat())}",
                    event_type="buyback",
                    label="Buyback announcement",
                    event_date=event_date,
                    period_label=period_label,
                    detail=_release_buyback_detail(release),
                    source_label="SEC earnings release",
                    source_url=source_url,
                )
            )

    for record in restatements:
        event_date = _restatement_event_date(record)
        if event_date is None:
            continue
        period_end = getattr(record, "period_end", None)
        period_label = f"FY{period_end.year}" if period_end is not None else None
        changed_count = len(getattr(record, "changed_metric_keys", []) or [])
        detail = f"{changed_count} metric updates detected" if changed_count else "Detected from amended filing"
        events.append(
            CompanyChartsEventPayload(
                key=f"restatement-{getattr(record, 'id', event_date.isoformat())}",
                event_type="restatement",
                label="Financial restatement",
                event_date=event_date,
                period_label=period_label,
                detail=detail,
                source_label="SEC filing delta",
                source_url=_to_str_or_none(getattr(record, "source", None)),
            )
        )

    for record in capital_markets_events:
        event_type_text = (_to_str_or_none(getattr(record, "event_type", None)) or "").lower()
        summary_text = (_to_str_or_none(getattr(record, "summary", None)) or "").lower()
        if not any(keyword in event_type_text or keyword in summary_text for keyword in ("acquisition", "merger", "m&a", "takeover", "combination")):
            continue
        event_date = _capital_markets_event_date(record)
        if event_date is None:
            continue
        has_m_and_a = True
        events.append(
            CompanyChartsEventPayload(
                key=f"m-and-a-{getattr(record, 'id', event_date.isoformat())}",
                event_type="major_m_and_a",
                label="Major M&A announcement",
                event_date=event_date,
                period_label=None,
                detail=_truncate_text(_to_str_or_none(getattr(record, "summary", None)) or "Capital markets disclosure", 180),
                source_label="SEC capital markets filing",
                source_url=_to_str_or_none(getattr(record, "source_url", None)),
            )
        )

    if not has_buyback:
        buyback_fallback = _build_buyback_fallback_event(annuals)
        if buyback_fallback is not None:
            events.append(buyback_fallback)

    if not has_m_and_a:
        acquisition_fallback = _build_acquisition_fallback_event(annuals)
        if acquisition_fallback is not None:
            events.append(acquisition_fallback)

    events.sort(key=lambda item: (item.event_date, item.key), reverse=True)
    events = events[:MAX_CHART_EVENTS]

    sparse_note = None
    coverage = {event.event_type for event in events}
    if len(coverage) < 3:
        sparse_note = "Sparse filing signal: showing only events found in recent official disclosures and conservative metric-derived fallbacks."

    default_enabled = [event_type for event_type in DEFAULT_ENABLED_CHART_EVENT_TYPES if event_type in CHART_EVENT_TYPES]
    if "earnings" not in coverage and default_enabled:
        default_enabled = [event_type for event_type in default_enabled if event_type != "earnings"]

    return CompanyChartsEventOverlayPayload(
        title="Event overlays",
        available_event_types=list(CHART_EVENT_TYPES),
        default_enabled_event_types=default_enabled,
        events=events,
        sparse_data_note=sparse_note,
    )


def _build_quarter_change_payload(
    *,
    annuals: list[Any],
    event_overlay: CompanyChartsEventOverlayPayload,
    forecast_state: dict[str, Any],
) -> CompanyChartsQuarterChangePayload:
    if len(annuals) < 2:
        return CompanyChartsQuarterChangePayload(
            empty_state="Need at least two reported annual periods to summarize what changed.",
        )

    latest = annuals[-1]
    prior = annuals[-2]
    latest_label = f"FY{latest.period_end.year}"
    prior_label = f"FY{prior.period_end.year}"

    revenue_latest = _statement_value(latest, "revenue")
    revenue_prior = _statement_value(prior, "revenue")
    eps_latest = _statement_value(latest, "eps")
    eps_prior = _statement_value(prior, "eps")
    fcf_latest = _statement_value(latest, "free_cash_flow")
    fcf_prior = _statement_value(prior, "free_cash_flow")

    items: list[CompanyChartsQuarterChangeItemPayload] = []
    for key, label, current_value, previous_value in (
        ("revenue_delta", "Revenue", revenue_latest, revenue_prior),
        ("eps_delta", "EPS", eps_latest, eps_prior),
        ("fcf_delta", "Free cash flow", fcf_latest, fcf_prior),
    ):
        delta = _safe_diff(current_value, previous_value)
        change = _growth_rate(current_value, previous_value)
        if delta is None:
            continue
        items.append(
            CompanyChartsQuarterChangeItemPayload(
                key=key,
                label=label,
                value=_format_delta(delta, change),
                detail=f"{latest_label} vs {prior_label}",
            )
        )

    recent_period_events = [
        event
        for event in event_overlay.events
        if event.period_label in {latest_label, prior_label}
    ]
    if recent_period_events:
        grouped = sorted({event.label for event in recent_period_events})
        items.append(
            CompanyChartsQuarterChangeItemPayload(
                key="recent_events",
                label="Event context",
                value=str(len(recent_period_events)),
                detail=", ".join(grouped[:3]),
            )
        )

    exp_1y = forecast_state.get("exp_1y")
    if isinstance(exp_1y, (int, float)):
        items.append(
            CompanyChartsQuarterChangeItemPayload(
                key="next_year_outlook",
                label="Next-year outlook",
                value=_pct(float(exp_1y)),
                detail="Base-case growth from current model state",
            )
        )

    if not items:
        return CompanyChartsQuarterChangePayload(
            latest_period_label=latest_label,
            prior_period_label=prior_label,
            empty_state="Not enough comparable metrics to summarize period-over-period changes.",
        )

    summary = f"{latest_label} vs {prior_label} combines reported deltas with filing-event context."
    return CompanyChartsQuarterChangePayload(
        latest_period_label=latest_label,
        prior_period_label=prior_label,
        summary=summary,
        items=items[:5],
    )


def _release_event_date(release: Any) -> DateType | None:
    acceptance = _normalize_datetime(getattr(release, "filing_acceptance_at", None))
    if acceptance is not None:
        return acceptance.date()
    filing_date = getattr(release, "filing_date", None)
    if isinstance(filing_date, DateType):
        return filing_date
    report_end = getattr(release, "reported_period_end", None)
    if isinstance(report_end, DateType):
        return report_end
    return None


def _restatement_event_date(record: Any) -> DateType | None:
    acceptance = _normalize_datetime(getattr(record, "filing_acceptance_at", None))
    if acceptance is not None:
        return acceptance.date()
    filing_date = getattr(record, "filing_date", None)
    if isinstance(filing_date, DateType):
        return filing_date
    period_end = getattr(record, "period_end", None)
    if isinstance(period_end, DateType):
        return period_end
    return None


def _capital_markets_event_date(record: Any) -> DateType | None:
    filing_date = getattr(record, "filing_date", None)
    if isinstance(filing_date, DateType):
        return filing_date
    report_date = getattr(record, "report_date", None)
    if isinstance(report_date, DateType):
        return report_date
    checked = _normalize_datetime(getattr(record, "last_checked", None))
    return checked.date() if checked is not None else None


def _capital_markets_event_effective_at(record: Any) -> datetime | None:
    filing_date = getattr(record, "filing_date", None)
    if isinstance(filing_date, DateType):
        return datetime.combine(filing_date, TimeType.max, tzinfo=timezone.utc)
    report_date = getattr(record, "report_date", None)
    if isinstance(report_date, DateType):
        return datetime.combine(report_date, TimeType.max, tzinfo=timezone.utc)
    return _normalize_datetime(getattr(record, "last_checked", None))


def _release_has_guidance(release: Any) -> bool:
    return any(
        getattr(release, field, None) is not None
        for field in ("revenue_guidance_low", "revenue_guidance_high", "eps_guidance_low", "eps_guidance_high")
    )


def _release_has_buyback(release: Any) -> bool:
    amount = getattr(release, "share_repurchase_amount", None)
    return isinstance(amount, (int, float)) and float(amount) > 0


def _release_guidance_detail(release: Any) -> str:
    revenue_low = _to_float_or_none(getattr(release, "revenue_guidance_low", None))
    revenue_high = _to_float_or_none(getattr(release, "revenue_guidance_high", None))
    eps_low = _to_float_or_none(getattr(release, "eps_guidance_low", None))
    eps_high = _to_float_or_none(getattr(release, "eps_guidance_high", None))
    parts: list[str] = []
    if revenue_low is not None or revenue_high is not None:
        if revenue_low is not None and revenue_high is not None:
            parts.append(f"Revenue ${_compact_money(revenue_low)}-${_compact_money(revenue_high)}")
        else:
            parts.append(f"Revenue ${_compact_money(revenue_low if revenue_low is not None else revenue_high or 0.0)}")
    if eps_low is not None or eps_high is not None:
        if eps_low is not None and eps_high is not None:
            parts.append(f"EPS ${eps_low:.2f}-${eps_high:.2f}")
        else:
            parts.append(f"EPS ${((eps_low if eps_low is not None else eps_high) or 0.0):.2f}")
    return "; ".join(parts) if parts else "Management guidance updated"


def _release_buyback_detail(release: Any) -> str:
    amount = _to_float_or_none(getattr(release, "share_repurchase_amount", None))
    if amount is None:
        return "Buyback signal detected in release"
    return f"Share repurchase authorization ${_compact_money(amount)}"


def _build_buyback_fallback_event(annuals: list[Any]) -> CompanyChartsEventPayload | None:
    for statement in reversed(annuals):
        value = _statement_value(statement, "share_buybacks")
        if value is None or value <= 0:
            continue
        period_end = getattr(statement, "period_end", None)
        if period_end is None:
            continue
        return CompanyChartsEventPayload(
            key=f"buyback-fallback-{period_end.isoformat()}",
            event_type="buyback",
            label="Buyback activity",
            event_date=period_end,
            period_label=f"FY{period_end.year}",
            detail=f"Annual share buybacks reported at ${_compact_money(value)}",
            source_label="SEC financial statement",
        )
    return None


def _build_acquisition_fallback_event(annuals: list[Any]) -> CompanyChartsEventPayload | None:
    for statement in reversed(annuals):
        value = _statement_value(statement, "acquisitions")
        if value is None or value <= 0:
            continue
        period_end = getattr(statement, "period_end", None)
        if period_end is None:
            continue
        return CompanyChartsEventPayload(
            key=f"m-and-a-fallback-{period_end.isoformat()}",
            event_type="major_m_and_a",
            label="M&A activity",
            event_date=period_end,
            period_label=f"FY{period_end.year}",
            detail=f"Acquisition cash use reported at ${_compact_money(value)}",
            source_label="SEC cash-flow statement",
        )
    return None


def _compact_money(value: float) -> str:
    absolute = abs(float(value))
    sign = "-" if value < 0 else ""
    if absolute >= 1_000_000_000:
        return f"{sign}{absolute / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{sign}{absolute / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{sign}{absolute / 1_000:.1f}K"
    return f"{sign}{absolute:.0f}"


def _safe_diff(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return float(current) - float(previous)


def _format_delta(delta: float, change: float | None) -> str:
    direction = "+" if delta >= 0 else "-"
    magnitude = _compact_money(abs(delta))
    if change is None:
        return f"{direction}${magnitude}"
    return f"{direction}${magnitude} ({_pct(change)})"


def _to_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "..."


def _actual_series(statements: list[Any], key: str) -> list[CompanyChartsSeriesPointPayload]:
    points: list[CompanyChartsSeriesPointPayload] = []
    for statement in statements:
        value = _statement_value(statement, key) if key != "ebitda_proxy" else _ebitda_proxy(statement)
        if value is None:
            continue
        points.append(CompanyChartsSeriesPointPayload(period_label=f"FY{statement.period_end.year}", fiscal_year=statement.period_end.year, period_end=statement.period_end, value=_round(value, 2), series_kind="actual"))
    return points


def _forecast_revenue(actual: list[CompanyChartsSeriesPointPayload]) -> tuple[list[CompanyChartsSeriesPointPayload], list[float]]:
    visible_actual = _contiguous_visible_series_points(actual)
    values = [value for _point, value in visible_actual]
    if not values:
        return [], []
    current = values[-1]
    if current <= 0:
        return [], []
    historical_growth = _historical_growth_rates(values)
    # Clamp extreme years before averaging so one anomalous filing does not dominate the baseline.
    winsorized_growth = [_clip(value, REVENUE_FORECAST_GROWTH_FLOOR, REVENUE_FORECAST_GROWTH_CAP) for value in historical_growth]
    recent_growth = _weighted_recent_growth(winsorized_growth)
    cagr_growth = _cagr(values[-4:]) if len(values) >= 2 else None
    cagr_growth = _clip(cagr_growth, REVENUE_FORECAST_GROWTH_FLOOR, REVENUE_FORECAST_GROWTH_CAP) if cagr_growth is not None else None

    recent_component = recent_growth if recent_growth is not None else REVENUE_FORECAST_TERMINAL_GROWTH
    cagr_component = cagr_growth if cagr_growth is not None else recent_component
    baseline_growth = _clip(
        (recent_component * REVENUE_FORECAST_RECENT_BLEND_WEIGHT) + (cagr_component * REVENUE_FORECAST_CAGR_BLEND_WEIGHT),
        REVENUE_FORECAST_GROWTH_FLOOR,
        REVENUE_FORECAST_GROWTH_CAP,
    )
    year = visible_actual[-1][0].fiscal_year or datetime.now(timezone.utc).year
    points: list[CompanyChartsSeriesPointPayload] = []
    curve: list[float] = []
    current_growth = baseline_growth
    for index in range(1, 4):
        growth = _clip(current_growth, REVENUE_FORECAST_GROWTH_FLOOR, REVENUE_FORECAST_GROWTH_CAP)
        current *= 1 + growth
        curve.append(growth)
        points.append(CompanyChartsSeriesPointPayload(period_label=f"FY{year + index}E", fiscal_year=year + index, period_end=None, value=_round(current, 2), series_kind="forecast"))
        # Revert each forward year toward a modest terminal rate instead of extending the latest regime unchanged.
        current_growth = growth + ((REVENUE_FORECAST_TERMINAL_GROWTH - growth) * REVENUE_FORECAST_REVERSION_SPEED)
    return points, curve


def _growth_series(points: list[CompanyChartsSeriesPointPayload], kind: str) -> list[CompanyChartsSeriesPointPayload]:
    visible_points = _visible_series_points(points)
    result: list[CompanyChartsSeriesPointPayload] = []
    for (previous_point, previous), (payload, current) in zip(visible_points, visible_points[1:]):
        if not _series_points_are_adjacent(previous_point, payload):
            continue
        growth = _growth_rate(current, previous)
        if growth is None:
            continue
        result.append(CompanyChartsSeriesPointPayload(period_label=payload.period_label, fiscal_year=payload.fiscal_year, period_end=payload.period_end, value=_round(growth, 4), series_kind=kind))
    return result


def _forecast_growth_series(points: list[CompanyChartsSeriesPointPayload], growths: list[float]) -> list[CompanyChartsSeriesPointPayload]:
    return [CompanyChartsSeriesPointPayload(period_label=point.period_label, fiscal_year=point.fiscal_year, period_end=None, value=_round(growth, 4), series_kind="forecast") for point, growth in zip(points, growths)]


def _margin_projected_series(statements: list[Any], revenue_actual: list[CompanyChartsSeriesPointPayload], revenue_forecast: list[CompanyChartsSeriesPointPayload], metrics: list[tuple[str, str]]) -> list[CompanyChartsSeriesPayload]:
    actual_revenue = {
        point.fiscal_year: value
        for point, value in _visible_series_points(revenue_actual)
        if point.fiscal_year is not None
    }
    forecast_revenue = {
        point.fiscal_year: value
        for point, value in _visible_series_points(revenue_forecast)
        if point.fiscal_year is not None
    }
    payloads: list[CompanyChartsSeriesPayload] = []
    for key, label in metrics:
        actual_points: list[CompanyChartsSeriesPointPayload] = []
        margins: list[float] = []
        for statement in statements:
            value = _metric_projection_value(statement, key)
            if value is None:
                continue
            actual_points.append(CompanyChartsSeriesPointPayload(period_label=f"FY{statement.period_end.year}", fiscal_year=statement.period_end.year, period_end=statement.period_end, value=_round(value, 2), series_kind="actual"))
            revenue_value = actual_revenue.get(statement.period_end.year)
            margin = _safe_divide(value, revenue_value)
            if margin is not None:
                margins.append(margin)
        if not actual_points:
            continue
        payloads.append(_series(f"{key}_actual", f"{label} Reported", "usd", "line", "actual", "solid", actual_points))
        margin_path = _margin_convergence_path(margins, key, len(forecast_revenue))
        if margin_path and forecast_revenue:
            forecast_points: list[CompanyChartsSeriesPointPayload] = []
            for (year, revenue), margin in zip(sorted(forecast_revenue.items()), margin_path):
                if revenue <= 0:
                    continue
                forecast_value = revenue * margin
                if not isfinite(forecast_value):
                    continue
                forecast_points.append(
                    CompanyChartsSeriesPointPayload(
                        period_label=f"FY{year}E",
                        fiscal_year=year,
                        period_end=None,
                        value=_round(forecast_value, 2),
                        series_kind="forecast",
                    )
                )
            if forecast_points:
                payloads.append(_series(f"{key}_forecast", f"{label} Forecast", "usd", "line", "forecast", "dashed", forecast_points))
    return payloads


def _eps_series(statements: list[Any], net_income_forecast: list[CompanyChartsSeriesPointPayload]) -> tuple[list[CompanyChartsSeriesPointPayload], list[CompanyChartsSeriesPointPayload]]:
    actual: list[CompanyChartsSeriesPointPayload] = []
    shares_history: list[float] = []
    for statement in statements:
        shares = _statement_value(statement, "weighted_average_shares_diluted")
        net_income = _statement_value(statement, "net_income")
        if shares not in (None, 0):
            shares_history.append(float(shares))
        eps = _statement_value(statement, "eps")
        if eps is None and net_income is not None and shares not in (None, 0):
            eps = float(net_income) / float(shares)
        if eps is not None:
            actual.append(CompanyChartsSeriesPointPayload(period_label=f"FY{statement.period_end.year}", fiscal_year=statement.period_end.year, period_end=statement.period_end, value=_round(eps, 3), series_kind="actual"))
    if not net_income_forecast or not shares_history:
        return actual, []
    share_forecast = _forecast_diluted_shares(shares_history, len(net_income_forecast))
    if not share_forecast:
        return actual, []
    forecast: list[CompanyChartsSeriesPointPayload] = []
    for point, diluted_shares in zip(net_income_forecast, share_forecast):
        # Suppress forecast EPS if the share bridge becomes unusable instead of fabricating a denominator.
        value = _safe_divide(_point_value(point), diluted_shares)
        if value is None:
            continue
        forecast.append(CompanyChartsSeriesPointPayload(period_label=point.period_label, fiscal_year=point.fiscal_year, period_end=None, value=_round(value, 3), series_kind="forecast"))
    return actual, forecast


def _series(key: str, label: str, unit: str, chart_type: str, series_kind: str, stroke_style: str, points: list[CompanyChartsSeriesPointPayload]) -> CompanyChartsSeriesPayload:
    return CompanyChartsSeriesPayload(key=key, label=label, unit=unit, chart_type=chart_type, series_kind=series_kind, stroke_style=stroke_style, points=points)


def _series_points_by_key(series_list: list[CompanyChartsSeriesPayload], key: str) -> CompanyChartsSeriesPayload | None:
    return next((series for series in series_list if series.key == key), None)


def _driver_line_points(line: Any, *, digits: int) -> list[CompanyChartsSeriesPointPayload]:
    points: list[CompanyChartsSeriesPointPayload] = []
    for year, value in zip(getattr(line, "years", []), getattr(line, "values", [])):
        points.append(
            CompanyChartsSeriesPointPayload(
                period_label=f"FY{year}E",
                fiscal_year=year,
                period_end=None,
                value=_round(value, digits),
                series_kind="forecast",
            )
        )
    return points


def _driver_series(
    key: str,
    label: str,
    unit: str,
    chart_type: str,
    stroke_style: str,
    line: Any,
    digits: int,
) -> CompanyChartsSeriesPayload:
    return CompanyChartsSeriesPayload(
        key=key,
        label=label,
        unit=unit,
        chart_type=chart_type,
        series_kind="forecast",
        stroke_style=stroke_style,
        points=_driver_line_points(line, digits=digits),
    )


def _rows_to_assumption_items(rows: list[dict[str, str]]) -> list[CompanyChartsAssumptionItemPayload]:
    return [
        CompanyChartsAssumptionItemPayload(
            key=str(row.get("key") or "item"),
            label=str(row.get("label") or row.get("key") or "Item"),
            value=str(row.get("value") or "N/A"),
            detail=str(row.get("detail")) if row.get("detail") is not None else None,
        )
        for row in rows
    ]


def _build_projection_studio_payload(
    annuals: list[Any],
    driver_bundle: Any | None,
    methodology: CompanyChartsMethodologyPayload,
) -> CompanyChartsProjectionStudioPayload | None:
    if driver_bundle is None:
        return None

    scenarios = getattr(driver_bundle, "scenarios", None)
    line_traces = getattr(driver_bundle, "line_traces", None)
    if not isinstance(scenarios, dict) or not isinstance(line_traces, dict) or not line_traces:
        return None

    base_scenario = scenarios.get("base")
    if base_scenario is None or not getattr(getattr(base_scenario, "revenue", None), "years", []):
        return None

    schedule_sections = _build_projection_studio_schedule_sections(annuals, line_traces)
    drivers_used = _build_projection_studio_driver_cards(annuals, driver_bundle, line_traces)
    scenarios_comparison = _build_projection_studio_scenarios_comparison(driver_bundle)
    sensitivity_matrix = _build_projection_studio_sensitivity_matrix(annuals, driver_bundle, line_traces)
    if not schedule_sections or len(sensitivity_matrix) != 25:
        return None

    return CompanyChartsProjectionStudioPayload(
        methodology=methodology,
        schedule_sections=schedule_sections,
        drivers_used=drivers_used,
        scenarios_comparison=scenarios_comparison,
        sensitivity_matrix=sensitivity_matrix,
    )


def _build_projection_studio_schedule_sections(
    annuals: list[Any],
    line_traces: dict[str, dict[int, Any]],
) -> list[CompanyChartsScheduleSectionPayload]:
    section_specs = (
        (
            "income_statement",
            "Income Statement",
            (
                ("revenue", "Revenue", "usd"),
                ("cost_of_revenue", "Cost of Revenue", "usd"),
                ("gross_profit", "Gross Profit", "usd"),
                ("operating_income", "Operating Income", "usd"),
                ("pretax_income", "Pretax Income", "usd"),
                ("income_tax", "Income Tax", "usd"),
                ("net_income", "Net Income", "usd"),
                ("eps", "Diluted EPS", "usd_per_share"),
            ),
        ),
        (
            "balance_sheet",
            "Balance Sheet",
            (
                ("net_ppe", "Net PP&E", "usd"),
                ("accounts_receivable", "Accounts Receivable", "usd"),
                ("inventory", "Inventory", "usd"),
                ("accounts_payable", "Accounts Payable", "usd"),
                ("deferred_revenue", "Deferred Revenue", "usd"),
                ("accrued_operating_liabilities", "Accrued Operating Liabilities", "usd"),
            ),
        ),
        (
            "cash_flow_statement",
            "Cash Flow Statement",
            (
                ("depreciation_amortization", "Depreciation and Amortization", "usd"),
                ("sbc_expense", "SBC Expense", "usd"),
                ("capex", "Capex", "usd"),
                ("operating_cash_flow", "Operating Cash Flow", "usd"),
                ("free_cash_flow", "Free Cash Flow", "usd"),
            ),
        ),
    )

    sections: list[CompanyChartsScheduleSectionPayload] = []
    for key, title, row_specs in section_specs:
        rows = [
            row
            for row in (
                _build_projection_studio_row(annuals, line_key, label, unit, line_traces)
                for line_key, label, unit in row_specs
            )
            if row is not None
        ]
        if rows:
            sections.append(CompanyChartsScheduleSectionPayload(key=key, title=title, rows=rows))
    return sections


def _build_projection_studio_row(
    annuals: list[Any],
    line_key: str,
    label: str,
    unit: str,
    line_traces: dict[str, dict[int, Any]],
) -> CompanyChartsProjectedRowPayload | None:
    reported_values: dict[int, float | None] = {}
    for statement in annuals[-PROJECTION_STUDIO_REPORTED_PERIODS:]:
        year = getattr(getattr(statement, "period_end", None), "year", None)
        if year is None:
            continue
        value = _projection_studio_reported_value(statement, line_key)
        if value is None:
            continue
        reported_values[int(year)] = _projection_studio_round_value(value, unit)

    trace_map = line_traces.get(line_key) or {}
    projected_values: dict[int, float | None] = {}
    formula_traces: dict[int, CompanyChartsFormulaTracePayload] = {}
    for year, trace in sorted(trace_map.items()):
        if getattr(trace, "result_value", None) is not None:
            projected_values[int(year)] = _projection_studio_round_value(float(trace.result_value), unit)
        formula_traces[int(year)] = _serialize_projection_studio_formula_trace(trace)

    if not reported_values and not projected_values:
        return None

    return CompanyChartsProjectedRowPayload(
        key=line_key,
        label=label,
        unit=unit,
        reported_values=reported_values,
        projected_values=projected_values,
        formula_traces=formula_traces,
    )


def _projection_studio_reported_value(statement: Any, line_key: str) -> float | None:
    if line_key == "income_tax":
        return _statement_value(statement, "income_tax_expense")
    if line_key == "depreciation_amortization":
        return _statement_value(statement, "depreciation_and_amortization")
    if line_key == "net_ppe":
        return _statement_value(statement, "net_ppe")
    if line_key == "sbc_expense":
        return _statement_value(statement, "stock_based_compensation")
    if line_key == "cost_of_revenue":
        cost_of_revenue = _statement_value(statement, "cost_of_revenue")
        if cost_of_revenue is not None:
            return cost_of_revenue
        revenue = _statement_value(statement, "revenue")
        gross_profit = _statement_value(statement, "gross_profit")
        return (revenue - gross_profit) if revenue is not None and gross_profit is not None else None
    if line_key == "eps":
        eps = _statement_value(statement, "eps")
        if eps is not None:
            return eps
        net_income = _statement_value(statement, "net_income")
        diluted_shares = _statement_value(statement, "weighted_average_shares_diluted")
        return _safe_divide(net_income, diluted_shares)
    if line_key == "gross_profit":
        gross_profit = _statement_value(statement, "gross_profit")
        if gross_profit is not None:
            return gross_profit
        revenue = _statement_value(statement, "revenue")
        cost_of_revenue = _statement_value(statement, "cost_of_revenue")
        return (revenue - cost_of_revenue) if revenue is not None and cost_of_revenue is not None else None
    if line_key == "free_cash_flow":
        return _metric_projection_value(statement, "free_cash_flow")
    return _statement_value(statement, line_key)


def _serialize_projection_studio_formula_trace(trace: Any) -> CompanyChartsFormulaTracePayload:
    return CompanyChartsFormulaTracePayload(
        line_item=str(getattr(trace, "line_item", "")),
        year=int(getattr(trace, "year", 0)),
        formula_label=str(getattr(trace, "formula_label", "")),
        formula_template=str(getattr(trace, "formula_template", "")),
        formula_computation=str(getattr(trace, "formula_computation", "")),
        result_value=getattr(trace, "result_value", None),
        inputs=[
            CompanyChartsFormulaInputPayload(
                key=str(getattr(input_item, "key", "")),
                label=str(getattr(input_item, "label", "")),
                value=getattr(input_item, "value", None),
                formatted_value=str(getattr(input_item, "formatted_value", "")),
                source_detail=str(getattr(input_item, "source_detail", "")),
                source_kind=str(getattr(input_item, "source_kind", "sec")),
                is_override=bool(getattr(input_item, "is_override", False)),
                original_value=getattr(input_item, "original_value", None),
                original_source=str(getattr(input_item, "original_source", "")) if getattr(input_item, "original_source", None) is not None else None,
            )
            for input_item in getattr(trace, "inputs", [])
        ],
        confidence=str(getattr(trace, "confidence", "high")),
        scenario_state=str(getattr(trace, "scenario_state", "baseline")),
    )


def _build_company_charts_what_if_payload(
    baseline_bundle: Any | None,
    scenario_bundle: Any | None,
) -> CompanyChartsWhatIfPayload:
    override_context = getattr(scenario_bundle, "override_context", None) or getattr(baseline_bundle, "override_context", None)
    if override_context is None:
        return CompanyChartsWhatIfPayload()
    return CompanyChartsWhatIfPayload(
        impact_summary=_build_company_charts_what_if_impact_summary(baseline_bundle, scenario_bundle),
        overrides_applied=[_serialize_company_charts_what_if_override(item) for item in getattr(override_context, "applied", [])],
        overrides_clipped=[_serialize_company_charts_what_if_override(item) for item in getattr(override_context, "clipped", [])],
        driver_control_metadata=[_serialize_company_charts_driver_control(item) for item in getattr(override_context, "controls", [])],
    )


def _build_company_charts_what_if_impact_summary(
    baseline_bundle: Any | None,
    scenario_bundle: Any | None,
) -> CompanyChartsWhatIfImpactSummaryPayload | None:
    if baseline_bundle is None or scenario_bundle is None:
        return None

    baseline_scenarios = getattr(baseline_bundle, "scenarios", None) or {}
    scenario_scenarios = getattr(scenario_bundle, "scenarios", None) or {}
    baseline_base = baseline_scenarios.get("base") if isinstance(baseline_scenarios, dict) else None
    scenario_base = scenario_scenarios.get("base") if isinstance(scenario_scenarios, dict) else None
    forecast_years = getattr(getattr(scenario_base, "revenue", None), "years", []) if scenario_base is not None else []
    forecast_year = int(forecast_years[0]) if forecast_years else None
    metrics = [
        _build_company_charts_what_if_metric(
            "revenue_growth",
            "Revenue Growth",
            "percent",
            getattr(baseline_bundle, "base_next_year_growth", None),
            getattr(scenario_bundle, "base_next_year_growth", None),
        ),
        _build_company_charts_what_if_metric(
            "revenue",
            "Revenue",
            "usd",
            _first_line_value(getattr(baseline_base, "revenue", None)),
            _first_line_value(getattr(scenario_base, "revenue", None)),
        ),
        _build_company_charts_what_if_metric(
            "operating_income",
            "Operating Income",
            "usd",
            _first_line_value(getattr(baseline_base, "operating_income", None)),
            _first_line_value(getattr(scenario_base, "operating_income", None)),
        ),
        _build_company_charts_what_if_metric(
            "free_cash_flow",
            "Free Cash Flow",
            "usd",
            _first_line_value(getattr(baseline_base, "free_cash_flow", None)),
            _first_line_value(getattr(scenario_base, "free_cash_flow", None)),
        ),
        _build_company_charts_what_if_metric(
            "eps",
            "Diluted EPS",
            "usd_per_share",
            _first_line_value(getattr(baseline_base, "eps", None)),
            _first_line_value(getattr(scenario_base, "eps", None)),
        ),
    ]
    return CompanyChartsWhatIfImpactSummaryPayload(
        forecast_year=forecast_year,
        metrics=[metric for metric in metrics if metric is not None],
    )


def _build_company_charts_what_if_metric(
    key: str,
    label: str,
    unit: str,
    baseline_value: float | None,
    scenario_value: float | None,
) -> CompanyChartsWhatIfImpactMetricPayload | None:
    if baseline_value is None and scenario_value is None:
        return None
    delta_value = None
    delta_percent = None
    if baseline_value is not None and scenario_value is not None:
        delta_value = scenario_value - baseline_value
        delta_percent = _safe_divide(delta_value, abs(baseline_value)) if baseline_value not in (None, 0) else None
    return CompanyChartsWhatIfImpactMetricPayload(
        key=key,
        label=label,
        unit=unit,
        baseline_value=baseline_value,
        scenario_value=scenario_value,
        delta_value=delta_value,
        delta_percent=delta_percent,
    )


def _serialize_company_charts_what_if_override(item: Any) -> CompanyChartsWhatIfOverridePayload:
    return CompanyChartsWhatIfOverridePayload(
        key=str(getattr(item, "key", "")),
        label=str(getattr(item, "label", "")),
        unit=str(getattr(item, "unit", "")),
        requested_value=getattr(item, "requested_value", None),
        applied_value=getattr(item, "applied_value", None),
        baseline_value=getattr(item, "baseline_value", None),
        min_value=getattr(item, "min_value", None),
        max_value=getattr(item, "max_value", None),
        clipped=bool(getattr(item, "clipped", False)),
        source_detail=str(getattr(item, "source_detail", "")),
        source_kind=str(getattr(item, "source_kind", "sec")),
    )


def _serialize_company_charts_driver_control(item: Any) -> CompanyChartsDriverControlMetadataPayload:
    return CompanyChartsDriverControlMetadataPayload(
        key=str(getattr(item, "key", "")),
        label=str(getattr(item, "label", "")),
        unit=str(getattr(item, "unit", "")),
        baseline_value=getattr(item, "baseline_value", None),
        current_value=getattr(item, "current_value", None),
        min_value=getattr(item, "min_value", None),
        max_value=getattr(item, "max_value", None),
        step=getattr(item, "step", None),
        source_detail=str(getattr(item, "source_detail", "")),
        source_kind=str(getattr(item, "source_kind", "sec")),
    )


def _first_line_value(line: Any) -> float | None:
    values = getattr(line, "values", None) or []
    if not values:
        return None
    first_value = values[0]
    return float(first_value) if first_value is not None else None


def _build_projection_studio_driver_cards(
    annuals: list[Any],
    driver_bundle: Any,
    line_traces: dict[str, dict[int, Any]],
) -> list[CompanyChartsDriverCardPayload]:
    assumption_rows = {
        str(row.get("key")): row
        for row in getattr(driver_bundle, "assumption_rows", [])
        if row.get("key") is not None
    }
    source_periods = [f"FY{statement.period_end.year}" for statement in annuals[-PROJECTION_STUDIO_REPORTED_PERIODS:] if getattr(statement, "period_end", None) is not None]
    card_specs = (
        ("revenue_method", "Revenue Drivers", ("revenue",)),
        ("cost_schedule", "Cost Structure", ("cost_of_revenue", "gross_profit", "operating_income")),
        (
            "operating_working_capital",
            "Operating Working Capital",
            ("accounts_receivable", "inventory", "accounts_payable", "deferred_revenue", "accrued_operating_liabilities"),
        ),
        ("reinvestment", "Reinvestment + Capex", ("depreciation_amortization", "capex", "free_cash_flow")),
        ("below_line_bridge", "Below-The-Line Bridge", ("pretax_income", "income_tax", "net_income")),
        ("dilution", "Dilution Bridge", ("diluted_shares", "eps")),
    )

    cards: list[CompanyChartsDriverCardPayload] = []
    for assumption_key, title, trace_keys in card_specs:
        row = assumption_rows.get(assumption_key, {})
        default_markers, fallback_markers = _projection_studio_trace_markers(line_traces, trace_keys)
        if not row and not default_markers and not fallback_markers:
            continue
        cards.append(
            CompanyChartsDriverCardPayload(
                key=assumption_key,
                title=title,
                value=str(row.get("value") or "Trace-derived"),
                detail=str(row.get("detail")) if row.get("detail") is not None else None,
                source_periods=source_periods,
                default_markers=default_markers,
                fallback_markers=fallback_markers,
            )
        )
    return cards


def _projection_studio_trace_markers(
    line_traces: dict[str, dict[int, Any]],
    trace_keys: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    default_markers: list[str] = []
    fallback_markers: list[str] = []
    for trace_key in trace_keys:
        trace_map = line_traces.get(trace_key) or {}
        if not trace_map:
            continue
        first_year = min(trace_map)
        trace = trace_map[first_year]
        for input_item in getattr(trace, "inputs", []):
            source_kind = str(getattr(input_item, "source_kind", "sec"))
            source_detail = str(getattr(input_item, "source_detail", ""))
            if source_kind == "default" and source_detail and source_detail not in default_markers:
                default_markers.append(source_detail)
            if source_kind == "fallback" and source_detail and source_detail not in fallback_markers:
                fallback_markers.append(source_detail)
    return default_markers, fallback_markers


def _build_projection_studio_scenarios_comparison(driver_bundle: Any) -> list[CompanyChartsProjectedRowPayload]:
    scenarios = getattr(driver_bundle, "scenarios", None)
    if not isinstance(scenarios, dict):
        return []
    base = scenarios.get("base")
    bull = scenarios.get("bull")
    bear = scenarios.get("bear")
    if base is None or bull is None or bear is None:
        return []

    return [
        CompanyChartsProjectedRowPayload(
            key="scenario_next_year_growth",
            label="Next-Year Revenue Growth",
            unit="percent",
            scenario_values={
                "base": _projection_studio_round_value(getattr(driver_bundle, "base_next_year_growth", None), "percent"),
                "bull": _projection_studio_round_value(getattr(driver_bundle, "bull_next_year_growth", None), "percent"),
                "bear": _projection_studio_round_value(getattr(driver_bundle, "bear_next_year_growth", None), "percent"),
            },
        ),
        CompanyChartsProjectedRowPayload(
            key="scenario_next_year_revenue",
            label="Next-Year Revenue",
            unit="usd",
            scenario_values={
                "base": _projection_studio_first_year_value(base.revenue.values, "usd"),
                "bull": _projection_studio_first_year_value(bull.revenue.values, "usd"),
                "bear": _projection_studio_first_year_value(bear.revenue.values, "usd"),
            },
        ),
        CompanyChartsProjectedRowPayload(
            key="scenario_next_year_operating_income",
            label="Next-Year Operating Income",
            unit="usd",
            scenario_values={
                "base": _projection_studio_first_year_value(base.operating_income.values, "usd"),
                "bull": _projection_studio_first_year_value(bull.operating_income.values, "usd"),
                "bear": _projection_studio_first_year_value(bear.operating_income.values, "usd"),
            },
        ),
        CompanyChartsProjectedRowPayload(
            key="scenario_next_year_free_cash_flow",
            label="Next-Year Free Cash Flow",
            unit="usd",
            scenario_values={
                "base": _projection_studio_first_year_value(base.free_cash_flow.values, "usd"),
                "bull": _projection_studio_first_year_value(bull.free_cash_flow.values, "usd"),
                "bear": _projection_studio_first_year_value(bear.free_cash_flow.values, "usd"),
            },
        ),
        CompanyChartsProjectedRowPayload(
            key="scenario_next_year_eps",
            label="Next-Year Diluted EPS",
            unit="usd_per_share",
            scenario_values={
                "base": _projection_studio_first_year_value(base.eps.values, "usd_per_share"),
                "bull": _projection_studio_first_year_value(bull.eps.values, "usd_per_share"),
                "bear": _projection_studio_first_year_value(bear.eps.values, "usd_per_share"),
            },
        ),
    ]


def _build_projection_studio_sensitivity_matrix(
    annuals: list[Any],
    driver_bundle: Any,
    line_traces: dict[str, dict[int, Any]],
) -> list[CompanyChartsSensitivityCellPayload]:
    scenarios = getattr(driver_bundle, "scenarios", None)
    if not isinstance(scenarios, dict) or not annuals:
        return []

    base = scenarios.get("base")
    if base is None or not getattr(base, "bridge", None):
        return []

    latest_revenue = _statement_value(annuals[-1], "revenue")
    base_revenue = _first_numeric(getattr(base.revenue, "values", []))
    base_operating_income = _first_numeric(getattr(base.operating_income, "values", []))
    base_eps = _first_numeric(getattr(base.eps, "values", []))
    base_diluted_shares = _first_numeric(getattr(base.diluted_shares, "values", []))
    base_bridge = base.bridge[0] if getattr(base, "bridge", None) else None
    if latest_revenue in (None, 0) or base_revenue is None or base_operating_income is None or base_eps is None or base_diluted_shares in (None, 0) or base_bridge is None:
        return []

    base_growth = getattr(driver_bundle, "base_next_year_growth", None)
    if base_growth is None:
        base_growth = _growth_rate(base_revenue, latest_revenue)
    base_margin = _safe_divide(base_operating_income, base_revenue)
    tax_trace = (line_traces.get("income_tax") or {}).get(int(base_bridge.year))
    tax_rate = _projection_trace_input_value(tax_trace, "effective_tax_rate") if tax_trace is not None else _safe_divide(base_bridge.taxes, base_bridge.pretax_income)
    if base_growth is None or base_margin is None or tax_rate is None:
        return []

    pretax_offset = float(base_bridge.pretax_income) - float(base_bridge.ebit)
    margin_profile = _metric_margin_profile("operating_income")
    cells: list[CompanyChartsSensitivityCellPayload] = []
    for row_index, margin_delta in enumerate(PROJECTION_STUDIO_SENSITIVITY_DELTAS):
        margin = _clip(float(base_margin) + margin_delta, float(margin_profile["floor"]), float(margin_profile["cap"]))
        for column_index, growth_delta in enumerate(PROJECTION_STUDIO_SENSITIVITY_DELTAS):
            growth = _clip(float(base_growth) + growth_delta, REVENUE_FORECAST_GROWTH_FLOOR, REVENUE_FORECAST_GROWTH_CAP)
            is_base = row_index == 2 and column_index == 2
            if is_base:
                eps_value = float(base_eps)
            else:
                revenue = float(latest_revenue) * (1.0 + growth)
                operating_income = revenue * margin
                pretax_income = operating_income + pretax_offset
                taxes = pretax_income * (tax_rate if pretax_income >= 0 else min(tax_rate, 0.15))
                net_income = pretax_income - taxes
                eps_value = _safe_divide(net_income, base_diluted_shares)
            cells.append(
                CompanyChartsSensitivityCellPayload(
                    row_index=row_index,
                    column_index=column_index,
                    revenue_growth=_projection_studio_round_value(growth, "percent"),
                    operating_margin=_projection_studio_round_value(margin, "percent"),
                    eps=_projection_studio_round_value(eps_value, "usd_per_share"),
                    is_base=is_base,
                )
            )
    return cells


def _projection_trace_input_value(trace: Any, key: str) -> float | None:
    if trace is None:
        return None
    for input_item in getattr(trace, "inputs", []):
        if getattr(input_item, "key", None) == key and isinstance(getattr(input_item, "value", None), (int, float)):
            return float(input_item.value)
    return None


def _projection_studio_first_year_value(values: list[float], unit: str) -> float | None:
    if not values:
        return None
    return _projection_studio_round_value(values[0], unit)



def _first_numeric(values: list[Any]) -> float | None:
    for value in values:
        if isinstance(value, (int, float)) and isfinite(float(value)):
            return float(value)
    return None


def _projection_studio_round_value(value: float | None, unit: str) -> float | None:
    if value is None or not isfinite(float(value)):
        return None
    digits = 2
    if unit in {"percent", "ratio"}:
        digits = 4
    elif unit == "usd_per_share":
        digits = 3
    elif unit == "shares":
        digits = 2
    return _round(float(value), digits)


def _build_revenue_outlook_bridge_card(
    revenue_actual: list[CompanyChartsSeriesPointPayload],
    driver_bundle: Any | None,
) -> CompanyChartsCardPayload | None:
    if driver_bundle is None:
        return None

    bridge_rows = list(getattr(driver_bundle, "revenue_bridge_rows", []) or [])
    if not bridge_rows:
        return None

    visible_revenue = _visible_series_points(revenue_actual)
    if not visible_revenue:
        return None

    prior_point, prior_revenue = visible_revenue[-1]
    base_scenario = getattr(driver_bundle, "scenarios", {}).get("base") if isinstance(getattr(driver_bundle, "scenarios", None), dict) else None
    next_year = getattr(base_scenario.revenue, "years", [None])[0] if base_scenario is not None else None
    next_value = getattr(base_scenario.revenue, "values", [None])[0] if base_scenario is not None else None
    if next_year is None or next_value is None:
        return None

    forecast_label = f"FY{next_year}E"
    series = [
        _series(
            "revenue_bridge_start",
            "Starting Revenue",
            "usd",
            "bar",
            "actual",
            "solid",
            [
                CompanyChartsSeriesPointPayload(
                    period_label=prior_point.period_label,
                    fiscal_year=prior_point.fiscal_year,
                    period_end=prior_point.period_end,
                    value=_round(prior_revenue, 2),
                    series_kind="actual",
                    annotation=f"Last reported revenue carried into the {forecast_label} bridge.",
                )
            ],
        )
    ]

    for row in bridge_rows:
        amount = row.get("revenue_impact")
        if not isinstance(amount, (int, float)):
            continue
        series.append(
            _series(
                str(row.get("key") or "revenue_bridge_component"),
                str(row.get("label") or "Bridge Component"),
                "usd",
                "bar",
                "forecast",
                "muted",
                [
                    CompanyChartsSeriesPointPayload(
                        period_label=forecast_label,
                        fiscal_year=next_year,
                        period_end=None,
                        value=_round(float(amount), 2),
                        series_kind="forecast",
                        annotation=str(row.get("detail")) if row.get("detail") is not None else None,
                    )
                ],
            )
        )

    series.append(
        _series(
            "revenue_bridge_end",
            "Base Revenue Forecast",
            "usd",
            "bar",
            "forecast",
            "dashed",
            [
                CompanyChartsSeriesPointPayload(
                    period_label=forecast_label,
                    fiscal_year=next_year,
                    period_end=None,
                    value=_round(float(next_value), 2),
                    series_kind="forecast",
                    annotation=f"Base-case revenue implied for {forecast_label}.",
                )
            ],
        )
    )

    component_labels = [str(row.get("label") or "Component") for row in bridge_rows]
    highlights = [
        f"{prior_point.period_label} reported revenue bridges into {forecast_label} base revenue through {_join_series_labels(component_labels)}.",
        "Forecast bridge values remain internal projections rather than reported results.",
    ]

    return CompanyChartsCardPayload(
        key="revenue_outlook_bridge",
        title="Revenue Outlook Bridge",
        subtitle="Year-one bridge from the last reported period into the base forecast",
        metric_label="Revenue Bridge",
        unit_label="USD",
        series=series,
        highlights=highlights,
    )


def _build_margin_path_card(
    statements: list[Any],
    revenue_card: CompanyChartsCardPayload,
    profit_series: list[CompanyChartsSeriesPayload],
    driver_bundle: Any | None,
) -> CompanyChartsCardPayload | None:
    forecast_revenue_points = _select_revenue_forecast_points(revenue_card)
    actual_gross_margin = _margin_points_from_statements(statements, "gross_profit", kind="actual")
    actual_operating_margin = _margin_points_from_statements(statements, "operating_income", kind="actual")
    actual_net_margin = _margin_points_from_statements(statements, "net_income", kind="actual")

    series: list[CompanyChartsSeriesPayload] = []
    if actual_gross_margin:
        series.append(_series("gross_margin_actual", "Gross Margin Reported", "percent", "line", "actual", "solid", actual_gross_margin))
    if actual_operating_margin:
        series.append(_series("operating_margin_actual", "Operating Margin Reported", "percent", "line", "actual", "solid", actual_operating_margin))
    if actual_net_margin:
        series.append(_series("net_margin_actual", "Net Margin Reported", "percent", "line", "actual", "solid", actual_net_margin))

    if forecast_revenue_points:
        projected_gross_margin = getattr(driver_bundle, "projected_gross_margin", None) if driver_bundle is not None else None
        if projected_gross_margin is None:
            projected_gross_margin = _stable_margin_ratio(actual_gross_margin)
        gross_forecast = _flat_ratio_points(forecast_revenue_points, projected_gross_margin)
        operating_forecast = _ratio_points_from_series(
            _series_points_by_key(profit_series, "operating_income_forecast") or _series_points_by_key(profit_series, "operating_income_base"),
            forecast_revenue_points,
        )
        net_forecast = _ratio_points_from_series(
            _series_points_by_key(profit_series, "net_income_forecast") or _series_points_by_key(profit_series, "net_income_base"),
            forecast_revenue_points,
        )

        if gross_forecast:
            annotation = (
                "Projected gross margin holds the driver cost-of-revenue ratio."
                if driver_bundle is not None and getattr(driver_bundle, "projected_gross_margin", None) is not None
                else "Projected gross margin holds a normalized reported ratio because heuristic mode lacks an explicit cost-of-revenue schedule."
            )
            for point in gross_forecast:
                point.annotation = annotation
            series.append(_series("gross_margin_forecast", "Gross Margin Forecast", "percent", "line", "forecast", "dashed", gross_forecast))
        if operating_forecast:
            series.append(_series("operating_margin_forecast", "Operating Margin Forecast", "percent", "line", "forecast", "dashed", operating_forecast))
        if net_forecast:
            series.append(_series("net_margin_forecast", "Net Margin Forecast", "percent", "line", "forecast", "dashed", net_forecast))

    if not series:
        return None

    highlights = [
        "Reported and projected margin paths remain separated so forecast ratios never read as filed results.",
    ]
    if driver_bundle is None:
        highlights.append("Heuristic mode uses reported gross-margin history as the gross-margin anchor when no explicit projected cost-of-revenue schedule is available.")

    return CompanyChartsCardPayload(
        key="margin_path",
        title="Margin Path",
        subtitle="Gross, operating, and net margin across reported and projected periods",
        metric_label="Margin",
        unit_label="Percent",
        series=series,
        highlights=highlights,
    )


def _build_fcf_outlook_card(
    statements: list[Any],
    profit_series: list[CompanyChartsSeriesPayload],
    cash_series: list[CompanyChartsSeriesPayload],
    driver_bundle: Any | None,
) -> CompanyChartsCardPayload | None:
    series: list[CompanyChartsSeriesPayload] = []

    actual_net_income = _actual_series(statements, "net_income")
    actual_depreciation = _actual_series(statements, "depreciation_and_amortization")
    actual_sbc = _actual_series(statements, "stock_based_compensation")
    actual_delta_working_capital = _actual_delta_operating_working_capital_points(statements)
    actual_operating_cash_flow = _actual_series(statements, "operating_cash_flow")
    actual_capex = _actual_series(statements, "capex")
    actual_free_cash_flow = _actual_series(statements, "free_cash_flow")

    if actual_net_income:
        series.append(_series("fcf_net_income_actual", "Net Income Reported", "usd", "line", "actual", "solid", actual_net_income))
    if actual_depreciation:
        series.append(_series("fcf_depreciation_actual", "D&A Reported", "usd", "line", "actual", "solid", actual_depreciation))
    if actual_sbc:
        series.append(_series("fcf_sbc_actual", "SBC Reported", "usd", "line", "actual", "solid", actual_sbc))
    if actual_delta_working_capital:
        series.append(_series("fcf_delta_wc_actual", "Delta Operating WC Reported", "usd", "line", "actual", "solid", actual_delta_working_capital))
    if actual_operating_cash_flow:
        series.append(_series("fcf_ocf_actual", "Operating CF Reported", "usd", "line", "actual", "solid", actual_operating_cash_flow))
    if actual_capex:
        series.append(_series("fcf_capex_actual", "Capex Reported", "usd", "line", "actual", "solid", actual_capex))
    if actual_free_cash_flow:
        series.append(_series("fcf_fcf_actual", "Free CF Reported", "usd", "line", "actual", "solid", actual_free_cash_flow))

    highlights = [
        "Reported and forecast cash-flow bridge items remain labeled separately so the FCF path stays audit-friendly.",
    ]

    forecast_net_income = _series_points_by_key(profit_series, "net_income_forecast")
    forecast_operating_cash_flow = _series_points_by_key(cash_series, "operating_cash_flow_forecast")
    forecast_capex = _series_points_by_key(cash_series, "capex_forecast")
    forecast_free_cash_flow = _series_points_by_key(cash_series, "free_cash_flow_forecast")

    def _append_forecast_series_from_visible_base() -> bool:
        appended = False
        if forecast_net_income is not None:
            series.append(_series("fcf_net_income_forecast", "Net Income Forecast", "usd", "line", "forecast", "dashed", forecast_net_income.points))
            appended = True
        if forecast_operating_cash_flow is not None:
            series.append(_series("fcf_ocf_forecast", "Operating CF Forecast", "usd", "line", "forecast", "dashed", forecast_operating_cash_flow.points))
            appended = True
        if forecast_capex is not None:
            series.append(_series("fcf_capex_forecast", "Capex Forecast", "usd", "line", "forecast", "dashed", forecast_capex.points))
            appended = True
        if forecast_free_cash_flow is not None:
            series.append(_series("fcf_fcf_forecast", "Free CF Forecast", "usd", "line", "forecast", "dashed", forecast_free_cash_flow.points))
            appended = True
        return appended

    if driver_bundle is not None:
        base_scenario = getattr(driver_bundle, "scenarios", {}).get("base") if isinstance(getattr(driver_bundle, "scenarios", None), dict) else None
        bridge_points = list(getattr(base_scenario, "bridge", []) or []) if base_scenario is not None else []
        if bridge_points:
            series.extend(
                [
                    _series("fcf_net_income_forecast", "Net Income Base", "usd", "line", "forecast", "dashed", _bridge_points_to_series_points(bridge_points, "net_income")),
                    _series("fcf_depreciation_forecast", "D&A Base", "usd", "line", "forecast", "dashed", _bridge_points_to_series_points(bridge_points, "depreciation")),
                    _series("fcf_sbc_forecast", "SBC Base", "usd", "line", "forecast", "dashed", _bridge_points_to_series_points(bridge_points, "stock_based_compensation")),
                    _series("fcf_delta_wc_forecast", "Delta Operating WC Base", "usd", "line", "forecast", "dashed", _bridge_points_to_series_points(bridge_points, "delta_working_capital")),
                    _series("fcf_ocf_forecast", "Operating CF Base", "usd", "line", "forecast", "dashed", _bridge_points_to_series_points(bridge_points, "operating_cash_flow")),
                    _series("fcf_capex_forecast", "Capex Base", "usd", "line", "forecast", "dashed", _bridge_points_to_series_points(bridge_points, "capex")),
                    _series("fcf_fcf_forecast", "Free CF Base", "usd", "line", "forecast", "dashed", _bridge_points_to_series_points(bridge_points, "free_cash_flow")),
                ]
            )
            highlights.append("Base-case FCF bridge keeps net income, D&A, SBC, operating working capital, and capex explicit in forecast mode.")
        elif _append_forecast_series_from_visible_base():
            highlights.append("Driver mode fell back to the visible base net income, operating cash flow, capex, and free cash flow series because the detailed bridge payload was unavailable for this ticker.")
    else:
        if _append_forecast_series_from_visible_base():
            highlights.append("Heuristic mode exposes the earnings-to-cash path through net income, operating cash flow, capex, and free cash flow without a detailed working-capital bridge.")

    if not series:
        return None

    return CompanyChartsCardPayload(
        key="fcf_outlook",
        title="FCF Outlook",
        subtitle="Path from earnings and cash-flow inputs into free cash flow",
        metric_label="Free Cash Flow",
        unit_label="USD",
        series=series,
        highlights=highlights,
    )


def _select_revenue_forecast_points(card: CompanyChartsCardPayload) -> list[CompanyChartsSeriesPointPayload]:
    for key in ("revenue_base", "revenue_forecast"):
        series = _series_points_by_key(card.series, key)
        if series is not None:
            return series.points
    return []


def _margin_points_from_statements(
    statements: list[Any],
    metric_key: str,
    *,
    kind: str,
) -> list[CompanyChartsSeriesPointPayload]:
    points: list[CompanyChartsSeriesPointPayload] = []
    for statement in statements:
        revenue = _statement_value(statement, "revenue")
        if revenue in (None, 0):
            continue
        metric_value = _statement_value(statement, metric_key)
        if metric_value is None and metric_key == "gross_profit":
            cost_of_revenue = _statement_value(statement, "cost_of_revenue")
            if cost_of_revenue is not None:
                metric_value = revenue - cost_of_revenue
        ratio = _safe_divide(metric_value, revenue)
        if ratio is None:
            continue
        points.append(
            CompanyChartsSeriesPointPayload(
                period_label=f"FY{statement.period_end.year}",
                fiscal_year=statement.period_end.year,
                period_end=statement.period_end,
                value=_round(ratio, 4),
                series_kind=kind,
            )
        )
    return points


def _ratio_points_from_series(
    numerator_series: CompanyChartsSeriesPayload | None,
    revenue_points: list[CompanyChartsSeriesPointPayload],
) -> list[CompanyChartsSeriesPointPayload]:
    if numerator_series is None:
        return []
    numerator_by_year = {
        point.fiscal_year: value
        for point, value in _visible_series_points(numerator_series.points)
        if point.fiscal_year is not None
    }
    ratio_points: list[CompanyChartsSeriesPointPayload] = []
    for point, revenue in _visible_series_points(revenue_points):
        if point.fiscal_year is None:
            continue
        numerator = numerator_by_year.get(point.fiscal_year)
        ratio = _safe_divide(numerator, revenue)
        if ratio is None:
            continue
        ratio_points.append(
            CompanyChartsSeriesPointPayload(
                period_label=point.period_label,
                fiscal_year=point.fiscal_year,
                period_end=point.period_end,
                value=_round(ratio, 4),
                series_kind=point.series_kind,
            )
        )
    return ratio_points


def _flat_ratio_points(
    revenue_points: list[CompanyChartsSeriesPointPayload],
    ratio: float | None,
) -> list[CompanyChartsSeriesPointPayload]:
    if ratio is None:
        return []
    points: list[CompanyChartsSeriesPointPayload] = []
    for point in revenue_points:
        points.append(
            CompanyChartsSeriesPointPayload(
                period_label=point.period_label,
                fiscal_year=point.fiscal_year,
                period_end=point.period_end,
                value=_round(ratio, 4),
                series_kind="forecast",
            )
        )
    return points


def _stable_margin_ratio(points: list[CompanyChartsSeriesPointPayload]) -> float | None:
    values = [value for _point, value in _visible_series_points(points)]
    if not values:
        return None
    window = values[-3:]
    return fmean(window)


def _actual_delta_operating_working_capital_points(statements: list[Any]) -> list[CompanyChartsSeriesPointPayload]:
    points: list[CompanyChartsSeriesPointPayload] = []
    previous_balance: float | None = None
    for statement in statements:
        balance = _operating_working_capital_balance(statement)
        if balance is not None and previous_balance is not None:
            points.append(
                CompanyChartsSeriesPointPayload(
                    period_label=f"FY{statement.period_end.year}",
                    fiscal_year=statement.period_end.year,
                    period_end=statement.period_end,
                    value=_round(balance - previous_balance, 2),
                    series_kind="actual",
                )
            )
        previous_balance = balance
    return points


def _operating_working_capital_balance(statement: Any) -> float | None:
    accounts_receivable = _statement_value(statement, "accounts_receivable")
    inventory = _statement_value(statement, "inventory")
    accounts_payable = _statement_value(statement, "accounts_payable")
    deferred_revenue = _statement_value(statement, "deferred_revenue")
    accrued_operating_liabilities = _statement_value(statement, "accrued_operating_liabilities")
    if all(value is None for value in (accounts_receivable, inventory, accounts_payable, deferred_revenue, accrued_operating_liabilities)):
        return None
    return float(accounts_receivable or 0.0) + float(inventory or 0.0) - float(accounts_payable or 0.0) - float(deferred_revenue or 0.0) - float(accrued_operating_liabilities or 0.0)


def _bridge_points_to_series_points(
    bridge_points: list[Any],
    attribute: str,
) -> list[CompanyChartsSeriesPointPayload]:
    points: list[CompanyChartsSeriesPointPayload] = []
    for bridge_point in bridge_points:
        value = getattr(bridge_point, attribute, None)
        if not isinstance(value, (int, float)):
            continue
        points.append(
            CompanyChartsSeriesPointPayload(
                period_label=f"FY{bridge_point.year}E",
                fiscal_year=bridge_point.year,
                period_end=None,
                value=_round(float(value), 2),
                series_kind="forecast",
            )
        )
    return points


def _join_series_labels(labels: list[str]) -> str:
    cleaned = [label for label in labels if label]
    if not cleaned:
        return "forecast effects"
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"


def _statement_value(statement: Any, key: str) -> float | None:
    data = getattr(statement, "data", None)
    if not isinstance(data, dict):
        return None
    value = data.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    if key == "weighted_average_shares_diluted":
        alias = data.get("weighted_average_diluted_shares")
        if isinstance(alias, (int, float)):
            return float(alias)
    if key == "net_ppe":
        for alias_key in (
            "net_ppe",
            "net_property_plant_equipment",
            "net_property_plant_and_equipment",
            "property_plant_and_equipment_net",
            "ppe_net",
            "fixed_assets_net",
        ):
            alias = data.get(alias_key)
            if isinstance(alias, (int, float)):
                return float(alias)
    return None


def _ebitda_proxy(statement: Any) -> float | None:
    operating_income = _statement_value(statement, "operating_income")
    depreciation = _statement_value(statement, "depreciation_and_amortization")
    if operating_income is None and depreciation is None:
        return None
    return float(operating_income or 0) + float(depreciation or 0)


def _metric_projection_value(statement: Any, key: str) -> float | None:
    if key == "ebitda_proxy":
        return _ebitda_proxy(statement)
    value = _statement_value(statement, key)
    if value is None and key == "free_cash_flow":
        operating_cash_flow = _statement_value(statement, "operating_cash_flow")
        capex = _statement_value(statement, "capex")
        # Some filings persist OCF and capex but omit explicit FCF, so derive FCF from the available cash flow fields.
        value = operating_cash_flow - capex if operating_cash_flow is not None and capex is not None else None
    return value


def _point_value(point: CompanyChartsSeriesPointPayload) -> float | None:
    value = getattr(point, "value", None)
    if not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if isfinite(numeric) else None


def _visible_series_points(points: list[CompanyChartsSeriesPointPayload]) -> list[tuple[CompanyChartsSeriesPointPayload, float]]:
    visible: list[tuple[CompanyChartsSeriesPointPayload, float]] = []
    for point in points:
        value = _point_value(point)
        if value is None:
            continue
        visible.append((point, value))
    return visible


def _contiguous_visible_series_points(points: list[CompanyChartsSeriesPointPayload]) -> list[tuple[CompanyChartsSeriesPointPayload, float]]:
    visible = _visible_series_points(points)
    if not visible:
        return []
    contiguous: list[tuple[CompanyChartsSeriesPointPayload, float]] = [visible[-1]]
    for item in reversed(visible[:-1]):
        if not _series_points_are_adjacent(item[0], contiguous[-1][0]):
            break
        contiguous.append(item)
    contiguous.reverse()
    return contiguous


def _series_points_are_adjacent(previous: CompanyChartsSeriesPointPayload, current: CompanyChartsSeriesPointPayload) -> bool:
    if previous.fiscal_year is None or current.fiscal_year is None:
        return True
    return current.fiscal_year - previous.fiscal_year == 1


def _growth_rate(current: float | None, previous: float | None) -> float | None:
    if (
        current is None
        or previous is None
        or not isfinite(float(current))
        or not isfinite(float(previous))
        or previous <= 0
        or current < 0
    ):
        return None
    return (float(current) / float(previous)) - 1


def _historical_growth_rates(values: list[float | None]) -> list[float]:
    growths: list[float] = []
    for previous, current in zip(values, values[1:]):
        growth = _growth_rate(current, previous)
        if growth is not None:
            growths.append(growth)
    return growths


def _weighted_recent_growth(growths: list[float]) -> float | None:
    if not growths:
        return None
    window = growths[-len(REVENUE_FORECAST_RECENT_WEIGHTS):]
    weights = REVENUE_FORECAST_RECENT_WEIGHTS[-len(window):]
    total_weight = sum(weights)
    if total_weight == 0:
        return None
    return sum(value * weight for value, weight in zip(window, weights)) / total_weight


def _metric_margin_profile(key: str) -> dict[str, Any]:
    if key in {"operating_income", "ebitda_proxy"}:
        return MARGIN_FORECAST_PROFILES["operating"]
    if key == "net_income":
        return MARGIN_FORECAST_PROFILES["net_income"]
    if key in {"operating_cash_flow", "free_cash_flow"}:
        return MARGIN_FORECAST_PROFILES["cash_flow"]
    if key == "capex":
        return MARGIN_FORECAST_PROFILES["capex"]
    return MARGIN_FORECAST_PROFILES["operating"]


def _normalized_margin(margins: list[float], key: str) -> float | None:
    if not margins:
        return None
    profile = _metric_margin_profile(key)
    floor = float(profile["floor"])
    cap = float(profile["cap"])
    recent_weight = float(profile["normalized_recent_weight"])
    # Winsorize observed margins first so unusually strong or weak years do not anchor the full forecast path.
    winsorized = [_clip(value, floor, cap) for value in margins]
    recent_window = winsorized[-min(MARGIN_FORECAST_NORMALIZATION_WINDOW, len(winsorized)) :]
    history_average = fmean(winsorized)
    recent_average = fmean(recent_window)
    normalized = (history_average * (1 - recent_weight)) + (recent_average * recent_weight)
    return _clip(normalized, floor, cap)


def _margin_convergence_path(margins: list[float], key: str, horizon: int) -> list[float]:
    if not margins or horizon <= 0:
        return []
    profile = _metric_margin_profile(key)
    floor = float(profile["floor"])
    cap = float(profile["cap"])
    reversion_weights = tuple(float(weight) for weight in profile["reversion_weights"])
    recent_margin = _clip(margins[-1], floor, cap)
    normalized_margin = _normalized_margin(margins, key)
    if normalized_margin is None:
        return []
    path: list[float] = []
    for index in range(horizon):
        weight = reversion_weights[min(index, len(reversion_weights) - 1)]
        margin = recent_margin + ((normalized_margin - recent_margin) * weight)
        path.append(_clip(margin, floor, cap))
    return path


def _forecast_diluted_shares(shares_history: list[float], horizon: int) -> list[float]:
    if not shares_history or horizon <= 0:
        return []
    latest_shares = float(shares_history[-1])
    if latest_shares <= 0:
        return []

    share_growths = [
        _clip(value, DILUTED_SHARE_FORECAST_CHANGE_FLOOR, DILUTED_SHARE_FORECAST_CHANGE_CAP)
        for value in _historical_growth_rates(shares_history)
    ]
    # Start from the recent buyback/dilution trend, then mean-revert toward flat share count to avoid runaway bridges.
    current_growth = _weighted_recent_growth(share_growths) if share_growths else 0.0
    current_growth = _clip(current_growth or 0.0, DILUTED_SHARE_FORECAST_CHANGE_FLOOR, DILUTED_SHARE_FORECAST_CHANGE_CAP)

    forecast: list[float] = []
    shares = latest_shares
    for _ in range(horizon):
        growth = _clip(current_growth, DILUTED_SHARE_FORECAST_CHANGE_FLOOR, DILUTED_SHARE_FORECAST_CHANGE_CAP)
        shares *= 1 + growth
        forecast.append(shares)
        current_growth = growth + ((0.0 - growth) * DILUTED_SHARE_FORECAST_REVERSION_SPEED)
    return forecast


def _cagr(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    normalized: list[float] = []
    for value in values:
        if not isinstance(value, (int, float)):
            return None
        numeric = float(value)
        if not isfinite(numeric) or numeric <= 0:
            return None
        normalized.append(numeric)
    return (normalized[-1] / normalized[0]) ** (1 / (len(normalized) - 1)) - 1


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    normalized_numerator = float(numerator)
    normalized_denominator = float(denominator)
    if (
        not isfinite(normalized_numerator)
        or not isfinite(normalized_denominator)
        or normalized_denominator <= 0
    ):
        return None
    return normalized_numerator / normalized_denominator


def _blend(*values: float | None) -> float | None:
    cleaned = [float(value) for value in values if isinstance(value, (int, float))]
    return fmean(cleaned) if cleaned else None


def _score(value: float | None, lower: float, upper: float) -> int | None:
    if value is None:
        return None
    return int(round(((_clip(value, lower, upper) - lower) / (upper - lower)) * 100))


def _forecast_stability_profile(
    session: Session,
    company: Company,
    statements: list[Any],
    revenue_actual: list[CompanyChartsSeriesPointPayload],
    earnings_points: list[Any],
    earnings_releases: list[Any],
    restatements: list[Any],
    driver_bundle: Any | None,
) -> CompanyChartsForecastDiagnosticsPayload:
    history_depth = len(statements)
    thin_history = history_depth < FORECAST_STABILITY_THIN_HISTORY_PERIODS
    revenue_values = [_point_value(point) for point in revenue_actual]
    growths = _historical_growth_rates(revenue_values)
    volatility_window = growths[-FORECAST_STABILITY_VOLATILITY_WINDOW:] if growths else []
    average_absolute_growth = (
        sum(abs(value) for value in volatility_window) / len(volatility_window)
        if volatility_window
        else None
    )
    volatility_band = _growth_volatility_band(average_absolute_growth)
    sector_template = _forecast_stability_sector_template(company)
    backtest = _walk_forward_forecast_backtest(session, company, statements, earnings_releases)

    missing_inputs: list[str] = []
    missing_data_penalty = 0
    missing_revenue_points = max(0, history_depth - len(revenue_actual))
    if missing_revenue_points > 0:
        missing_data_penalty += missing_revenue_points * FORECAST_STABILITY_MISSING_REVENUE_POINT_PENALTY
        missing_inputs.append("reported_revenue_history_gaps")
    elif not revenue_actual:
        missing_inputs.append("reported_revenue_history_missing")

    raw_quality = getattr(earnings_points[-1], "quality_score", None) if earnings_points else None
    normalized_quality = _normalized_earnings_quality(raw_quality)
    quality_penalty = 0
    if normalized_quality is None:
        quality_penalty = FORECAST_STABILITY_MISSING_QUALITY_SIGNAL_PENALTY
        missing_data_penalty += quality_penalty
        missing_inputs.append("latest_earnings_quality_missing")
    elif normalized_quality < 0.4:
        quality_penalty = FORECAST_STABILITY_LOW_QUALITY_PENALTY

    short_history_penalty = max(0, FORECAST_STABILITY_TARGET_HISTORY_PERIODS - history_depth) * FORECAST_STABILITY_HISTORY_GAP_PENALTY
    cyclicality_penalty = min(18, int(round((average_absolute_growth or 0.0) * 30)))
    structural_break_penalty = _structural_break_penalty(growths, statements)
    mna_penalty = _major_mna_penalty(statements)
    restatement_penalty = _restatement_penalty(restatements)
    share_instability_penalty = _share_instability_penalty(statements)
    scenario_dispersion = _scenario_dispersion(driver_bundle)
    scenario_penalty = min(8, int(round((scenario_dispersion or 0.0) * 24)))
    empirical_score = _empirical_stability_score(backtest["weighted_error"], backtest["sample_size"], sector_template)

    final_score = int(
        _clip(
            empirical_score
            - short_history_penalty
            - cyclicality_penalty
            - structural_break_penalty
            - mna_penalty
            - restatement_penalty
            - share_instability_penalty
            - scenario_penalty
            - quality_penalty
            - missing_data_penalty,
            FORECAST_STABILITY_MIN_SCORE,
            FORECAST_STABILITY_MAX_SCORE,
        )
    )
    guidance_usage = _guidance_usage(driver_bundle, earnings_releases)

    components = [
        CompanyChartsScoreComponentPayload(
            key="backtest_error",
            label="Historical backtests",
            value=_round(backtest["weighted_error"], 4),
            display_value=_backtest_display(backtest["weighted_error"], backtest["error_band"], backtest["sample_size"]),
            impact=int(round(empirical_score - FORECAST_STABILITY_BASE_SCORE)),
            detail=(
                "Point-in-time walk-forward revenue, EBIT, EPS, and FCF errors anchor the stability score before risk penalties are applied. "
                f"Metric weights: {_metric_weight_display(backtest['metric_weights'])}."
            ),
        ),
        CompanyChartsScoreComponentPayload(
            key="history_depth",
            label="History depth",
            value=history_depth,
            display_value=f"{history_depth} annual periods",
            impact=-short_history_penalty,
            detail="Short public history limits the number of walk-forward snapshots available for calibration.",
        ),
        CompanyChartsScoreComponentPayload(
            key="growth_volatility",
            label="Cyclicality",
            value=_round(average_absolute_growth, 4),
            display_value=(f"{(average_absolute_growth or 0.0) * 100:.0f}% avg abs YoY ({volatility_band})" if average_absolute_growth is not None else "Unavailable"),
            impact=-cyclicality_penalty,
            detail="Large swings in historical revenue growth make future driver assumptions less stable.",
        ),
        CompanyChartsScoreComponentPayload(
            key="structural_breaks",
            label="Structural breaks",
            value=structural_break_penalty,
            display_value=f"{structural_break_penalty} pts",
            impact=-structural_break_penalty,
            detail="Recent growth or margin regime shifts reduce trust in extrapolating earlier history.",
        ),
        CompanyChartsScoreComponentPayload(
            key="major_m_and_a",
            label="Major M&A",
            value=mna_penalty,
            display_value=f"{mna_penalty} pts",
            impact=-mna_penalty,
            detail="Acquisition-heavy periods can break comparability between historical and forecast economics.",
        ),
        CompanyChartsScoreComponentPayload(
            key="accounting_restatements",
            label="Accounting restatements",
            value=restatement_penalty,
            display_value=f"{restatement_penalty} pts",
            impact=-restatement_penalty,
            detail="Recent restatements lower confidence that past reported drivers are a stable base for forecasting.",
        ),
        CompanyChartsScoreComponentPayload(
            key="share_count_stability",
            label="Share-count stability",
            value=share_instability_penalty,
            display_value=f"{share_instability_penalty} pts",
            impact=-share_instability_penalty,
            detail="Unstable diluted share counts weaken EPS stability even when revenue forecasts are reasonable.",
        ),
        CompanyChartsScoreComponentPayload(
            key="scenario_dispersion",
            label="Scenario dispersion",
            value=_round(scenario_dispersion, 4),
            display_value=_dispersion_display(scenario_dispersion),
            impact=-scenario_penalty,
            detail="Wide spread between bull, base, and bear cases keeps the stability score conservative.",
        ),
        CompanyChartsScoreComponentPayload(
            key="latest_earnings_quality",
            label="Parser confidence",
            value=_round(float(raw_quality), 3) if isinstance(raw_quality, (int, float)) else None,
            display_value=_format_quality_display(raw_quality),
            impact=-quality_penalty,
            detail="Low or missing parser confidence is treated as a conservative penalty rather than a positive boost.",
        ),
        CompanyChartsScoreComponentPayload(
            key="missing_data_penalty",
            label="Missing-data penalty",
            value=missing_data_penalty,
            display_value=f"{missing_data_penalty} pts",
            impact=-missing_data_penalty,
            detail="Missing revenue history or missing quality signals reduce the score rather than being silently imputed.",
        ),
    ]

    return CompanyChartsForecastDiagnosticsPayload(
        final_score=final_score,
        summary=_forecast_stability_summary(
            history_depth,
            sector_template["label"],
            backtest["sample_size"],
            backtest["weighted_error"],
            backtest["error_band"],
            backtest["metric_weights"],
            guidance_usage,
            scenario_dispersion,
        ),
        history_depth_years=history_depth,
        thin_history=thin_history,
        growth_volatility=_round(average_absolute_growth, 4),
        growth_volatility_band=volatility_band,
        missing_data_penalty=missing_data_penalty + quality_penalty,
        quality_score=_round(float(raw_quality), 3) if isinstance(raw_quality, (int, float)) else None,
        missing_inputs=missing_inputs,
        sample_size=int(backtest["sample_size"]),
        scenario_dispersion=_round(scenario_dispersion, 4),
        sector_template=sector_template["label"],
        guidance_usage=guidance_usage,
        historical_backtest_error_band=backtest["error_band"],
        backtest_weighted_error=_round(backtest["weighted_error"], 4),
        backtest_horizon_errors={str(key): _round(value, 4) for key, value in backtest["horizon_errors"].items()},
        backtest_metric_weights={key: _round(value, 4) for key, value in backtest["metric_weights"].items()},
        backtest_metric_errors={key: _round(value, 4) for key, value in backtest["metric_errors"].items()},
        backtest_metric_horizon_errors={
            key: {str(horizon): _round(value, 4) for horizon, value in horizon_errors.items()}
            for key, horizon_errors in backtest["metric_horizon_errors"].items()
        },
        backtest_metric_sample_sizes={key: int(value) for key, value in backtest["metric_sample_sizes"].items()},
        components=components,
    )


def _empirical_stability_score(weighted_error: float | None, sample_size: int, sector_template: dict[str, Any]) -> int:
    if weighted_error is None or sample_size < len(FORECAST_STABILITY_BACKTEST_HORIZONS):
        return FORECAST_STABILITY_BASE_SCORE
    tight = float(sector_template["tight"])
    moderate = float(sector_template["moderate"])
    wide = float(sector_template["wide"])
    if weighted_error <= tight:
        return 82
    if weighted_error <= moderate:
        return 72
    if weighted_error <= wide:
        return 60
    return 46


def _walk_forward_forecast_backtest(
    session: Session,
    company: Company,
    statements: list[Any],
    earnings_releases: list[Any],
) -> dict[str, Any]:
    metric_horizon_errors: dict[str, dict[int, list[float]]] = {
        metric: {horizon: [] for horizon in FORECAST_STABILITY_BACKTEST_HORIZONS}
        for metric in FORECAST_STABILITY_BACKTEST_METRIC_WEIGHTS
    }
    metric_actuals_by_year = {
        metric: {
            statement.period_end.year: value
            for statement in statements
            if getattr(statement, "period_end", None) is not None
            for value in [_actual_metric_value(statement, metric)]
            if value is not None
        }
        for metric in FORECAST_STABILITY_BACKTEST_METRIC_WEIGHTS
    }
    metric_sample_sizes = {metric: 0 for metric in FORECAST_STABILITY_BACKTEST_METRIC_WEIGHTS}
    sample_size = 0
    for cutoff_index in range(1, len(statements) - 1):
        historical = statements[: cutoff_index + 1]
        revenue_actual = _actual_series(historical, "revenue")
        if len(revenue_actual) < 2:
            continue
        cutoff_as_of = _statement_effective_at(historical[-1])
        visible_releases = _visible_releases_as_of(earnings_releases, cutoff_as_of)
        driver_bundle = build_driver_forecast_bundle(historical, visible_releases, company=company)
        growth_actual = _growth_series(revenue_actual, "actual")
        hist_3y = _cagr([_point_value(point) for point in revenue_actual[-4:]]) if len(revenue_actual) >= 4 else None
        forecast_state = _build_forecast_state(historical, revenue_actual, growth_actual, hist_3y, driver_bundle, company.name)
        realized_snapshot = False
        for metric in FORECAST_STABILITY_BACKTEST_METRIC_WEIGHTS:
            metric_points = _forecast_metric_points(forecast_state, metric)
            realized_metric = False
            for point in metric_points:
                if point.fiscal_year is None:
                    continue
                horizon = point.fiscal_year - historical[-1].period_end.year
                if horizon not in FORECAST_STABILITY_BACKTEST_HORIZONS:
                    continue
                realized_error = _absolute_percentage_error(_point_value(point), metric_actuals_by_year[metric].get(point.fiscal_year))
                if realized_error is None:
                    continue
                metric_horizon_errors[metric][horizon].append(realized_error)
                realized_metric = True
                realized_snapshot = True
            if realized_metric:
                metric_sample_sizes[metric] += 1
        if realized_snapshot:
            sample_size += 1

    metric_horizon_means = {
        metric: {
            horizon: (sum(errors) / len(errors) if errors else None)
            for horizon, errors in horizon_errors.items()
        }
        for metric, horizon_errors in metric_horizon_errors.items()
    }
    metric_errors = {
        metric: _weighted_backtest_error(horizon_errors)
        for metric, horizon_errors in metric_horizon_means.items()
    }
    horizon_means = _weighted_metric_horizon_errors(metric_horizon_means)
    weighted_error = _weighted_backtest_error(horizon_means)
    error_band = _error_band(weighted_error, _forecast_stability_sector_template(company))
    return {
        "sample_size": sample_size,
        "weighted_error": weighted_error,
        "error_band": error_band,
        "horizon_errors": horizon_means,
        "metric_weights": dict(FORECAST_STABILITY_BACKTEST_METRIC_WEIGHTS),
        "metric_errors": metric_errors,
        "metric_horizon_errors": metric_horizon_means,
        "metric_sample_sizes": metric_sample_sizes,
    }


def _walk_forward_revenue_backtest(
    session: Session,
    company: Company,
    statements: list[Any],
    earnings_releases: list[Any],
) -> dict[str, Any]:
    return _walk_forward_forecast_backtest(session, company, statements, earnings_releases)


def _primary_revenue_forecast_points(forecast_state: dict[str, Any]) -> list[CompanyChartsSeriesPointPayload]:
    revenue_card = forecast_state.get("revenue_card")
    series = getattr(revenue_card, "series", [])
    for key in ("revenue_base", "revenue_forecast"):
        matched = next((item for item in series if item.key == key), None)
        if matched is not None:
            return list(matched.points)
    return []


def _forecast_metric_points(forecast_state: dict[str, Any], metric: str) -> list[CompanyChartsSeriesPointPayload]:
    if metric == "revenue":
        return _primary_revenue_forecast_points(forecast_state)
    if metric == "operating_income":
        matched = _series_points_by_key(forecast_state.get("profit_series", []), "operating_income_forecast")
        return list(matched.points) if matched is not None else []
    if metric == "free_cash_flow":
        matched = _series_points_by_key(forecast_state.get("cash_series", []), "free_cash_flow_forecast")
        return list(matched.points) if matched is not None else []
    if metric == "eps":
        eps_card = forecast_state.get("eps_card")
        series = getattr(eps_card, "series", [])
        for key in ("eps_base", "eps_forecast"):
            matched = next((item for item in series if item.key == key), None)
            if matched is not None:
                return list(matched.points)
    return []


def _actual_metric_value(statement: Any, metric: str) -> float | None:
    if metric in {"revenue", "operating_income", "free_cash_flow"}:
        return _metric_projection_value(statement, metric)
    if metric == "eps":
        eps = _statement_value(statement, "eps")
        if eps is not None:
            return eps
        net_income = _statement_value(statement, "net_income")
        diluted_shares = _statement_value(statement, "weighted_average_shares_diluted")
        return _safe_divide(net_income, diluted_shares)
    return None


def _weighted_metric_horizon_errors(metric_horizon_errors: dict[str, dict[int, float | None]]) -> dict[int, float | None]:
    horizon_means: dict[int, float | None] = {}
    for horizon in FORECAST_STABILITY_BACKTEST_HORIZONS:
        weighted_sum = 0.0
        total_weight = 0.0
        for metric, weight in FORECAST_STABILITY_BACKTEST_METRIC_WEIGHTS.items():
            value = metric_horizon_errors.get(metric, {}).get(horizon)
            if value is None:
                continue
            weighted_sum += float(value) * float(weight)
            total_weight += float(weight)
        horizon_means[horizon] = (weighted_sum / total_weight) if total_weight > 0 else None
    return horizon_means


def _weighted_backtest_error(horizon_errors: dict[int, float | None]) -> float | None:
    weighted_sum = 0.0
    total_weight = 0.0
    for horizon, weight in FORECAST_STABILITY_BACKTEST_WEIGHTS.items():
        value = horizon_errors.get(horizon)
        if value is None:
            continue
        weighted_sum += float(value) * float(weight)
        total_weight += float(weight)
    if total_weight <= 0:
        return None
    return weighted_sum / total_weight


def _absolute_percentage_error(predicted: float | None, actual: float | None) -> float | None:
    if predicted is None or actual is None:
        return None
    denominator = abs(float(actual))
    if denominator <= 0:
        return None
    return abs(float(predicted) - float(actual)) / denominator


def _forecast_stability_sector_template(company: Company) -> dict[str, Any]:
    sector = (company.market_sector or company.sector or "").strip().lower()
    return FORECAST_STABILITY_SECTOR_TEMPLATES.get(sector, FORECAST_STABILITY_SECTOR_TEMPLATES["default"])


def _error_band(weighted_error: float | None, sector_template: dict[str, Any]) -> str:
    if weighted_error is None:
        return "insufficient_sample"
    if weighted_error <= float(sector_template["tight"]):
        return "tight"
    if weighted_error <= float(sector_template["moderate"]):
        return "moderate"
    if weighted_error <= float(sector_template["wide"]):
        return "wide"
    return "very_wide"


def _structural_break_penalty(growths: list[float], statements: list[Any]) -> int:
    if len(growths) < 3:
        return 0
    pivot = max(1, len(growths) - 2)
    early = growths[:pivot]
    recent = growths[pivot:]
    if not early or not recent:
        return 0
    growth_shift = abs(fmean(recent) - fmean(early))
    margin_shift = 0.0
    margins = [
        _safe_divide(_statement_value(statement, "operating_income"), _statement_value(statement, "revenue"))
        for statement in statements
    ]
    cleaned_margins = [value for value in margins if value is not None]
    if len(cleaned_margins) >= 3:
        margin_pivot = max(1, len(cleaned_margins) - 2)
        margin_shift = abs(fmean(cleaned_margins[margin_pivot:]) - fmean(cleaned_margins[:margin_pivot]))
    return min(18, int(round(max(growth_shift * 40, margin_shift * 80))))


def _major_mna_penalty(statements: list[Any]) -> int:
    ratios = [
        _safe_divide(abs(acquisitions), revenue)
        for statement in statements[-3:]
        for acquisitions, revenue in [(_statement_value(statement, "acquisitions"), _statement_value(statement, "revenue"))]
        if acquisitions is not None and revenue is not None
    ]
    if not ratios:
        return 0
    return min(16, int(round(max(ratios) * 60)))


def _restatement_penalty(restatements: list[Any]) -> int:
    if not restatements:
        return 0
    impact = 0.0
    for record in restatements[:6]:
        confidence_impact = getattr(record, "confidence_impact", None)
        severity = 0.0
        if isinstance(confidence_impact, dict):
            severity = abs(float(confidence_impact.get("score_delta") or confidence_impact.get("penalty") or 0.0))
        changed_metric_keys = getattr(record, "changed_metric_keys", None)
        key_weight = min(1.0, (len(changed_metric_keys) if isinstance(changed_metric_keys, list) else 0) / 6)
        impact += max(severity, 0.5 + key_weight)
    return min(18, int(round(impact * 2)))


def _share_instability_penalty(statements: list[Any]) -> int:
    shares_history = [
        shares
        for statement in statements
        for shares in [_statement_value(statement, "weighted_average_shares_diluted")]
        if shares is not None and shares > 0
    ]
    share_growths = [abs(value) for value in _historical_growth_rates(shares_history)]
    if not share_growths:
        return 0
    return min(14, int(round(fmean(share_growths) * 120)))


def _scenario_dispersion(driver_bundle: Any | None) -> float | None:
    if driver_bundle is None:
        return None
    base = getattr(driver_bundle, "base_next_year_growth", None)
    bull = getattr(driver_bundle, "bull_next_year_growth", None)
    bear = getattr(driver_bundle, "bear_next_year_growth", None)
    values = [float(value) for value in (base, bull, bear) if isinstance(value, (int, float))]
    if len(values) < 2 or base is None:
        return None
    return max(values) - min(values)


def _guidance_usage(driver_bundle: Any | None, earnings_releases: list[Any]) -> str:
    guidance_releases = [
        release
        for release in earnings_releases
        if any(getattr(release, field, None) is not None for field in ("revenue_guidance_low", "revenue_guidance_high", "eps_guidance_low", "eps_guidance_high"))
    ]
    if driver_bundle is not None and getattr(driver_bundle, "guidance_anchor", None) is not None:
        return "management_guidance_applied"
    if guidance_releases:
        return "guidance_available_not_applied"
    return "no_guidance_visible"


def _visible_releases_as_of(releases: list[Any], as_of: datetime | None) -> list[Any]:
    if as_of is None:
        return list(releases)
    return [release for release in releases if (_earnings_release_effective_at(release) or datetime.min.replace(tzinfo=timezone.utc)) <= as_of]


def _statement_effective_at(statement: Any) -> datetime | None:
    acceptance_at = _normalize_datetime(getattr(statement, "filing_acceptance_at", None))
    if acceptance_at is not None:
        return acceptance_at
    period_end = getattr(statement, "period_end", None)
    if period_end is None:
        return None
    return datetime.combine(period_end, TimeType.max, tzinfo=timezone.utc)


def _earnings_release_effective_at(release: Any) -> datetime | None:
    acceptance_at = _normalize_datetime(getattr(release, "filing_acceptance_at", None))
    if acceptance_at is not None:
        return acceptance_at
    filing_date = getattr(release, "filing_date", None)
    if filing_date is not None:
        return datetime.combine(filing_date, TimeType.max, tzinfo=timezone.utc)
    reported_period_end = getattr(release, "reported_period_end", None)
    if reported_period_end is not None:
        return datetime.combine(reported_period_end, TimeType.max, tzinfo=timezone.utc)
    return _normalize_datetime(getattr(release, "last_updated", None)) or _normalize_datetime(getattr(release, "last_checked", None))


def _backtest_display(weighted_error: float | None, error_band: str, sample_size: int) -> str:
    if weighted_error is None or sample_size <= 0:
        return "Insufficient walk-forward sample"
    return f"{weighted_error * 100:.1f}% composite weighted APE ({error_band}) across {sample_size} snapshots"


def _metric_weight_display(metric_weights: dict[str, float]) -> str:
    parts = [
        f"{FORECAST_STABILITY_BACKTEST_METRIC_LABELS.get(metric, metric).upper()} {weight * 100:.0f}%"
        for metric, weight in metric_weights.items()
    ]
    if not parts:
        return "No metric weights"
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _dispersion_display(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{value * 100:.1f}% bull/bear spread"


def _norm(value: int | None) -> float | None:
    return round(float(value) / 100, 3) if isinstance(value, (int, float)) else None


def _tone(value: int | None) -> str:
    if value is None:
        return "unavailable"
    if value >= 75:
        return "positive"
    if value >= 55:
        return "neutral"
    if value >= 40:
        return "caution"
    return "negative"


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.0f}%"


def _normalized_earnings_quality(value: float | None) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    quality = float(value)
    if 0 <= quality <= 1:
        return quality
    if quality >= 0:
        return quality / 100.0
    return quality


def _format_quality_display(value: float | None) -> str:
    if not isinstance(value, (int, float)):
        return "Missing"
    quality = float(value)
    if 1 < quality <= 100:
        return f"{quality:.2f}%"
    return f"{quality:.2f}"


def _forecast_stability_summary(
    history_depth: int,
    sector_template: str,
    sample_size: int,
    weighted_error: float | None,
    error_band: str,
    metric_weights: dict[str, float],
    guidance_usage: str,
    scenario_dispersion: float | None,
) -> str:
    backtest_text = (
        f"{weighted_error * 100:.1f}% composite weighted APE ({error_band}) across {sample_size} point-in-time walk-forward snapshots with {_metric_weight_display(metric_weights)}"
        if weighted_error is not None and sample_size > 0
        else "insufficient walk-forward sample, so the score stays conservative"
    )
    dispersion_text = _dispersion_display(scenario_dispersion).lower()
    return (
        f"Forecast stability uses the {sector_template} sector template and {history_depth} annual periods; "
        f"historical backtests show {backtest_text}; guidance status {guidance_usage}; scenario dispersion {dispersion_text}. "
        "This is a conservative stability signal, not statistical confidence."
    )


def _growth_volatility_band(value: float | None) -> str:
    if value is None:
        return "unavailable"
    for threshold, label in FORECAST_STABILITY_VOLATILITY_BANDS:
        if value < threshold:
            return label
    return "high"


def _stability_label(score: int | None) -> str:
    if score is None:
        return "Guarded stability"
    if score >= 78:
        return "Higher stability"
    if score >= 60:
        return "Moderate stability"
    if score >= 40:
        return "Guarded stability"
    return "Low stability"


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(float(value), digits)


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _latest_checked(items: list[Any]) -> datetime | None:
    values = [getattr(item, "last_checked", None) for item in items if getattr(item, "last_checked", None) is not None]
    normalized = [_normalize_datetime(value) for value in values if value is not None]
    return max(normalized) if normalized else None


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _merge(*values: datetime | None) -> datetime | None:
    normalized = [_normalize_datetime(value) for value in values if value is not None]
    return max(normalized) if normalized else None


def _as_of_text(as_of: datetime | None, latest_period: DateType | None) -> str | None:
    if as_of is not None:
        return _normalize_datetime(as_of).isoformat()
    return latest_period.isoformat() if latest_period is not None else None


def _as_of_key(as_of: datetime | None) -> str:
    normalized = _normalize_datetime(as_of)
    return normalized.isoformat() if normalized is not None else "latest"
