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
    CompanyChartsFactorValuePayload,
    CompanyChartsFactorsPayload,
    CompanyChartsForecastDiagnosticsPayload,
    CompanyChartsLegendItemPayload,
    CompanyChartsLegendPayload,
    CompanyChartsMethodologyPayload,
    CompanyChartsScoreComponentPayload,
    CompanyChartsScoreBadgePayload,
    CompanyChartsSeriesPayload,
    CompanyChartsSeriesPointPayload,
    CompanyChartsSummaryPayload,
)
from app.models import Company, CompanyChartsDashboardSnapshot
from app.source_registry import SourceUsage, build_provenance_entries, build_source_mix
from app.services.cache_queries import (
    get_company_earnings_model_points,
    get_company_earnings_releases,
    get_company_financials,
    get_company_financial_restatements,
    get_company_snapshot,
    select_point_in_time_financials,
)
from app.services.company_charts_driver_model import build_driver_forecast_bundle
from app.services.refresh_state import mark_dataset_checked


CHARTS_DASHBOARD_SCHEMA_VERSION = "company_charts_dashboard_v8"
CHARTS_DASHBOARD_INPUT_FINGERPRINT_VERSION = "company-charts-dashboard-inputs-v8"
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


def get_company_charts_dashboard_snapshot(session: Session, company_id: int, *, as_of: datetime | None = None, schema_version: str = CHARTS_DASHBOARD_SCHEMA_VERSION) -> CompanyChartsDashboardSnapshot | None:
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
    driver_bundle = build_driver_forecast_bundle(annuals, earnings_releases)
    timestamp = generated_at or datetime.now(timezone.utc)
    source_inputs_last_refreshed_at = _merge(
        _latest_checked(annuals),
        _latest_checked(earnings_points),
        _latest_checked(earnings_releases),
        _latest_checked(restatements),
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
        ),
        forecast_methodology=CompanyChartsMethodologyPayload(
            version=CHARTS_DASHBOARD_SCHEMA_VERSION,
            label=str(forecast_state["methodology_label"]),
            summary=str(forecast_state["methodology_summary"]),
            disclaimer=str(forecast_state["methodology_disclaimer"]),
            score_name=forecast_stability.score_name,
            heuristic=bool(forecast_state["methodology_heuristic"]),
            score_components=[component.label for component in forecast_stability.components],
            stability_label=stability_label,
            confidence_label=stability_label,
        ),
        forecast_diagnostics=forecast_stability,
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
    payload = build_company_charts_dashboard_response(session, company_id, as_of=as_of, generated_at=timestamp, payload_version=payload_version_hash)
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


def _build_forecast_state(
    annuals: list[Any],
    revenue_actual: list[CompanyChartsSeriesPointPayload],
    growth_actual: list[CompanyChartsSeriesPointPayload],
    hist_3y: float | None,
    driver_bundle: Any | None,
    company_name: str,
) -> dict[str, Any]:
    if driver_bundle is not None:
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

    revenue_forecast, growth_curve = _forecast_revenue(revenue_actual)
    growth_forecast = _forecast_growth_series(revenue_forecast, growth_curve)
    profit_series = _margin_projected_series(annuals, revenue_actual, revenue_forecast, [("operating_income", "EBIT"), ("net_income", "Net Income"), ("ebitda_proxy", "EBITDA")])
    cash_series = _margin_projected_series(annuals, revenue_actual, revenue_forecast, [("operating_cash_flow", "Operating CF"), ("free_cash_flow", "Free CF"), ("capex", "Capex")])
    net_income_forecast = _series_points_by_key(profit_series, "net_income_forecast")
    eps_actual, eps_forecast = _eps_series(annuals, net_income_forecast.points if net_income_forecast is not None else [])
    exp_1y = _growth_rate(_point_value(revenue_forecast[0]) if revenue_forecast else None, _point_value(revenue_actual[-1]) if revenue_actual else None)
    exp_3y = _cagr([_point_value(revenue_actual[-1])] + [_point_value(point) for point in revenue_forecast[:3]]) if revenue_actual and len(revenue_forecast) >= 3 else None
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
        "assumptions_card": CompanyChartsAssumptionsCardPayload(items=[
            CompanyChartsAssumptionItemPayload(key="horizon", label="Forecast Horizon", value="3 fiscal years", detail="Annual-only forecast surface."),
            CompanyChartsAssumptionItemPayload(key="growth_guardrails", label="Growth Guardrails", value="-18% to +30%", detail="Forecast revenue growth is clipped."),
            CompanyChartsAssumptionItemPayload(key="history_depth", label="History Depth", value=f"{len(annuals)} annual periods", detail="Shorter annual history makes deterministic extrapolation less stable."),
            CompanyChartsAssumptionItemPayload(key="growth_volatility_band", label="Growth Volatility Band", value="Heuristic", detail="The fallback heuristic engine uses revenue volatility to dampen extrapolation."),
            CompanyChartsAssumptionItemPayload(key="fallback_mode", label="Forecast Mode", value="Heuristic fallback", detail="The driver engine is bypassed when statement coverage is too thin for explicit cost, reinvestment, or dilution schedules."),
            CompanyChartsAssumptionItemPayload(key="base_case_next_year", label="Base-Case Next Year", value=_pct(exp_1y), detail="Implied next-year revenue growth."),
        ]),
        "calculations_card": None,
        "profit_subtitle": "Margin-based projections with guardrails",
        "cash_subtitle": "Cash generation stays visually distinct from projections",
        "methodology_label": "Deterministic projection with empirical stability overlay",
        "methodology_summary": "Annual historical official filings are normalized into a deterministic three-year projection, then paired with a point-in-time walk-forward stability score calibrated to realized revenue, EBIT, EPS, and FCF error bands plus explicit penalties for cyclicality, structural breaks, M&A, restatements, and share-count instability.",
        "methodology_disclaimer": "Forecast stability is a conservative communication aid grounded in historical multi-metric walk-forward error, not a probability, prediction interval, or statistical confidence measure. Forecast values remain projections rather than reported results or analyst consensus.",
        "methodology_heuristic": True,
    }


def _annual_statements(financials: list[Any]) -> list[Any]:
    seen: dict[DateType, Any] = {}
    for statement in financials:
        if getattr(statement, "filing_type", None) in ANNUAL_FILING_TYPES and statement.period_end not in seen:
            seen[statement.period_end] = statement
    ordered = sorted(seen.values(), key=lambda item: item.period_end)
    return ordered[-8:]


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
        driver_bundle = build_driver_forecast_bundle(historical, visible_releases)
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
