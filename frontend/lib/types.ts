export type CacheState = "fresh" | "stale" | "missing";
export type RefreshReason = "manual" | "missing" | "stale" | "fresh" | "none";

export interface RefreshState {
  triggered: boolean;
  reason: RefreshReason;
  ticker: string | null;
  job_id: string | null;
}

export interface CompanyPayload {
  ticker: string;
  cik: string;
  name: string;
  sector: string | null;
  market_sector: string | null;
  market_industry: string | null;
  last_checked: string | null;
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
  total_liabilities: number | null;
  operating_cash_flow: number | null;
  capex: number | null;
  acquisitions: number | null;
  debt_changes: number | null;
  dividends: number | null;
  share_buybacks: number | null;
  free_cash_flow: number | null;
  eps: number | null;
  shares_outstanding: number | null;
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

export interface CompanyFinancialsResponse {
  company: CompanyPayload | null;
  financials: FinancialPayload[];
  price_history: PriceHistoryPoint[];
  refresh: RefreshState;
}

export interface InsiderTradePayload {
  name: string;
  role: string | null;
  date: string | null;
  action: string;
  transaction_code: string | null;
  shares: number | null;
  price: number | null;
  value: number | null;
  ownership_after: number | null;
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
  fund_strategy: string | null;
  reporting_date: string;
  shares_held: number | null;
  market_value: number | null;
  change_in_shares: number | null;
  percent_change: number | null;
  portfolio_weight: number | null;
}

export interface CompanyInstitutionalHoldingsResponse {
  company: CompanyPayload | null;
  institutional_holdings: InstitutionalHoldingPayload[];
  refresh: RefreshState;
}

export interface ModelPayload {
  model_name: string;
  model_version: string;
  created_at: string;
  input_periods: Record<string, unknown> | Array<Record<string, unknown>>;
  result: Record<string, unknown>;
}

export interface CompanyModelsResponse {
  company: CompanyPayload | null;
  requested_models: string[];
  models: ModelPayload[];
  refresh: RefreshState;
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
  error: string | null;
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
  revenue_history: PeerRevenuePoint[];
}

export interface CompanyPeersResponse {
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
  sequence: number;
  timestamp: string;
  stage: string;
  message: string;
  status: "queued" | "running" | "completed" | "failed";
  level: "info" | "success" | "error";
}

export interface ConsoleEntry {
  id: string;
  timestamp: string;
  stage: string;
  message: string;
  level: "info" | "success" | "error";
  status: "queued" | "running" | "completed" | "failed";
  source: "backend" | "client";
}
