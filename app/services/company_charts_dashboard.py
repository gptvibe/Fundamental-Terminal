from __future__ import annotations

from datetime import date as DateType, datetime, timezone
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
    CompanyChartsLegendItemPayload,
    CompanyChartsLegendPayload,
    CompanyChartsMethodologyPayload,
    CompanyChartsScoreBadgePayload,
    CompanyChartsSeriesPayload,
    CompanyChartsSeriesPointPayload,
    CompanyChartsSummaryPayload,
)
from app.models import Company, CompanyChartsDashboardSnapshot
from app.source_registry import SourceUsage, build_provenance_entries, build_source_mix
from app.services.cache_queries import get_company_earnings_model_points, get_company_financials, get_company_snapshot, select_point_in_time_financials
from app.services.refresh_state import mark_dataset_checked


CHARTS_DASHBOARD_SCHEMA_VERSION = "company_charts_dashboard_v1"
CHARTS_DASHBOARD_INPUT_FINGERPRINT_VERSION = "company-charts-dashboard-inputs-v1"
ANNUAL_FILING_TYPES = {"10-K", "20-F", "40-F"}


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
    earnings_points = get_company_earnings_model_points(session, company_id, limit=8)
    timestamp = generated_at or datetime.now(timezone.utc)

    revenue_actual = _actual_series(annuals, "revenue")
    revenue_forecast, growth_curve = _forecast_revenue(revenue_actual)
    growth_actual = _growth_series(revenue_actual, "actual")
    growth_forecast = _forecast_growth_series(revenue_forecast, growth_curve)
    profit_series = _margin_projected_series(annuals, revenue_actual, revenue_forecast, [("operating_income", "EBIT"), ("net_income", "Net Income"), ("ebitda_proxy", "EBITDA")])
    cash_series = _margin_projected_series(annuals, revenue_actual, revenue_forecast, [("operating_cash_flow", "Operating CF"), ("free_cash_flow", "Free CF"), ("capex", "Capex")])
    eps_actual, eps_forecast = _eps_series(annuals, revenue_forecast)

    hist_3y = _cagr([_point_value(point) for point in revenue_actual[-4:]]) if len(revenue_actual) >= 4 else None
    exp_1y = _growth_rate(_point_value(revenue_forecast[0]) if revenue_forecast else None, _point_value(revenue_actual[-1]) if revenue_actual else None)
    exp_3y = _cagr([_point_value(revenue_actual[-1])] + [_point_value(point) for point in revenue_forecast[:3]]) if revenue_actual and len(revenue_forecast) >= 3 else None

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
    confidence_score = _confidence_score(annuals, revenue_actual, earnings_points)

    factors = CompanyChartsFactorsPayload(
        primary=CompanyChartsFactorValuePayload(key="growth", label="Growth", score=growth_score, normalized_score=_norm(growth_score), tone=_tone(growth_score), detail=f"Hist 3Y CAGR {_pct(hist_3y)}; forecast 1Y {_pct(exp_1y)}."),
        supporting=[
            CompanyChartsFactorValuePayload(key="quality", label="Quality", score=quality_score, normalized_score=_norm(quality_score), tone=_tone(quality_score), detail="Margins and cash conversion from reported periods."),
            CompanyChartsFactorValuePayload(key="momentum", label="Momentum", score=momentum_score, normalized_score=_norm(momentum_score), tone=_tone(momentum_score), detail="Recent growth and earnings drift."),
            CompanyChartsFactorValuePayload(key="value", label="Value", score=None, normalized_score=None, tone="unavailable", unavailable_reason="Hidden until a trustworthy valuation input set is available."),
            CompanyChartsFactorValuePayload(key="forecast_confidence", label="Forecast Confidence", score=confidence_score, normalized_score=_norm(confidence_score), tone=_tone(confidence_score), detail=f"Based on {len(annuals)} annual periods and persisted quality signals."),
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
                SourceUsage("ft_company_charts_dashboard", role="derived", as_of=latest_period or as_of, last_refreshed_at=timestamp),
                SourceUsage("sec_companyfacts", role="primary", as_of=latest_period or as_of, last_refreshed_at=_latest_checked(annuals)) if annuals else None,
                SourceUsage("ft_model_engine", role="derived", as_of=latest_period or as_of, last_refreshed_at=_latest_checked(earnings_points)) if earnings_points else None,
            ]
            if usage is not None
        ]
    )
    title = "Growth Outlook"
    thesis = f"{company.name} reported {_pct(hist_3y)} 3Y revenue CAGR; the base-case projection implies {_pct(exp_1y)} next-year growth with {_confidence_label(confidence_score).lower()} confidence." if hist_3y is not None and exp_1y is not None else "Historical official filings are normalized first, and projected values remain explicitly labeled as forecast."
    secondary_badges = [
        CompanyChartsScoreBadgePayload(key=item.key, label=item.label, score=item.score, tone=item.tone, detail=item.detail, unavailable_reason=item.unavailable_reason)
        for item in factors.supporting
    ]

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
                "Value stays explicitly unavailable until a trustworthy valuation input set exists.",
            ],
            freshness_badges=[f"Updated {timestamp.date().isoformat()}", f"Reported through FY{latest_period.year}" if latest_period is not None else "Awaiting annual history"],
            source_badges=["Official filings", "Deterministic forecast v1", "Benchmark hidden unless trustworthy"],
        ),
        factors=factors,
        legend=CompanyChartsLegendPayload(title="Actual vs Forecast", items=[
            CompanyChartsLegendItemPayload(key="actual", label="Reported", style="solid", tone="actual", description="Historical official filings."),
            CompanyChartsLegendItemPayload(key="forecast", label="Forecast", style="dashed", tone="forecast", description="Internal projection, not reported results."),
        ]),
        cards=CompanyChartsCardsPayload(
            revenue=CompanyChartsCardPayload(key="revenue", title="Revenue", subtitle="Reported history with guarded projection", metric_label="Revenue", unit_label="USD", empty_state="Reported revenue history is unavailable." if not revenue_actual else None, series=[_series("revenue_actual", "Reported", "usd", "line", "actual", "solid", revenue_actual), _series("revenue_forecast", "Forecast", "usd", "line", "forecast", "dashed", revenue_forecast)], highlights=[item for item in [f"Hist 3Y CAGR {_pct(hist_3y)}" if hist_3y is not None else None, f"Base-case next year {_pct(exp_1y)}" if exp_1y is not None else None] if item]),
            revenue_growth=CompanyChartsCardPayload(key="revenue_growth", title="Revenue Growth", subtitle="Year-over-year reported and projected growth", metric_label="Revenue Growth", unit_label="Percent", empty_state="Revenue growth requires at least two annual periods." if not growth_actual else None, series=[_series("revenue_growth_actual", "Reported", "percent", "bar", "actual", "solid", growth_actual), _series("revenue_growth_forecast", "Forecast", "percent", "bar", "forecast", "muted", growth_forecast)]),
            profit_metric=CompanyChartsCardPayload(key="profit_metric", title="Profit Metrics", subtitle="Margin-based projections with guardrails", metric_label="Profit", unit_label="USD", empty_state="Profit history is unavailable for the selected periods." if not profit_series else None, series=profit_series),
            cash_flow_metric=CompanyChartsCardPayload(key="cash_flow_metric", title="Cash Flow Metrics", subtitle="Cash generation stays visually distinct from projections", metric_label="Cash Flow", unit_label="USD", empty_state="Cash flow history is unavailable for the selected periods." if not cash_series else None, series=cash_series),
            eps=CompanyChartsCardPayload(key="eps", title="EPS", subtitle="Diluted EPS with guarded share-count trend", metric_label="EPS", unit_label="USD / share", empty_state="EPS history is unavailable for the selected periods." if not eps_actual else None, series=[_series("eps_actual", "Reported", "usd_per_share", "bar", "actual", "solid", eps_actual), _series("eps_forecast", "Forecast", "usd_per_share", "bar", "forecast", "muted", eps_forecast)]),
            growth_summary=CompanyChartsComparisonCardPayload(subtitle="Benchmark comparison stays hidden until a trustworthy series is available.", comparisons=[
                CompanyChartsComparisonItemPayload(key="historical_3y", label="Hist 3Y CAGR", company_value=_round(hist_3y, 4), benchmark_label="Benchmark hidden", benchmark_available=False, unit="percent", company_label="Company"),
                CompanyChartsComparisonItemPayload(key="expected_1y", label="Exp 1Y", company_value=_round(exp_1y, 4), benchmark_label="Benchmark hidden", benchmark_available=False, unit="percent", company_label="Company"),
                CompanyChartsComparisonItemPayload(key="expected_3y", label="Exp 3Y CAGR", company_value=_round(exp_3y, 4), benchmark_label="Benchmark hidden", benchmark_available=False, unit="percent", company_label="Company"),
            ], empty_state="Growth summary requires a few annual revenue periods." if hist_3y is None and exp_1y is None and exp_3y is None else None),
            forecast_assumptions=CompanyChartsAssumptionsCardPayload(items=[
                CompanyChartsAssumptionItemPayload(key="horizon", label="Forecast Horizon", value="3 fiscal years", detail="Annual-only forecast surface."),
                CompanyChartsAssumptionItemPayload(key="growth_guardrails", label="Growth Guardrails", value="-18% to +30%", detail="Forecast revenue growth is clipped."),
                CompanyChartsAssumptionItemPayload(key="history_depth", label="History Depth", value=f"{len(annuals)} annual periods", detail="More history improves trend stability."),
                CompanyChartsAssumptionItemPayload(key="base_case_next_year", label="Base-Case Next Year", value=_pct(exp_1y), detail="Implied next-year revenue growth."),
            ]),
        ),
        forecast_methodology=CompanyChartsMethodologyPayload(version=CHARTS_DASHBOARD_SCHEMA_VERSION, label="Deterministic internal projection", summary="Annual historical official filings are normalized, then projected with guarded trend, margin, and share-count rules.", disclaimer="Forecast values are internal projections derived from historical official data. They are not reported results and are not analyst consensus.", confidence_label=_confidence_label(confidence_score)),
        payload_version=payload_version or CHARTS_DASHBOARD_SCHEMA_VERSION,
        refresh=RefreshState(triggered=False, reason="fresh", ticker=company.ticker, job_id=None),
        diagnostics=diagnostics,
        provenance=provenance,
        as_of=_as_of_text(as_of, latest_period),
        last_refreshed_at=_merge(_latest_checked(annuals), _latest_checked(earnings_points), timestamp),
        source_mix=build_source_mix(provenance),
        confidence_flags=sorted(set(list(diagnostics.stale_flags) + list(diagnostics.missing_field_flags) + (["reduced_forecast_confidence"] if confidence_score < 60 else []))),
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
    values = [_point_value(point) for point in actual]
    if not values:
        return [], []
    growths = [_growth_rate(cur, prev) for prev, cur in zip(values, values[1:]) if _growth_rate(cur, prev) is not None]
    latest = growths[-1] if growths else 0.0
    average = fmean(growths[-3:]) if growths else latest
    cagr = _cagr(values[-4:]) if len(values) >= 4 else average
    base = _clip(((latest * 0.45) + (average * 0.2) + ((cagr or average) * 0.35)), -0.18, 0.30)
    current = values[-1]
    year = actual[-1].fiscal_year or datetime.now(timezone.utc).year
    points: list[CompanyChartsSeriesPointPayload] = []
    curve: list[float] = []
    for index in range(1, 4):
        growth = _clip(base * (0.92 ** (index - 1)), -0.18, 0.30)
        current *= 1 + growth
        curve.append(growth)
        points.append(CompanyChartsSeriesPointPayload(period_label=f"FY{year + index}E", fiscal_year=year + index, period_end=None, value=_round(current, 2), series_kind="forecast"))
    return points, curve


def _growth_series(points: list[CompanyChartsSeriesPointPayload], kind: str) -> list[CompanyChartsSeriesPointPayload]:
    values = [_point_value(point) for point in points]
    result: list[CompanyChartsSeriesPointPayload] = []
    for payload, previous, current in zip(points[1:], values, values[1:]):
        growth = _growth_rate(current, previous)
        if growth is None:
            continue
        result.append(CompanyChartsSeriesPointPayload(period_label=payload.period_label, fiscal_year=payload.fiscal_year, period_end=payload.period_end, value=_round(growth, 4), series_kind=kind))
    return result


def _forecast_growth_series(points: list[CompanyChartsSeriesPointPayload], growths: list[float]) -> list[CompanyChartsSeriesPointPayload]:
    return [CompanyChartsSeriesPointPayload(period_label=point.period_label, fiscal_year=point.fiscal_year, period_end=None, value=_round(growth, 4), series_kind="forecast") for point, growth in zip(points, growths)]


def _margin_projected_series(statements: list[Any], revenue_actual: list[CompanyChartsSeriesPointPayload], revenue_forecast: list[CompanyChartsSeriesPointPayload], metrics: list[tuple[str, str]]) -> list[CompanyChartsSeriesPayload]:
    actual_revenue = {point.fiscal_year: _point_value(point) for point in revenue_actual if point.fiscal_year}
    forecast_revenue = {point.fiscal_year: _point_value(point) for point in revenue_forecast if point.fiscal_year}
    payloads: list[CompanyChartsSeriesPayload] = []
    for key, label in metrics:
        actual_points: list[CompanyChartsSeriesPointPayload] = []
        margins: list[float] = []
        for statement in statements:
            value = _statement_value(statement, key) if key != "ebitda_proxy" else _ebitda_proxy(statement)
            if value is None and key == "free_cash_flow":
                operating_cash_flow = _statement_value(statement, "operating_cash_flow")
                capex = _statement_value(statement, "capex")
                value = operating_cash_flow - capex if operating_cash_flow is not None and capex is not None else None
            if value is None:
                continue
            actual_points.append(CompanyChartsSeriesPointPayload(period_label=f"FY{statement.period_end.year}", fiscal_year=statement.period_end.year, period_end=statement.period_end, value=_round(value, 2), series_kind="actual"))
            revenue_value = actual_revenue.get(statement.period_end.year)
            if revenue_value not in (None, 0):
                margins.append(float(value) / float(revenue_value))
        if not actual_points:
            continue
        payloads.append(_series(f"{key}_actual", f"{label} Reported", "usd", "line", "actual", "solid", actual_points))
        if margins and forecast_revenue:
            base_margin = _clip((margins[-1] * 0.65) + (fmean(margins[-3:]) * 0.35), -0.25, 0.45 if key != "capex" else 0.25)
            forecast_points = [CompanyChartsSeriesPointPayload(period_label=f"FY{year}E", fiscal_year=year, period_end=None, value=_round(revenue * base_margin, 2), series_kind="forecast") for year, revenue in sorted(forecast_revenue.items())]
            payloads.append(_series(f"{key}_forecast", f"{label} Forecast", "usd", "line", "forecast", "dashed", forecast_points))
    return payloads


def _eps_series(statements: list[Any], revenue_forecast: list[CompanyChartsSeriesPointPayload]) -> tuple[list[CompanyChartsSeriesPointPayload], list[CompanyChartsSeriesPointPayload]]:
    actual: list[CompanyChartsSeriesPointPayload] = []
    shares_history: list[float] = []
    margin_history: list[float] = []
    for statement in statements:
        shares = _statement_value(statement, "weighted_average_shares_diluted")
        revenue = _statement_value(statement, "revenue")
        net_income = _statement_value(statement, "net_income")
        if shares not in (None, 0):
            shares_history.append(float(shares))
        if net_income is not None and revenue not in (None, 0):
            margin_history.append(float(net_income) / float(revenue))
        eps = _statement_value(statement, "eps")
        if eps is None and net_income is not None and shares not in (None, 0):
            eps = float(net_income) / float(shares)
        if eps is not None:
            actual.append(CompanyChartsSeriesPointPayload(period_label=f"FY{statement.period_end.year}", fiscal_year=statement.period_end.year, period_end=statement.period_end, value=_round(eps, 3), series_kind="actual"))
    if not revenue_forecast or not shares_history or not margin_history:
        return actual, []
    share_growths = [_growth_rate(cur, prev) for prev, cur in zip(shares_history, shares_history[1:]) if _growth_rate(cur, prev) is not None]
    share_growth = _clip(fmean(share_growths[-3:]) if share_growths else 0.0, -0.03, 0.06)
    last_shares = shares_history[-1]
    margin = _clip(fmean(margin_history[-3:]), -0.2, 0.3)
    forecast = []
    for point in revenue_forecast:
        last_shares *= 1 + share_growth
        forecast.append(CompanyChartsSeriesPointPayload(period_label=point.period_label, fiscal_year=point.fiscal_year, period_end=None, value=_round((_point_value(point) * margin) / last_shares if last_shares else None, 3), series_kind="forecast"))
    return actual, forecast


def _series(key: str, label: str, unit: str, chart_type: str, series_kind: str, stroke_style: str, points: list[CompanyChartsSeriesPointPayload]) -> CompanyChartsSeriesPayload:
    return CompanyChartsSeriesPayload(key=key, label=label, unit=unit, chart_type=chart_type, series_kind=series_kind, stroke_style=stroke_style, points=points)


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


def _point_value(point: CompanyChartsSeriesPointPayload) -> float:
    return float(point.value or 0)


def _growth_rate(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (float(current) / float(previous)) - 1


def _cagr(values: list[float]) -> float | None:
    cleaned = [float(value) for value in values if value not in (None, 0)]
    if len(cleaned) < 2 or cleaned[0] <= 0 or cleaned[-1] <= 0:
        return None
    return (cleaned[-1] / cleaned[0]) ** (1 / (len(cleaned) - 1)) - 1


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _blend(*values: float | None) -> float | None:
    cleaned = [float(value) for value in values if isinstance(value, (int, float))]
    return fmean(cleaned) if cleaned else None


def _score(value: float | None, lower: float, upper: float) -> int | None:
    if value is None:
        return None
    return int(round(((_clip(value, lower, upper) - lower) / (upper - lower)) * 100))


def _confidence_score(statements: list[Any], revenue_actual: list[CompanyChartsSeriesPointPayload], earnings_points: list[Any]) -> int:
    score = 78 - max(0, 5 - len(statements)) * 6
    growths = [_growth_rate(cur, prev) for prev, cur in zip([_point_value(point) for point in revenue_actual], [_point_value(point) for point in revenue_actual][1:]) if _growth_rate(cur, prev) is not None]
    if growths:
        score -= int(round((sum(abs(value) for value in growths[-4:]) / len(growths[-4:])) * 12))
    quality = getattr(earnings_points[-1], "quality_score", None) if earnings_points else None
    if isinstance(quality, (int, float)):
        score += int(round((float(quality) - 0.5) * 20))
    return int(_clip(score, 20, 95))


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


def _confidence_label(score: int | None) -> str:
    if score is None:
        return "Moderate"
    if score >= 80:
        return "High"
    if score >= 60:
        return "Moderate"
    return "Guarded"


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
