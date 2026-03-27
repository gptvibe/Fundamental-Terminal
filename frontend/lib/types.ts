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

export interface CompanyPayload {
  ticker: string;
  cik: string;
  name: string;
  sector: string | null;
  market_sector: string | null;
  market_industry: string | null;
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
  segment_breakdown: FinancialSegmentPayload[];
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

export type ModelStatus = "ok" | "partial" | "proxy" | "insufficient_data" | "unsupported" | "unknown";

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
  provenance_details: Record<string, unknown>;
  fetched_at: string;
  refresh: RefreshState;
  // v2 grouped sections
  rates_credit?: MacroSeriesItemPayload[];
  inflation_labor?: MacroSeriesItemPayload[];
  growth_activity?: MacroSeriesItemPayload[];
  relevant_series?: string[];
  sector_exposure?: string[];
  hqm_snapshot?: Record<string, unknown> | null;
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

export interface AlertsSummaryPayload {
  total: number;
  high: number;
  medium: number;
  low: number;
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

