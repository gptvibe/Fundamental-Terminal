from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, Number, ProvenanceEnvelope, RefreshState


class FinancialSegmentPayload(BaseModel):
    segment_id: str
    segment_name: str
    axis_key: str | None = None
    axis_label: str | None = None
    kind: Literal["business", "geographic", "other"] = "business"
    revenue: Number = None
    share_of_revenue: Number = None
    operating_income: Number = None
    assets: Number = None


class FilingParserSegmentPayload(BaseModel):
    name: str
    revenue: Number = None


class FilingParserInsightPayload(BaseModel):
    accession_number: str | None = None
    filing_type: str
    period_start: DateType
    period_end: DateType
    source: str
    last_updated: datetime
    last_checked: datetime
    revenue: Number = None
    net_income: Number = None
    operating_income: Number = None
    segments: list[FilingParserSegmentPayload] = Field(default_factory=list)


class FinancialPayload(BaseModel):
    filing_type: str
    statement_type: str
    period_start: DateType
    period_end: DateType
    source: str
    last_updated: datetime
    last_checked: datetime
    revenue: Number = None
    gross_profit: Number = None
    operating_income: Number = None
    net_income: Number = None
    total_assets: Number = None
    current_assets: Number = None
    total_liabilities: Number = None
    current_liabilities: Number = None
    retained_earnings: Number = None
    sga: Number = None
    research_and_development: Number = None
    interest_expense: Number = None
    income_tax_expense: Number = None
    inventory: Number = None
    cash_and_cash_equivalents: Number = None
    short_term_investments: Number = None
    cash_and_short_term_investments: Number = None
    accounts_receivable: Number = None
    accounts_payable: Number = None
    goodwill_and_intangibles: Number = None
    current_debt: Number = None
    long_term_debt: Number = None
    stockholders_equity: Number = None
    lease_liabilities: Number = None
    operating_cash_flow: Number = None
    depreciation_and_amortization: Number = None
    capex: Number = None
    acquisitions: Number = None
    debt_changes: Number = None
    dividends: Number = None
    share_buybacks: Number = None
    free_cash_flow: Number = None
    eps: Number = None
    shares_outstanding: Number = None
    stock_based_compensation: Number = None
    weighted_average_diluted_shares: Number = None
    segment_breakdown: list[FinancialSegmentPayload] = Field(default_factory=list)


class PriceHistoryPayload(BaseModel):
    date: DateType
    close: float
    volume: int | None = None


class CompanyFinancialsResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    financials: list[FinancialPayload]
    price_history: list[PriceHistoryPayload]
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)


class MetricsValuesPayload(BaseModel):
    revenue_growth: Number = None
    gross_margin: Number = None
    operating_margin: Number = None
    fcf_margin: Number = None
    roic_proxy: Number = None
    leverage_ratio: Number = None
    current_ratio: Number = None
    share_dilution: Number = None
    sbc_burden: Number = None
    buyback_yield: Number = None
    dividend_yield: Number = None
    working_capital_days: Number = None
    accrual_ratio: Number = None
    cash_conversion: Number = None
    segment_concentration: Number = None


class MetricsProvenancePayload(BaseModel):
    statement_type: str
    statement_source: str
    price_source: str | None = None
    formula_version: str


class MetricsQualityPayload(BaseModel):
    available_metrics: int
    missing_metrics: list[str] = Field(default_factory=list)
    coverage_ratio: float
    flags: list[str] = Field(default_factory=list)


class MetricsTimeseriesPointPayload(BaseModel):
    cadence: Literal["quarterly", "annual", "ttm"]
    period_start: DateType
    period_end: DateType
    filing_type: str
    metrics: MetricsValuesPayload
    provenance: MetricsProvenancePayload
    quality: MetricsQualityPayload


class CompanyMetricsTimeseriesResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    series: list[MetricsTimeseriesPointPayload]
    last_financials_check: datetime | None = None
    last_price_check: datetime | None = None
    staleness_reason: str | None = None
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)


class DerivedMetricValuePayload(BaseModel):
    metric_key: str
    metric_value: Number = None
    is_proxy: bool
    provenance: dict[str, Any]
    quality_flags: list[str] = Field(default_factory=list)


class DerivedMetricPeriodPayload(BaseModel):
    period_type: Literal["quarterly", "annual", "ttm"]
    period_start: DateType
    period_end: DateType
    filing_type: str
    metrics: list[DerivedMetricValuePayload]


class CompanyDerivedMetricsResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    period_type: Literal["quarterly", "annual", "ttm"]
    periods: list[DerivedMetricPeriodPayload]
    available_metric_keys: list[str]
    last_metrics_check: datetime | None = None
    last_financials_check: datetime | None = None
    last_price_check: datetime | None = None
    staleness_reason: str | None = None
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)


class CompanyDerivedMetricsSummaryResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    period_type: Literal["quarterly", "annual", "ttm"]
    latest_period_end: DateType | None = None
    metrics: list[DerivedMetricValuePayload]
    last_metrics_check: datetime | None = None
    last_financials_check: datetime | None = None
    last_price_check: datetime | None = None
    staleness_reason: str | None = None
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)


class CompanyFilingInsightsResponse(BaseModel):
    company: CompanyPayload | None
    insights: list[FilingParserInsightPayload]
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)


class FilingComparisonReferencePayload(BaseModel):
    accession_number: str | None = None
    filing_type: str
    statement_type: str
    period_start: DateType
    period_end: DateType
    source: str
    last_updated: datetime
    last_checked: datetime
    filing_acceptance_at: datetime | None = None
    fetch_timestamp: datetime | None = None


class FilingComparisonMetricDeltaPayload(BaseModel):
    metric_key: str
    label: str
    unit: Literal["usd", "usd_per_share", "shares", "ratio"]
    previous_value: Number = None
    current_value: Number = None
    delta: Number = None
    relative_change: float | None = None
    direction: Literal["added", "removed", "increase", "decrease", "changed"]


class FilingComparisonRiskIndicatorPayload(BaseModel):
    indicator_key: str
    label: str
    severity: Literal["medium", "high"]
    description: str
    current_value: Number = None
    previous_value: Number = None


class FilingComparisonSegmentShiftPayload(BaseModel):
    segment_id: str
    segment_name: str
    kind: Literal["business", "geographic", "other"] = "other"
    current_revenue: Number = None
    previous_revenue: Number = None
    revenue_delta: Number = None
    current_share_of_revenue: float | None = None
    previous_share_of_revenue: float | None = None
    share_delta: float | None = None
    direction: Literal["added", "removed", "increase", "decrease", "changed"]


class FilingComparisonAmendedValuePayload(BaseModel):
    metric_key: str
    label: str
    previous_value: Number = None
    amended_value: Number = None
    delta: Number = None
    relative_change: float | None = None
    direction: Literal["added", "removed", "increase", "decrease", "changed"]
    accession_number: str | None = None
    form: str | None = None
    detection_kind: Literal["amended_filing", "companyfacts_revision"]
    amended_at: datetime | None = None
    source: str
    confidence_severity: Literal["low", "medium", "high"]
    confidence_flags: list[str] = Field(default_factory=list)


class ChangesSinceLastFilingSummaryPayload(BaseModel):
    filing_type: str | None = None
    current_period_start: DateType | None = None
    current_period_end: DateType | None = None
    previous_period_start: DateType | None = None
    previous_period_end: DateType | None = None
    metric_delta_count: int = 0
    new_risk_indicator_count: int = 0
    segment_shift_count: int = 0
    share_count_change_count: int = 0
    capital_structure_change_count: int = 0
    amended_prior_value_count: int = 0


class CompanyChangesSinceLastFilingResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    current_filing: FilingComparisonReferencePayload | None = None
    previous_filing: FilingComparisonReferencePayload | None = None
    summary: ChangesSinceLastFilingSummaryPayload
    metric_deltas: list[FilingComparisonMetricDeltaPayload] = Field(default_factory=list)
    new_risk_indicators: list[FilingComparisonRiskIndicatorPayload] = Field(default_factory=list)
    segment_shifts: list[FilingComparisonSegmentShiftPayload] = Field(default_factory=list)
    share_count_changes: list[FilingComparisonMetricDeltaPayload] = Field(default_factory=list)
    capital_structure_changes: list[FilingComparisonMetricDeltaPayload] = Field(default_factory=list)
    amended_prior_values: list[FilingComparisonAmendedValuePayload] = Field(default_factory=list)
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)


class FinancialRestatementFactPayload(BaseModel):
    accession_number: str | None = None
    form: str | None = None
    taxonomy: str | None = None
    tag: str | None = None
    unit: str | None = None
    filed_at: DateType | None = None
    period_start: DateType | None = None
    period_end: DateType | None = None
    value: Number = None


class FinancialRestatementMetricChangePayload(BaseModel):
    metric_key: str
    previous_value: Number = None
    current_value: Number = None
    delta: Number = None
    relative_change: float | None = None
    direction: Literal["added", "removed", "increase", "decrease", "changed"]
    previous_fact: FinancialRestatementFactPayload | None = None
    current_fact: FinancialRestatementFactPayload | None = None
    value_changed: bool | None = None


class FinancialRestatementConfidenceImpactPayload(BaseModel):
    severity: Literal["low", "medium", "high"]
    flags: list[str] = Field(default_factory=list)
    largest_relative_change: float | None = None
    changed_metric_count: int = 0


class FinancialRestatementPayload(BaseModel):
    accession_number: str
    previous_accession_number: str | None = None
    filing_type: str
    form: str
    is_amendment: bool
    detection_kind: Literal["amended_filing", "companyfacts_revision"]
    period_start: DateType
    period_end: DateType
    filing_date: DateType | None = None
    previous_filing_date: DateType | None = None
    filing_acceptance_at: datetime | None = None
    previous_filing_acceptance_at: datetime | None = None
    source: str
    previous_source: str | None = None
    changed_metric_keys: list[str] = Field(default_factory=list)
    normalized_data_changes: list[FinancialRestatementMetricChangePayload] = Field(default_factory=list)
    companyfacts_changes: list[FinancialRestatementMetricChangePayload] = Field(default_factory=list)
    confidence_impact: FinancialRestatementConfidenceImpactPayload
    last_updated: datetime
    last_checked: datetime


class FinancialRestatementPeriodSummaryPayload(BaseModel):
    filing_type: str
    period_start: DateType
    period_end: DateType
    restatement_count: int
    changed_metric_keys: list[str] = Field(default_factory=list)
    latest_accession_number: str | None = None
    latest_filing_date: DateType | None = None


class FinancialRestatementSummaryPayload(BaseModel):
    total_restatements: int
    amended_filings: int
    companyfacts_revisions: int
    amended_metric_keys: list[str] = Field(default_factory=list)
    changed_periods: list[FinancialRestatementPeriodSummaryPayload] = Field(default_factory=list)
    high_confidence_impacts: int = 0
    medium_confidence_impacts: int = 0
    low_confidence_impacts: int = 0
    latest_filing_date: DateType | None = None
    latest_filing_acceptance_at: datetime | None = None


class CompanyFinancialRestatementsResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    summary: FinancialRestatementSummaryPayload
    restatements: list[FinancialRestatementPayload]
    refresh: RefreshState


class CompanyFactsResponse(BaseModel):
    facts: dict[str, Any]
