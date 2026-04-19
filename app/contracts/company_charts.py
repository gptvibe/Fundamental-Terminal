from __future__ import annotations

from datetime import date as DateType

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    score_key: str = "forecast_stability"
    score_name: str = "Forecast Stability"
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
    sample_size: int = 0
    scenario_dispersion: Number = None
    sector_template: str | None = None
    guidance_usage: str | None = None
    historical_backtest_error_band: str | None = None
    backtest_weighted_error: Number = None
    backtest_horizon_errors: dict[str, Number] = Field(default_factory=dict)
    backtest_metric_weights: dict[str, Number] = Field(default_factory=dict)
    backtest_metric_errors: dict[str, Number] = Field(default_factory=dict)
    backtest_metric_horizon_errors: dict[str, dict[str, Number]] = Field(default_factory=dict)
    backtest_metric_sample_sizes: dict[str, int] = Field(default_factory=dict)
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


class CompanyChartsWhatIfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overrides: dict[str, float] = Field(default_factory=dict)

    @field_validator("overrides")
    @classmethod
    def _validate_override_keys(cls, overrides: dict[str, float]) -> dict[str, float]:
        from app.services.company_charts_driver_model import SUPPORTED_DRIVER_OVERRIDE_KEYS

        unknown_keys = sorted(set(overrides) - set(SUPPORTED_DRIVER_OVERRIDE_KEYS))
        if unknown_keys:
            supported_keys = ", ".join(sorted(SUPPORTED_DRIVER_OVERRIDE_KEYS))
            raise ValueError(
                f"Unsupported override keys: {', '.join(unknown_keys)}. Supported keys: {supported_keys}."
            )
        return overrides


class CompanyChartsFormulaInputPayload(BaseModel):
    key: str
    label: str
    value: Number = None
    formatted_value: str
    source_detail: str
    source_kind: str
    is_override: bool = False
    original_value: Number = None
    original_source: str | None = None


class CompanyChartsFormulaTracePayload(BaseModel):
    line_item: str
    year: int
    formula_label: str
    formula_template: str
    formula_computation: str
    result_value: Number = None
    inputs: list[CompanyChartsFormulaInputPayload] = Field(default_factory=list)
    confidence: str = "high"
    scenario_state: str = "baseline"


class CompanyChartsProjectedRowPayload(BaseModel):
    key: str
    label: str
    unit: str
    reported_values: dict[int, Number] = Field(default_factory=dict)
    projected_values: dict[int, Number] = Field(default_factory=dict)
    formula_traces: dict[int, CompanyChartsFormulaTracePayload] = Field(default_factory=dict)
    scenario_values: dict[str, Number] = Field(default_factory=dict)
    detail: str | None = None


class CompanyChartsScheduleSectionPayload(BaseModel):
    key: str
    title: str
    rows: list[CompanyChartsProjectedRowPayload] = Field(default_factory=list)


class CompanyChartsDriverCardPayload(BaseModel):
    key: str
    title: str
    value: str
    detail: str | None = None
    source_periods: list[str] = Field(default_factory=list)
    default_markers: list[str] = Field(default_factory=list)
    fallback_markers: list[str] = Field(default_factory=list)


class CompanyChartsSensitivityCellPayload(BaseModel):
    row_index: int
    column_index: int
    revenue_growth: Number = None
    operating_margin: Number = None
    eps: Number = None
    is_base: bool = False


class CompanyChartsCardsPayload(BaseModel):
    revenue: CompanyChartsCardPayload = Field(default_factory=lambda: CompanyChartsCardPayload(key="revenue", title="Revenue"))
    revenue_growth: CompanyChartsCardPayload = Field(default_factory=lambda: CompanyChartsCardPayload(key="revenue_growth", title="Revenue Growth"))
    profit_metric: CompanyChartsCardPayload = Field(default_factory=lambda: CompanyChartsCardPayload(key="profit_metric", title="Profit Metrics"))
    cash_flow_metric: CompanyChartsCardPayload = Field(default_factory=lambda: CompanyChartsCardPayload(key="cash_flow_metric", title="Cash Flow Metrics"))
    eps: CompanyChartsCardPayload = Field(default_factory=lambda: CompanyChartsCardPayload(key="eps", title="EPS"))
    growth_summary: CompanyChartsComparisonCardPayload = Field(default_factory=CompanyChartsComparisonCardPayload)
    forecast_assumptions: CompanyChartsAssumptionsCardPayload | None = None
    forecast_calculations: CompanyChartsAssumptionsCardPayload | None = None
    revenue_outlook_bridge: CompanyChartsCardPayload | None = None
    margin_path: CompanyChartsCardPayload | None = None
    fcf_outlook: CompanyChartsCardPayload | None = None


class CompanyChartsMethodologyPayload(BaseModel):
    version: str
    label: str
    summary: str
    disclaimer: str
    forecast_horizon_years: int = 3
    score_name: str = "Forecast Stability"
    heuristic: bool = True
    score_components: list[str] = Field(default_factory=list)
    stability_label: str | None = None
    confidence_label: str | None = None

    @model_validator(mode="after")
    def _sync_stability_labels(self) -> CompanyChartsMethodologyPayload:
        if self.stability_label is None and self.confidence_label is not None:
            self.stability_label = self.confidence_label
        elif self.confidence_label is None and self.stability_label is not None:
            self.confidence_label = self.stability_label
        return self


class CompanyChartsProjectionStudioPayload(BaseModel):
    methodology: CompanyChartsMethodologyPayload | None = None
    schedule_sections: list[CompanyChartsScheduleSectionPayload] = Field(default_factory=list)
    drivers_used: list[CompanyChartsDriverCardPayload] = Field(default_factory=list)
    scenarios_comparison: list[CompanyChartsProjectedRowPayload] = Field(default_factory=list)
    sensitivity_matrix: list[CompanyChartsSensitivityCellPayload] = Field(default_factory=list)


class CompanyChartsWhatIfImpactMetricPayload(BaseModel):
    key: str
    label: str
    unit: str
    baseline_value: Number = None
    scenario_value: Number = None
    delta_value: Number = None
    delta_percent: Number = None


class CompanyChartsWhatIfImpactSummaryPayload(BaseModel):
    forecast_year: int | None = None
    metrics: list[CompanyChartsWhatIfImpactMetricPayload] = Field(default_factory=list)


class CompanyChartsWhatIfOverridePayload(BaseModel):
    key: str
    label: str
    unit: str
    requested_value: Number = None
    applied_value: Number = None
    baseline_value: Number = None
    min_value: Number = None
    max_value: Number = None
    clipped: bool = False
    source_detail: str
    source_kind: str


class CompanyChartsDriverControlMetadataPayload(BaseModel):
    key: str
    label: str
    unit: str
    baseline_value: Number = None
    current_value: Number = None
    min_value: Number = None
    max_value: Number = None
    step: Number = None
    source_detail: str
    source_kind: str


class CompanyChartsWhatIfPayload(BaseModel):
    impact_summary: CompanyChartsWhatIfImpactSummaryPayload | None = None
    overrides_applied: list[CompanyChartsWhatIfOverridePayload] = Field(default_factory=list)
    overrides_clipped: list[CompanyChartsWhatIfOverridePayload] = Field(default_factory=list)
    driver_control_metadata: list[CompanyChartsDriverControlMetadataPayload] = Field(default_factory=list)


class CompanyChartsForecastAccuracySamplePayload(BaseModel):
    metric_key: str
    metric_label: str
    unit: str
    anchor_fiscal_year: int
    target_fiscal_year: int
    cutoff_as_of: str
    predicted_value: Number = None
    actual_value: Number = None
    absolute_error: Number = None
    absolute_percentage_error: Number = None
    directionally_correct: bool | None = None


class CompanyChartsForecastAccuracyMetricPayload(BaseModel):
    key: str
    label: str
    unit: str
    sample_count: int = 0
    directional_sample_count: int = 0
    mean_absolute_error: Number = None
    mean_absolute_percentage_error: Number = None
    directional_accuracy: Number = None


class CompanyChartsForecastAccuracyAggregatePayload(BaseModel):
    snapshot_count: int = 0
    sample_count: int = 0
    directional_sample_count: int = 0
    mean_absolute_percentage_error: Number = None
    directional_accuracy: Number = None


class CompanyChartsForecastAccuracyResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    status: str = "insufficient_history"
    insufficient_history_reason: str | None = None
    max_backtests: int = 6
    metrics: list[CompanyChartsForecastAccuracyMetricPayload] = Field(default_factory=list)
    aggregate: CompanyChartsForecastAccuracyAggregatePayload = Field(default_factory=CompanyChartsForecastAccuracyAggregatePayload)
    samples: list[CompanyChartsForecastAccuracySamplePayload] = Field(default_factory=list)
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)


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
            version="company_charts_dashboard_v9",
            label="Driver-based integrated forecast",
            summary="Revenue is modeled from a pricing proxy, residual-implied demand growth, and share or mix proxies, then layered with segment rollups, guidance, and backlog or capacity overlays when available. EBIT flows from explicit variable, semi-variable, and fixed cost schedules; operating working capital is forecast through receivables, inventory, payables, deferred revenue, and accrued operating-liability days while excluding cash and financing items; pretax income then bridges through debt-funded interest expense, cash yield, and other income or expense; operating cash flow subtracts delta operating working capital, capex covers maintenance capital plus positive-growth fixed-capital reinvestment from sales-to-capital, and free cash flow and diluted EPS are layered on top with disclosed cash, debt, SBC, buybacks, acquisition dilution, and convert dilution where available. Forecast Stability is then calibrated against point-in-time walk-forward backtests for revenue, EBIT, EPS, and FCF before conservative penalties are applied. When disclosure is sparse, the engine uses conservative component-level fallbacks before dropping all the way back to the older guarded heuristic path.",
            disclaimer="Forecast stability is conservative, based on historical revenue, EBIT, EPS, and FCF walk-forward error plus risk penalties, and is not a probability or statistical confidence measure.",
        )
    )
    forecast_diagnostics: CompanyChartsForecastDiagnosticsPayload = Field(default_factory=CompanyChartsForecastDiagnosticsPayload)
    projection_studio: CompanyChartsProjectionStudioPayload | None = None
    what_if: CompanyChartsWhatIfPayload | None = None
    payload_version: str = "company_charts_dashboard_v9"
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
