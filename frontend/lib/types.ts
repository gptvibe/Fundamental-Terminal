export type CacheState = "fresh" | "stale" | "missing";
export type RefreshReason = "manual" | "missing" | "stale" | "fresh" | "none";

export interface RefreshState {
  triggered: boolean;
  reason: RefreshReason;
  ticker: string | null;
  job_id: string | null;
}

export interface DataQualityDiagnosticsPayload {
  coverage_ratio: number | null;
  fallback_ratio: number | null;
  stale_flags: string[];
  parser_confidence: number | null;
  missing_field_flags: string[];
  reconciliation_penalty: number | null;
  reconciliation_disagreement_count: number;
}

export type SourceTier =
  | "official_regulator"
  | "official_statistical"
  | "official_treasury_or_fed"
  | "derived_from_official"
  | "commercial_fallback"
  | "manual_override";

export type SourceRole = "primary" | "supplemental" | "derived" | "fallback";

export interface SourceMixPayload {
  source_ids: string[];
  source_tiers: SourceTier[];
  primary_source_ids: string[];
  fallback_source_ids: string[];
  official_only: boolean;
}

export interface ProvenanceEntryPayload {
  source_id: string;
  source_tier: SourceTier;
  display_label: string;
  url: string;
  default_freshness_ttl_seconds: number;
  disclosure_note: string;
  role: SourceRole;
  as_of: string | null;
  last_refreshed_at: string | null;
}

export interface ProvenanceEnvelope {
  provenance: ProvenanceEntryPayload[];
  as_of: string | null;
  last_refreshed_at: string | null;
  source_mix: SourceMixPayload;
  confidence_flags: string[];
}

export interface RegulatedEntityPayload {
  issuer_type: "bank" | "bank_holding_company";
  reporting_basis: "fdic_call_report" | "fr_y9c" | "mixed_regulatory";
  confidence_score: number | null;
  confidence_flags: string[];
}

export interface CompanyPayload {
  ticker: string;
  cik: string;
  name: string;
  sector: string | null;
  market_sector: string | null;
  market_industry: string | null;
  oil_exposure_type: "upstream" | "integrated" | "refiner" | "midstream" | "services" | "non_oil";
  oil_support_status: "supported" | "partial" | "unsupported";
  oil_support_reasons: string[];
  regulated_entity?: RegulatedEntityPayload | null;
  strict_official_mode: boolean;
  last_checked: string | null;
  last_checked_financials: string | null;
  last_checked_prices: string | null;
  last_checked_insiders: string | null;
  last_checked_institutional: string | null;
  last_checked_filings: string | null;
  earnings_last_checked?: string | null;
  cache_state: CacheState;
}

export interface CompanySearchResponse {
  query: string;
  results: CompanyPayload[];
  refresh: RefreshState;
}

export interface CompanyResolutionResponse {
  query: string;
  resolved: boolean;
  ticker: string | null;
  name: string | null;
  error: "not_found" | "lookup_failed" | null;
}

export interface FinancialPayload {
  filing_type: string;
  statement_type: string;
  period_start: string;
  period_end: string;
  source: string;
  last_updated: string;
  last_checked: string;
  revenue: number | null;
  gross_profit: number | null;
  operating_income: number | null;
  net_income: number | null;
  total_assets: number | null;
  current_assets: number | null;
  total_liabilities: number | null;
  current_liabilities: number | null;
  retained_earnings: number | null;
  sga: number | null;
  research_and_development: number | null;
  interest_expense: number | null;
  income_tax_expense: number | null;
  inventory: number | null;
  cash_and_cash_equivalents: number | null;
  short_term_investments: number | null;
  cash_and_short_term_investments: number | null;
  accounts_receivable: number | null;
  accounts_payable: number | null;
  goodwill_and_intangibles: number | null;
  current_debt: number | null;
  long_term_debt: number | null;
  stockholders_equity: number | null;
  lease_liabilities: number | null;
  operating_cash_flow: number | null;
  depreciation_and_amortization: number | null;
  capex: number | null;
  acquisitions: number | null;
  debt_changes: number | null;
  dividends: number | null;
  share_buybacks: number | null;
  free_cash_flow: number | null;
  eps: number | null;
  shares_outstanding: number | null;
  stock_based_compensation: number | null;
  weighted_average_diluted_shares: number | null;
  regulated_bank?: RegulatedBankFinancialPayload | null;
  segment_breakdown: FinancialSegmentPayload[];
  reconciliation: FinancialReconciliationPayload | null;
}

export interface RegulatedBankFinancialPayload {
  source_id: "fdic_bankfind_financials" | "federal_reserve_fr_y9c";
  reporting_basis: "fdic_call_report" | "fr_y9c";
  confidence_score: number | null;
  confidence_flags: string[];
  net_interest_income: number | null;
  noninterest_income: number | null;
  noninterest_expense: number | null;
  pretax_income: number | null;
  provision_for_credit_losses: number | null;
  deposits_total: number | null;
  core_deposits: number | null;
  uninsured_deposits: number | null;
  loans_net: number | null;
  net_interest_margin: number | null;
  nonperforming_assets_ratio: number | null;
  common_equity_tier1_ratio: number | null;
  tier1_risk_weighted_ratio: number | null;
  total_risk_based_capital_ratio: number | null;
  return_on_assets_ratio: number | null;
  return_on_equity_ratio: number | null;
  tangible_common_equity: number | null;
}

export interface FinancialSegmentPayload {
  segment_id: string;
  segment_name: string;
  axis_key: string | null;
  axis_label: string | null;
  kind: "business" | "geographic" | "other";
  revenue: number | null;
  share_of_revenue: number | null;
  operating_income: number | null;
  assets: number | null;
}

export interface SegmentMixDriverPayload {
  segment_id: string;
  segment_name: string;
  kind: "business" | "geographic" | "other";
  status: "existing" | "new" | "removed";
  current_revenue: number | null;
  previous_revenue: number | null;
  revenue_delta: number | null;
  current_share_of_revenue: number | null;
  previous_share_of_revenue: number | null;
  share_delta: number | null;
  operating_income: number | null;
  operating_margin: number | null;
  previous_operating_margin: number | null;
  operating_margin_delta: number | null;
  share_of_operating_income: number | null;
}

export interface SegmentConcentrationPayload {
  segment_count: number;
  top_segment_id: string | null;
  top_segment_name: string | null;
  top_segment_share: number | null;
  top_two_share: number | null;
  hhi: number | null;
}

export interface SegmentDisclosurePayload {
  code: string;
  label: string;
  detail: string;
  severity: "info" | "medium" | "high";
}

export interface SegmentLensPayload {
  kind: "business" | "geographic";
  axis_label: string | null;
  as_of: string | null;
  last_refreshed_at: string | null;
  provenance_sources: string[];
  confidence_score: number | null;
  confidence_flags: string[];
  summary: string | null;
  top_mix_movers: SegmentMixDriverPayload[];
  top_margin_contributors: SegmentMixDriverPayload[];
  concentration: SegmentConcentrationPayload;
  unusual_disclosures: SegmentDisclosurePayload[];
}

export interface SegmentAnalysisPayload {
  business: SegmentLensPayload | null;
  geographic: SegmentLensPayload | null;
}

export interface SegmentHistorySegmentPayload {
  name: string;
  revenue: number | null;
  operating_income: number | null;
  operating_margin: number | null;
  share_of_revenue: number | null;
}

export interface SegmentComparabilityFlagsPayload {
  no_prior_comparable_disclosure: boolean;
  segment_axis_changed: boolean;
  partial_operating_income_disclosure: boolean;
  new_or_removed_segments: boolean;
}

export interface SegmentHistoryPeriodPayload {
  period_end: string;
  fiscal_year: number | null;
  kind: "business" | "geographic";
  segments: SegmentHistorySegmentPayload[];
  comparability_flags: SegmentComparabilityFlagsPayload;
}

export interface CompanySegmentHistoryResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  kind: "business" | "geographic";
  years: number;
  periods: SegmentHistoryPeriodPayload[];
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
}

export interface FinancialFactReferencePayload {
  accession_number: string | null;
  form: string | null;
  taxonomy: string | null;
  tag: string | null;
  unit: string | null;
  source: string | null;
  filed_at: string | null;
  period_start: string | null;
  period_end: string | null;
  value: number | null;
}

export interface FinancialReconciliationComparisonPayload {
  metric_key: string;
  status: "match" | "disagreement" | "companyfacts_only" | "parser_only" | "unavailable";
  companyfacts_value: number | null;
  filing_parser_value: number | null;
  delta: number | null;
  relative_delta: number | null;
  confidence_penalty: number | null;
  companyfacts_fact: FinancialFactReferencePayload | null;
  filing_parser_fact: FinancialFactReferencePayload | null;
}

export interface FinancialReconciliationPayload {
  status: "matched" | "disagreement" | "parser_missing" | "unsupported_form";
  as_of: string | null;
  last_refreshed_at: string | null;
  provenance_sources: string[];
  confidence_score: number | null;
  confidence_penalty: number | null;
  confidence_flags: string[];
  missing_field_flags: string[];
  matched_accession_number: string | null;
  matched_filing_type: string | null;
  matched_period_start: string | null;
  matched_period_end: string | null;
  matched_source: string | null;
  disagreement_count: number;
  comparisons: FinancialReconciliationComparisonPayload[];
}

export interface PriceHistoryPoint {
  date: string;
  close: number | null;
  volume: number | null;
}

export interface FundamentalsTrendPoint {
  date: string;
  revenue: number | null;
  eps: number | null;
  free_cash_flow: number | null;
}

export interface FinancialHistoryPoint {
  year: number;
  revenue: number | null;
  net_income: number | null;
  eps: number | null;
  operating_cash_flow: number | null;
}

export interface CompanyFinancialsResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  financials: FinancialPayload[];
  price_history: PriceHistoryPoint[];
  segment_analysis?: SegmentAnalysisPayload | null;
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
}

export interface CompanyCompareItemPayload {
  ticker: string;
  financials: CompanyFinancialsResponse;
  metrics_summary: CompanyDerivedMetricsSummaryResponse;
  models: CompanyModelsResponse;
}

export interface CompanyCompareResponse {
  tickers: string[];
  companies: CompanyCompareItemPayload[];
}

export interface CapitalStructureSectionMetaPayload {
  as_of: string | null;
  last_refreshed_at: string | null;
  provenance_sources: string[];
  confidence_score: number | null;
  confidence_flags: string[];
}

export interface CapitalStructureBucketPayload {
  bucket_key: string;
  label: string;
  amount: number | null;
}

export interface CapitalStructureSummaryPayload {
  total_debt: number | null;
  lease_liabilities: number | null;
  interest_expense: number | null;
  debt_due_next_twelve_months: number | null;
  lease_due_next_twelve_months: number | null;
  gross_shareholder_payout: number | null;
  net_shareholder_payout: number | null;
  net_share_change: number | null;
  net_dilution_ratio: number | null;
}

export interface CapitalStructureDebtMaturityPayload {
    buckets: CapitalStructureBucketPayload[];
    meta: CapitalStructureSectionMetaPayload;
}

export interface CapitalStructureLeaseObligationsPayload {
  buckets: CapitalStructureBucketPayload[];
  meta: CapitalStructureSectionMetaPayload;
}

export interface CapitalStructureDebtRollforwardPayload {
  opening_total_debt: number | null;
  ending_total_debt: number | null;
  debt_issued: number | null;
  debt_repaid: number | null;
  net_debt_change: number | null;
  unexplained_change: number | null;
  meta: CapitalStructureSectionMetaPayload;
}

export interface CapitalStructureInterestBurdenPayload {
  interest_expense: number | null;
  average_total_debt: number | null;
  interest_to_average_debt: number | null;
  interest_to_revenue: number | null;
  interest_to_operating_cash_flow: number | null;
  interest_coverage_proxy: number | null;
  meta: CapitalStructureSectionMetaPayload;
}

export interface CapitalStructurePayoutMixPayload {
  dividends_share: number | null;
  repurchases_share: number | null;
  sbc_offset_share: number | null;
}

export interface CapitalStructureCapitalReturnsPayload {
  dividends: number | null;
  share_repurchases: number | null;
  stock_based_compensation: number | null;
  gross_shareholder_payout: number | null;
  net_shareholder_payout: number | null;
  payout_mix: CapitalStructurePayoutMixPayload;
  meta: CapitalStructureSectionMetaPayload;
}

export interface CapitalStructureNetDilutionBridgePayload {
    opening_shares: number | null;
    shares_issued: number | null;
    shares_issued_proxy: number | null;
    shares_repurchased: number | null;
    other_share_change: number | null;
    ending_shares: number | null;
    weighted_average_diluted_shares: number | null;
    net_share_change: number | null;
    net_dilution_ratio: number | null;
    share_repurchase_cash: number | null;
    stock_based_compensation: number | null;
    meta: CapitalStructureSectionMetaPayload;
}

export interface CapitalStructureSnapshotPayload {
  accession_number: string | null;
  filing_type: string;
  statement_type: string;
  period_start: string;
  period_end: string;
  source: string;
  filing_acceptance_at: string | null;
  last_updated: string;
  last_checked: string;
  summary: CapitalStructureSummaryPayload;
  debt_maturity_ladder: CapitalStructureDebtMaturityPayload;
  lease_obligations: CapitalStructureLeaseObligationsPayload;
  debt_rollforward: CapitalStructureDebtRollforwardPayload;
  interest_burden: CapitalStructureInterestBurdenPayload;
  capital_returns: CapitalStructureCapitalReturnsPayload;
  net_dilution_bridge: CapitalStructureNetDilutionBridgePayload;
  provenance_details: Record<string, unknown>;
  quality_flags: string[];
  confidence_score: number | null;
}

export interface CompanyCapitalStructureResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  latest: CapitalStructureSnapshotPayload | null;
  history: CapitalStructureSnapshotPayload[];
  last_capital_structure_check: string | null;
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
}

export interface MetricsValuesPayload {
  revenue_growth: number | null;
  gross_margin: number | null;
  operating_margin: number | null;
  fcf_margin: number | null;
  roic_proxy: number | null;
  leverage_ratio: number | null;
  current_ratio: number | null;
  share_dilution: number | null;
  sbc_burden: number | null;
  buyback_yield: number | null;
  dividend_yield: number | null;
  working_capital_days: number | null;
  accrual_ratio: number | null;
  cash_conversion: number | null;
  segment_concentration: number | null;
  net_interest_margin: number | null;
  provision_burden: number | null;
  asset_quality_ratio: number | null;
  cet1_ratio: number | null;
  tier1_capital_ratio: number | null;
  total_capital_ratio: number | null;
  core_deposit_ratio: number | null;
  uninsured_deposit_ratio: number | null;
  tangible_book_value_per_share: number | null;
  roatce: number | null;
}

export interface MetricsProvenancePayload {
  statement_type: string;
  statement_source: string;
  price_source: string | null;
  formula_version: string;
}

export interface MetricsQualityPayload {
  available_metrics: number;
  missing_metrics: string[];
  coverage_ratio: number;
  flags: string[];
}

export interface MetricsTimeseriesPointPayload {
  cadence: "quarterly" | "annual" | "ttm";
  period_start: string;
  period_end: string;
  filing_type: string;
  metrics: MetricsValuesPayload;
  provenance: MetricsProvenancePayload;
  quality: MetricsQualityPayload;
}

export interface CompanyMetricsTimeseriesResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  series: MetricsTimeseriesPointPayload[];
  last_financials_check: string | null;
  last_price_check: string | null;
  staleness_reason: string | null;
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
}

export interface DerivedMetricValuePayload {
  metric_key: string;
  metric_value: number | null;
  is_proxy: boolean;
  provenance: Record<string, unknown>;
  quality_flags: string[];
}

export interface DerivedMetricPeriodPayload {
  period_type: "quarterly" | "annual" | "ttm";
  period_start: string;
  period_end: string;
  filing_type: string;
  metrics: DerivedMetricValuePayload[];
}

export interface CompanyDerivedMetricsResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  period_type: "quarterly" | "annual" | "ttm";
  periods: DerivedMetricPeriodPayload[];
  available_metric_keys: string[];
  last_metrics_check: string | null;
  last_financials_check: string | null;
  last_price_check: string | null;
  staleness_reason: string | null;
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
}

export interface CompanyDerivedMetricsSummaryResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  period_type: "quarterly" | "annual" | "ttm";
  latest_period_end: string | null;
  metrics: DerivedMetricValuePayload[];
  last_metrics_check: string | null;
  last_financials_check: string | null;
  last_price_check: string | null;
  staleness_reason: string | null;
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
}

export interface FilingParserSegmentPayload {
  name: string;
  revenue: number | null;
}

export interface FilingParserInsightPayload {
  accession_number: string | null;
  filing_type: string;
  period_start: string;
  period_end: string;
  source: string;
  last_updated: string;
  last_checked: string;
  revenue: number | null;
  net_income: number | null;
  operating_income: number | null;
  segments: FilingParserSegmentPayload[];
}

export interface CompanyFilingInsightsResponse {
  company: CompanyPayload | null;
  insights: FilingParserInsightPayload[];
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
}

export interface FilingComparisonReferencePayload {
  accession_number: string | null;
  filing_type: string;
  statement_type: string;
  period_start: string;
  period_end: string;
  source: string;
  last_updated: string;
  last_checked: string;
  filing_acceptance_at: string | null;
  fetch_timestamp: string | null;
}

export interface FilingComparisonMetricDeltaPayload {
  metric_key: string;
  label: string;
  unit: "usd" | "usd_per_share" | "shares" | "ratio";
  previous_value: number | null;
  current_value: number | null;
  delta: number | null;
  relative_change: number | null;
  direction: "added" | "removed" | "increase" | "decrease" | "changed";
}

export interface FilingComparisonRiskIndicatorPayload {
  indicator_key: string;
  label: string;
  severity: "medium" | "high";
  description: string;
  current_value: number | null;
  previous_value: number | null;
}

export interface FilingComparisonSegmentShiftPayload {
  segment_id: string;
  segment_name: string;
  kind: "business" | "geographic" | "other";
  current_revenue: number | null;
  previous_revenue: number | null;
  revenue_delta: number | null;
  current_share_of_revenue: number | null;
  previous_share_of_revenue: number | null;
  share_delta: number | null;
  direction: "added" | "removed" | "increase" | "decrease" | "changed";
}

export interface FilingComparisonAmendedValuePayload {
  metric_key: string;
  label: string;
  previous_value: number | null;
  amended_value: number | null;
  delta: number | null;
  relative_change: number | null;
  direction: "added" | "removed" | "increase" | "decrease" | "changed";
  accession_number: string | null;
  form: string | null;
  detection_kind: "amended_filing" | "companyfacts_revision";
  amended_at: string | null;
  source: string;
  confidence_severity: "low" | "medium" | "high";
  confidence_flags: string[];
}

export interface ChangesSinceLastFilingSummaryPayload {
  filing_type: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  previous_period_start: string | null;
  previous_period_end: string | null;
  metric_delta_count: number;
  new_risk_indicator_count: number;
  segment_shift_count: number;
  share_count_change_count: number;
  capital_structure_change_count: number;
  amended_prior_value_count: number;
}

export interface CompanyChangesSinceLastFilingResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  current_filing: FilingComparisonReferencePayload | null;
  previous_filing: FilingComparisonReferencePayload | null;
  summary: ChangesSinceLastFilingSummaryPayload;
  metric_deltas: FilingComparisonMetricDeltaPayload[];
  new_risk_indicators: FilingComparisonRiskIndicatorPayload[];
  segment_shifts: FilingComparisonSegmentShiftPayload[];
  share_count_changes: FilingComparisonMetricDeltaPayload[];
  capital_structure_changes: FilingComparisonMetricDeltaPayload[];
  amended_prior_values: FilingComparisonAmendedValuePayload[];
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
}

export interface FinancialRestatementFactPayload {
  accession_number: string | null;
  form: string | null;
  taxonomy: string | null;
  tag: string | null;
  unit: string | null;
  filed_at: string | null;
  period_start: string | null;
  period_end: string | null;
  value: number | null;
}

export interface FinancialRestatementMetricChangePayload {
  metric_key: string;
  previous_value: number | null;
  current_value: number | null;
  delta: number | null;
  relative_change: number | null;
  direction: "added" | "removed" | "increase" | "decrease" | "changed";
  previous_fact: FinancialRestatementFactPayload | null;
  current_fact: FinancialRestatementFactPayload | null;
  value_changed?: boolean | null;
}

export interface FinancialRestatementConfidenceImpactPayload {
  severity: "low" | "medium" | "high";
  flags: string[];
  largest_relative_change: number | null;
  changed_metric_count: number;
}

export interface FinancialRestatementPayload {
  accession_number: string;
  previous_accession_number: string | null;
  filing_type: string;
  form: string;
  is_amendment: boolean;
  detection_kind: "amended_filing" | "companyfacts_revision";
  period_start: string;
  period_end: string;
  filing_date: string | null;
  previous_filing_date: string | null;
  filing_acceptance_at: string | null;
  previous_filing_acceptance_at: string | null;
  source: string;
  previous_source: string | null;
  changed_metric_keys: string[];
  normalized_data_changes: FinancialRestatementMetricChangePayload[];
  companyfacts_changes: FinancialRestatementMetricChangePayload[];
  confidence_impact: FinancialRestatementConfidenceImpactPayload;
  last_updated: string;
  last_checked: string;
}

export interface FinancialRestatementPeriodSummaryPayload {
  filing_type: string;
  period_start: string;
  period_end: string;
  restatement_count: number;
  changed_metric_keys: string[];
  latest_accession_number: string | null;
  latest_filing_date: string | null;
}

export interface FinancialRestatementSummaryPayload {
  total_restatements: number;
  amended_filings: number;
  companyfacts_revisions: number;
  amended_metric_keys: string[];
  changed_periods: FinancialRestatementPeriodSummaryPayload[];
  high_confidence_impacts: number;
  medium_confidence_impacts: number;
  low_confidence_impacts: number;
  latest_filing_date: string | null;
  latest_filing_acceptance_at: string | null;
}

export interface CompanyFinancialRestatementsResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  summary: FinancialRestatementSummaryPayload;
  restatements: FinancialRestatementPayload[];
  refresh: RefreshState;
}
export interface InsiderTradePayload {
  name: string;
  role: string | null;
  date: string | null;
  filing_date: string | null;
  filing_type: string | null;
  accession_number: string | null;
  source: string | null;
  action: string;
  transaction_code: string | null;
  shares: number | null;
  price: number | null;
  value: number | null;
  ownership_after: number | null;
  security_title: string | null;
  is_derivative: boolean | null;
  ownership_nature: string | null;
  exercise_price: number | null;
  expiration_date: string | null;
  footnote_tags: string[] | null;
  is_10b5_1: boolean;
}

export interface InsiderActivityMetricsPayload {
  total_buy_value: number;
  total_sell_value: number;
  net_value: number;
  unique_insiders_buying: number;
  unique_insiders_selling: number;
}

export interface InsiderActivitySummaryPayload {
  sentiment: "bullish" | "neutral" | "bearish";
  summary_lines: string[];
  metrics: InsiderActivityMetricsPayload;
}

export interface CompanyInsiderTradesResponse {
  company: CompanyPayload | null;
  insider_trades: InsiderTradePayload[];
  summary: InsiderActivitySummaryPayload;
  refresh: RefreshState;
}

export interface InstitutionalHoldingPayload {
  fund_name: string;
  fund_cik: string | null;
  fund_manager: string | null;
  manager_query: string | null;
  universe_source: string | null;
  fund_strategy: string | null;
  accession_number: string | null;
  filing_form: string | null;
  base_form: string | null;
  is_amendment: boolean;
  reporting_date: string;
  filing_date: string | null;
  shares_held: number | null;
  market_value: number | null;
  change_in_shares: number | null;
  percent_change: number | null;
  portfolio_weight: number | null;
  put_call: string | null;
  investment_discretion: string | null;
  voting_authority_sole: number | null;
  voting_authority_shared: number | null;
  voting_authority_none: number | null;
  source: string | null;
}

export interface CompanyInstitutionalHoldingsResponse {
  company: CompanyPayload | null;
  institutional_holdings: InstitutionalHoldingPayload[];
  refresh: RefreshState;
}

export interface InstitutionalHoldingsSummaryPayload {
  total_rows: number;
  unique_managers: number;
  amended_rows: number;
  latest_reporting_date: string | null;
}

export interface CompanyInstitutionalHoldingsSummaryResponse {
  company: CompanyPayload | null;
  summary: InstitutionalHoldingsSummaryPayload;
  refresh: RefreshState;
}

export interface ModelPayload {
  schema_version?: string;
  model_name: string;
  model_version: string;
  created_at: string;
  input_periods: Record<string, unknown> | Array<Record<string, unknown>>;
  result: Record<string, unknown>;
}

export type ModelStatus = "supported" | "partial" | "proxy" | "insufficient_data" | "unsupported";

export interface ValuationApplicabilityMatch {
  field: string;
  value: string;
  keyword: string;
}

export interface ValuationApplicability {
  is_supported: boolean;
  reason: string;
  matches: ValuationApplicabilityMatch[];
  classification: Record<string, string | null>;
}

export interface PriceSnapshotMetadata {
  latest_price: number | null;
  price_date: string | null;
  price_source: string | null;
  price_available: boolean;
}

export interface CompanyModelsResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  requested_models: string[];
  models: ModelPayload[];
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
}

export interface OilCurvePointPayload {
  label: string;
  value: number | null;
  units: string;
  observation_date: string | null;
}

export interface OilCurveSeriesPayload {
  series_id: string;
  label: string;
  units: string;
  status: string;
  points: OilCurvePointPayload[];
  latest_value: number | null;
  latest_observation_date: string | null;
}

export interface OilScenarioCasePayload {
  scenario_id: string;
  label: string;
  benchmark_value: number | null;
  benchmark_delta_percent: number | null;
  revenue_delta_percent: number | null;
  operating_margin_delta_bps: number | null;
  free_cash_flow_delta_percent: number | null;
  confidence_flags: string[];
}

export interface OilSensitivityPayload {
  metric_basis: string;
  lookback_quarters: number;
  elasticity: number | null;
  r_squared: number | null;
  sample_size: number;
  direction: string;
  status: string;
  confidence_flags: string[];
}

export interface OilExposureProfilePayload {
  profile_id: string;
  label: string;
  oil_exposure_type: string;
  oil_support_status: string;
  oil_support_reasons: string[];
  relevance_reasons: string[];
  hedging_signal: string;
  pass_through_signal: string;
  evidence: Array<Record<string, unknown>>;
}

export interface CompanyOilScenarioOverlayResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  status: string;
  fetched_at: string;
  strict_official_mode: boolean;
  exposure_profile: OilExposureProfilePayload;
  benchmark_series: OilCurveSeriesPayload[];
  scenarios: OilScenarioCasePayload[];
  sensitivity: OilSensitivityPayload | null;
  diagnostics: DataQualityDiagnosticsPayload;
  refresh: RefreshState;
}

export interface OilCurveYearPointPayload {
  year: number;
  price: number | null;
}

export interface OilScenarioBenchmarkOptionPayload {
  value: string;
  label: string;
}

export interface OilScenarioEligibilityPayload {
  eligible: boolean;
  status: string;
  oil_exposure_type: string;
  reasons: string[];
}

export interface OilScenarioOfficialBaseCurvePayload {
  benchmark_id?: string | null;
  label?: string | null;
  units?: string;
  points?: OilCurveYearPointPayload[];
  available_benchmarks?: OilScenarioBenchmarkOptionPayload[];
}

export interface OilScenarioUserEditableDefaultsPayload {
  benchmark_id?: string | null;
  benchmark_options?: OilScenarioBenchmarkOptionPayload[];
  short_term_curve?: OilCurveYearPointPayload[];
  long_term_anchor?: number | null;
  fade_years?: number;
  annual_after_tax_sensitivity?: number | null;
  base_fair_value_per_share?: number | null;
  diluted_shares?: number | null;
  current_share_price?: number | null;
  current_share_price_source?: string;
  current_oil_price?: number | null;
  current_oil_price_source?: string | null;
  realized_spread_mode?: string;
  current_realized_spread?: number | null;
  current_realized_spread_source?: string | null;
  custom_realized_spread?: number | null;
  mean_reversion_target_spread?: number | null;
  mean_reversion_years?: number;
  realized_spread_reference_benchmark?: string | null;
}

export interface OilScenarioSensitivitySourcePayload {
  kind: "manual_override" | "disclosed" | "derived_from_official";
  value?: number | null;
  metric_basis?: string | null;
  status?: string | null;
  confidence_flags?: string[];
}

export interface OilScenarioExtensionOptionPayload {
  preset_id: string;
  label: string;
  status: string;
  reason?: string | null;
  source_id?: string | null;
}

export interface OilScenarioPhase2ExtensionsPayload {
  downstream_offset_supported: boolean;
  downstream_offset_percent?: number | null;
  downstream_offset_reason?: string | null;
  refiner_rac_supported: boolean;
  refiner_rac_reason?: string | null;
  aeo_presets_supported: boolean;
  aeo_presets_reason?: string | null;
  aeo_preset_options?: OilScenarioExtensionOptionPayload[];
}

export interface OilScenarioOverlayYearResultPayload {
  year: number;
  base_oil_price: number | null;
  scenario_oil_price: number | null;
  oil_price_delta: number | null;
  base_realized_price?: number | null;
  scenario_realized_price?: number | null;
  realized_price_delta?: number | null;
  earnings_delta_after_tax: number | null;
  per_share_delta: number | null;
  present_value_per_share: number | null;
  discount_factor: number | null;
}

export interface OilScenarioOverlayOutputsPayload {
  status: string;
  model_status: string;
  reason: string;
  base_fair_value_per_share?: number | null;
  eps_delta_per_dollar_oil?: number | null;
  overlay_pv_per_share?: number | null;
  scenario_fair_value_per_share?: number | null;
  delta_vs_base_per_share?: number | null;
  delta_vs_base_percent?: number | null;
  implied_upside_downside?: number | null;
  yearly_deltas?: OilScenarioOverlayYearResultPayload[];
  assumptions?: Record<string, unknown>;
  confidence_flags?: string[];
}

export interface OilScenarioRequirementsPayload {
  strict_official_mode: boolean;
  manual_price_required: boolean;
  manual_price_reason?: string | null;
  manual_sensitivity_required: boolean;
  manual_sensitivity_reason?: string | null;
  price_input_mode: string;
  realized_spread_supported?: boolean;
  realized_spread_reason?: string | null;
  realized_spread_fallback_label?: string | null;
}

export interface OilScenarioDirectEvidenceFieldPayload {
  status: string;
  reason?: string | null;
  source_url?: string | null;
  accession_number?: string | null;
  filing_form?: string | null;
  confidence_flags?: string[];
  provenance_sources?: string[];
}

export interface OilScenarioDisclosedSensitivityEvidencePayload extends OilScenarioDirectEvidenceFieldPayload {
  benchmark?: string | null;
  oil_price_change_per_bbl?: number | null;
  annual_after_tax_earnings_change?: number | null;
  annual_after_tax_sensitivity?: number | null;
  metric_basis?: string | null;
}

export interface OilScenarioDilutedSharesEvidencePayload extends OilScenarioDirectEvidenceFieldPayload {
  value?: number | null;
  unit?: string | null;
  taxonomy?: string | null;
  tag?: string | null;
}

export interface OilScenarioRealizedBenchmarkRowPayload {
  period_label: string;
  benchmark?: string | null;
  realized_price?: number | null;
  benchmark_price?: number | null;
  realized_percent_of_benchmark?: number | null;
  premium_discount?: number | null;
}

export interface OilScenarioRealizedPriceComparisonEvidencePayload extends OilScenarioDirectEvidenceFieldPayload {
  benchmark?: string | null;
  rows?: OilScenarioRealizedBenchmarkRowPayload[];
}

export interface OilScenarioDirectCompanyEvidencePayload {
  status: string;
  checked_at?: string | null;
  parser_confidence_flags?: string[];
  disclosed_sensitivity: OilScenarioDisclosedSensitivityEvidencePayload;
  diluted_shares: OilScenarioDilutedSharesEvidencePayload;
  realized_price_comparison: OilScenarioRealizedPriceComparisonEvidencePayload;
}

export interface CompanyOilScenarioResponse extends CompanyOilScenarioOverlayResponse {
  eligibility?: OilScenarioEligibilityPayload;
  official_base_curve?: OilScenarioOfficialBaseCurvePayload;
  user_editable_defaults?: OilScenarioUserEditableDefaultsPayload;
  sensitivity_source?: OilScenarioSensitivitySourcePayload;
  phase2_extensions?: OilScenarioPhase2ExtensionsPayload;
  overlay_outputs?: OilScenarioOverlayOutputsPayload;
  requirements?: OilScenarioRequirementsPayload;
  direct_company_evidence?: OilScenarioDirectCompanyEvidencePayload;
}

export interface MarketCurvePointPayload {
  tenor: string;
  rate: number;
  observation_date: string;
}

export interface MarketSlopePayload {
  label: string;
  value: number | null;
  short_tenor: string;
  long_tenor: string;
  observation_date: string | null;
}

export interface MarketFredSeriesPayload {
  series_id: string;
  label: string;
  category: string;
  units: string;
  value: number | null;
  observation_date: string | null;
  state: string;
}

export interface MacroHistoryPoint {
  date: string;
  value: number;
}

export interface MacroSeriesItemPayload {
  series_id: string;
  label: string;
  source_name: string;
  source_url: string;
  units: string;
  value: number | null;
  previous_value: number | null;
  change: number | null;
  change_percent: number | null;
  observation_date: string | null;
  release_date: string | null;
  history: MacroHistoryPoint[];
  status: string;
}

export interface CompanyMarketContextResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  status: string;
  curve_points: MarketCurvePointPayload[];
  slope_2s10s: MarketSlopePayload;
  slope_3m10y: MarketSlopePayload;
  fred_series: MarketFredSeriesPayload[];
  provenance_details?: Record<string, unknown> | null;
  fetched_at: string;
  refresh: RefreshState;
  // v2 grouped sections
  rates_credit?: MacroSeriesItemPayload[];
  inflation_labor?: MacroSeriesItemPayload[];
  growth_activity?: MacroSeriesItemPayload[];
  cyclical_demand?: MacroSeriesItemPayload[];
  cyclical_costs?: MacroSeriesItemPayload[];
  relevant_series?: string[];
  relevant_indicators?: MacroSeriesItemPayload[];
  sector_exposure?: string[];
  hqm_snapshot?: Record<string, unknown> | null;
}

export interface SectorChartPointPayload {
  label: string;
  value: number | null;
}

export interface SectorChartSeriesPayload {
  series_key: string;
  label: string;
  unit: string;
  points: SectorChartPointPayload[];
}

export interface SectorChartPayload {
  chart_id: string;
  title: string;
  subtitle: string | null;
  unit: string;
  series: SectorChartSeriesPayload[];
}

export interface SectorMetricPayload {
  metric_id: string;
  label: string;
  unit: string;
  value: number | null;
  previous_value: number | null;
  change: number | null;
  change_percent: number | null;
  as_of: string | null;
  status: string;
}

export interface SectorDetailRowPayload {
  label: string;
  unit: string;
  current_value: number | null;
  prior_value: number | null;
  change: number | null;
  change_percent: number | null;
  as_of: string | null;
  note: string | null;
}

export interface SectorDetailViewPayload {
  title: string;
  rows: SectorDetailRowPayload[];
}

export interface SectorRefreshPolicyPayload {
  cadence_label: string;
  ttl_seconds: number;
  notes: string[];
}

export interface SectorPluginPayload {
  plugin_id: string;
  title: string;
  description: string;
  status: string;
  relevance_reasons: string[];
  source_ids: string[];
  refresh_policy: SectorRefreshPolicyPayload;
  summary_metrics: SectorMetricPayload[];
  charts: SectorChartPayload[];
  detail_view: SectorDetailViewPayload;
  confidence_flags: string[];
  as_of: string | null;
  last_refreshed_at: string | null;
}

export interface CompanySectorContextResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  status: string;
  matched_plugin_ids: string[];
  plugins: SectorPluginPayload[];
  fetched_at: string;
  refresh: RefreshState;
}

export interface MarketContextStatusPayload {
  state: string;
  label: string;
  observation_date: string | null;
  source: string;
  treasury_status?: string;
}

export interface FilingPayload {
  accession_number: string | null;
  form: string;
  filing_date: string | null;
  report_date: string | null;
  primary_document: string | null;
  primary_doc_description: string | null;
  items: string | null;
  source_url: string;
}

export interface CompanyFilingsResponse {
  company: CompanyPayload | null;
  filings: FilingPayload[];
  timeline_source: "sec_submissions" | "cached_financials";
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
  error: string | null;
}

export interface BeneficialOwnershipFilingPayload {
  accession_number: string | null;
  form: string;
  base_form: "SC 13D" | "SC 13G";
  filing_date: string | null;
  report_date: string | null;
  is_amendment: boolean;
  primary_document: string | null;
  primary_doc_description: string | null;
  source_url: string;
  summary: string;
  parties: BeneficialOwnershipPartyPayload[];
  previous_accession_number: string | null;
  amendment_sequence: number | null;
  amendment_chain_size: number | null;
  previous_filing_date: string | null;
  previous_percent_owned: number | null;
  percent_change_pp: number | null;
  change_direction: "increase" | "decrease" | "unchanged" | "new" | "unknown" | null;
}

export interface BeneficialOwnershipPartyPayload {
  party_name: string;
  role: string | null;
  filer_cik: string | null;
  shares_owned: number | null;
  percent_owned: number | null;
  event_date: string | null;
  purpose: string | null;
}

export interface CompanyBeneficialOwnershipResponse {
  company: CompanyPayload | null;
  filings: BeneficialOwnershipFilingPayload[];
  refresh: RefreshState;
  error: string | null;
}

export interface BeneficialOwnershipSummaryPayload {
  total_filings: number;
  initial_filings: number;
  amendments: number;
  unique_reporting_persons: number;
  latest_filing_date: string | null;
  latest_event_date: string | null;
  max_reported_percent: number | null;
  chains_with_amendments: number;
  amendments_with_delta: number;
  ownership_increase_events: number;
  ownership_decrease_events: number;
  ownership_unchanged_events: number;
  largest_increase_pp: number | null;
  largest_decrease_pp: number | null;
}

export interface CompanyBeneficialOwnershipSummaryResponse {
  company: CompanyPayload | null;
  summary: BeneficialOwnershipSummaryPayload;
  refresh: RefreshState;
  error: string | null;
}

export interface GovernanceFilingPayload {
  accession_number: string | null;
  form: string;
  filing_date: string | null;
  report_date: string | null;
  primary_document: string | null;
  primary_doc_description: string | null;
  source_url: string;
  summary: string;
  meeting_date: string | null;
  executive_comp_table_detected: boolean;
  vote_item_count: number;
  board_nominee_count: number | null;
  key_amounts: number[];
  vote_outcomes: GovernanceVoteOutcomePayload[];
}

export interface GovernanceVoteOutcomePayload {
  proposal_number: number;
  title: string | null;
  for_votes: number | null;
  against_votes: number | null;
  abstain_votes: number | null;
  broker_non_votes: number | null;
}

export interface CompanyGovernanceResponse {
  company: CompanyPayload | null;
  filings: GovernanceFilingPayload[];
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
  error: string | null;
}

export interface GovernanceSummaryPayload {
  total_filings: number;
  definitive_proxies: number;
  supplemental_proxies: number;
  filings_with_meeting_date: number;
  filings_with_exec_comp: number;
  filings_with_vote_items: number;
  latest_meeting_date: string | null;
  max_vote_item_count: number;
}

export interface CompanyGovernanceSummaryResponse {
  company: CompanyPayload | null;
  summary: GovernanceSummaryPayload;
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
  error: string | null;
}

export interface ExecCompRowPayload {
  executive_name: string;
  executive_title: string | null;
  fiscal_year: number | null;
  salary: number | null;
  bonus: number | null;
  stock_awards: number | null;
  option_awards: number | null;
  non_equity_incentive: number | null;
  other_compensation: number | null;
  total_compensation: number | null;
}

export interface CompanyExecutiveCompensationResponse {
  company: CompanyPayload | null;
  rows: ExecCompRowPayload[];
  fiscal_years: number[];
  source: "cached" | "live" | "none";
  refresh: RefreshState;
  error: string | null;
}

export interface FilingEventPayload {
  accession_number: string | null;
  form: string;
  filing_date: string | null;
  report_date: string | null;
  items: string | null;
  item_code: string | null;
  category: string;
  primary_document: string | null;
  primary_doc_description: string | null;
  source_url: string;
  summary: string;
  key_amounts: number[];
  exhibit_references: string[];
}

export interface CompanyEventsResponse {
  company: CompanyPayload | null;
  events: FilingEventPayload[];
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
  error: string | null;
}

export interface FilingEventsSummaryPayload {
  total_events: number;
  unique_accessions: number;
  categories: Record<string, number>;
  latest_event_date: string | null;
  max_key_amount: number | null;
}

export interface CompanyFilingEventsSummaryResponse {
  company: CompanyPayload | null;
  summary: FilingEventsSummaryPayload;
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
  error: string | null;
}

export interface CapitalRaisePayload {
  accession_number: string | null;
  form: string;
  filing_date: string | null;
  report_date: string | null;
  primary_document: string | null;
  primary_doc_description: string | null;
  source_url: string;
  summary: string;
  event_type: string | null;
  security_type: string | null;
  offering_amount: number | null;
  shelf_size: number | null;
  is_late_filer: boolean;
}

export interface CompanyCapitalRaisesResponse {
  company: CompanyPayload | null;
  filings: CapitalRaisePayload[];
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
  error: string | null;
}

export interface CapitalMarketsSummaryPayload {
  total_filings: number;
  late_filer_notices: number;
  registration_filings: number;
  prospectus_filings: number;
  latest_filing_date: string | null;
  max_offering_amount: number | null;
}

export interface CompanyCapitalMarketsSummaryResponse {
  company: CompanyPayload | null;
  summary: CapitalMarketsSummaryPayload;
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
  error: string | null;
}

export type EarningsParseState = "parsed" | "metadata_only";

export interface EarningsReleasePayload {
  accession_number: string;
  form: string;
  filing_date: string | null;
  report_date: string | null;
  primary_document: string | null;
  exhibit_document: string | null;
  exhibit_type: string | null;
  source_url: string;
  parse_state: EarningsParseState;
  reported_period_label: string | null;
  reported_period_end: string | null;
  revenue: number | null;
  operating_income: number | null;
  net_income: number | null;
  diluted_eps: number | null;
  revenue_guidance_low: number | null;
  revenue_guidance_high: number | null;
  eps_guidance_low: number | null;
  eps_guidance_high: number | null;
  share_repurchase_amount: number | null;
  dividend_per_share: number | null;
  highlights: string[];
}

export interface EarningsSummaryPayload {
  total_releases: number;
  parsed_releases: number;
  metadata_only_releases: number;
  releases_with_guidance: number;
  releases_with_buybacks: number;
  releases_with_dividends: number;
  latest_filing_date: string | null;
  latest_report_date: string | null;
  latest_reported_period_end: string | null;
  latest_revenue: number | null;
  latest_operating_income: number | null;
  latest_net_income: number | null;
  latest_diluted_eps: number | null;
}

export interface CompanyEarningsResponse {
  company: CompanyPayload | null;
  earnings_releases: EarningsReleasePayload[];
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
  error: string | null;
}

export interface CompanyEarningsSummaryResponse {
  company: CompanyPayload | null;
  summary: EarningsSummaryPayload;
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
  error: string | null;
}

export interface EarningsModelInputPayload {
  field: string;
  value: number | null;
  period_end: string;
  sec_tags: string[];
}

export interface EarningsModelExplainabilityPayload {
  formula_version: string;
  period_end: string;
  filing_type: string;
  inputs: EarningsModelInputPayload[];
  component_values: Record<string, number | null>;
  proxy_usage: Record<string, boolean>;
  segment_deltas: Array<Record<string, unknown>>;
  release_statement_coverage: Record<string, unknown>;
  quality_formula: string;
  eps_drift_formula: string;
  momentum_formula: string;
}

export interface EarningsModelPointPayload {
  period_start: string;
  period_end: string;
  filing_type: string;
  quality_score: number | null;
  quality_score_delta: number | null;
  eps_drift: number | null;
  earnings_momentum_drift: number | null;
  segment_contribution_delta: number | null;
  release_statement_coverage_ratio: number | null;
  fallback_ratio: number | null;
  stale_period_warning: boolean;
  quality_flags: string[];
  source_statement_ids: number[];
  source_release_ids: number[];
  explainability: EarningsModelExplainabilityPayload;
}

export interface EarningsBacktestWindowPayload {
  accession_number: string;
  filing_date: string | null;
  reported_period_end: string | null;
  pre_price: number | null;
  post_price: number | null;
  price_return: number | null;
  quality_score_delta: number | null;
  eps_drift: number | null;
  quality_directional_consistent: boolean | null;
  eps_directional_consistent: boolean | null;
  price_source: string | null;
}

export interface EarningsBacktestPayload {
  window_sessions: number;
  quality_directional_consistency: number | null;
  quality_total_windows: number;
  quality_consistent_windows: number;
  eps_directional_consistency: number | null;
  eps_total_windows: number;
  eps_consistent_windows: number;
  windows: EarningsBacktestWindowPayload[];
}

export interface EarningsPeerContextPayload {
  peer_group_basis: "market_industry" | "market_sector";
  peer_group_size: number;
  quality_percentile: number | null;
  eps_drift_percentile: number | null;
  sector_group_size: number;
  sector_quality_percentile: number | null;
  sector_eps_drift_percentile: number | null;
}

export interface EarningsAlertPayload {
  id: string;
  type: "quality_regime_shift" | "eps_drift_sign_flip" | "segment_share_change";
  level: "high" | "medium" | "low";
  title: string;
  detail: string;
  period_end: string;
}

export interface CompanyEarningsWorkspaceResponse {
  company: CompanyPayload | null;
  earnings_releases: EarningsReleasePayload[];
  summary: EarningsSummaryPayload;
  model_points: EarningsModelPointPayload[];
  backtests: EarningsBacktestPayload;
  peer_context: EarningsPeerContextPayload;
  alerts: EarningsAlertPayload[];
  refresh: RefreshState;
  diagnostics: DataQualityDiagnosticsPayload;
  error: string | null;
}

export interface ActivityFeedEntryPayload {
  id: string;
  date: string | null;
  type: string;
  badge: string;
  title: string;
  detail: string;
  href: string | null;
}

export interface CompanyActivityFeedResponse {
  company: CompanyPayload | null;
  entries: ActivityFeedEntryPayload[];
  refresh: RefreshState;
  error: string | null;
}

export interface AlertPayload {
  id: string;
  level: "high" | "medium" | "low";
  title: string;
  detail: string;
  source: string;
  date: string | null;
  href: string | null;
}

export interface CommentLetterPayload {
  accession_number: string;
  filing_date: string | null;
  description: string;
  sec_url: string;
}

export interface ModelEvaluationMetricDeltaPayload {
  calibration: number | null;
  stability: number | null;
  mean_absolute_error: number | null;
  root_mean_square_error: number | null;
  mean_signed_error: number | null;
  sample_count: number | null;
}

export interface ModelEvaluationMetricPayload {
  model_name: string;
  sample_count: number;
  calibration: number | null;
  stability: number | null;
  mean_absolute_error: number | null;
  root_mean_square_error: number | null;
  mean_signed_error: number | null;
  status: string;
  delta: ModelEvaluationMetricDeltaPayload;
}

export interface ModelEvaluationRunPayload {
  id: number | null;
  suite_key: string;
  candidate_label: string;
  baseline_label: string | null;
  status: string;
  completed_at: string | null;
  configuration: Record<string, unknown>;
  summary: Record<string, unknown>;
  artifacts: Record<string, unknown>;
  models: ModelEvaluationMetricPayload[];
  deltas_present: boolean;
}

export interface AlertsSummaryPayload {
  total: number;
  high: number;
  medium: number;
  low: number;
}

export interface ModelEvaluationResponse extends ProvenanceEnvelope {
  run: ModelEvaluationRunPayload | null;
}

export interface CompanyAlertsResponse {
  company: CompanyPayload | null;
  alerts: AlertPayload[];
  summary: AlertsSummaryPayload;
  refresh: RefreshState;
  error: string | null;
}

export interface CompanyActivityOverviewResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  entries: ActivityFeedEntryPayload[];
  alerts: AlertPayload[];
  summary: AlertsSummaryPayload;
  market_context_status?: MarketContextStatusPayload | null;
  refresh: RefreshState;
  error: string | null;
}

export interface CompanyCommentLettersResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  letters: CommentLetterPayload[];
  refresh: RefreshState;
  error: string | null;
}

export type ScreenerPeriodType = "quarterly" | "annual" | "ttm";
export type ScreenerRankingScoreKey = "quality" | "value" | "capital_allocation" | "dilution_risk" | "filing_risk";
export type ScreenerSortDirection = "asc" | "desc";
export type ScreenerSortField =
  | "ticker"
  | "period_end"
  | "revenue_growth"
  | "operating_margin"
  | "fcf_margin"
  | "leverage_ratio"
  | "dilution"
  | "sbc_burden"
  | "shareholder_yield"
  | "filing_lag_days"
  | "restatement_count"
  | "quality_score"
  | "value_score"
  | "capital_allocation_score"
  | "dilution_risk_score"
  | "filing_risk_score";

export interface ScreenerMetricSnapshotPayload {
  value: number | null;
  unit: string;
  is_proxy: boolean;
  source_key: string;
  quality_flags: string[];
}

export interface ScreenerRankingComponentPayload {
  component_key: string;
  label: string;
  source_key: string;
  value: number | null;
  unit: string;
  weight: number;
  directionality: "higher_increases_score" | "lower_increases_score";
  component_score: number | null;
  is_proxy: boolean;
  confidence_notes: string[];
}

export interface ScreenerRankingPayload {
  score_key: ScreenerRankingScoreKey;
  label: string;
  score: number | null;
  rank: number | null;
  percentile: number | null;
  universe_size: number;
  universe_basis: "candidate_universe_pre_filter";
  score_directionality: "higher_is_better" | "higher_is_worse";
  confidence_notes: string[];
  components: ScreenerRankingComponentPayload[];
}

export interface ScreenerRankingsPayload {
  quality: ScreenerRankingPayload;
  value: ScreenerRankingPayload;
  capital_allocation: ScreenerRankingPayload;
  dilution_risk: ScreenerRankingPayload;
  filing_risk: ScreenerRankingPayload;
}

export interface ScreenerRankingDefinitionComponentPayload {
  component_key: string;
  label: string;
  source_key: string;
  unit: string;
  weight: number;
  directionality: "higher_increases_score" | "lower_increases_score";
  notes: string[];
}

export interface ScreenerRankingDefinitionPayload {
  score_key: ScreenerRankingScoreKey;
  label: string;
  description: string;
  score_directionality: "higher_is_better" | "higher_is_worse";
  universe_basis: "candidate_universe_pre_filter";
  method_summary: string;
  components: ScreenerRankingDefinitionComponentPayload[];
  confidence_notes_policy: string[];
  notes: string[];
}

export interface ScreenerMetricsPayload {
  revenue_growth: ScreenerMetricSnapshotPayload;
  operating_margin: ScreenerMetricSnapshotPayload;
  fcf_margin: ScreenerMetricSnapshotPayload;
  leverage_ratio: ScreenerMetricSnapshotPayload;
  dilution: ScreenerMetricSnapshotPayload;
  sbc_burden: ScreenerMetricSnapshotPayload;
  shareholder_yield: ScreenerMetricSnapshotPayload;
}

export interface ScreenerFilingQualityPayload {
  filing_lag_days: ScreenerMetricSnapshotPayload;
  stale_period_flag: ScreenerMetricSnapshotPayload;
  restatement_flag: ScreenerMetricSnapshotPayload;
  restatement_count: number;
  latest_restatement_filing_date: string | null;
  latest_restatement_period_end: string | null;
  aggregated_quality_flags: string[];
}

export interface ScreenerCompanyPayload {
  ticker: string;
  cik: string;
  name: string;
  sector: string | null;
  market_sector: string | null;
  market_industry: string | null;
  cache_state: CacheState;
}

export interface ScreenerResultPayload {
  company: ScreenerCompanyPayload;
  period_type: ScreenerPeriodType;
  period_end: string | null;
  filing_type: string | null;
  last_metrics_check: string | null;
  last_model_check: string | null;
  metrics: ScreenerMetricsPayload;
  filing_quality: ScreenerFilingQualityPayload;
  rankings: ScreenerRankingsPayload;
}

export interface ScreenerCoverageSummaryPayload {
  candidate_count: number;
  matched_count: number;
  returned_count: number;
  fresh_count: number;
  stale_count: number;
  missing_shareholder_yield_count: number;
  restatement_flagged_count: number;
  stale_period_flagged_count: number;
}

export interface ScreenerSortPayload {
  field: ScreenerSortField;
  direction: ScreenerSortDirection;
}

export interface ScreenerFilterInputPayload {
  revenue_growth_min: number | null;
  operating_margin_min: number | null;
  fcf_margin_min: number | null;
  leverage_ratio_max: number | null;
  dilution_max: number | null;
  sbc_burden_max: number | null;
  shareholder_yield_min: number | null;
  max_filing_lag_days: number | null;
  exclude_restatements: boolean;
  exclude_stale_periods: boolean;
  excluded_quality_flags: string[];
}

export interface OfficialScreenerSearchRequest {
  period_type: ScreenerPeriodType;
  ticker_universe: string[];
  filters: ScreenerFilterInputPayload;
  sort: ScreenerSortPayload;
  limit: number;
  offset: number;
}

export interface OfficialScreenerQueryPayload {
  period_type: ScreenerPeriodType;
  ticker_universe: string[];
  filters: ScreenerFilterInputPayload;
  sort: ScreenerSortPayload;
  limit: number;
  offset: number;
  strict_official_only: boolean;
}

export interface ScreenerFilterDefinitionPayload {
  field: string;
  label: string;
  description: string;
  comparator: "min" | "max" | "boolean" | "exclude_any";
  source_kind: "derived_metric" | "model_result" | "restatement_record" | "quality_flag";
  source_key: string;
  unit: string | null;
  official_only: boolean;
  notes: string[];
  suggested_values: string[];
}

export interface OfficialScreenerMetadataResponse extends ProvenanceEnvelope {
  strict_official_only: boolean;
  default_period_type: ScreenerPeriodType;
  period_types: ScreenerPeriodType[];
  default_sort: ScreenerSortPayload;
  filters: ScreenerFilterDefinitionPayload[];
  rankings: ScreenerRankingDefinitionPayload[];
  notes: string[];
}

export interface OfficialScreenerSearchResponse extends ProvenanceEnvelope {
  query: OfficialScreenerQueryPayload;
  coverage: ScreenerCoverageSummaryPayload;
  results: ScreenerResultPayload[];
}

export interface WatchlistSummaryRequest {
  tickers: string[];
}

export interface WatchlistLatestAlertPayload {
  id: string;
  level: "high" | "medium" | "low";
  title: string;
  source: string;
  date: string | null;
  href: string | null;
}

export interface WatchlistLatestActivityPayload {
  id: string;
  type: string;
  badge: string;
  title: string;
  date: string | null;
  href: string | null;
}

export interface WatchlistCoveragePayload {
  financial_periods: number;
  price_points: number;
}

export interface WatchlistSummaryItemPayload {
  ticker: string;
  name: string | null;
  sector: string | null;
  cik: string | null;
  last_checked: string | null;
  refresh: RefreshState;
  alert_summary: AlertsSummaryPayload;
  latest_alert: WatchlistLatestAlertPayload | null;
  latest_activity: WatchlistLatestActivityPayload | null;
  coverage: WatchlistCoveragePayload;
  fair_value_gap: number | null;
  roic: number | null;
  shareholder_yield: number | null;
  implied_growth: number | null;
  fair_value_gap_status?: ModelStatus | null;
  implied_growth_status?: ModelStatus | null;
  valuation_band_percentile: number | null;
  balance_sheet_risk: number | null;
  market_context_status?: MarketContextStatusPayload | null;
}

export interface WatchlistSummaryResponse {
  tickers: string[];
  companies: WatchlistSummaryItemPayload[];
}

export interface PeerOptionPayload {
  ticker: string;
  name: string;
  sector: string | null;
  market_sector: string | null;
  market_industry: string | null;
  last_checked: string | null;
  cache_state: CacheState;
  is_focus: boolean;
}

export interface PeerRevenuePoint {
  period_end: string;
  revenue: number | null;
  revenue_growth: number | null;
}

export interface PeerMetricsPayload {
  ticker: string;
  name: string;
  sector: string | null;
  market_sector: string | null;
  market_industry: string | null;
  is_focus: boolean;
  cache_state: CacheState;
  last_checked: string | null;
  period_end: string | null;
  price_date: string | null;
  latest_price: number | null;
  pe: number | null;
  ev_to_ebit: number | null;
  price_to_free_cash_flow: number | null;
  roe: number | null;
  revenue_growth: number | null;
  piotroski_score: number | null;
  altman_z_score: number | null;
  fair_value_gap: number | null;
  roic: number | null;
  shareholder_yield: number | null;
  implied_growth: number | null;
  dcf_model_status?: ModelStatus | null;
  reverse_dcf_model_status?: ModelStatus | null;
  valuation_band_percentile: number | null;
  revenue_history: PeerRevenuePoint[];
}

export interface CompanyPeersResponse extends ProvenanceEnvelope {
  company: CompanyPayload | null;
  peer_basis: string;
  available_companies: PeerOptionPayload[];
  selected_tickers: string[];
  peers: PeerMetricsPayload[];
  notes: Record<string, string>;
  refresh: RefreshState;
}

export interface RefreshQueuedResponse {
  status: "queued";
  ticker: string;
  force: boolean;
  refresh: RefreshState;
}

export interface JobStatusEvent {
  job_id: string;
  trace_id: string;
  sequence: number;
  timestamp: string;
  ticker: string;
  kind: string;
  stage: string;
  message: string;
  status: "queued" | "running" | "completed" | "failed";
  level: "info" | "success" | "error";
}

export interface ConsoleEntry {
  id: string;
  job_id?: string;
  trace_id?: string;
  ticker?: string;
  kind?: string;
  timestamp: string;
  stage: string;
  message: string;
  level: "info" | "success" | "error";
  status: "queued" | "running" | "completed" | "failed";
  source: "backend" | "client";
}

export interface Form144FilingPayload {
  accession_number: string | null;
  form: string;
  filing_date: string | null;
  filer_name: string | null;
  relationship_to_issuer: string | null;
  issuer_name: string | null;
  security_title: string | null;
  planned_sale_date: string | null;
  shares_to_be_sold: number | null;
  aggregate_market_value: number | null;
  shares_owned_after_sale: number | null;
  broker_name: string | null;
  source_url: string | null;
  summary: string | null;
}

export interface CompanyForm144Response {
  company: CompanyPayload | null;
  filings: Form144FilingPayload[];
  refresh: RefreshState;
}

