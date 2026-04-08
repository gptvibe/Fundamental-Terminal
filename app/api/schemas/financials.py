from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, Number, ProvenanceEnvelope, RefreshState
from app.api.schemas.models import CompanyModelsResponse


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


class SegmentMixDriverPayload(BaseModel):
    segment_id: str
    segment_name: str
    kind: Literal["business", "geographic", "other"] = "other"
    status: Literal["existing", "new", "removed"] = "existing"
    current_revenue: Number = None
    previous_revenue: Number = None
    revenue_delta: Number = None
    current_share_of_revenue: Number = None
    previous_share_of_revenue: Number = None
    share_delta: Number = None
    operating_income: Number = None
    operating_margin: Number = None
    previous_operating_margin: Number = None
    operating_margin_delta: Number = None
    share_of_operating_income: Number = None


class SegmentConcentrationPayload(BaseModel):
    segment_count: int = 0
    top_segment_id: str | None = None
    top_segment_name: str | None = None
    top_segment_share: Number = None
    top_two_share: Number = None
    hhi: Number = None


class SegmentDisclosurePayload(BaseModel):
    code: str
    label: str
    detail: str
    severity: Literal["info", "medium", "high"] = "info"


class SegmentLensPayload(BaseModel):
    kind: Literal["business", "geographic"]
    axis_label: str | None = None
    as_of: DateType | None = None
    last_refreshed_at: datetime | None = None
    provenance_sources: list[str] = Field(default_factory=list)
    confidence_score: Number = None
    confidence_flags: list[str] = Field(default_factory=list)
    summary: str | None = None
    top_mix_movers: list[SegmentMixDriverPayload] = Field(default_factory=list)
    top_margin_contributors: list[SegmentMixDriverPayload] = Field(default_factory=list)
    concentration: SegmentConcentrationPayload = Field(default_factory=SegmentConcentrationPayload)
    unusual_disclosures: list[SegmentDisclosurePayload] = Field(default_factory=list)


class SegmentAnalysisPayload(BaseModel):
    business: SegmentLensPayload | None = None
    geographic: SegmentLensPayload | None = None


class SegmentHistorySegmentPayload(BaseModel):
    name: str
    revenue: Number = None
    operating_income: Number = None
    operating_margin: Number = None
    share_of_revenue: Number = None


class SegmentComparabilityFlagsPayload(BaseModel):
    no_prior_comparable_disclosure: bool = False
    segment_axis_changed: bool = False
    partial_operating_income_disclosure: bool = False
    new_or_removed_segments: bool = False


class SegmentHistoryPeriodPayload(BaseModel):
    period_end: DateType
    fiscal_year: int | None = None
    kind: Literal["business", "geographic"]
    segments: list[SegmentHistorySegmentPayload] = Field(default_factory=list)
    comparability_flags: SegmentComparabilityFlagsPayload = Field(default_factory=SegmentComparabilityFlagsPayload)


class CompanySegmentHistoryResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    kind: Literal["business", "geographic"]
    years: int
    periods: list[SegmentHistoryPeriodPayload] = Field(default_factory=list)
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)


class FilingParserSegmentPayload(BaseModel):
    name: str
    revenue: Number = None


class FilingParserSectionPayload(BaseModel):
    key: str
    label: str
    title: str | None = None
    source: str | None = None
    excerpt: str | None = None
    signal_terms: list[str] = Field(default_factory=list)


class FilingParserNonGaapPayload(BaseModel):
    mention_count: int = 0
    terms: list[str] = Field(default_factory=list)
    reconciliation_mentions: int = 0
    has_reconciliation: bool = False
    source: str | None = None
    excerpt: str | None = None


class FilingParserControlsPayload(BaseModel):
    auditor_names: list[str] = Field(default_factory=list)
    auditor_change_terms: list[str] = Field(default_factory=list)
    control_terms: list[str] = Field(default_factory=list)
    material_weakness: bool = False
    ineffective_controls: bool = False
    non_reliance: bool = False
    source: str | None = None
    excerpt: str | None = None


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
    mdna: FilingParserSectionPayload | None = None
    footnotes: list[FilingParserSectionPayload] = Field(default_factory=list)
    non_gaap: FilingParserNonGaapPayload = Field(default_factory=FilingParserNonGaapPayload)
    controls: FilingParserControlsPayload = Field(default_factory=FilingParserControlsPayload)


class FinancialFactReferencePayload(BaseModel):
    accession_number: str | None = None
    form: str | None = None
    taxonomy: str | None = None
    tag: str | None = None
    unit: str | None = None
    source: str | None = None
    filed_at: DateType | None = None
    period_start: DateType | None = None
    period_end: DateType | None = None
    value: Number = None


class FinancialReconciliationComparisonPayload(BaseModel):
    metric_key: str
    status: Literal["match", "disagreement", "companyfacts_only", "parser_only", "unavailable"]
    companyfacts_value: Number = None
    filing_parser_value: Number = None
    delta: Number = None
    relative_delta: float | None = None
    confidence_penalty: Number = None
    companyfacts_fact: FinancialFactReferencePayload | None = None
    filing_parser_fact: FinancialFactReferencePayload | None = None


class FinancialReconciliationPayload(BaseModel):
    status: Literal["matched", "disagreement", "parser_missing", "unsupported_form"]
    as_of: DateType | None = None
    last_refreshed_at: datetime | None = None
    provenance_sources: list[str] = Field(default_factory=list)
    confidence_score: Number = None
    confidence_penalty: Number = None
    confidence_flags: list[str] = Field(default_factory=list)
    missing_field_flags: list[str] = Field(default_factory=list)
    matched_accession_number: str | None = None
    matched_filing_type: str | None = None
    matched_period_start: DateType | None = None
    matched_period_end: DateType | None = None
    matched_source: str | None = None
    disagreement_count: int = 0
    comparisons: list[FinancialReconciliationComparisonPayload] = Field(default_factory=list)


class RegulatedBankFinancialPayload(BaseModel):
    source_id: Literal["fdic_bankfind_financials", "federal_reserve_fr_y9c"]
    reporting_basis: Literal["fdic_call_report", "fr_y9c"]
    confidence_score: Number = None
    confidence_flags: list[str] = Field(default_factory=list)
    net_interest_income: Number = None
    noninterest_income: Number = None
    noninterest_expense: Number = None
    pretax_income: Number = None
    provision_for_credit_losses: Number = None
    deposits_total: Number = None
    core_deposits: Number = None
    uninsured_deposits: Number = None
    loans_net: Number = None
    net_interest_margin: Number = None
    nonperforming_assets_ratio: Number = None
    common_equity_tier1_ratio: Number = None
    tier1_risk_weighted_ratio: Number = None
    total_risk_based_capital_ratio: Number = None
    return_on_assets_ratio: Number = None
    return_on_equity_ratio: Number = None
    tangible_common_equity: Number = None


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
    regulated_bank: RegulatedBankFinancialPayload | None = None
    segment_breakdown: list[FinancialSegmentPayload] = Field(default_factory=list)
    reconciliation: FinancialReconciliationPayload | None = None


class PriceHistoryPayload(BaseModel):
    date: DateType
    close: float
    volume: int | None = None


class CompanyFinancialsResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    financials: list[FinancialPayload]
    price_history: list[PriceHistoryPayload]
    segment_analysis: SegmentAnalysisPayload | None = None
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)


class CompanyCompareItemPayload(BaseModel):
    ticker: str
    financials: CompanyFinancialsResponse
    metrics_summary: "CompanyDerivedMetricsSummaryResponse"
    models: CompanyModelsResponse


class CompanyCompareResponse(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    companies: list[CompanyCompareItemPayload] = Field(default_factory=list)


class CapitalStructureSectionMetaPayload(BaseModel):
    as_of: DateType | None = None
    last_refreshed_at: datetime | None = None
    provenance_sources: list[str] = Field(default_factory=list)
    confidence_score: Number = None
    confidence_flags: list[str] = Field(default_factory=list)


class CapitalStructureBucketPayload(BaseModel):
    bucket_key: str
    label: str
    amount: Number = None


class CapitalStructureSummaryPayload(BaseModel):
    total_debt: Number = None
    lease_liabilities: Number = None
    interest_expense: Number = None
    debt_due_next_twelve_months: Number = None
    lease_due_next_twelve_months: Number = None
    gross_shareholder_payout: Number = None
    net_shareholder_payout: Number = None
    net_share_change: Number = None
    net_dilution_ratio: Number = None


class CapitalStructureDebtMaturityPayload(BaseModel):
    buckets: list[CapitalStructureBucketPayload] = Field(default_factory=list)
    meta: CapitalStructureSectionMetaPayload = Field(default_factory=CapitalStructureSectionMetaPayload)


class CapitalStructureLeaseObligationsPayload(BaseModel):
    buckets: list[CapitalStructureBucketPayload] = Field(default_factory=list)
    meta: CapitalStructureSectionMetaPayload = Field(default_factory=CapitalStructureSectionMetaPayload)


class CapitalStructureDebtRollforwardPayload(BaseModel):
    opening_total_debt: Number = None
    ending_total_debt: Number = None
    debt_issued: Number = None
    debt_repaid: Number = None
    net_debt_change: Number = None
    unexplained_change: Number = None
    meta: CapitalStructureSectionMetaPayload = Field(default_factory=CapitalStructureSectionMetaPayload)


class CapitalStructureInterestBurdenPayload(BaseModel):
    interest_expense: Number = None
    average_total_debt: Number = None
    interest_to_average_debt: Number = None
    interest_to_revenue: Number = None
    interest_to_operating_cash_flow: Number = None
    interest_coverage_proxy: Number = None
    meta: CapitalStructureSectionMetaPayload = Field(default_factory=CapitalStructureSectionMetaPayload)


class CapitalStructurePayoutMixPayload(BaseModel):
    dividends_share: Number = None
    repurchases_share: Number = None
    sbc_offset_share: Number = None


class CapitalStructureCapitalReturnsPayload(BaseModel):
    dividends: Number = None
    share_repurchases: Number = None
    stock_based_compensation: Number = None
    gross_shareholder_payout: Number = None
    net_shareholder_payout: Number = None
    payout_mix: CapitalStructurePayoutMixPayload = Field(default_factory=CapitalStructurePayoutMixPayload)
    meta: CapitalStructureSectionMetaPayload = Field(default_factory=CapitalStructureSectionMetaPayload)


class CapitalStructureNetDilutionBridgePayload(BaseModel):
    opening_shares: Number = None
    shares_issued: Number = None
    shares_issued_proxy: Number = None
    shares_repurchased: Number = None
    other_share_change: Number = None
    ending_shares: Number = None
    weighted_average_diluted_shares: Number = None
    net_share_change: Number = None
    net_dilution_ratio: Number = None
    share_repurchase_cash: Number = None
    stock_based_compensation: Number = None
    meta: CapitalStructureSectionMetaPayload = Field(default_factory=CapitalStructureSectionMetaPayload)


class CapitalStructureSnapshotPayload(BaseModel):
    accession_number: str | None = None
    filing_type: str
    statement_type: str
    period_start: DateType
    period_end: DateType
    source: str
    filing_acceptance_at: datetime | None = None
    last_updated: datetime
    last_checked: datetime
    summary: CapitalStructureSummaryPayload = Field(default_factory=CapitalStructureSummaryPayload)
    debt_maturity_ladder: CapitalStructureDebtMaturityPayload = Field(default_factory=CapitalStructureDebtMaturityPayload)
    lease_obligations: CapitalStructureLeaseObligationsPayload = Field(default_factory=CapitalStructureLeaseObligationsPayload)
    debt_rollforward: CapitalStructureDebtRollforwardPayload = Field(default_factory=CapitalStructureDebtRollforwardPayload)
    interest_burden: CapitalStructureInterestBurdenPayload = Field(default_factory=CapitalStructureInterestBurdenPayload)
    capital_returns: CapitalStructureCapitalReturnsPayload = Field(default_factory=CapitalStructureCapitalReturnsPayload)
    net_dilution_bridge: CapitalStructureNetDilutionBridgePayload = Field(default_factory=CapitalStructureNetDilutionBridgePayload)
    provenance_details: dict[str, Any] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    confidence_score: Number = None


class CompanyCapitalStructureResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    latest: CapitalStructureSnapshotPayload | None = None
    history: list[CapitalStructureSnapshotPayload] = Field(default_factory=list)
    last_capital_structure_check: datetime | None = None
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
    net_interest_margin: Number = None
    provision_burden: Number = None
    asset_quality_ratio: Number = None
    cet1_ratio: Number = None
    tier1_capital_ratio: Number = None
    total_capital_ratio: Number = None
    core_deposit_ratio: Number = None
    uninsured_deposit_ratio: Number = None
    tangible_book_value_per_share: Number = None
    roatce: Number = None


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


class FilingHighSignalEvidencePayload(BaseModel):
    label: str
    excerpt: str
    source: str
    filing_type: str | None = None
    period_end: DateType | None = None


class FilingHighSignalChangePayload(BaseModel):
    change_key: str
    category: Literal["mda", "footnote", "non_gaap", "controls", "comment_letter"]
    importance: Literal["medium", "high"]
    title: str
    summary: str
    why_it_matters: str
    signal_tags: list[str] = Field(default_factory=list)
    current_period_end: DateType | None = None
    previous_period_end: DateType | None = None
    evidence: list[FilingHighSignalEvidencePayload] = Field(default_factory=list)


class FilingCommentLetterItemPayload(BaseModel):
    accession_number: str | None = None
    filing_date: DateType | None = None
    description: str
    sec_url: str
    is_new_since_current_filing: bool = False


class FilingCommentLetterHistoryPayload(BaseModel):
    total_letters: int = 0
    letters_since_previous_filing: int = 0
    latest_filing_date: DateType | None = None
    recent_letters: list[FilingCommentLetterItemPayload] = Field(default_factory=list)


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
    high_signal_change_count: int = 0
    comment_letter_count: int = 0


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
    high_signal_changes: list[FilingHighSignalChangePayload] = Field(default_factory=list)
    comment_letter_history: FilingCommentLetterHistoryPayload = Field(default_factory=FilingCommentLetterHistoryPayload)
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)


class FinancialRestatementMetricChangePayload(BaseModel):
    metric_key: str
    previous_value: Number = None
    current_value: Number = None
    delta: Number = None
    relative_change: float | None = None
    direction: Literal["added", "removed", "increase", "decrease", "changed"]
    previous_fact: FinancialFactReferencePayload | None = None
    current_fact: FinancialFactReferencePayload | None = None
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
