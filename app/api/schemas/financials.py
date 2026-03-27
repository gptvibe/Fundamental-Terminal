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


class CompanyFactsResponse(BaseModel):
    facts: dict[str, Any]
