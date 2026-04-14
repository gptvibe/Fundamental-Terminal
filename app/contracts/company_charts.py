from __future__ import annotations

from datetime import date as DateType

from pydantic import BaseModel, Field

from app.contracts.common import CompanyPayload, DataQualityDiagnosticsPayload, Number, ProvenanceEnvelope, RefreshState


class CompanyChartsScoreBadgePayload(BaseModel):
    key: str
    label: str
    score: Number = None
    tone: str = "neutral"
    detail: str | None = None
    unavailable_reason: str | None = None


class CompanyChartsSummaryPayload(BaseModel):
    headline: str = "Growth Outlook"
    primary_score: CompanyChartsScoreBadgePayload = Field(default_factory=lambda: CompanyChartsScoreBadgePayload(key="growth", label="Growth"))
    secondary_badges: list[CompanyChartsScoreBadgePayload] = Field(default_factory=list)
    thesis: str | None = None
    unavailable_notes: list[str] = Field(default_factory=list)
    freshness_badges: list[str] = Field(default_factory=list)
    source_badges: list[str] = Field(default_factory=list)


class CompanyChartsFactorValuePayload(BaseModel):
    key: str
    label: str
    score: Number = None
    normalized_score: Number = None
    tone: str = "neutral"
    detail: str | None = None
    unavailable_reason: str | None = None


class CompanyChartsScoreComponentPayload(BaseModel):
    key: str
    label: str
    value: Number = None
    display_value: str | None = None
    impact: int = 0
    detail: str | None = None


class CompanyChartsForecastDiagnosticsPayload(BaseModel):
    score_key: str = "forecast_confidence"
    score_name: str = "Forecast Reliability"
    heuristic: bool = True
    final_score: Number = None
    summary: str | None = None
    history_depth_years: int = 0
    thin_history: bool = False
    growth_volatility: Number = None
    growth_volatility_band: str | None = None
    missing_data_penalty: int = 0
    quality_score: Number = None
    missing_inputs: list[str] = Field(default_factory=list)
    components: list[CompanyChartsScoreComponentPayload] = Field(default_factory=list)


class CompanyChartsFactorsPayload(BaseModel):
    primary: CompanyChartsFactorValuePayload | None = None
    supporting: list[CompanyChartsFactorValuePayload] = Field(default_factory=list)


class CompanyChartsLegendItemPayload(BaseModel):
    key: str
    label: str
    style: str = "solid"
    tone: str = "actual"
    description: str | None = None


class CompanyChartsLegendPayload(BaseModel):
    title: str = "Actual vs Forecast"
    items: list[CompanyChartsLegendItemPayload] = Field(default_factory=list)


class CompanyChartsSeriesPointPayload(BaseModel):
    period_label: str
    fiscal_year: int | None = None
    period_end: DateType | None = None
    value: Number = None
    series_kind: str
    annotation: str | None = None


class CompanyChartsSeriesPayload(BaseModel):
    key: str
    label: str
    unit: str
    chart_type: str
    series_kind: str
    stroke_style: str = "solid"
    points: list[CompanyChartsSeriesPointPayload] = Field(default_factory=list)


class CompanyChartsCardPayload(BaseModel):
    key: str
    title: str
    subtitle: str | None = None
    metric_label: str | None = None
    unit_label: str | None = None
    empty_state: str | None = None
    series: list[CompanyChartsSeriesPayload] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)


class CompanyChartsComparisonItemPayload(BaseModel):
    key: str
    label: str
    company_value: Number = None
    benchmark_value: Number = None
    benchmark_label: str | None = None
    unit: str = "percent"
    company_label: str | None = None
    benchmark_available: bool = False


class CompanyChartsComparisonCardPayload(BaseModel):
    key: str = "growth_summary"
    title: str = "Growth Summary"
    subtitle: str | None = None
    comparisons: list[CompanyChartsComparisonItemPayload] = Field(default_factory=list)
    empty_state: str | None = None


class CompanyChartsAssumptionItemPayload(BaseModel):
    key: str
    label: str
    value: str
    detail: str | None = None


class CompanyChartsAssumptionsCardPayload(BaseModel):
    key: str = "forecast_assumptions"
    title: str = "Forecast Assumptions"
    items: list[CompanyChartsAssumptionItemPayload] = Field(default_factory=list)
    empty_state: str | None = None


class CompanyChartsCardsPayload(BaseModel):
    revenue: CompanyChartsCardPayload = Field(default_factory=lambda: CompanyChartsCardPayload(key="revenue", title="Revenue"))
    revenue_growth: CompanyChartsCardPayload = Field(default_factory=lambda: CompanyChartsCardPayload(key="revenue_growth", title="Revenue Growth"))
    profit_metric: CompanyChartsCardPayload = Field(default_factory=lambda: CompanyChartsCardPayload(key="profit_metric", title="Profit Metrics"))
    cash_flow_metric: CompanyChartsCardPayload = Field(default_factory=lambda: CompanyChartsCardPayload(key="cash_flow_metric", title="Cash Flow Metrics"))
    eps: CompanyChartsCardPayload = Field(default_factory=lambda: CompanyChartsCardPayload(key="eps", title="EPS"))
    growth_summary: CompanyChartsComparisonCardPayload = Field(default_factory=CompanyChartsComparisonCardPayload)
    forecast_assumptions: CompanyChartsAssumptionsCardPayload | None = None


class CompanyChartsMethodologyPayload(BaseModel):
    version: str
    label: str
    summary: str
    disclaimer: str
    forecast_horizon_years: int = 3
    score_name: str = "Forecast Reliability"
    heuristic: bool = True
    score_components: list[str] = Field(default_factory=list)
    confidence_label: str | None = None


class CompanyChartsDashboardResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    title: str = "Growth Outlook"
    build_state: str = "building"
    build_status: str = "Charts dashboard is warming up."
    summary: CompanyChartsSummaryPayload = Field(default_factory=CompanyChartsSummaryPayload)
    factors: CompanyChartsFactorsPayload = Field(default_factory=CompanyChartsFactorsPayload)
    legend: CompanyChartsLegendPayload = Field(default_factory=CompanyChartsLegendPayload)
    cards: CompanyChartsCardsPayload = Field(default_factory=CompanyChartsCardsPayload)
    forecast_methodology: CompanyChartsMethodologyPayload = Field(
        default_factory=lambda: CompanyChartsMethodologyPayload(
            version="company_charts_dashboard_v3",
            label="Deterministic internal projection",
            summary="Forecasts are generated from persisted historical official inputs with guarded trend and margin rules.",
            disclaimer="Forecast values are projections derived in-house from historical official data and are not reported results or analyst consensus.",
        )
    )
    forecast_diagnostics: CompanyChartsForecastDiagnosticsPayload = Field(default_factory=CompanyChartsForecastDiagnosticsPayload)
    payload_version: str = "company_charts_dashboard_v3"
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
