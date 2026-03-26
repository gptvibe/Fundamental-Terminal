from __future__ import annotations

import logging
import asyncio
import hashlib
import html
import json
import os
import re
import threading
import time
from email.utils import format_datetime
from datetime import date as DateType, datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db_session
from app.model_engine.engine import ModelEngine
from app.model_engine.models import dupont as dupont_model
from app.models import EarningsModelPoint, EarningsRelease, ExecutiveCompensation, FinancialStatement, Form144Filing, InsiderTrade, ModelRun, PriceHistory, ProxyStatement
from app.services.insider_analytics import build_insider_analytics
from app.services.insider_activity import build_insider_activity_summary
from app.services.institutional_holdings import get_institutional_fund_strategy
from app.services.ownership_analytics import build_ownership_analytics
from app.services.peer_comparison import build_peer_comparison
from app.services import (
    CompanyCacheSnapshot,
    get_company_capital_markets_events,
    get_company_coverage_counts,
    get_company_earnings_cache_status,
    get_company_earnings_model_cache_status,
    get_company_earnings_model_points,
    get_company_earnings_releases,
    get_company_derived_metric_points,
    get_company_derived_metrics_last_checked,
    get_company_executive_compensation,
    get_company_filing_events,
    get_company_filing_insights,
    get_company_financials,
    get_company_form144_cache_status,
    get_company_form144_filings,
    get_company_insider_trade_cache_status,
    get_company_insider_trades,
    get_company_institutional_holdings,
    get_company_institutional_holdings_cache_status,
    get_company_models,
    get_company_price_cache_status,
    get_company_price_history,
    get_company_proxy_cache_status,
    get_company_proxy_statements,
    get_company_snapshot,
    get_company_snapshot_by_cik,
    get_company_snapshots_by_ticker,
    queue_company_refresh,
    search_company_snapshots,
    status_broker,
)
from app.services.cache_queries import get_company_beneficial_ownership_reports
from app.services.beneficial_ownership import collect_beneficial_ownership_reports
from app.services.derived_metrics_mart import build_summary_payload, to_period_payload
from app.services.market_context import (
    get_cached_market_context_status,
    get_company_market_context_v2,
    get_market_context_snapshot,
    get_market_context_v2,
)
from app.services.proxy_parser import ExecCompRow, ProxyFilingSignals, ProxyVoteOutcome, parse_proxy_filing_signals
from app.services.derived_metrics import build_metrics_timeseries
from app.services.earnings_intelligence import build_earnings_alerts, build_earnings_directional_backtest, build_earnings_peer_percentiles, build_sector_alert_profile
from app.services.sec_edgar import EdgarClient, FilingMetadata

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Financial Cache API", version="1.1.0")

Number = int | float | None
CORE_FILING_TIMELINE_FORMS = {"10-K", "10-Q", "8-K", "20-F", "40-F", "6-K"}
MAX_FILING_TIMELINE_ITEMS = 60
ALLOWED_SEC_EMBED_HOSTS = {"www.sec.gov", "sec.gov", "data.sec.gov"}
ALLOWED_SEC_EMBED_MIME_PREFIXES = ("text/html", "application/html", "application/xhtml+xml", "text/plain")
ALLOWED_SEC_EMBED_EXTENSIONS = (".htm", ".html", ".xhtml", ".txt")
MAX_SEC_EMBED_BYTES = 5 * 1024 * 1024
FILINGS_TIMELINE_TTL_SECONDS = settings.sec_filings_timeline_ttl_seconds
SEARCH_RESPONSE_TTL_SECONDS = 60
_search_response_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_search_response_cache_lock = threading.Lock()
_hot_response_cache: dict[str, tuple[float, float, dict[str, Any]]] = {}
_hot_response_cache_lock = threading.Lock()


class RefreshState(BaseModel):
    triggered: bool = Field(default=False)
    reason: Literal["manual", "missing", "stale", "fresh", "none"] = Field(default="none")
    ticker: str | None = Field(default=None)
    job_id: str | None = Field(default=None)


class CompanyPayload(BaseModel):
    ticker: str
    cik: str
    name: str
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None
    last_checked: datetime | None = None
    last_checked_financials: datetime | None = None
    last_checked_prices: datetime | None = None
    last_checked_insiders: datetime | None = None
    last_checked_institutional: datetime | None = None
    last_checked_filings: datetime | None = None
    earnings_last_checked: datetime | None = None
    cache_state: Literal["fresh", "stale", "missing"]


class CompanySearchResponse(BaseModel):
    query: str
    results: list[CompanyPayload]
    refresh: RefreshState


class CompanyResolutionResponse(BaseModel):
    query: str
    resolved: bool
    ticker: str | None = None
    name: str | None = None
    error: Literal["not_found", "lookup_failed"] | None = None


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


class CompanyFinancialsResponse(BaseModel):
    company: CompanyPayload | None
    financials: list[FinancialPayload]
    price_history: list[PriceHistoryPayload]
    refresh: RefreshState


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


class CompanyMetricsTimeseriesResponse(BaseModel):
    company: CompanyPayload | None
    series: list[MetricsTimeseriesPointPayload]
    last_financials_check: datetime | None = None
    last_price_check: datetime | None = None
    staleness_reason: str | None = None
    refresh: RefreshState


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


class CompanyDerivedMetricsResponse(BaseModel):
    company: CompanyPayload | None
    period_type: Literal["quarterly", "annual", "ttm"]
    periods: list[DerivedMetricPeriodPayload]
    available_metric_keys: list[str]
    last_metrics_check: datetime | None = None
    last_financials_check: datetime | None = None
    last_price_check: datetime | None = None
    staleness_reason: str | None = None
    refresh: RefreshState


class CompanyDerivedMetricsSummaryResponse(BaseModel):
    company: CompanyPayload | None
    period_type: Literal["quarterly", "annual", "ttm"]
    latest_period_end: DateType | None = None
    metrics: list[DerivedMetricValuePayload]
    last_metrics_check: datetime | None = None
    last_financials_check: datetime | None = None
    last_price_check: datetime | None = None
    staleness_reason: str | None = None
    refresh: RefreshState


class CompanyFilingInsightsResponse(BaseModel):
    company: CompanyPayload | None
    insights: list[FilingParserInsightPayload]
    refresh: RefreshState


class CompanyFactsResponse(BaseModel):
    facts: dict[str, Any]


class InsiderTradePayload(BaseModel):
    name: str
    role: str | None = None
    date: DateType | None = None
    filing_date: DateType | None = None
    filing_type: str | None = None
    accession_number: str | None = None
    source: str | None = None
    action: str
    transaction_code: str | None = None
    shares: Number = None
    price: Number = None
    value: Number = None
    ownership_after: Number = None
    security_title: str | None = None
    is_derivative: bool | None = None
    ownership_nature: str | None = None
    exercise_price: Number = None
    expiration_date: DateType | None = None
    footnote_tags: list[str] | None = None
    is_10b5_1: bool


class InsiderActivityMetricsPayload(BaseModel):
    total_buy_value: float
    total_sell_value: float
    net_value: float
    unique_insiders_buying: int
    unique_insiders_selling: int


class InsiderActivitySummaryPayload(BaseModel):
    sentiment: Literal["bullish", "neutral", "bearish"]
    summary_lines: list[str]
    metrics: InsiderActivityMetricsPayload


class CompanyInsiderTradesResponse(BaseModel):
    company: CompanyPayload | None
    insider_trades: list[InsiderTradePayload]
    summary: InsiderActivitySummaryPayload
    refresh: RefreshState


class Form144FilingPayload(BaseModel):
    accession_number: str
    form: str
    filing_date: DateType | None = None
    report_date: DateType | None = None
    filer_name: str | None = None
    relationship_to_issuer: str | None = None
    issuer_name: str | None = None
    security_title: str | None = None
    planned_sale_date: DateType | None = None
    shares_to_be_sold: Number = None
    aggregate_market_value: Number = None
    shares_owned_after_sale: Number = None
    broker_name: str | None = None
    source_url: str
    summary: str


class CompanyForm144Response(BaseModel):
    company: CompanyPayload | None
    filings: list[Form144FilingPayload]
    refresh: RefreshState


class EarningsReleasePayload(BaseModel):
    accession_number: str
    form: str
    filing_date: DateType | None = None
    report_date: DateType | None = None
    source_url: str
    primary_document: str | None = None
    exhibit_document: str | None = None
    exhibit_type: str | None = None
    reported_period_label: str | None = None
    reported_period_end: DateType | None = None
    revenue: Number = None
    operating_income: Number = None
    net_income: Number = None
    diluted_eps: Number = None
    revenue_guidance_low: Number = None
    revenue_guidance_high: Number = None
    eps_guidance_low: Number = None
    eps_guidance_high: Number = None
    share_repurchase_amount: Number = None
    dividend_per_share: Number = None
    highlights: list[str] = Field(default_factory=list)
    parse_state: Literal["parsed", "metadata_only"]


class CompanyEarningsResponse(BaseModel):
    company: CompanyPayload | None
    earnings_releases: list[EarningsReleasePayload]
    refresh: RefreshState
    error: str | None = None


class EarningsSummaryPayload(BaseModel):
    total_releases: int
    parsed_releases: int
    metadata_only_releases: int
    releases_with_guidance: int
    releases_with_buybacks: int
    releases_with_dividends: int
    latest_filing_date: DateType | None = None
    latest_report_date: DateType | None = None
    latest_reported_period_end: DateType | None = None
    latest_revenue: Number = None
    latest_operating_income: Number = None
    latest_net_income: Number = None
    latest_diluted_eps: Number = None


class CompanyEarningsSummaryResponse(BaseModel):
    company: CompanyPayload | None
    summary: EarningsSummaryPayload
    refresh: RefreshState
    error: str | None = None


class EarningsModelInputPayload(BaseModel):
    field: str
    value: Number = None
    period_end: str
    sec_tags: list[str] = Field(default_factory=list)


class EarningsModelExplainabilityPayload(BaseModel):
    formula_version: str
    period_end: str
    filing_type: str
    inputs: list[EarningsModelInputPayload] = Field(default_factory=list)
    component_values: dict[str, Number] = Field(default_factory=dict)
    proxy_usage: dict[str, bool] = Field(default_factory=dict)
    segment_deltas: list[dict[str, Any]] = Field(default_factory=list)
    release_statement_coverage: dict[str, Any] = Field(default_factory=dict)
    quality_formula: str
    eps_drift_formula: str
    momentum_formula: str


class EarningsModelPointPayload(BaseModel):
    period_start: DateType
    period_end: DateType
    filing_type: str
    quality_score: Number = None
    quality_score_delta: Number = None
    eps_drift: Number = None
    earnings_momentum_drift: Number = None
    segment_contribution_delta: Number = None
    release_statement_coverage_ratio: Number = None
    fallback_ratio: Number = None
    stale_period_warning: bool
    quality_flags: list[str] = Field(default_factory=list)
    source_statement_ids: list[int] = Field(default_factory=list)
    source_release_ids: list[int] = Field(default_factory=list)
    explainability: EarningsModelExplainabilityPayload


class EarningsBacktestWindowPayload(BaseModel):
    accession_number: str
    filing_date: DateType | None = None
    reported_period_end: DateType | None = None
    pre_price: Number = None
    post_price: Number = None
    price_return: Number = None
    quality_score_delta: Number = None
    eps_drift: Number = None
    quality_directional_consistent: bool | None = None
    eps_directional_consistent: bool | None = None
    price_source: str | None = None


class EarningsBacktestPayload(BaseModel):
    window_sessions: int
    quality_directional_consistency: Number = None
    quality_total_windows: int
    quality_consistent_windows: int
    eps_directional_consistency: Number = None
    eps_total_windows: int
    eps_consistent_windows: int
    windows: list[EarningsBacktestWindowPayload] = Field(default_factory=list)


class EarningsPeerContextPayload(BaseModel):
    peer_group_basis: Literal["market_industry", "market_sector"]
    peer_group_size: int
    quality_percentile: Number = None
    eps_drift_percentile: Number = None
    sector_group_size: int
    sector_quality_percentile: Number = None
    sector_eps_drift_percentile: Number = None


class EarningsAlertPayload(BaseModel):
    id: str
    type: Literal["quality_regime_shift", "eps_drift_sign_flip", "segment_share_change"]
    level: Literal["high", "medium", "low"]
    title: str
    detail: str
    period_end: DateType


class CompanyEarningsWorkspaceResponse(BaseModel):
    company: CompanyPayload | None
    earnings_releases: list[EarningsReleasePayload]
    summary: EarningsSummaryPayload
    model_points: list[EarningsModelPointPayload]
    backtests: EarningsBacktestPayload
    peer_context: EarningsPeerContextPayload
    alerts: list[EarningsAlertPayload]
    refresh: RefreshState
    error: str | None = None


class LargestInsiderTradePayload(BaseModel):
    insider: str
    type: Literal["BUY", "SELL", "OTHER"]
    value: float
    date: DateType | None = None


class InsiderAnalyticsResponse(BaseModel):
    buy_value_30d: float
    sell_value_30d: float
    buy_sell_ratio: float
    largest_trade: LargestInsiderTradePayload | None = None
    insider_activity_trend: Literal["increasing_buying", "increasing_selling", "stable", "mixed"]


class InstitutionalHoldingPayload(BaseModel):
    fund_name: str
    fund_cik: str | None = None
    fund_manager: str | None = None
    manager_query: str | None = None
    universe_source: str | None = None
    fund_strategy: str | None = None
    accession_number: str | None = None
    filing_form: str | None = None
    base_form: str | None = None
    is_amendment: bool = False
    reporting_date: DateType
    filing_date: DateType | None = None
    shares_held: Number = None
    market_value: Number = None
    change_in_shares: Number = None
    percent_change: Number = None
    portfolio_weight: Number = None
    put_call: str | None = None
    investment_discretion: str | None = None
    voting_authority_sole: Number = None
    voting_authority_shared: Number = None
    voting_authority_none: Number = None
    source: str | None = None


class CompanyInstitutionalHoldingsResponse(BaseModel):
    company: CompanyPayload | None
    institutional_holdings: list[InstitutionalHoldingPayload]
    refresh: RefreshState


class InstitutionalHoldingsSummaryPayload(BaseModel):
    total_rows: int
    unique_managers: int
    amended_rows: int
    latest_reporting_date: DateType | None = None


class CompanyInstitutionalHoldingsSummaryResponse(BaseModel):
    company: CompanyPayload | None
    summary: InstitutionalHoldingsSummaryPayload
    refresh: RefreshState


class TopHolderPayload(BaseModel):
    fund: str
    shares: float


class OwnershipAnalyticsResponse(BaseModel):
    top_holders: list[TopHolderPayload]
    institutional_ownership: float
    ownership_concentration: float
    quarterly_inflow: float
    quarterly_outflow: float
    new_positions: int
    sold_positions: int
    reporting_date: DateType | None = None


class ModelPayload(BaseModel):
    schema_version: str = "2.0"
    model_name: str
    model_version: str
    created_at: datetime
    input_periods: dict[str, Any] | list[dict[str, Any]]
    result: dict[str, Any]


class CompanyModelsResponse(BaseModel):
    company: CompanyPayload | None
    requested_models: list[str]
    models: list[ModelPayload]
    refresh: RefreshState


class RefreshQueuedResponse(BaseModel):
    status: Literal["queued"]
    ticker: str
    force: bool
    refresh: RefreshState


class PeerOptionPayload(BaseModel):
    ticker: str
    name: str
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None
    last_checked: datetime | None = None
    cache_state: Literal["fresh", "stale", "missing"]
    is_focus: bool = False


class PeerRevenuePointPayload(BaseModel):
    period_end: DateType
    revenue: Number = None
    revenue_growth: Number = None


class PeerMetricsPayload(BaseModel):
    ticker: str
    name: str
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None
    is_focus: bool = False
    cache_state: Literal["fresh", "stale", "missing"]
    last_checked: datetime | None = None
    period_end: DateType | None = None
    price_date: DateType | None = None
    latest_price: Number = None
    pe: Number = None
    ev_to_ebit: Number = None
    price_to_free_cash_flow: Number = None
    roe: Number = None
    revenue_growth: Number = None
    piotroski_score: Number = None
    altman_z_score: Number = None
    fair_value_gap: Number = None
    roic: Number = None
    shareholder_yield: Number = None
    implied_growth: Number = None
    dcf_model_status: str | None = None
    reverse_dcf_model_status: str | None = None
    valuation_band_percentile: Number = None
    revenue_history: list[PeerRevenuePointPayload] = Field(default_factory=list)


class CompanyPeersResponse(BaseModel):
    company: CompanyPayload | None
    peer_basis: str
    available_companies: list[PeerOptionPayload]
    selected_tickers: list[str]
    peers: list[PeerMetricsPayload]
    notes: dict[str, str]
    refresh: RefreshState


class FilingPayload(BaseModel):
    accession_number: str | None = None
    form: str
    filing_date: DateType | None = None
    report_date: DateType | None = None
    primary_document: str | None = None
    primary_doc_description: str | None = None
    items: str | None = None
    source_url: str


class FilingTimelineItemPayload(BaseModel):
    date: DateType | None = None
    form: str
    description: str
    accession: str | None = None


class FilingSearchResultPayload(BaseModel):
    form: str
    company: str
    filing_date: DateType | None = None
    filing_link: str


class CompanyFilingsResponse(BaseModel):
    company: CompanyPayload | None
    filings: list[FilingPayload]
    timeline_source: Literal["sec_submissions", "cached_financials"]
    refresh: RefreshState
    error: str | None = None


class BeneficialOwnershipPartyPayload(BaseModel):
    party_name: str
    role: str | None = None
    filer_cik: str | None = None
    shares_owned: Number = None
    percent_owned: Number = None
    event_date: DateType | None = None
    purpose: str | None = None


class BeneficialOwnershipFilingPayload(BaseModel):
    accession_number: str | None = None
    form: str
    base_form: Literal["SC 13D", "SC 13G"]
    filing_date: DateType | None = None
    report_date: DateType | None = None
    is_amendment: bool
    primary_document: str | None = None
    primary_doc_description: str | None = None
    source_url: str
    summary: str
    parties: list[BeneficialOwnershipPartyPayload] = Field(default_factory=list)
    previous_accession_number: str | None = None
    amendment_sequence: int | None = None
    amendment_chain_size: int | None = None
    previous_filing_date: DateType | None = None
    previous_percent_owned: Number = None
    percent_change_pp: Number = None
    change_direction: Literal["increase", "decrease", "unchanged", "new", "unknown"] | None = None


class CompanyBeneficialOwnershipResponse(BaseModel):
    company: CompanyPayload | None
    filings: list[BeneficialOwnershipFilingPayload]
    refresh: RefreshState
    error: str | None = None


class BeneficialOwnershipSummaryPayload(BaseModel):
    total_filings: int
    initial_filings: int
    amendments: int
    unique_reporting_persons: int
    latest_filing_date: DateType | None = None
    latest_event_date: DateType | None = None
    max_reported_percent: Number = None
    chains_with_amendments: int
    amendments_with_delta: int
    ownership_increase_events: int
    ownership_decrease_events: int
    ownership_unchanged_events: int
    largest_increase_pp: Number = None
    largest_decrease_pp: Number = None


class CompanyBeneficialOwnershipSummaryResponse(BaseModel):
    company: CompanyPayload | None
    summary: BeneficialOwnershipSummaryPayload
    refresh: RefreshState
    error: str | None = None


class CapitalRaisePayload(BaseModel):
    accession_number: str | None = None
    form: str
    filing_date: DateType | None = None
    report_date: DateType | None = None
    primary_document: str | None = None
    primary_doc_description: str | None = None
    source_url: str
    summary: str
    event_type: str | None = None
    security_type: str | None = None
    offering_amount: Number = None
    shelf_size: Number = None
    is_late_filer: bool = False


class CompanyCapitalRaisesResponse(BaseModel):
    company: CompanyPayload | None
    filings: list[CapitalRaisePayload]
    refresh: RefreshState
    error: str | None = None


class CapitalMarketsSummaryPayload(BaseModel):
    total_filings: int
    late_filer_notices: int
    registration_filings: int
    prospectus_filings: int
    latest_filing_date: DateType | None = None
    max_offering_amount: Number = None


class CompanyCapitalMarketsSummaryResponse(BaseModel):
    company: CompanyPayload | None
    summary: CapitalMarketsSummaryPayload
    refresh: RefreshState
    error: str | None = None


class GovernanceFilingPayload(BaseModel):
    accession_number: str | None = None
    form: str
    filing_date: DateType | None = None
    report_date: DateType | None = None
    primary_document: str | None = None
    primary_doc_description: str | None = None
    source_url: str
    summary: str
    meeting_date: DateType | None = None
    executive_comp_table_detected: bool = False
    vote_item_count: int = 0
    board_nominee_count: int | None = None
    key_amounts: list[float] = Field(default_factory=list)
    vote_outcomes: list["GovernanceVoteOutcomePayload"] = Field(default_factory=list)


class GovernanceVoteOutcomePayload(BaseModel):
    proposal_number: int
    title: str | None = None
    for_votes: int | None = None
    against_votes: int | None = None
    abstain_votes: int | None = None
    broker_non_votes: int | None = None


class CompanyGovernanceResponse(BaseModel):
    company: CompanyPayload | None
    filings: list[GovernanceFilingPayload]
    refresh: RefreshState
    error: str | None = None


class GovernanceSummaryPayload(BaseModel):
    total_filings: int
    definitive_proxies: int
    supplemental_proxies: int
    filings_with_meeting_date: int
    filings_with_exec_comp: int
    filings_with_vote_items: int
    latest_meeting_date: DateType | None = None
    max_vote_item_count: int = 0


class CompanyGovernanceSummaryResponse(BaseModel):
    company: CompanyPayload | None
    summary: GovernanceSummaryPayload
    refresh: RefreshState
    error: str | None = None


class ExecCompRowPayload(BaseModel):
    executive_name: str
    executive_title: str | None = None
    fiscal_year: int | None = None
    salary: float | None = None
    bonus: float | None = None
    stock_awards: float | None = None
    option_awards: float | None = None
    non_equity_incentive: float | None = None
    other_compensation: float | None = None
    total_compensation: float | None = None


class CompanyExecutiveCompensationResponse(BaseModel):
    company: CompanyPayload | None
    rows: list[ExecCompRowPayload]
    fiscal_years: list[int]
    source: str  # "cached" | "live" | "none"
    refresh: RefreshState
    error: str | None = None


class FilingEventPayload(BaseModel):
    accession_number: str | None = None
    form: str
    filing_date: DateType | None = None
    report_date: DateType | None = None
    items: str | None = None
    item_code: str | None = None
    category: str
    primary_document: str | None = None
    primary_doc_description: str | None = None
    source_url: str
    summary: str
    key_amounts: list[float] = Field(default_factory=list)
    exhibit_references: list[str] = Field(default_factory=list)


class CompanyEventsResponse(BaseModel):
    company: CompanyPayload | None
    events: list[FilingEventPayload]
    refresh: RefreshState
    error: str | None = None


class FilingEventsSummaryPayload(BaseModel):
    total_events: int
    unique_accessions: int
    categories: dict[str, int]
    latest_event_date: DateType | None = None
    max_key_amount: Number = None


class CompanyFilingEventsSummaryResponse(BaseModel):
    company: CompanyPayload | None
    summary: FilingEventsSummaryPayload
    refresh: RefreshState
    error: str | None = None


class ActivityFeedEntryPayload(BaseModel):
    id: str
    date: DateType | None = None
    type: str
    badge: str
    title: str
    detail: str
    href: str | None = None


class CompanyActivityFeedResponse(BaseModel):
    company: CompanyPayload | None
    entries: list[ActivityFeedEntryPayload]
    refresh: RefreshState
    error: str | None = None


class AlertPayload(BaseModel):
    id: str
    level: Literal["high", "medium", "low"]
    title: str
    detail: str
    source: str
    date: DateType | None = None
    href: str | None = None


class AlertsSummaryPayload(BaseModel):
    total: int
    high: int
    medium: int
    low: int


class CompanyAlertsResponse(BaseModel):
    company: CompanyPayload | None
    alerts: list[AlertPayload]
    summary: AlertsSummaryPayload
    refresh: RefreshState
    error: str | None = None


class CompanyActivityOverviewResponse(BaseModel):
    company: CompanyPayload | None
    entries: list[ActivityFeedEntryPayload]
    alerts: list[AlertPayload]
    summary: AlertsSummaryPayload
    market_context_status: dict[str, Any] | None = None
    refresh: RefreshState
    error: str | None = None


class MarketCurvePointPayload(BaseModel):
    tenor: str
    rate: float
    observation_date: DateType


class MarketSlopePayload(BaseModel):
    label: str
    value: Number = None
    long_tenor: str
    short_tenor: str
    observation_date: DateType | None = None


class MarketFredSeriesPayload(BaseModel):
    series_id: str
    label: str
    category: str
    units: str
    value: Number = None
    observation_date: DateType | None = None
    state: str


class MacroHistoryPointPayload(BaseModel):
    date: str
    value: float


class MacroSeriesItemPayload(BaseModel):
    series_id: str
    label: str
    source_name: str
    source_url: str
    units: str
    value: Number = None
    previous_value: Number = None
    change: Number = None
    change_percent: Number = None
    observation_date: DateType | None = None
    release_date: DateType | None = None
    history: list[MacroHistoryPointPayload] = Field(default_factory=list)
    status: str


class CompanyMarketContextResponse(BaseModel):
    company: CompanyPayload | None
    status: str
    curve_points: list[MarketCurvePointPayload]
    slope_2s10s: MarketSlopePayload
    slope_3m10y: MarketSlopePayload
    fred_series: list[MarketFredSeriesPayload]
    provenance: dict[str, Any]
    fetched_at: datetime
    refresh: RefreshState
    # v2 grouped sections
    rates_credit: list[MacroSeriesItemPayload] = Field(default_factory=list)
    inflation_labor: list[MacroSeriesItemPayload] = Field(default_factory=list)
    growth_activity: list[MacroSeriesItemPayload] = Field(default_factory=list)
    relevant_series: list[str] = Field(default_factory=list)
    sector_exposure: list[str] = Field(default_factory=list)
    hqm_snapshot: dict[str, Any] | None = None


class WatchlistSummaryRequest(BaseModel):
    tickers: list[str] = Field(default_factory=list)


class WatchlistLatestAlertPayload(BaseModel):
    id: str
    level: Literal["high", "medium", "low"]
    title: str
    source: str
    date: DateType | None = None
    href: str | None = None


class WatchlistLatestActivityPayload(BaseModel):
    id: str
    type: str
    badge: str
    title: str
    date: DateType | None = None
    href: str | None = None


class WatchlistCoveragePayload(BaseModel):
    financial_periods: int
    price_points: int


class WatchlistSummaryItemPayload(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    cik: str | None = None
    last_checked: datetime | None = None
    refresh: RefreshState
    alert_summary: AlertsSummaryPayload
    latest_alert: WatchlistLatestAlertPayload | None = None
    latest_activity: WatchlistLatestActivityPayload | None = None
    coverage: WatchlistCoveragePayload
    fair_value_gap: Number = None
    roic: Number = None
    shareholder_yield: Number = None
    implied_growth: Number = None
    fair_value_gap_status: str | None = None
    implied_growth_status: str | None = None
    valuation_band_percentile: Number = None
    balance_sheet_risk: Number = None
    market_context_status: dict[str, Any] | None = None


class WatchlistSummaryResponse(BaseModel):
    tickers: list[str]
    companies: list[WatchlistSummaryItemPayload]


_filings_timeline_cache: dict[str, tuple[float, list[FilingPayload]]] = {}
try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None

_redis_client = None
if redis is not None:
    try:
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
        )
    except Exception:
        logging.getLogger(__name__).warning("Redis client unavailable; falling back to process cache")
        _redis_client = None


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/jobs/{job_id}/events")
async def stream_job_events(job_id: str, request: Request) -> StreamingResponse:
    if not status_broker.has_job(job_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown job ID")

    backlog, queue, unsubscribe = status_broker.subscribe(job_id)

    async def event_generator():
        try:
            for event in backlog:
                yield status_broker.format_sse(job_id, event)
                if event.status in {"completed", "failed"}:
                    return

            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                yield status_broker.format_sse(job_id, event)
                if event.status in {"completed", "failed"}:
                    break
        finally:
            unsubscribe()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/companies/search", response_model=CompanySearchResponse)
def search_companies(
    request: Request,
    http_response: Response,
    background_tasks: BackgroundTasks,
    query: str | None = Query(default=None, min_length=1),
    ticker: str | None = Query(default=None, min_length=1),
    refresh: bool = Query(default=True),
    session: Session = Depends(get_db_session),
) -> CompanySearchResponse:
    raw_query = query if query is not None else ticker
    if raw_query is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="query is required")

    normalized_query = _normalize_search_query(raw_query)
    hot_key = f"search:{normalized_query}:refresh={int(refresh)}"
    cached_hot = _get_hot_cached_payload(hot_key)
    if cached_hot is not None:
        payload, is_fresh = cached_hot
        cached_response = CompanySearchResponse.model_validate(payload)
        if not is_fresh and _looks_like_ticker(normalized_query):
            stale_refresh = _trigger_refresh(background_tasks, _normalize_ticker(normalized_query), reason="stale")
            cached_response = cached_response.model_copy(update={"refresh": stale_refresh})

        not_modified = _apply_conditional_headers(
            request,
            http_response,
            cached_response,
            last_modified=max(
                (item.last_checked for item in cached_response.results if item.last_checked is not None),
                default=None,
            ),
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return cached_response

    if not refresh:
        cached_response = _get_cached_search_response(normalized_query)
        if cached_response is not None:
            _store_hot_cached_payload(hot_key, cached_response)
            not_modified = _apply_conditional_headers(
                request,
                http_response,
                cached_response,
                last_modified=max(
                    (item.last_checked for item in cached_response.results if item.last_checked is not None),
                    default=None,
                ),
            )
            if not_modified is not None:
                return not_modified  # type: ignore[return-value]
            return cached_response

    normalized_ticker = _normalize_ticker(normalized_query)
    normalized_cik = _normalize_cik_query(normalized_query)
    snapshots = search_company_snapshots(session, normalized_query)
    exact_match = next(
        (
            snapshot
            for snapshot in snapshots
            if snapshot.company.ticker == normalized_ticker or (normalized_cik is not None and snapshot.company.cik == normalized_cik)
        ),
        None,
    )

    refresh_state = RefreshState()
    if not refresh:
        if exact_match is None:
            refresh_state = RefreshState(
                triggered=False,
                reason="none",
                ticker=normalized_ticker if _looks_like_ticker(normalized_query) else None,
                job_id=None,
            )
        elif exact_match.cache_state in {"missing", "stale"}:
            refresh_state = RefreshState(
                triggered=False,
                reason=exact_match.cache_state,
                ticker=exact_match.company.ticker,
                job_id=None,
            )
        else:
            refresh_state = RefreshState(triggered=False, reason="fresh", ticker=exact_match.company.ticker, job_id=None)
    elif exact_match is None:
        if not snapshots and _looks_like_ticker(normalized_query):
            refresh_state = _trigger_refresh(background_tasks, normalized_ticker, reason="missing")
        else:
            refresh_state = RefreshState(triggered=False, reason="none", ticker=normalized_ticker if _looks_like_ticker(normalized_query) else None, job_id=None)
    elif exact_match.cache_state in {"missing", "stale"}:
        refresh_state = _trigger_refresh(background_tasks, exact_match.company.ticker, reason=exact_match.cache_state)
    else:
        refresh_state = RefreshState(triggered=False, reason="fresh", ticker=exact_match.company.ticker, job_id=None)

    payload = CompanySearchResponse(
        query=normalized_query,
        results=[_serialize_company(snapshot) for snapshot in snapshots],
        refresh=refresh_state,
    )
    if not refresh:
        _store_cached_search_response(normalized_query, payload)
    _store_hot_cached_payload(hot_key, payload)
    not_modified = _apply_conditional_headers(
        request,
        http_response,
        payload,
        last_modified=max((item.last_checked for item in payload.results if item.last_checked is not None), default=None),
    )
    if not_modified is not None:
        return not_modified  # type: ignore[return-value]
    return payload


@app.get("/api/companies/resolve", response_model=CompanyResolutionResponse)
def resolve_company_identifier(query: str = Query(..., min_length=1), session: Session = Depends(get_db_session)) -> CompanyResolutionResponse:
    normalized_query = _normalize_search_query(query)

    client = EdgarClient()
    try:
        identity = client.resolve_company(normalized_query)
    except ValueError:
        return CompanyResolutionResponse(query=normalized_query, resolved=False, error="not_found")
    except Exception:
        logging.getLogger(__name__).exception("SEC company resolution failed for '%s'", normalized_query)
        return CompanyResolutionResponse(query=normalized_query, resolved=False, error="lookup_failed")
    finally:
        client.close()

    return CompanyResolutionResponse(
        query=normalized_query,
        resolved=True,
        ticker=_resolve_canonical_ticker(session, identity) or identity.ticker,
        name=identity.name,
        error=None,
    )


@app.get("/api/companies/{ticker}/financials", response_model=CompanyFinancialsResponse)
def company_financials(
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFinancialsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    hot_key = f"financials:{normalized_ticker}"
    cached_hot = _get_hot_cached_payload(hot_key)
    if cached_hot is not None:
        payload_data, is_fresh = cached_hot
        cached_response = CompanyFinancialsResponse.model_validate(payload_data)
        if not is_fresh:
            stale_refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="stale")
            cached_response = cached_response.model_copy(update={"refresh": stale_refresh})

        not_modified = _apply_conditional_headers(
            request,
            http_response,
            cached_response,
            last_modified=cached_response.company.last_checked if cached_response.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return cached_response

    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyFinancialsResponse(
            company=None,
            financials=[],
            price_history=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )
        _store_hot_cached_payload(hot_key, payload)
        return payload

    financials = get_company_financials(session, snapshot.company.id)
    price_last_checked, price_cache_state = get_company_price_cache_status(session, snapshot.company.id)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)
    price_history = get_company_price_history(session, snapshot.company.id)
    payload = CompanyFinancialsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
        ),
        financials=[_serialize_financial(statement) for statement in financials],
        price_history=[_serialize_price_history(point) for point in price_history],
        refresh=refresh,
    )
    _store_hot_cached_payload(hot_key, payload)
    not_modified = _apply_conditional_headers(
        request,
        http_response,
        payload,
        last_modified=payload.company.last_checked if payload.company else None,
    )
    if not_modified is not None:
        return not_modified  # type: ignore[return-value]
    return payload


@app.get("/api/companies/{ticker}/filing-insights", response_model=CompanyFilingInsightsResponse)
def company_filing_insights(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFilingInsightsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyFilingInsightsResponse(
            company=None,
            insights=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    insights = get_company_filing_insights(session, snapshot.company.id)
    insights_last_checked = max((item.last_checked for item in insights if item.last_checked is not None), default=None)
    refresh = _refresh_for_filing_insights(background_tasks, snapshot)
    return CompanyFilingInsightsResponse(
        company=_serialize_company(snapshot, last_checked=insights_last_checked),
        insights=[_serialize_filing_parser_insight(item) for item in insights],
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/metrics-timeseries", response_model=CompanyMetricsTimeseriesResponse)
def company_metrics_timeseries(
    ticker: str,
    background_tasks: BackgroundTasks,
    cadence: Literal["quarterly", "annual", "ttm"] | None = Query(default=None),
    max_points: int = Query(default=24, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> CompanyMetricsTimeseriesResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyMetricsTimeseriesResponse(
            company=None,
            series=[],
            last_financials_check=None,
            last_price_check=None,
            staleness_reason="company_missing",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    financials = get_company_financials(session, snapshot.company.id)
    price_last_checked, price_cache_state = get_company_price_cache_status(session, snapshot.company.id)
    staleness_reason = _metrics_staleness_reason(snapshot, price_cache_state, financials)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)
    price_history = get_company_price_history(session, snapshot.company.id)
    series = build_metrics_timeseries(financials, price_history, cadence=cadence, max_points=max_points)
    return CompanyMetricsTimeseriesResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
        ),
        series=[MetricsTimeseriesPointPayload.model_validate(point) for point in series],
        last_financials_check=snapshot.last_checked,
        last_price_check=price_last_checked,
        staleness_reason=staleness_reason,
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/metrics", response_model=CompanyDerivedMetricsResponse)
def company_derived_metrics(
    ticker: str,
    background_tasks: BackgroundTasks,
    period_type: Literal["quarterly", "annual", "ttm"] = Query(default="ttm"),
    max_periods: int = Query(default=24, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> CompanyDerivedMetricsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyDerivedMetricsResponse(
            company=None,
            period_type=period_type,
            periods=[],
            available_metric_keys=[],
            last_metrics_check=None,
            last_financials_check=None,
            last_price_check=None,
            staleness_reason="company_missing",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    price_last_checked, price_cache_state = get_company_price_cache_status(session, snapshot.company.id)
    financials = get_company_financials(session, snapshot.company.id)
    staleness_reason = _metrics_staleness_reason(snapshot, price_cache_state, financials)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)

    rows = get_company_derived_metric_points(
        session,
        snapshot.company.id,
        period_type=period_type,
        max_periods=max_periods,
    )
    last_metrics_check = get_company_derived_metrics_last_checked(session, snapshot.company.id)
    if not rows:
        refresh = _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
        if staleness_reason == "fresh":
            staleness_reason = "metrics_missing"

    period_payload = [DerivedMetricPeriodPayload.model_validate(item) for item in to_period_payload(rows)]
    available_metric_keys = sorted({item.metric_key for item in rows})
    return CompanyDerivedMetricsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
        ),
        period_type=period_type,
        periods=period_payload,
        available_metric_keys=available_metric_keys,
        last_metrics_check=last_metrics_check,
        last_financials_check=snapshot.last_checked,
        last_price_check=price_last_checked,
        staleness_reason=staleness_reason,
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/metrics/summary", response_model=CompanyDerivedMetricsSummaryResponse)
def company_derived_metrics_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    period_type: Literal["quarterly", "annual", "ttm"] = Query(default="ttm"),
    session: Session = Depends(get_db_session),
) -> CompanyDerivedMetricsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyDerivedMetricsSummaryResponse(
            company=None,
            period_type=period_type,
            latest_period_end=None,
            metrics=[],
            last_metrics_check=None,
            last_financials_check=None,
            last_price_check=None,
            staleness_reason="company_missing",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    price_last_checked, price_cache_state = get_company_price_cache_status(session, snapshot.company.id)
    financials = get_company_financials(session, snapshot.company.id)
    staleness_reason = _metrics_staleness_reason(snapshot, price_cache_state, financials)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)

    rows = get_company_derived_metric_points(session, snapshot.company.id, max_periods=24)
    last_metrics_check = get_company_derived_metrics_last_checked(session, snapshot.company.id)
    if not rows:
        refresh = _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
        if staleness_reason == "fresh":
            staleness_reason = "metrics_missing"

    summary = build_summary_payload(rows, period_type)
    metric_payload = [DerivedMetricValuePayload.model_validate(item) for item in summary["metrics"]]
    return CompanyDerivedMetricsSummaryResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
        ),
        period_type=summary["period_type"],
        latest_period_end=summary["latest_period_end"],
        metrics=metric_payload,
        last_metrics_check=last_metrics_check,
        last_financials_check=snapshot.last_checked,
        last_price_check=price_last_checked,
        staleness_reason=staleness_reason,
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/insider-trades", response_model=CompanyInsiderTradesResponse)
def company_insider_trades(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyInsiderTradesResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyInsiderTradesResponse(
            company=None,
            insider_trades=[],
            summary=_serialize_insider_activity_summary(build_insider_activity_summary([])),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    insider_last_checked, insider_cache_state = get_company_insider_trade_cache_status(session, snapshot.company)
    insider_trades = get_company_insider_trades(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(background_tasks, snapshot.company.ticker, reason=insider_cache_state)
        if insider_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    return CompanyInsiderTradesResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, insider_last_checked),
            last_checked_insiders=insider_last_checked,
        ),
        insider_trades=[_serialize_insider_trade(trade) for trade in insider_trades],
        summary=_serialize_insider_activity_summary(build_insider_activity_summary(insider_trades)),
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/institutional-holdings", response_model=CompanyInstitutionalHoldingsResponse)
def company_institutional_holdings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyInstitutionalHoldingsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyInstitutionalHoldingsResponse(
            company=None,
            institutional_holdings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    holdings_last_checked, holdings_cache_state = get_company_institutional_holdings_cache_status(session, snapshot.company)
    holdings = get_company_institutional_holdings(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(background_tasks, snapshot.company.ticker, reason=holdings_cache_state)
        if holdings_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    return CompanyInstitutionalHoldingsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, holdings_last_checked),
            last_checked_institutional=holdings_last_checked,
        ),
        institutional_holdings=[_serialize_institutional_holding(holding) for holding in holdings],
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/institutional-holdings/summary", response_model=CompanyInstitutionalHoldingsSummaryResponse)
def company_institutional_holdings_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyInstitutionalHoldingsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyInstitutionalHoldingsSummaryResponse(
            company=None,
            summary=InstitutionalHoldingsSummaryPayload(total_rows=0, unique_managers=0, amended_rows=0, latest_reporting_date=None),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    holdings_last_checked, holdings_cache_state = get_company_institutional_holdings_cache_status(session, snapshot.company)
    holdings = get_company_institutional_holdings(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(background_tasks, snapshot.company.ticker, reason=holdings_cache_state)
        if holdings_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    rows = [_serialize_institutional_holding(holding) for holding in holdings]
    return CompanyInstitutionalHoldingsSummaryResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, holdings_last_checked),
            last_checked_institutional=holdings_last_checked,
        ),
        summary=_build_institutional_holdings_summary(rows),
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/form-144-filings", response_model=CompanyForm144Response)
def company_form144_filings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyForm144Response:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyForm144Response(
            company=None,
            filings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    form144_last_checked, form144_cache_state = get_company_form144_cache_status(session, snapshot.company)
    filings = get_company_form144_filings(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(background_tasks, snapshot.company.ticker, reason=form144_cache_state)
        if form144_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    return CompanyForm144Response(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, form144_last_checked),
        ),
        filings=[_serialize_form144_filing(filing) for filing in filings],
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/earnings", response_model=CompanyEarningsResponse)
def company_earnings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEarningsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEarningsResponse(
            company=None,
            earnings_releases=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    earnings_last_checked, earnings_cache_state = get_company_earnings_cache_status(session, snapshot.company)
    earnings_releases = get_company_earnings_releases(session, snapshot.company.id)
    refresh = _refresh_for_earnings(background_tasks, snapshot, earnings_cache_state)
    payload = [_serialize_earnings_release(release) for release in earnings_releases]
    return CompanyEarningsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, earnings_last_checked),
            last_checked_earnings=earnings_last_checked,
        ),
        earnings_releases=payload,
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/earnings/summary", response_model=CompanyEarningsSummaryResponse)
def company_earnings_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEarningsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEarningsSummaryResponse(
            company=None,
            summary=_build_earnings_summary([]),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    earnings_last_checked, earnings_cache_state = get_company_earnings_cache_status(session, snapshot.company)
    earnings_releases = get_company_earnings_releases(session, snapshot.company.id)
    refresh = _refresh_for_earnings(background_tasks, snapshot, earnings_cache_state)
    payload = [_serialize_earnings_release(release) for release in earnings_releases]
    return CompanyEarningsSummaryResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, earnings_last_checked),
            last_checked_earnings=earnings_last_checked,
        ),
        summary=_build_earnings_summary(payload),
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/earnings/workspace", response_model=CompanyEarningsWorkspaceResponse)
def company_earnings_workspace(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEarningsWorkspaceResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEarningsWorkspaceResponse(
            company=None,
            earnings_releases=[],
            summary=_build_earnings_summary([]),
            model_points=[],
            backtests=EarningsBacktestPayload(
                window_sessions=3,
                quality_directional_consistency=None,
                quality_total_windows=0,
                quality_consistent_windows=0,
                eps_directional_consistency=None,
                eps_total_windows=0,
                eps_consistent_windows=0,
                windows=[],
            ),
            peer_context=EarningsPeerContextPayload(
                peer_group_basis="market_sector",
                peer_group_size=0,
                quality_percentile=None,
                eps_drift_percentile=None,
                sector_group_size=0,
                sector_quality_percentile=None,
                sector_eps_drift_percentile=None,
            ),
            alerts=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    earnings_last_checked, earnings_cache_state = get_company_earnings_cache_status(session, snapshot.company)
    model_last_checked, model_cache_state = get_company_earnings_model_cache_status(session, snapshot.company.id)
    earnings_releases = get_company_earnings_releases(session, snapshot.company.id)
    model_rows = get_company_earnings_model_points(session, snapshot.company.id)
    refresh = _refresh_for_earnings_workspace(background_tasks, snapshot, earnings_cache_state, model_cache_state)

    release_payload = [_serialize_earnings_release(release) for release in earnings_releases]
    model_payload = [_serialize_earnings_model_point(point) for point in model_rows]
    backtest_payload = EarningsBacktestPayload.model_validate(
        build_earnings_directional_backtest(
            model_rows,
            earnings_releases,
            get_company_price_history(session, snapshot.company.id),
        )
    )
    latest_point = model_rows[-1] if model_rows else None
    peer_payload = EarningsPeerContextPayload.model_validate(
        build_earnings_peer_percentiles(session, snapshot.company, latest_point)
    )
    alert_profile = build_sector_alert_profile(session, snapshot.company)
    alerts_payload = [EarningsAlertPayload.model_validate(item) for item in build_earnings_alerts(model_rows, profile=alert_profile)]

    return CompanyEarningsWorkspaceResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, _merge_last_checked(earnings_last_checked, model_last_checked)),
            last_checked_earnings=_merge_last_checked(earnings_last_checked, model_last_checked),
        ),
        earnings_releases=release_payload,
        summary=_build_earnings_summary(release_payload),
        model_points=model_payload,
        backtests=backtest_payload,
        peer_context=peer_payload,
        alerts=alerts_payload,
        refresh=refresh,
    )


@app.get("/api/insiders/{ticker}", response_model=InsiderAnalyticsResponse)
def insider_analytics(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> InsiderAnalyticsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    trades = get_company_insider_trades(session, snapshot.company.id, limit=400)
    return _serialize_insider_analytics(build_insider_analytics(trades))


@app.get("/api/ownership/{ticker}", response_model=OwnershipAnalyticsResponse)
def ownership_analytics(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> OwnershipAnalyticsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    holdings = get_company_institutional_holdings(session, snapshot.company.id, limit=600)
    analytics = build_ownership_analytics(holdings)
    return _serialize_ownership_analytics(analytics)


@app.post(
    "/api/companies/{ticker}/refresh",
    response_model=RefreshQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def refresh_company(
    ticker: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    session: Session = Depends(get_db_session),
) -> RefreshQueuedResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    queue_ticker = snapshot.company.ticker if snapshot is not None else normalized_ticker
    job_id = queue_company_refresh(background_tasks, queue_ticker, force=force)
    return RefreshQueuedResponse(
        status="queued",
        ticker=queue_ticker,
        force=force,
        refresh=RefreshState(triggered=True, reason="manual", ticker=queue_ticker, job_id=job_id),
    )


@app.get("/api/companies/{ticker}/models", response_model=CompanyModelsResponse)
def company_models(
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
    model: str | None = Query(default=None),
    dupont_mode: str | None = Query(default=None, description="optional DuPont basis: auto|annual|ttm"),
    session: Session = Depends(get_db_session),
) -> CompanyModelsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_models = _parse_requested_models(model)
    if not settings.valuation_workbench_enabled:
        requested_models = [
            item
            for item in requested_models
            if item not in {"reverse_dcf", "roic", "capital_allocation"}
        ]
    normalized_mode = (dupont_mode or "").lower() or None
    if normalized_mode is not None and normalized_mode not in {"auto", "annual", "ttm"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dupont_mode must be one of: auto, annual, ttm")
    hot_key = f"models:{normalized_ticker}:models={','.join(requested_models)}:dupont={normalized_mode or 'default'}"
    cached_hot = _get_hot_cached_payload(hot_key)
    if cached_hot is not None:
        payload_data, is_fresh = cached_hot
        cached_response = CompanyModelsResponse.model_validate(payload_data)
        if not is_fresh:
            stale_refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="stale")
            cached_response = cached_response.model_copy(update={"refresh": stale_refresh})

        not_modified = _apply_conditional_headers(
            request,
            http_response,
            cached_response,
            last_modified=cached_response.company.last_checked if cached_response.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return cached_response

    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyModelsResponse(
            company=None,
            requested_models=requested_models,
            models=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )
        _store_hot_cached_payload(hot_key, payload)
        return payload

    token = None
    try:
        if normalized_mode is not None:
            token = dupont_model.set_mode_override(normalized_mode)

        refresh = _refresh_for_snapshot(background_tasks, snapshot)
        if snapshot.cache_state == "fresh" and requested_models:
            model_job_results = ModelEngine(session).compute_models(snapshot.company.id, model_names=requested_models, force=False)
            if any(not result.cached for result in model_job_results):
                session.commit()

        models = get_company_models(
            session,
            snapshot.company.id,
            requested_models or None,
            config_by_model={"dupont": {"mode": dupont_model.get_mode()}},
        )
        status_counts: dict[str, int] = {}
        for model_run in models:
            result = model_run.result if isinstance(model_run.result, dict) else {}
            model_status = str(result.get("model_status") or result.get("status") or "unknown")
            status_counts[model_status] = status_counts.get(model_status, 0) + 1
        logging.getLogger(__name__).info(
            "TELEMETRY model_view ticker=%s models=%s status_counts=%s",
            snapshot.company.ticker,
            ",".join(requested_models) if requested_models else "all",
            status_counts,
        )
        payload = CompanyModelsResponse(
            company=_serialize_company(snapshot),
            requested_models=requested_models,
            models=[_serialize_model(model_run) for model_run in models],
            refresh=refresh,
        )
        _store_hot_cached_payload(hot_key, payload)
        not_modified = _apply_conditional_headers(
            request,
            http_response,
            payload,
            last_modified=payload.company.last_checked if payload.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return payload
    finally:
        if token is not None:
            dupont_model.reset_mode_override(token)


@app.get("/api/companies/{ticker}/market-context", response_model=CompanyMarketContextResponse)
def company_market_context(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyMarketContextResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyMarketContextResponse(
            company=None,
            status="insufficient_data",
            curve_points=[],
            slope_2s10s=MarketSlopePayload(label="2s10s", value=None, short_tenor="2y", long_tenor="10y", observation_date=None),
            slope_3m10y=MarketSlopePayload(label="3m10y", value=None, short_tenor="3m", long_tenor="10y", observation_date=None),
            fred_series=[],
            provenance={
                "treasury": {"status": "missing"},
                "fred": {
                    "enabled": bool(settings.fred_api_key),
                    "status": "missing_api_key" if not settings.fred_api_key else "missing",
                },
            },
            fetched_at=datetime.now(timezone.utc),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    company = snapshot.company
    payload = get_company_market_context_v2(
        session,
        company.id,
        sector=company.sector,
        market_sector=company.market_sector,
        market_industry=company.market_industry,
    )
    return _v2_dict_to_response(payload, company=_serialize_company(snapshot), refresh=refresh)


def _v2_dict_to_response(
    payload: dict[str, Any],
    *,
    company: "CompanyPayload | None",
    refresh: "RefreshState",
) -> "CompanyMarketContextResponse":
    """Convert a v2 macro payload dict to CompanyMarketContextResponse."""
    # Legacy curve_points
    curve_points = [
        MarketCurvePointPayload(
            tenor=p["tenor"],
            rate=p["rate"],
            observation_date=p["observation_date"],
        )
        for p in (payload.get("curve_points") or [])
    ]
    s2 = payload.get("slope_2s10s") or {}
    s3 = payload.get("slope_3m10y") or {}
    slope_2s10s = MarketSlopePayload(
        label=str(s2.get("label") or "2s10s"),
        value=s2.get("value"),
        short_tenor=str(s2.get("short_tenor") or "2y"),
        long_tenor=str(s2.get("long_tenor") or "10y"),
        observation_date=s2.get("observation_date"),
    )
    slope_3m10y = MarketSlopePayload(
        label=str(s3.get("label") or "3m10y"),
        value=s3.get("value"),
        short_tenor=str(s3.get("short_tenor") or "3m"),
        long_tenor=str(s3.get("long_tenor") or "10y"),
        observation_date=s3.get("observation_date"),
    )
    fred_series = [
        MarketFredSeriesPayload(
            series_id=str(item.get("series_id", "")),
            label=str(item.get("label", "")),
            category=str(item.get("category", "")),
            units=str(item.get("units", "")),
            value=item.get("value"),
            observation_date=item.get("observation_date"),
            state=str(item.get("state", "ok")),
        )
        for item in (payload.get("fred_series") or [])
    ]
    # v2 grouped sections
    def _items(section_key: str) -> list[MacroSeriesItemPayload]:
        return [
            MacroSeriesItemPayload(
                series_id=str(d.get("series_id", "")),
                label=str(d.get("label", "")),
                source_name=str(d.get("source_name", "")),
                source_url=str(d.get("source_url", "")),
                units=str(d.get("units", "")),
                value=d.get("value"),
                previous_value=d.get("previous_value"),
                change=d.get("change"),
                change_percent=d.get("change_percent"),
                observation_date=d.get("observation_date"),
                release_date=d.get("release_date"),
                history=[
                    MacroHistoryPointPayload(date=h["date"], value=h["value"])
                    for h in (d.get("history") or [])
                ],
                status=str(d.get("status", "ok")),
            )
            for d in (payload.get(section_key) or [])
        ]

    fetched_raw = payload.get("fetched_at") or ""
    try:
        fetched_at = datetime.fromisoformat(str(fetched_raw))
    except Exception:
        fetched_at = datetime.now(timezone.utc)

    return CompanyMarketContextResponse(
        company=company,
        status=str(payload.get("status") or "ok"),
        curve_points=curve_points,
        slope_2s10s=slope_2s10s,
        slope_3m10y=slope_3m10y,
        fred_series=fred_series,
        provenance=payload.get("provenance") or {},
        fetched_at=fetched_at,
        refresh=refresh,
        rates_credit=_items("rates_credit"),
        inflation_labor=_items("inflation_labor"),
        growth_activity=_items("growth_activity"),
        relevant_series=list(payload.get("relevant_series") or []),
        sector_exposure=list(payload.get("sector_exposure") or []),
        hqm_snapshot=payload.get("hqm_snapshot"),
    )


@app.get("/api/market-context", response_model=CompanyMarketContextResponse)
def global_market_context(
    session: Session = Depends(get_db_session),
) -> CompanyMarketContextResponse:
    payload = get_market_context_v2(session)
    return _v2_dict_to_response(
        payload,
        company=None,
        refresh=RefreshState(triggered=False, reason="none", ticker=None, job_id=None),
    )


@app.get("/api/companies/{ticker}/peers", response_model=CompanyPeersResponse)
def company_peers(
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
    peers: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> CompanyPeersResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    selected_tickers = _parse_csv_values(peers)
    hot_key = f"peers:{normalized_ticker}:selected={','.join(selected_tickers)}"
    cached_hot = _get_hot_cached_payload(hot_key)
    if cached_hot is not None:
        payload_data, is_fresh = cached_hot
        cached_response = CompanyPeersResponse.model_validate(payload_data)
        if not is_fresh:
            stale_refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="stale")
            cached_response = cached_response.model_copy(update={"refresh": stale_refresh})

        not_modified = _apply_conditional_headers(
            request,
            http_response,
            cached_response,
            last_modified=cached_response.company.last_checked if cached_response.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return cached_response

    if snapshot is None:
        payload = CompanyPeersResponse(
            company=None,
            peer_basis="Cached peer universe",
            available_companies=[],
            selected_tickers=[],
            peers=[],
            notes={},
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )
        _store_hot_cached_payload(hot_key, payload)
        return payload

    price_last_checked, price_cache_state = get_company_price_cache_status(session, snapshot.company.id)
    financials = get_company_financials(session, snapshot.company.id)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)
    payload = build_peer_comparison(session, snapshot.company.ticker, selected_tickers=selected_tickers)
    logging.getLogger(__name__).info(
        "TELEMETRY peer_view ticker=%s selected=%s count=%s",
        snapshot.company.ticker,
        selected_tickers,
        len(payload.get("peers") or []) if payload else 0,
    )
    if payload is None:
        empty_payload = CompanyPeersResponse(
            company=None,
            peer_basis="Cached peer universe",
            available_companies=[],
            selected_tickers=[],
            peers=[],
            notes={},
            refresh=refresh,
        )
        _store_hot_cached_payload(hot_key, empty_payload)
        return empty_payload

    response_payload = CompanyPeersResponse(
        company=_serialize_company(
            payload["company"],
            last_checked=_merge_last_checked(payload["company"].last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
        ),
        peer_basis=payload["peer_basis"],
        available_companies=[PeerOptionPayload(**item) for item in payload["available_companies"]],
        selected_tickers=payload["selected_tickers"],
        peers=[PeerMetricsPayload(**item) for item in payload["peers"]],
        notes=payload["notes"],
        refresh=refresh,
    )
    _store_hot_cached_payload(hot_key, response_payload)
    not_modified = _apply_conditional_headers(
        request,
        http_response,
        response_payload,
        last_modified=response_payload.company.last_checked if response_payload.company else None,
    )
    if not_modified is not None:
        return not_modified  # type: ignore[return-value]
    return response_payload


@app.get("/api/companies/{ticker}/filings", response_model=CompanyFilingsResponse)
def company_filings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFilingsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyFilingsResponse(
            company=None,
            filings=[],
            timeline_source="sec_submissions",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)

    cached_filings = _load_filings_from_cache(snapshot.company.cik)
    if cached_filings is not None:
        return CompanyFilingsResponse(
            company=_serialize_company(snapshot, last_checked_filings=_filings_cache_last_checked(cached_filings)),
            filings=cached_filings,
            timeline_source="sec_submissions",
            refresh=refresh,
            error=None,
        )

    client = EdgarClient()
    try:
        submissions = client.get_submissions(snapshot.company.cik)
        filing_index = client.build_filing_index(submissions)
        filings = _serialize_recent_filings(snapshot.company.cik, filing_index)
        _store_filings_in_cache(snapshot.company.cik, filings)
        return CompanyFilingsResponse(
            company=_serialize_company(snapshot, last_checked_filings=_filings_cache_last_checked(filings)),
            filings=filings,
            timeline_source="sec_submissions",
            refresh=refresh,
            error=None,
        )
    except Exception:
        logging.getLogger(__name__).exception("Unable to load SEC filing timeline for '%s'", snapshot.company.ticker)
        _evict_filings_cache(snapshot.company.cik)
        fallback_filings = _serialize_cached_statement_filings(get_company_financials(session, snapshot.company.id))
        return CompanyFilingsResponse(
            company=_serialize_company(snapshot, last_checked_filings=_filings_cache_last_checked(fallback_filings)),
            filings=fallback_filings,
            timeline_source="cached_financials",
            refresh=refresh,
            error=(
                "SEC submissions are temporarily unavailable. Showing cached annual and quarterly filings only."
                if fallback_filings
                else "SEC submissions are temporarily unavailable. Try refreshing again shortly."
            ),
        )
    finally:
        client.close()


@app.get("/api/companies/{ticker}/beneficial-ownership", response_model=CompanyBeneficialOwnershipResponse)
def company_beneficial_ownership(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyBeneficialOwnershipResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyBeneficialOwnershipResponse(
            company=None,
            filings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    cached_reports = get_company_beneficial_ownership_reports(session, snapshot.company.id)
    filings = _enrich_beneficial_ownership_amendment_history(
        [_serialize_cached_beneficial_ownership_report(report) for report in cached_reports]
    )
    return CompanyBeneficialOwnershipResponse(
        company=_serialize_company(snapshot),
        filings=filings,
        refresh=refresh,
        error=None,
    )


@app.get("/api/companies/{ticker}/beneficial-ownership/summary", response_model=CompanyBeneficialOwnershipSummaryResponse)
def company_beneficial_ownership_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyBeneficialOwnershipSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyBeneficialOwnershipSummaryResponse(
            company=None,
            summary=_empty_beneficial_ownership_summary(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    cached_reports = get_company_beneficial_ownership_reports(session, snapshot.company.id)
    filings = _enrich_beneficial_ownership_amendment_history(
        [_serialize_cached_beneficial_ownership_report(report) for report in cached_reports]
    )
    return CompanyBeneficialOwnershipSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_beneficial_ownership_summary(filings),
        refresh=refresh,
        error=None,
    )


@app.get("/api/companies/{ticker}/governance", response_model=CompanyGovernanceResponse)
def company_governance(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyGovernanceResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyGovernanceResponse(
            company=None,
            filings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_governance(background_tasks, session, snapshot)
    cached_proxy = get_company_proxy_statements(session, snapshot.company.id)
    filings = [_serialize_cached_proxy_statement(statement) for statement in cached_proxy]
    if not filings:
        filings = _load_live_governance_filings(snapshot.company.cik)
    return CompanyGovernanceResponse(
        company=_serialize_company(snapshot),
        filings=filings,
        refresh=refresh,
        error=None,
    )


@app.get("/api/companies/{ticker}/governance/summary", response_model=CompanyGovernanceSummaryResponse)
def company_governance_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyGovernanceSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyGovernanceSummaryResponse(
            company=None,
            summary=_empty_governance_summary(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_governance(background_tasks, session, snapshot)
    cached_proxy = get_company_proxy_statements(session, snapshot.company.id)
    filings = [_serialize_cached_proxy_statement(statement) for statement in cached_proxy]
    if not filings:
        filings = _load_live_governance_filings(snapshot.company.cik)
    return CompanyGovernanceSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_governance_summary(filings),
        refresh=refresh,
        error=None,
    )


@app.get("/api/companies/{ticker}/executive-compensation", response_model=CompanyExecutiveCompensationResponse)
def company_executive_compensation(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyExecutiveCompensationResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyExecutiveCompensationResponse(
            company=None,
            rows=[],
            fiscal_years=[],
            source="none",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_governance(background_tasks, session, snapshot)
    cached_rows = get_company_executive_compensation(session, snapshot.company.id)
    source = "cached" if cached_rows else "none"
    if cached_rows:
        serialized = [_serialize_exec_comp_row(row) for row in cached_rows]
    else:
        serialized = _load_live_exec_comp_rows(snapshot.company.cik)
        if serialized:
            source = "live"

    fiscal_years = sorted({row.fiscal_year for row in serialized if row.fiscal_year is not None}, reverse=True)
    return CompanyExecutiveCompensationResponse(
        company=_serialize_company(snapshot),
        rows=serialized,
        fiscal_years=fiscal_years,
        source=source,
        refresh=refresh,
        error=None,
    )


REGISTRATION_FORMS = {
    "S-1", "S-1/A",
    "S-3", "S-3/A",
    "S-4", "S-4/A",
    "F-1", "F-1/A",
    "F-3", "F-3/A",
    "424B1", "424B2", "424B3", "424B4", "424B5",
}

_REGISTRATION_FORM_SUMMARIES: dict[str, str] = {
    "S-1": "Initial registration statement for a domestic IPO or initial public offering.",
    "S-1/A": "Amendment to an S-1 registration statement.",
    "S-3": "Shelf registration statement for eligible domestic issuers.",
    "S-3/A": "Amendment to an S-3 shelf registration.",
    "S-4": "Registration statement for securities issued in business combination transactions.",
    "S-4/A": "Amendment to an S-4 registration statement.",
    "F-1": "Initial registration statement for foreign private issuers.",
    "F-1/A": "Amendment to an F-1 registration statement.",
    "F-3": "Shelf registration for eligible foreign private issuers.",
    "F-3/A": "Amendment to an F-3 registration statement.",
    "424B1": "Prospectus supplement filed under Rule 424(b)(1).",
    "424B2": "Prospectus supplement filed under Rule 424(b)(2).",
    "424B3": "Prospectus supplement filed under Rule 424(b)(3).",
    "424B4": "Prospectus supplement filed under Rule 424(b)(4).",
    "424B5": "Prospectus supplement filed under Rule 424(b)(5).",
}


@app.get("/api/companies/{ticker}/capital-raises", response_model=CompanyCapitalRaisesResponse)
def company_capital_raises(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCapitalRaisesResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyCapitalRaisesResponse(
            company=None,
            filings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    cached_events = get_company_capital_markets_events(session, snapshot.company.id)
    filings = [_serialize_cached_capital_markets_event(event) for event in cached_events]
    return CompanyCapitalRaisesResponse(
        company=_serialize_company(snapshot),
        filings=filings,
        refresh=refresh,
        error=None,
    )


@app.get("/api/companies/{ticker}/capital-markets", response_model=CompanyCapitalRaisesResponse)
def company_capital_markets(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCapitalRaisesResponse:
    return company_capital_raises(ticker=ticker, background_tasks=background_tasks, session=session)


@app.get("/api/companies/{ticker}/capital-markets/summary", response_model=CompanyCapitalMarketsSummaryResponse)
def company_capital_markets_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCapitalMarketsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyCapitalMarketsSummaryResponse(
            company=None,
            summary=_empty_capital_markets_summary(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    rows = [_serialize_cached_capital_markets_event(event) for event in get_company_capital_markets_events(session, snapshot.company.id)]
    return CompanyCapitalMarketsSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_capital_markets_summary(rows),
        refresh=refresh,
        error=None,
    )


@app.get("/api/companies/{ticker}/events", response_model=CompanyEventsResponse)
def company_events(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEventsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEventsResponse(
            company=None,
            events=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    events = [_serialize_cached_filing_event(event) for event in get_company_filing_events(session, snapshot.company.id)]
    return CompanyEventsResponse(
        company=_serialize_company(snapshot),
        events=events,
        refresh=refresh,
        error=None,
    )


@app.get("/api/companies/{ticker}/filing-events", response_model=CompanyEventsResponse)
def company_filing_events(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEventsResponse:
    return company_events(ticker=ticker, background_tasks=background_tasks, session=session)


@app.get("/api/companies/{ticker}/filing-events/summary", response_model=CompanyFilingEventsSummaryResponse)
def company_filing_events_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFilingEventsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyFilingEventsSummaryResponse(
            company=None,
            summary=_empty_filing_events_summary(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    rows = [_serialize_cached_filing_event(event) for event in get_company_filing_events(session, snapshot.company.id)]
    return CompanyFilingEventsSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_filing_events_summary(rows),
        refresh=refresh,
        error=None,
    )


@app.get("/api/companies/{ticker}/activity-feed", response_model=CompanyActivityFeedResponse)
def company_activity_feed(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyActivityFeedResponse:
    overview = _build_company_activity_overview_response(ticker=ticker, background_tasks=background_tasks, session=session)
    return CompanyActivityFeedResponse(
        company=overview.company,
        entries=overview.entries,
        refresh=overview.refresh,
        error=overview.error,
    )


@app.get("/api/companies/{ticker}/alerts", response_model=CompanyAlertsResponse)
def company_alerts(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyAlertsResponse:
    overview = _build_company_activity_overview_response(ticker=ticker, background_tasks=background_tasks, session=session)
    return CompanyAlertsResponse(
        company=overview.company,
        alerts=overview.alerts,
        summary=overview.summary,
        refresh=overview.refresh,
        error=overview.error,
    )


@app.get("/api/companies/{ticker}/activity-overview", response_model=CompanyActivityOverviewResponse)
def company_activity_overview(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyActivityOverviewResponse:
    return _build_company_activity_overview_response(ticker=ticker, background_tasks=background_tasks, session=session)


@app.post("/api/watchlist/summary", response_model=WatchlistSummaryResponse)
def watchlist_summary(
    payload: WatchlistSummaryRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> WatchlistSummaryResponse:
    normalized_tickers = _normalize_watchlist_tickers(payload.tickers)
    if len(normalized_tickers) > 50:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A maximum of 50 tickers is allowed")

    snapshots_by_ticker = get_company_snapshots_by_ticker(session, normalized_tickers)
    coverage_counts = get_company_coverage_counts(
        session,
        [snapshot.company.id for snapshot in snapshots_by_ticker.values()],
    )

    companies: list[WatchlistSummaryItemPayload] = []
    for ticker in normalized_tickers:
        snapshot = snapshots_by_ticker.get(ticker)
        if snapshot is None:
            companies.append(_build_missing_watchlist_summary_item(background_tasks, ticker))
            continue
        try:
            companies.append(
                _build_watchlist_summary_item(
                    session,
                    background_tasks,
                    ticker,
                    snapshot=snapshot,
                    coverage_counts=coverage_counts.get(snapshot.company.id),
                )
            )
        except Exception:
            logging.getLogger(__name__).exception("Unable to build watchlist summary item for '%s'", ticker)
            companies.append(_build_missing_watchlist_summary_item(background_tasks, ticker))
    logging.getLogger(__name__).info(
        "TELEMETRY watchlist_summary tickers=%s companies=%s",
        len(normalized_tickers),
        len(companies),
    )
    return WatchlistSummaryResponse(tickers=normalized_tickers, companies=companies)


@app.get("/api/filings/{ticker}", response_model=list[FilingTimelineItemPayload])
def filings_timeline(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> list[FilingTimelineItemPayload]:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    client = EdgarClient()
    try:
        submissions = client.get_submissions(snapshot.company.cik)
        filing_index = client.build_filing_index(submissions)
        filings = _serialize_recent_filings(snapshot.company.cik, filing_index)
        timeline: list[FilingTimelineItemPayload] = []
        for filing in filings:
            timeline.append(
                FilingTimelineItemPayload(
                    date=filing.filing_date or filing.report_date,
                    form=filing.form,
                    description=_filing_timeline_description(filing),
                    accession=filing.accession_number,
                )
            )
        return timeline
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to load normalized filing timeline for '%s'", snapshot.company.ticker)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to load filings")
    finally:
        client.close()


@app.get("/api/search_filings", response_model=list[FilingSearchResultPayload])
def search_filings(
    q: str = Query(..., min_length=2, max_length=120),
) -> list[FilingSearchResultPayload]:
    client = EdgarClient()
    try:
        response = client._request("GET", settings.sec_search_base_url, params={"q": q})
        payload = response.json()
        hits = ((payload or {}).get("hits") or {}).get("hits") or []
        results: list[FilingSearchResultPayload] = []
        for item in hits:
            parsed = _serialize_search_filing_hit(item)
            if parsed is not None:
                results.append(parsed)
        return results
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to search SEC filings for query '%s'", q)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to search filings")
    finally:
        client.close()


@app.get("/api/companies/{ticker}/financial-history", response_model=CompanyFactsResponse)
def company_financial_history(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> CompanyFactsResponse:
    normalized = _normalize_search_query(ticker)
    resolved_cik = _normalize_cik_query(normalized)
    if resolved_cik:
        cik = resolved_cik
    else:
        snapshot = _resolve_cached_company_snapshot(session, _normalize_ticker(ticker))
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown ticker")
        cik = snapshot.company.cik

    client = EdgarClient()
    try:
        facts = client.get_companyfacts(cik)
        if not isinstance(facts, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unexpected SEC companyfacts payload")
        return CompanyFactsResponse(facts=facts.get("facts", {}))
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to load SEC companyfacts for '%s'", cik)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to load SEC companyfacts")
    finally:
        client.close()


@app.get("/api/companies/{ticker}/filings/view", response_class=HTMLResponse)
def company_filing_view(
    ticker: str,
    source_url: str = Query(..., min_length=1),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown ticker")

    normalized_source_url = source_url.strip()
    if not _is_allowed_sec_embed_url(normalized_source_url):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported filing URL")

    parsed = urlparse(normalized_source_url)
    if parsed.netloc == "data.sec.gov" and parsed.path.endswith(".json"):
        return HTMLResponse(_render_unavailable_filing_view(normalized_source_url))

    client = EdgarClient()
    try:
        payload, content_type = _fetch_sec_document(client, normalized_source_url)
        return HTMLResponse(_build_embedded_filing_html(payload, normalized_source_url, content_type))
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to load SEC filing document for '%s'", normalized_source_url)
        return HTMLResponse(_render_unavailable_filing_view(normalized_source_url), status_code=status.HTTP_502_BAD_GATEWAY)
    finally:
        client.close()


def _refresh_for_snapshot(background_tasks: BackgroundTasks, snapshot: CompanyCacheSnapshot) -> RefreshState:
    if snapshot.cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=snapshot.cache_state)

    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _refresh_for_governance(
    background_tasks: BackgroundTasks,
    session: Session,
    snapshot: CompanyCacheSnapshot,
) -> RefreshState:
    if snapshot.cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=snapshot.cache_state)

    _last_checked, proxy_cache_state = get_company_proxy_cache_status(session, snapshot.company)
    if proxy_cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=proxy_cache_state)

    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _refresh_for_earnings(
    background_tasks: BackgroundTasks,
    snapshot: CompanyCacheSnapshot,
    earnings_cache_state: Literal["fresh", "stale", "missing"],
) -> RefreshState:
    if snapshot.cache_state == "missing":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
    if snapshot.cache_state == "stale":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="stale")
    if earnings_cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=earnings_cache_state)
    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _refresh_for_earnings_workspace(
    background_tasks: BackgroundTasks,
    snapshot: CompanyCacheSnapshot,
    earnings_cache_state: Literal["fresh", "stale", "missing"],
    model_cache_state: Literal["fresh", "stale", "missing"],
) -> RefreshState:
    if snapshot.cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=snapshot.cache_state)
    if earnings_cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=earnings_cache_state)
    if model_cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=model_cache_state)
    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _get_cached_search_response(query: str) -> CompanySearchResponse | None:
    now = time.monotonic()
    with _search_response_cache_lock:
        cached = _search_response_cache.get(query)
        if cached is None:
            return None
        expires_at, payload = cached
        if expires_at <= now:
            _search_response_cache.pop(query, None)
            return None
        return CompanySearchResponse.model_validate(payload)


def _store_cached_search_response(query: str, response: CompanySearchResponse) -> None:
    expires_at = time.monotonic() + SEARCH_RESPONSE_TTL_SECONDS
    with _search_response_cache_lock:
        _search_response_cache[query] = (expires_at, response.model_dump())


def _get_hot_cached_payload(key: str) -> tuple[dict[str, Any], bool] | None:
    now = time.monotonic()
    with _hot_response_cache_lock:
        cached = _hot_response_cache.get(key)
        if cached is None:
            return None

        fresh_until, stale_until, payload = cached
        if now <= stale_until:
            return payload, now <= fresh_until

        _hot_response_cache.pop(key, None)
        return None


def _store_hot_cached_payload(key: str, payload: BaseModel) -> None:
    now = time.monotonic()
    fresh_until = now + settings.hot_response_cache_ttl_seconds
    stale_until = fresh_until + settings.hot_response_cache_stale_ttl_seconds
    with _hot_response_cache_lock:
        _hot_response_cache[key] = (fresh_until, stale_until, payload.model_dump(mode="json"))


def _apply_conditional_headers(
    request: Request,
    response: Response,
    payload: BaseModel,
    *,
    last_modified: datetime | None,
) -> Response | None:
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    etag = f'W/"{hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]}"'
    response.headers["ETag"] = etag

    if last_modified is not None:
        normalized = last_modified if last_modified.tzinfo else last_modified.replace(tzinfo=timezone.utc)
        response.headers["Last-Modified"] = format_datetime(normalized, usegmt=True)

    response.headers["Cache-Control"] = "private, max-age=0, stale-while-revalidate=120"

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=dict(response.headers))

    if last_modified is not None:
        if_modified_since = request.headers.get("if-modified-since")
        if if_modified_since and response.headers.get("Last-Modified") == if_modified_since:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=dict(response.headers))

    return None


def _resolve_cached_company_snapshot(session: Session, ticker: str) -> CompanyCacheSnapshot | None:
    snapshot = get_company_snapshot(session, ticker)
    if snapshot is not None:
        return snapshot

    if not _looks_like_ticker(ticker):
        return None

    client = EdgarClient()
    try:
        identity = client.resolve_company(ticker)
    except ValueError:
        return None
    except Exception:
        logging.getLogger(__name__).exception("Company alias resolution failed for '%s'", ticker)
        return None
    finally:
        client.close()

    return get_company_snapshot_by_cik(session, identity.cik)


def _resolve_canonical_ticker(session: Session, identity: Any) -> str | None:
    snapshot = get_company_snapshot_by_cik(session, identity.cik)
    if snapshot is None:
        return None
    return snapshot.company.ticker


def _refresh_for_financial_page(
    background_tasks: BackgroundTasks,
    snapshot: CompanyCacheSnapshot,
    price_cache_state: Literal["fresh", "stale", "missing"],
    financials: list[FinancialStatement],
) -> RefreshState:
    if snapshot.cache_state == "missing" or price_cache_state == "missing":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
    if snapshot.cache_state == "stale" or price_cache_state == "stale":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="stale")
    if _needs_segment_backfill(financials):
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")

    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _metrics_staleness_reason(
    snapshot: CompanyCacheSnapshot,
    price_cache_state: Literal["fresh", "stale", "missing"],
    financials: list[FinancialStatement],
) -> str:
    if snapshot.cache_state == "missing":
        return "financials_missing"
    if snapshot.cache_state == "stale":
        return "financials_stale"
    if price_cache_state == "missing":
        return "price_missing"
    if price_cache_state == "stale":
        return "price_stale"
    if _needs_segment_backfill(financials):
        return "segment_backfill_missing"
    return "fresh"


def _refresh_for_filing_insights(
    background_tasks: BackgroundTasks,
    snapshot: CompanyCacheSnapshot,
) -> RefreshState:
    if snapshot.cache_state == "missing":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
    if snapshot.cache_state == "stale":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="stale")
    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _trigger_refresh(
    background_tasks: BackgroundTasks,
    ticker: str,
    *,
    reason: Literal["manual", "missing", "stale"],
) -> RefreshState:
    normalized_ticker = _normalize_ticker(ticker)
    job_id = queue_company_refresh(background_tasks, normalized_ticker, force=(reason == "missing"))
    return RefreshState(triggered=True, reason=reason, ticker=normalized_ticker, job_id=job_id)


def _serialize_company(
    snapshot: CompanyCacheSnapshot,
    last_checked: datetime | None = None,
    *,
    last_checked_prices: datetime | None = None,
    last_checked_insiders: datetime | None = None,
    last_checked_institutional: datetime | None = None,
    last_checked_filings: datetime | None = None,
    last_checked_earnings: datetime | None = None,
) -> CompanyPayload:
    return CompanyPayload(
        ticker=snapshot.company.ticker,
        cik=snapshot.company.cik,
        name=snapshot.company.name,
        sector=snapshot.company.sector,
        market_sector=snapshot.company.market_sector,
        market_industry=snapshot.company.market_industry,
        last_checked=last_checked if last_checked is not None else snapshot.last_checked,
        last_checked_financials=snapshot.last_checked,
        last_checked_prices=last_checked_prices,
        last_checked_insiders=last_checked_insiders,
        last_checked_institutional=last_checked_institutional,
        last_checked_filings=last_checked_filings,
        earnings_last_checked=last_checked_earnings,
        cache_state=snapshot.cache_state,
    )


def _serialize_financial(statement: FinancialStatement) -> FinancialPayload:
    data = statement.data or {}
    return FinancialPayload(
        filing_type=statement.filing_type,
        statement_type=statement.statement_type,
        period_start=statement.period_start,
        period_end=statement.period_end,
        source=statement.source,
        last_updated=statement.last_updated,
        last_checked=statement.last_checked,
        revenue=data.get("revenue"),
        gross_profit=data.get("gross_profit"),
        operating_income=data.get("operating_income"),
        net_income=data.get("net_income"),
        total_assets=data.get("total_assets"),
        current_assets=data.get("current_assets"),
        total_liabilities=data.get("total_liabilities"),
        current_liabilities=data.get("current_liabilities"),
        retained_earnings=data.get("retained_earnings"),
        sga=data.get("sga"),
        research_and_development=data.get("research_and_development"),
        interest_expense=data.get("interest_expense"),
        income_tax_expense=data.get("income_tax_expense"),
        inventory=data.get("inventory"),
        cash_and_cash_equivalents=data.get("cash_and_cash_equivalents"),
        short_term_investments=data.get("short_term_investments"),
        cash_and_short_term_investments=data.get("cash_and_short_term_investments"),
        accounts_receivable=data.get("accounts_receivable"),
        accounts_payable=data.get("accounts_payable"),
        goodwill_and_intangibles=data.get("goodwill_and_intangibles"),
        current_debt=data.get("current_debt"),
        long_term_debt=data.get("long_term_debt"),
        stockholders_equity=data.get("stockholders_equity"),
        lease_liabilities=data.get("lease_liabilities"),
        operating_cash_flow=data.get("operating_cash_flow"),
        depreciation_and_amortization=data.get("depreciation_and_amortization"),
        capex=data.get("capex"),
        acquisitions=data.get("acquisitions"),
        debt_changes=data.get("debt_changes"),
        dividends=data.get("dividends"),
        share_buybacks=data.get("share_buybacks"),
        free_cash_flow=data.get("free_cash_flow"),
        eps=data.get("eps"),
        shares_outstanding=data.get("shares_outstanding"),
        stock_based_compensation=data.get("stock_based_compensation"),
        weighted_average_diluted_shares=data.get("weighted_average_diluted_shares"),
        segment_breakdown=[_serialize_financial_segment(item) for item in data.get("segment_breakdown", []) if isinstance(item, dict)],
    )


def _serialize_financial_segment(payload: dict[str, Any]) -> FinancialSegmentPayload:
    return FinancialSegmentPayload(
        segment_id=str(payload.get("segment_id") or payload.get("segment_name") or "unknown"),
        segment_name=str(payload.get("segment_name") or payload.get("segment_id") or "Unknown"),
        axis_key=payload.get("axis_key"),
        axis_label=payload.get("axis_label"),
        kind=payload.get("kind") if payload.get("kind") in {"business", "geographic", "other"} else "other",
        revenue=payload.get("revenue"),
        share_of_revenue=payload.get("share_of_revenue"),
        operating_income=payload.get("operating_income"),
        assets=payload.get("assets"),
    )


def _serialize_filing_parser_segment(payload: dict[str, Any]) -> FilingParserSegmentPayload:
    return FilingParserSegmentPayload(
        name=str(payload.get("name") or payload.get("segment") or payload.get("segment_name") or "Unknown"),
        revenue=payload.get("revenue"),
    )


def _serialize_filing_parser_insight(statement: FinancialStatement) -> FilingParserInsightPayload:
    data = statement.data or {}
    return FilingParserInsightPayload(
        accession_number=_extract_accession_number(statement.source),
        filing_type=statement.filing_type,
        period_start=statement.period_start,
        period_end=statement.period_end,
        source=statement.source,
        last_updated=statement.last_updated,
        last_checked=statement.last_checked,
        revenue=data.get("revenue"),
        net_income=data.get("net_income"),
        operating_income=data.get("operating_income"),
        segments=[
            _serialize_filing_parser_segment(item)
            for item in data.get("segments", [])
            if isinstance(item, dict)
        ],
    )


def _needs_segment_backfill(financials: list[FinancialStatement]) -> bool:
    if not financials:
        return False

    return not any(
        isinstance(statement.data, dict)
        and isinstance(statement.data.get("segment_breakdown"), list)
        and len(statement.data.get("segment_breakdown") or []) > 0
        for statement in financials
    )


def _serialize_price_history(point: PriceHistory) -> PriceHistoryPayload:
    return PriceHistoryPayload(
        date=point.trade_date,
        close=point.close,
        volume=point.volume,
    )


def _serialize_insider_trade(trade: InsiderTrade) -> InsiderTradePayload:
    return InsiderTradePayload(
        name=trade.insider_name,
        role=trade.role,
        date=trade.transaction_date,
        filing_date=trade.filing_date,
        filing_type=trade.filing_type,
        accession_number=trade.accession_number,
        source=trade.source,
        action=trade.action,
        transaction_code=trade.transaction_code,
        shares=trade.shares,
        price=trade.price,
        value=trade.value,
        ownership_after=trade.ownership_after,
        security_title=getattr(trade, "security_title", None),
        is_derivative=getattr(trade, "is_derivative", None),
        ownership_nature=getattr(trade, "ownership_nature", None),
        exercise_price=getattr(trade, "exercise_price", None),
        expiration_date=getattr(trade, "expiration_date", None),
        footnote_tags=getattr(trade, "footnote_tags", None),
        is_10b5_1=trade.is_10b5_1,
    )


def _serialize_form144_filing(filing: Form144Filing) -> Form144FilingPayload:
    return Form144FilingPayload(
        accession_number=filing.accession_number,
        form=filing.form,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        filer_name=filing.filer_name,
        relationship_to_issuer=filing.relationship_to_issuer,
        issuer_name=filing.issuer_name,
        security_title=filing.security_title,
        planned_sale_date=filing.planned_sale_date,
        shares_to_be_sold=filing.shares_to_be_sold,
        aggregate_market_value=filing.aggregate_market_value,
        shares_owned_after_sale=filing.shares_owned_after_sale,
        broker_name=filing.broker_name,
        source_url=filing.source_url,
        summary=filing.summary,
    )


def _serialize_earnings_release(release: EarningsRelease) -> EarningsReleasePayload:
    return EarningsReleasePayload(
        accession_number=release.accession_number,
        form=release.form,
        filing_date=release.filing_date,
        report_date=release.report_date,
        source_url=release.source_url,
        primary_document=release.primary_document,
        exhibit_document=release.exhibit_document,
        exhibit_type=release.exhibit_type,
        reported_period_label=release.reported_period_label,
        reported_period_end=release.reported_period_end,
        revenue=release.revenue,
        operating_income=release.operating_income,
        net_income=release.net_income,
        diluted_eps=release.diluted_eps,
        revenue_guidance_low=release.revenue_guidance_low,
        revenue_guidance_high=release.revenue_guidance_high,
        eps_guidance_low=release.eps_guidance_low,
        eps_guidance_high=release.eps_guidance_high,
        share_repurchase_amount=release.share_repurchase_amount,
        dividend_per_share=release.dividend_per_share,
        highlights=list(release.highlights or []),
        parse_state=release.parse_state,
    )


def _serialize_earnings_model_point(point: EarningsModelPoint) -> EarningsModelPointPayload:
    explainability = dict(point.explainability or {})
    raw_inputs = explainability.get("inputs", [])
    inputs_payload = [
        EarningsModelInputPayload.model_validate(item)
        for item in raw_inputs
        if isinstance(item, dict)
    ]
    explainability_payload = EarningsModelExplainabilityPayload(
        formula_version=str(explainability.get("formula_version") or "sec_earnings_intel_v1"),
        period_end=str(explainability.get("period_end") or point.period_end.isoformat()),
        filing_type=str(explainability.get("filing_type") or point.filing_type),
        inputs=inputs_payload,
        component_values=dict(explainability.get("component_values") or {}),
        proxy_usage=dict(explainability.get("proxy_usage") or {}),
        segment_deltas=list(explainability.get("segment_deltas") or []),
        release_statement_coverage=dict(explainability.get("release_statement_coverage") or {}),
        quality_formula=str(explainability.get("quality_formula") or ""),
        eps_drift_formula=str(explainability.get("eps_drift_formula") or ""),
        momentum_formula=str(explainability.get("momentum_formula") or ""),
    )

    return EarningsModelPointPayload(
        period_start=point.period_start,
        period_end=point.period_end,
        filing_type=point.filing_type,
        quality_score=point.quality_score,
        quality_score_delta=point.quality_score_delta,
        eps_drift=point.eps_drift,
        earnings_momentum_drift=point.earnings_momentum_drift,
        segment_contribution_delta=point.segment_contribution_delta,
        release_statement_coverage_ratio=point.release_statement_coverage_ratio,
        fallback_ratio=point.fallback_ratio,
        stale_period_warning=point.stale_period_warning,
        quality_flags=list(point.quality_flags or []),
        source_statement_ids=[int(value) for value in list(point.source_statement_ids or [])],
        source_release_ids=[int(value) for value in list(point.source_release_ids or [])],
        explainability=explainability_payload,
    )


def _build_earnings_summary(releases: list[EarningsReleasePayload]) -> EarningsSummaryPayload:
    parsed_releases = [release for release in releases if release.parse_state == "parsed"]
    metadata_only_releases = len(releases) - len(parsed_releases)
    guidance_releases = [
        release
        for release in releases
        if any(
            value is not None
            for value in (
                release.revenue_guidance_low,
                release.revenue_guidance_high,
                release.eps_guidance_low,
                release.eps_guidance_high,
            )
        )
    ]
    buyback_releases = [release for release in releases if release.share_repurchase_amount is not None]
    dividend_releases = [release for release in releases if release.dividend_per_share is not None]
    latest = releases[0] if releases else None

    return EarningsSummaryPayload(
        total_releases=len(releases),
        parsed_releases=len(parsed_releases),
        metadata_only_releases=metadata_only_releases,
        releases_with_guidance=len(guidance_releases),
        releases_with_buybacks=len(buyback_releases),
        releases_with_dividends=len(dividend_releases),
        latest_filing_date=latest.filing_date if latest is not None else None,
        latest_report_date=latest.report_date if latest is not None else None,
        latest_reported_period_end=latest.reported_period_end if latest is not None else None,
        latest_revenue=latest.revenue if latest is not None else None,
        latest_operating_income=latest.operating_income if latest is not None else None,
        latest_net_income=latest.net_income if latest is not None else None,
        latest_diluted_eps=latest.diluted_eps if latest is not None else None,
    )


def _serialize_insider_activity_summary(summary) -> InsiderActivitySummaryPayload:
    return InsiderActivitySummaryPayload(
        sentiment=summary.sentiment,
        summary_lines=summary.summary_lines,
        metrics=InsiderActivityMetricsPayload(
            total_buy_value=summary.metrics.total_buy_value,
            total_sell_value=summary.metrics.total_sell_value,
            net_value=summary.metrics.net_value,
            unique_insiders_buying=summary.metrics.unique_insiders_buying,
            unique_insiders_selling=summary.metrics.unique_insiders_selling,
        ),
    )


def _serialize_insider_analytics(analytics) -> InsiderAnalyticsResponse:
    largest_trade_payload = None
    if analytics.largest_trade is not None:
        largest_trade_payload = LargestInsiderTradePayload(
            insider=analytics.largest_trade.insider,
            type=analytics.largest_trade.type,
            value=analytics.largest_trade.value,
            date=analytics.largest_trade.date,
        )

    return InsiderAnalyticsResponse(
        buy_value_30d=analytics.buy_value_30d,
        sell_value_30d=analytics.sell_value_30d,
        buy_sell_ratio=analytics.buy_sell_ratio,
        largest_trade=largest_trade_payload,
        insider_activity_trend=analytics.insider_activity_trend,
    )


def _serialize_ownership_analytics(analytics) -> OwnershipAnalyticsResponse:
    return OwnershipAnalyticsResponse(
        top_holders=[TopHolderPayload(fund=item.fund, shares=item.shares) for item in analytics.top_holders],
        institutional_ownership=analytics.institutional_ownership,
        ownership_concentration=analytics.ownership_concentration,
        quarterly_inflow=analytics.quarterly_inflow,
        quarterly_outflow=analytics.quarterly_outflow,
        new_positions=analytics.new_positions,
        sold_positions=analytics.sold_positions,
        reporting_date=analytics.reporting_date,
    )


def _serialize_institutional_holding(holding) -> InstitutionalHoldingPayload:
    return InstitutionalHoldingPayload(
        fund_name=holding.fund.fund_name,
        fund_cik=getattr(holding.fund, "fund_cik", None),
        fund_manager=getattr(holding.fund, "fund_manager", None),
        manager_query=getattr(holding.fund, "manager_query", None),
        universe_source=getattr(holding.fund, "universe_source", None),
        fund_strategy=get_institutional_fund_strategy(holding.fund.fund_name, getattr(holding.fund, "fund_manager", None)),
        accession_number=holding.accession_number,
        filing_form=getattr(holding, "filing_form", None),
        base_form=getattr(holding, "base_form", None),
        is_amendment=bool(getattr(holding, "is_amendment", False)),
        reporting_date=holding.reporting_date,
        filing_date=holding.filing_date,
        shares_held=holding.shares_held,
        market_value=holding.market_value,
        change_in_shares=holding.change_in_shares,
        percent_change=holding.percent_change,
        portfolio_weight=holding.portfolio_weight,
        put_call=getattr(holding, "put_call", None),
        investment_discretion=getattr(holding, "investment_discretion", None),
        voting_authority_sole=getattr(holding, "voting_authority_sole", None),
        voting_authority_shared=getattr(holding, "voting_authority_shared", None),
        voting_authority_none=getattr(holding, "voting_authority_none", None),
        source=holding.source,
    )


def _build_institutional_holdings_summary(rows: list[InstitutionalHoldingPayload]) -> InstitutionalHoldingsSummaryPayload:
    if not rows:
        return InstitutionalHoldingsSummaryPayload(total_rows=0, unique_managers=0, amended_rows=0, latest_reporting_date=None)

    unique_managers = len({
        (row.fund_cik or "", row.fund_name.strip().lower())
        for row in rows
        if row.fund_name.strip()
    })
    latest_reporting_date = max((row.reporting_date for row in rows), default=None)
    amended_rows = sum(1 for row in rows if row.is_amendment)
    return InstitutionalHoldingsSummaryPayload(
        total_rows=len(rows),
        unique_managers=unique_managers,
        amended_rows=amended_rows,
        latest_reporting_date=latest_reporting_date,
    )


def _serialize_model(model_run: ModelRun) -> ModelPayload:
    return ModelPayload(
        schema_version="2.0",
        model_name=model_run.model_name,
        model_version=model_run.model_version,
        created_at=model_run.created_at,
        input_periods=model_run.input_periods,
        result=model_run.result,
    )


def _serialize_recent_filings(cik: str, filing_index: dict[str, FilingMetadata]) -> list[FilingPayload]:
    filtered = [
        item
        for item in filing_index.values()
        if _is_core_filing_form(item.form)
    ]
    ordered = sorted(
        filtered,
        key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
        reverse=True,
    )
    return [_serialize_filing_metadata(cik, item) for item in ordered[:MAX_FILING_TIMELINE_ITEMS]]


def _serialize_beneficial_ownership_filings(cik: str, filing_index: dict[str, FilingMetadata]) -> list[BeneficialOwnershipFilingPayload]:
    filtered = [item for item in filing_index.values() if _is_beneficial_ownership_form(item.form)]
    ordered = sorted(
        filtered,
        key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
        reverse=True,
    )
    return [_serialize_beneficial_ownership_filing(cik, item) for item in ordered[:MAX_FILING_TIMELINE_ITEMS]]


def _serialize_beneficial_ownership_filing(cik: str, filing: FilingMetadata) -> BeneficialOwnershipFilingPayload:
    form_display = (filing.form or "UNKNOWN").upper()
    base_form = "SC 13D" if form_display.startswith("SC 13D") else "SC 13G"
    is_amendment = form_display.endswith("/A")
    description = _normalize_optional_text(filing.primary_doc_description)
    if description:
        summary = description
    elif base_form == "SC 13D":
        summary = "Beneficial ownership filing showing a major stake disclosure or activist-style amendment."
    else:
        summary = "Beneficial ownership filing showing passive ownership disclosure or amendment."

    return BeneficialOwnershipFilingPayload(
        accession_number=filing.accession_number,
        form=form_display,
        base_form=base_form,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        is_amendment=is_amendment,
        primary_document=_normalize_optional_text(filing.primary_document),
        primary_doc_description=description,
        source_url=_build_filing_document_url(cik, filing.accession_number, filing.primary_document),
        summary=summary,
        parties=[],
        previous_accession_number=None,
    )


def _serialize_cached_beneficial_ownership_report(report) -> BeneficialOwnershipFilingPayload:
    return BeneficialOwnershipFilingPayload(
        accession_number=report.accession_number,
        form=report.form,
        base_form=report.base_form,  # type: ignore[arg-type]
        filing_date=report.filing_date,
        report_date=report.report_date,
        is_amendment=report.is_amendment,
        primary_document=report.primary_document,
        primary_doc_description=report.primary_doc_description,
        source_url=report.source_url,
        summary=report.summary,
        parties=[
            BeneficialOwnershipPartyPayload(
                party_name=party.party_name,
                role=party.role,
                filer_cik=getattr(party, "filer_cik", None),
                shares_owned=getattr(party, "shares_owned", None),
                percent_owned=getattr(party, "percent_owned", None),
                event_date=getattr(party, "event_date", None),
                purpose=getattr(party, "purpose", None),
            )
            for party in report.parties
        ],
        previous_accession_number=getattr(report, "previous_accession_number", None),
        amendment_sequence=getattr(report, "amendment_sequence", None),
        amendment_chain_size=getattr(report, "amendment_chain_size", None),
    )


def _serialize_normalized_beneficial_ownership_report(report) -> BeneficialOwnershipFilingPayload:
    return BeneficialOwnershipFilingPayload(
        accession_number=report.accession_number,
        form=report.form,
        base_form=report.base_form,  # type: ignore[arg-type]
        filing_date=report.filing_date,
        report_date=report.report_date,
        is_amendment=report.is_amendment,
        primary_document=report.primary_document,
        primary_doc_description=report.primary_doc_description,
        source_url=report.source_url,
        summary=report.summary,
        parties=[
            BeneficialOwnershipPartyPayload(
                party_name=party.party_name,
                role=party.role,
                filer_cik=party.filer_cik,
                shares_owned=party.shares_owned,
                percent_owned=party.percent_owned,
                event_date=party.event_date,
                purpose=party.purpose,
            )
            for party in report.parties
        ],
        previous_accession_number=getattr(report, "previous_accession_number", None),
        amendment_sequence=getattr(report, "amendment_sequence", None),
        amendment_chain_size=getattr(report, "amendment_chain_size", None),
    )


def _build_beneficial_ownership_summary(
    filings: list[BeneficialOwnershipFilingPayload],
) -> BeneficialOwnershipSummaryPayload:
    if not filings:
        return _empty_beneficial_ownership_summary()

    _enrich_beneficial_ownership_amendment_history(filings)

    unique_people = {
        party.party_name.strip().lower()
        for filing in filings
        for party in filing.parties
        if party.party_name.strip()
    }
    max_percent = max(
        (party.percent_owned for filing in filings for party in filing.parties if party.percent_owned is not None),
        default=None,
    )
    latest_filing_date = max(
        (filing.filing_date or filing.report_date for filing in filings if filing.filing_date or filing.report_date),
        default=None,
    )
    latest_event_date = max(
        (party.event_date for filing in filings for party in filing.parties if party.event_date is not None),
        default=None,
    )
    amendments = sum(1 for filing in filings if filing.is_amendment)
    chains_with_amendments = len(
        {
            key
            for key, chain in _group_beneficial_ownership_chains(filings).items()
            if len(chain) > 1 and any(item.is_amendment for item in chain)
        }
    )

    amendments_with_delta = sum(
        1
        for filing in filings
        if filing.is_amendment and filing.percent_change_pp is not None
    )
    ownership_increase_events = sum(1 for filing in filings if filing.change_direction == "increase")
    ownership_decrease_events = sum(1 for filing in filings if filing.change_direction == "decrease")
    ownership_unchanged_events = sum(1 for filing in filings if filing.change_direction == "unchanged")

    positive_deltas = [
        filing.percent_change_pp
        for filing in filings
        if filing.percent_change_pp is not None and filing.percent_change_pp > 0
    ]
    negative_deltas = [
        filing.percent_change_pp
        for filing in filings
        if filing.percent_change_pp is not None and filing.percent_change_pp < 0
    ]

    return BeneficialOwnershipSummaryPayload(
        total_filings=len(filings),
        initial_filings=len(filings) - amendments,
        amendments=amendments,
        unique_reporting_persons=len(unique_people),
        latest_filing_date=latest_filing_date,
        latest_event_date=latest_event_date,
        max_reported_percent=max_percent,
        chains_with_amendments=chains_with_amendments,
        amendments_with_delta=amendments_with_delta,
        ownership_increase_events=ownership_increase_events,
        ownership_decrease_events=ownership_decrease_events,
        ownership_unchanged_events=ownership_unchanged_events,
        largest_increase_pp=max(positive_deltas, default=None),
        largest_decrease_pp=min(negative_deltas, default=None),
    )


def _empty_beneficial_ownership_summary() -> BeneficialOwnershipSummaryPayload:
    return BeneficialOwnershipSummaryPayload(
        total_filings=0,
        initial_filings=0,
        amendments=0,
        unique_reporting_persons=0,
        latest_filing_date=None,
        latest_event_date=None,
        max_reported_percent=None,
        chains_with_amendments=0,
        amendments_with_delta=0,
        ownership_increase_events=0,
        ownership_decrease_events=0,
        ownership_unchanged_events=0,
        largest_increase_pp=None,
        largest_decrease_pp=None,
    )


def _group_beneficial_ownership_chains(
    filings: list[BeneficialOwnershipFilingPayload],
) -> dict[str, list[BeneficialOwnershipFilingPayload]]:
    chains: dict[str, list[BeneficialOwnershipFilingPayload]] = {}
    for filing in filings:
        key = _beneficial_ownership_chain_key(filing)
        if key is None:
            continue
        chains.setdefault(key, []).append(filing)

    for chain in chains.values():
        chain.sort(
            key=lambda item: (
                item.filing_date or item.report_date or DateType.min,
                item.accession_number or "",
            )
        )
    return chains


def _beneficial_ownership_chain_key(filing: BeneficialOwnershipFilingPayload) -> str | None:
    for party in filing.parties:
        name = (party.party_name or "").strip().lower()
        if name:
            return f"{filing.base_form}:name:{name}"
        filer_cik = (party.filer_cik or "").strip()
        if filer_cik:
            return f"{filing.base_form}:cik:{filer_cik}"

    accession = (filing.accession_number or "").strip()
    document_token = _beneficial_ownership_document_token(filing.primary_document)
    if document_token:
        return f"{filing.base_form}:doc:{document_token}"
    if accession:
        return f"{filing.base_form}:accession:{accession}"
    return None


def _beneficial_ownership_document_token(primary_document: str | None) -> str | None:
    if not primary_document:
        return None
    stem, _ = os.path.splitext(primary_document)
    normalized = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if len(normalized) < 4:
        return None
    return normalized[:96]


def _beneficial_ownership_primary_percent(filing: BeneficialOwnershipFilingPayload) -> float | None:
    percents = [party.percent_owned for party in filing.parties if party.percent_owned is not None]
    if not percents:
        return None
    return max(float(percent) for percent in percents)


def _enrich_beneficial_ownership_amendment_history(
    filings: list[BeneficialOwnershipFilingPayload],
) -> list[BeneficialOwnershipFilingPayload]:
    if not filings:
        return filings

    filing_by_accession = {
        filing.accession_number: filing
        for filing in filings
        if filing.accession_number
    }

    for filing in filings:
        previous_accession = (filing.previous_accession_number or "").strip() or None
        if not previous_accession:
            continue
        previous_filing = filing_by_accession.get(previous_accession)
        if previous_filing is None:
            continue

        filing.previous_filing_date = previous_filing.filing_date or previous_filing.report_date
        previous_percent = _beneficial_ownership_primary_percent(previous_filing)
        current_percent = _beneficial_ownership_primary_percent(filing)
        filing.previous_percent_owned = previous_percent

        if previous_percent is None or current_percent is None:
            filing.change_direction = filing.change_direction or "unknown"
            continue

        percent_change = current_percent - previous_percent
        filing.percent_change_pp = percent_change

        if percent_change > 0:
            filing.change_direction = "increase"
        elif percent_change < 0:
            filing.change_direction = "decrease"
        else:
            filing.change_direction = "unchanged"

    for chain in _group_beneficial_ownership_chains(filings).values():
        chain_size = len(chain)
        for index, filing in enumerate(chain):
            if filing.amendment_sequence is None:
                filing.amendment_sequence = index + 1
            if filing.amendment_chain_size is None:
                filing.amendment_chain_size = chain_size

            if filing.previous_accession_number:
                continue

            if index == 0:
                filing.change_direction = filing.change_direction or ("unknown" if filing.is_amendment else "new")
                continue

            previous_filing = chain[index - 1]
            filing.previous_accession_number = previous_filing.accession_number
            filing.previous_filing_date = previous_filing.filing_date or previous_filing.report_date
            previous_percent = _beneficial_ownership_primary_percent(previous_filing)
            current_percent = _beneficial_ownership_primary_percent(filing)
            filing.previous_percent_owned = previous_percent

            if previous_percent is None or current_percent is None:
                filing.change_direction = filing.change_direction or "unknown"
                continue

            percent_change = current_percent - previous_percent
            filing.percent_change_pp = percent_change

            if percent_change > 0:
                filing.change_direction = "increase"
            elif percent_change < 0:
                filing.change_direction = "decrease"
            else:
                filing.change_direction = "unchanged"

    return filings


def _serialize_governance_filings(
    cik: str,
    filing_index: dict[str, FilingMetadata],
    client: EdgarClient | None = None,
) -> list[GovernanceFilingPayload]:
    filtered = [item for item in filing_index.values() if _is_governance_form(item.form)]
    ordered = sorted(
        filtered,
        key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
        reverse=True,
    )
    rows: list[GovernanceFilingPayload] = []
    for index, filing in enumerate(ordered[:MAX_FILING_TIMELINE_ITEMS]):
        signals = ProxyFilingSignals()
        if client is not None and filing.primary_document and index < 12:
            try:
                _, payload = client.get_filing_document_text(cik, filing.accession_number, filing.primary_document)
                signals = parse_proxy_filing_signals(payload)
            except Exception:
                signals = ProxyFilingSignals()
        rows.append(_serialize_governance_filing(cik, filing, signals=signals))
    return rows


def _load_live_governance_filings(cik: str) -> list[GovernanceFilingPayload]:
    client = EdgarClient()
    try:
        submissions = client.get_submissions(cik)
        filing_index = client.build_filing_index(submissions)
        return _serialize_governance_filings(cik, filing_index, client=client)
    except Exception:
        logging.getLogger(__name__).exception("Unable to load live governance filings for CIK %s", cik)
        return []
    finally:
        client.close()


def _load_live_exec_comp_rows(cik: str) -> list[ExecCompRowPayload]:
    client = EdgarClient()
    try:
        submissions = client.get_submissions(cik)
        filing_index = client.build_filing_index(submissions)
        filtered = [item for item in filing_index.values() if _is_governance_form(item.form)]
        ordered = sorted(
            filtered,
            key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
            reverse=True,
        )
        rows: list[ExecCompRowPayload] = []
        seen_keys: set[tuple[str, int | None]] = set()
        for filing in ordered[:12]:
            if not filing.primary_document:
                continue
            try:
                _source, payload = client.get_filing_document_text(cik, filing.accession_number, filing.primary_document)
                signals = parse_proxy_filing_signals(payload)
            except Exception:
                continue

            for row in signals.named_exec_rows:
                key = (row.executive_name.strip().lower(), row.fiscal_year)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rows.append(_serialize_exec_comp_row_from_signals(row))

        rows.sort(key=lambda item: (item.fiscal_year or 0, item.total_compensation or 0), reverse=True)
        return rows
    except Exception:
        logging.getLogger(__name__).exception("Unable to load live executive compensation rows for CIK %s", cik)
        return []
    finally:
        client.close()


def _serialize_governance_filing(
    cik: str,
    filing: FilingMetadata,
    *,
    signals: ProxyFilingSignals | None = None,
) -> GovernanceFilingPayload:
    resolved_signals = signals or ProxyFilingSignals()
    form_display = (filing.form or "UNKNOWN").upper()
    description = _normalize_optional_text(filing.primary_doc_description)
    if description:
        summary = description
    elif form_display == "DEF 14A":
        summary = _governance_summary_line(form_display, resolved_signals)
    else:
        summary = _governance_summary_line(form_display, resolved_signals)

    return GovernanceFilingPayload(
        accession_number=filing.accession_number,
        form=form_display,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        primary_document=_normalize_optional_text(filing.primary_document),
        primary_doc_description=description,
        source_url=_build_filing_document_url(cik, filing.accession_number, filing.primary_document),
        summary=summary,
        meeting_date=resolved_signals.meeting_date,
        executive_comp_table_detected=resolved_signals.executive_comp_table_detected,
        vote_item_count=resolved_signals.vote_item_count,
        board_nominee_count=resolved_signals.board_nominee_count,
        key_amounts=list(resolved_signals.key_amounts),
        vote_outcomes=[
            GovernanceVoteOutcomePayload(
                proposal_number=item.proposal_number,
                title=item.title,
                for_votes=item.for_votes,
                against_votes=item.against_votes,
                abstain_votes=item.abstain_votes,
                broker_non_votes=item.broker_non_votes,
            )
            for item in resolved_signals.vote_outcomes
        ],
    )


def _governance_summary_line(form_display: str, signals: ProxyFilingSignals) -> str:
    segments: list[str] = []
    if form_display == "DEF 14A":
        segments.append("Definitive proxy statement")
    else:
        segments.append("Additional proxy material")

    if signals.meeting_date is not None:
        segments.append(f"meeting date {signals.meeting_date.isoformat()}")
    if signals.vote_item_count > 0:
        segments.append(f"{signals.vote_item_count} proposal items detected")
    if signals.executive_comp_table_detected:
        segments.append("executive compensation table detected")

    return "; ".join(segments) + "."


def _serialize_exec_comp_row(db_row: ExecutiveCompensation) -> ExecCompRowPayload:
    """Serialize a cached ExecutiveCompensation ORM row to the API payload."""
    return ExecCompRowPayload(
        executive_name=db_row.executive_name,
        executive_title=db_row.executive_title,
        fiscal_year=db_row.fiscal_year,
        salary=db_row.salary,
        bonus=db_row.bonus,
        stock_awards=db_row.stock_awards,
        option_awards=db_row.option_awards,
        non_equity_incentive=db_row.non_equity_incentive,
        other_compensation=db_row.other_compensation,
        total_compensation=db_row.total_compensation,
    )


def _serialize_exec_comp_row_from_signals(row: ExecCompRow) -> ExecCompRowPayload:
    """Serialize an ExecCompRow dataclass (live-parsed) to the API payload."""
    return ExecCompRowPayload(
        executive_name=row.executive_name,
        executive_title=row.executive_title,
        fiscal_year=row.fiscal_year,
        salary=row.salary,
        bonus=row.bonus,
        stock_awards=row.stock_awards,
        option_awards=row.option_awards,
        non_equity_incentive=row.non_equity_incentive,
        other_compensation=row.other_compensation,
        total_compensation=row.total_compensation,
    )


def _build_governance_summary(filings: list[GovernanceFilingPayload]) -> GovernanceSummaryPayload:
    if not filings:
        return _empty_governance_summary()

    definitive = sum(1 for filing in filings if filing.form == "DEF 14A")
    filings_with_meeting = sum(1 for filing in filings if filing.meeting_date is not None)
    filings_with_comp = sum(1 for filing in filings if filing.executive_comp_table_detected)
    filings_with_votes = sum(1 for filing in filings if filing.vote_item_count > 0)
    latest_meeting_date = max((filing.meeting_date for filing in filings if filing.meeting_date is not None), default=None)
    max_vote_items = max((filing.vote_item_count for filing in filings), default=0)

    return GovernanceSummaryPayload(
        total_filings=len(filings),
        definitive_proxies=definitive,
        supplemental_proxies=len(filings) - definitive,
        filings_with_meeting_date=filings_with_meeting,
        filings_with_exec_comp=filings_with_comp,
        filings_with_vote_items=filings_with_votes,
        latest_meeting_date=latest_meeting_date,
        max_vote_item_count=max_vote_items,
    )


def _empty_governance_summary() -> GovernanceSummaryPayload:
    return GovernanceSummaryPayload(
        total_filings=0,
        definitive_proxies=0,
        supplemental_proxies=0,
        filings_with_meeting_date=0,
        filings_with_exec_comp=0,
        filings_with_vote_items=0,
        latest_meeting_date=None,
        max_vote_item_count=0,
    )


def _serialize_filing_events(cik: str, filing_index: dict[str, FilingMetadata]) -> list[FilingEventPayload]:
    filtered = [item for item in filing_index.values() if _is_event_form(item.form)]
    ordered = sorted(
        filtered,
        key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
        reverse=True,
    )
    return [_serialize_filing_event(cik, item) for item in ordered[:MAX_FILING_TIMELINE_ITEMS]]


def _serialize_filing_event(cik: str, filing: FilingMetadata) -> FilingEventPayload:
    items = _normalize_optional_text(filing.items)
    description = _normalize_optional_text(filing.primary_doc_description)
    category = _classify_filing_event(items, description)
    if description:
        summary = description
    elif items:
        summary = f"Current report covering Item(s) {items}."
    else:
        summary = "Current report with event-driven disclosure."

    return FilingEventPayload(
        accession_number=filing.accession_number,
        form=(filing.form or "UNKNOWN").upper(),
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        items=items,
        item_code=None,
        category=category,
        primary_document=_normalize_optional_text(filing.primary_document),
        primary_doc_description=description,
        source_url=_build_filing_document_url(cik, filing.accession_number, filing.primary_document),
        summary=summary,
        key_amounts=[],
        exhibit_references=[],
    )


def _serialize_cached_filing_event(event) -> FilingEventPayload:
    return FilingEventPayload(
        accession_number=event.accession_number,
        form=event.form,
        filing_date=event.filing_date,
        report_date=event.report_date,
        items=event.items,
        item_code=event.item_code,
        category=event.category,
        primary_document=event.primary_document,
        primary_doc_description=event.primary_doc_description,
        source_url=event.source_url,
        summary=event.summary,
        key_amounts=[float(value) for value in (event.key_amounts or [])],
        exhibit_references=[str(value) for value in (getattr(event, "exhibit_references", []) or [])],
    )


def _serialize_normalized_filing_event(event) -> FilingEventPayload:
    return FilingEventPayload(
        accession_number=event.accession_number,
        form=event.form,
        filing_date=event.filing_date,
        report_date=event.report_date,
        items=event.items,
        item_code=event.item_code,
        category=event.category,
        primary_document=event.primary_document,
        primary_doc_description=event.primary_doc_description,
        source_url=event.source_url,
        summary=event.summary,
        key_amounts=list(event.key_amounts),
        exhibit_references=list(event.exhibit_references),
    )


def _build_filing_events_summary(events: list[FilingEventPayload]) -> FilingEventsSummaryPayload:
    if not events:
        return _empty_filing_events_summary()

    categories: dict[str, int] = {}
    for event in events:
        categories[event.category] = categories.get(event.category, 0) + 1

    latest_event_date = max(
        (event.filing_date or event.report_date for event in events if event.filing_date or event.report_date),
        default=None,
    )
    max_key_amount = max(
        (amount for event in events for amount in event.key_amounts),
        default=None,
    )
    unique_accessions = len({event.accession_number for event in events if event.accession_number})

    return FilingEventsSummaryPayload(
        total_events=len(events),
        unique_accessions=unique_accessions,
        categories=categories,
        latest_event_date=latest_event_date,
        max_key_amount=max_key_amount,
    )


def _empty_filing_events_summary() -> FilingEventsSummaryPayload:
    return FilingEventsSummaryPayload(
        total_events=0,
        unique_accessions=0,
        categories={},
        latest_event_date=None,
        max_key_amount=None,
    )


def _serialize_filing_metadata(cik: str, filing: FilingMetadata) -> FilingPayload:
    source_url = _build_filing_document_url(cik, filing.accession_number, filing.primary_document)
    form_display = (filing.form or "UNKNOWN").upper()
    return FilingPayload(
        accession_number=filing.accession_number,
        form=form_display,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        primary_document=_normalize_optional_text(filing.primary_document),
        primary_doc_description=_normalize_optional_text(filing.primary_doc_description),
        items=_normalize_optional_text(filing.items),
        source_url=source_url,
    )


def _filing_timeline_description(filing: FilingPayload) -> str:
    explicit = _normalize_optional_text(filing.primary_doc_description)
    if explicit:
        return explicit

    items = _normalize_optional_text(filing.items)
    if filing.form == "8-K":
        if items:
            return f"Current report (Items {items})"
        return "Current report"
    if filing.form == "10-K":
        return "Annual report"
    if filing.form == "10-Q":
        return "Quarterly report"
    if items:
        return f"SEC filing (Items {items})"
    return "SEC filing"


def _serialize_search_filing_hit(hit: dict[str, Any]) -> FilingSearchResultPayload | None:
    source = hit.get("_source") if isinstance(hit, dict) else None
    if not isinstance(source, dict):
        return None

    form = str(source.get("form") or "").strip().upper()
    if not form:
        return None

    display_names = source.get("display_names")
    company = ""
    if isinstance(display_names, list) and display_names:
        company = str(display_names[0] or "").strip()
    if not company:
        company = str(source.get("entityName") or source.get("companyName") or "").strip()
    if not company:
        company = "Unknown"

    filing_date = _parse_date(source.get("filed") or source.get("filedAt") or source.get("filingDate"))
    filing_link = _resolve_search_filing_link(source)
    if not filing_link:
        return None

    return FilingSearchResultPayload(
        form=form,
        company=company,
        filing_date=filing_date,
        filing_link=filing_link,
    )


def _resolve_search_filing_link(source: dict[str, Any]) -> str | None:
    for key in ("link", "url", "filingHref", "filingLink", "html_url"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    adsh = str(source.get("adsh") or source.get("accessionNumber") or "").strip()
    ciks = source.get("ciks")
    cik = ""
    if isinstance(ciks, list) and ciks:
        cik = str(ciks[0] or "").strip()
    if not cik:
        cik = str(source.get("cik") or "").strip()

    accession = adsh.replace("-", "")
    if cik.isdigit() and accession.isdigit() and adsh:
        numeric_cik = str(int(cik))
        return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession}/"

    return None


def _filings_cache_last_checked(filings: list[FilingPayload]) -> datetime | None:
    dates = [filing.filing_date for filing in filings if filing.filing_date is not None]
    if not dates:
        return None
    return datetime.combine(max(dates), datetime.min.time(), tzinfo=timezone.utc)


def _serialize_cached_statement_filings(financials: list[FinancialStatement]) -> list[FilingPayload]:
    timeline: list[FilingPayload] = []
    seen_keys: set[tuple[str, str, DateType]] = set()

    for statement in financials:
        form = (statement.filing_type or "").upper()
        if not _is_core_filing_form(form):
            continue
        dedupe_key = (form, statement.source, statement.period_end)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        timeline.append(
            FilingPayload(
                accession_number=_extract_accession_number(statement.source),
                form=form,
                filing_date=None,
                report_date=statement.period_end,
                primary_document=_extract_primary_document_name(statement.source),
                primary_doc_description=None,
                items=None,
                source_url=statement.source,
            )
        )

    return sorted(
        timeline,
        key=lambda item: (item.report_date or DateType.min, item.form, item.accession_number or ""),
        reverse=True,
    )[:MAX_FILING_TIMELINE_ITEMS]


def _build_filing_document_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    accession_compact = accession_number.replace("-", "")
    numeric_cik = str(int(cik))
    if primary_document:
        return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}/{primary_document}"
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json#accn={accession_number}"


def _is_beneficial_ownership_form(form: str | None) -> bool:
    normalized = (form or "").upper()
    return normalized in {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}


def _is_registration_form(form: str | None) -> bool:
    return (form or "").upper() in REGISTRATION_FORMS


def _serialize_capital_raise_filings(
    cik: str, filing_index: dict[str, FilingMetadata]
) -> list[CapitalRaisePayload]:
    filtered = [item for item in filing_index.values() if _is_registration_form(item.form)]
    ordered = sorted(
        filtered,
        key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
        reverse=True,
    )
    results: list[CapitalRaisePayload] = []
    for item in ordered[:MAX_FILING_TIMELINE_ITEMS]:
        form_display = (item.form or "UNKNOWN").upper()
        description = _normalize_optional_text(item.primary_doc_description)
        summary = description or _REGISTRATION_FORM_SUMMARIES.get(form_display, "Registration or prospectus filing.")
        results.append(
            CapitalRaisePayload(
                accession_number=item.accession_number,
                form=form_display,
                filing_date=item.filing_date,
                report_date=item.report_date,
                primary_document=_normalize_optional_text(item.primary_document),
                primary_doc_description=description,
                source_url=_build_filing_document_url(cik, item.accession_number, item.primary_document),
                summary=summary,
                event_type=None,
                security_type=None,
                offering_amount=None,
                shelf_size=None,
                is_late_filer=False,
            )
        )
    return results


def _serialize_cached_capital_markets_event(event) -> CapitalRaisePayload:
    return CapitalRaisePayload(
        accession_number=event.accession_number,
        form=event.form,
        filing_date=event.filing_date,
        report_date=event.report_date,
        primary_document=event.primary_document,
        primary_doc_description=event.primary_doc_description,
        source_url=event.source_url,
        summary=event.summary,
        event_type=event.event_type,
        security_type=event.security_type,
        offering_amount=event.offering_amount,
        shelf_size=event.shelf_size,
        is_late_filer=event.is_late_filer,
    )


def _serialize_normalized_capital_markets_event(event) -> CapitalRaisePayload:
    return CapitalRaisePayload(
        accession_number=event.accession_number,
        form=event.form,
        filing_date=event.filing_date,
        report_date=event.report_date,
        primary_document=event.primary_document,
        primary_doc_description=event.primary_doc_description,
        source_url=event.source_url,
        summary=event.summary,
        event_type=event.event_type,
        security_type=event.security_type,
        offering_amount=event.offering_amount,
        shelf_size=event.shelf_size,
        is_late_filer=event.is_late_filer,
    )


def _build_capital_markets_summary(filings: list[CapitalRaisePayload]) -> CapitalMarketsSummaryPayload:
    if not filings:
        return _empty_capital_markets_summary()

    latest_filing_date = max(
        (filing.filing_date or filing.report_date for filing in filings if filing.filing_date or filing.report_date),
        default=None,
    )
    max_offering_amount = max((filing.offering_amount for filing in filings if filing.offering_amount is not None), default=None)

    return CapitalMarketsSummaryPayload(
        total_filings=len(filings),
        late_filer_notices=sum(1 for filing in filings if filing.is_late_filer),
        registration_filings=sum(1 for filing in filings if filing.event_type == "Registration"),
        prospectus_filings=sum(1 for filing in filings if filing.event_type == "Prospectus"),
        latest_filing_date=latest_filing_date,
        max_offering_amount=max_offering_amount,
    )


def _empty_capital_markets_summary() -> CapitalMarketsSummaryPayload:
    return CapitalMarketsSummaryPayload(
        total_filings=0,
        late_filer_notices=0,
        registration_filings=0,
        prospectus_filings=0,
        latest_filing_date=None,
        max_offering_amount=None,
    )


def _build_company_activity_overview_response(
    *,
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session,
) -> CompanyActivityOverviewResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyActivityOverviewResponse(
            company=None,
            entries=[],
            alerts=[],
            summary=AlertsSummaryPayload(total=0, high=0, medium=0, low=0),
            market_context_status=get_cached_market_context_status(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    activity = _load_company_activity_data(session, snapshot)
    entries = _build_activity_feed_entries(
        filings=activity["filings"],
        filing_events=activity["filing_events"],
        governance_filings=activity["governance_filings"],
        beneficial_filings=activity["beneficial_filings"],
        insider_trades=activity["insider_trades"],
        form144_filings=activity["form144_filings"],
        institutional_holdings=activity["institutional_holdings"],
    )
    alerts = _build_activity_alerts(
        beneficial_filings=activity["beneficial_filings"],
        capital_filings=activity["capital_filings"],
        insider_trades=activity["insider_trades"],
        institutional_holdings=activity["institutional_holdings"],
    )
    return CompanyActivityOverviewResponse(
        company=_serialize_company(snapshot),
        entries=entries,
        alerts=alerts,
        summary=_build_alerts_summary(alerts),
        market_context_status=get_cached_market_context_status(),
        refresh=refresh,
        error=None,
    )


def _build_alerts_summary(alerts: list[AlertPayload]) -> AlertsSummaryPayload:
    return AlertsSummaryPayload(
        total=len(alerts),
        high=sum(1 for alert in alerts if alert.level == "high"),
        medium=sum(1 for alert in alerts if alert.level == "medium"),
        low=sum(1 for alert in alerts if alert.level == "low"),
    )


def _load_company_activity_data(session: Session, snapshot: CompanyCacheSnapshot, *, compact: bool = False) -> dict[str, Any]:
    cached_filings = _load_filings_from_cache(snapshot.company.cik)
    fallback_filings = _serialize_cached_statement_filings(get_company_financials(session, snapshot.company.id))
    filings = cached_filings if cached_filings is not None else fallback_filings
    if compact:
        filings = filings[:24]

    filing_events = [
        _serialize_cached_filing_event(event)
        for event in get_company_filing_events(session, snapshot.company.id, limit=80 if compact else 300)
    ]
    beneficial_filings = [
        _serialize_cached_beneficial_ownership_report(report)
        for report in get_company_beneficial_ownership_reports(session, snapshot.company.id, limit=80 if compact else 200)
    ]
    insider_trades = [_serialize_insider_trade(trade) for trade in get_company_insider_trades(session, snapshot.company.id, limit=80 if compact else 200)]
    form144_filings = [_serialize_form144_filing(filing) for filing in get_company_form144_filings(session, snapshot.company.id, limit=80 if compact else 200)]
    institutional_holdings = [
        _serialize_institutional_holding(holding)
        for holding in get_company_institutional_holdings(session, snapshot.company.id, limit=80 if compact else 200)
    ]
    capital_filings = [
        _serialize_cached_capital_markets_event(event)
        for event in get_company_capital_markets_events(session, snapshot.company.id, limit=80 if compact else 200)
    ]
    governance_filings = [
        _serialize_cached_proxy_statement(statement)
        for statement in get_company_proxy_statements(session, snapshot.company.id, limit=40 if compact else 60)
    ]

    return {
        "filings": filings,
        "filing_events": filing_events,
        "governance_filings": governance_filings,
        "beneficial_filings": beneficial_filings,
        "insider_trades": insider_trades,
        "form144_filings": form144_filings,
        "institutional_holdings": institutional_holdings,
        "capital_filings": capital_filings,
    }


def _serialize_cached_proxy_statement(statement: ProxyStatement) -> GovernanceFilingPayload:
    return GovernanceFilingPayload(
        accession_number=statement.accession_number,
        form=statement.form,
        filing_date=statement.filing_date,
        report_date=statement.report_date,
        primary_document=statement.primary_document,
        primary_doc_description=None,
        source_url=statement.source_url,
        summary=_governance_summary_line(statement.form, _proxy_statement_signals(statement)),
        meeting_date=statement.meeting_date,
        executive_comp_table_detected=bool(statement.executive_comp_table_detected),
        vote_item_count=statement.vote_item_count,
        board_nominee_count=statement.board_nominee_count,
        key_amounts=[],
        vote_outcomes=[
            GovernanceVoteOutcomePayload(
                proposal_number=item.proposal_number,
                title=item.title,
                for_votes=item.for_votes,
                against_votes=item.against_votes,
                abstain_votes=item.abstain_votes,
                broker_non_votes=item.broker_non_votes,
            )
            for item in statement.vote_results
        ],
    )


def _proxy_statement_signals(statement: ProxyStatement) -> ProxyFilingSignals:
    return ProxyFilingSignals(
        meeting_date=statement.meeting_date,
        executive_comp_table_detected=bool(statement.executive_comp_table_detected),
        vote_item_count=statement.vote_item_count,
        board_nominee_count=statement.board_nominee_count,
        key_amounts=(),
        vote_outcomes=(),
        named_exec_rows=(),
    )


def _build_activity_feed_entries(
    *,
    filings: list[FilingPayload],
    filing_events: list[FilingEventPayload],
    governance_filings: list[GovernanceFilingPayload],
    beneficial_filings: list[BeneficialOwnershipFilingPayload],
    insider_trades: list[InsiderTradePayload],
    form144_filings: list[Form144FilingPayload],
    institutional_holdings: list[InstitutionalHoldingPayload],
) -> list[ActivityFeedEntryPayload]:
    entries: list[ActivityFeedEntryPayload] = []

    for filing in filings[:40]:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"filing-{filing.accession_number or filing.source_url}",
                date=filing.filing_date or filing.report_date,
                type="filing",
                badge=filing.form,
                title=_filing_timeline_description(filing),
                detail=filing.accession_number or "SEC filing",
                href=filing.source_url,
            )
        )

    for event in filing_events:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"event-{event.accession_number or event.source_url}-{event.item_code or 'na'}",
                date=event.filing_date or event.report_date,
                type="event",
                badge=event.category,
                title=event.summary,
                detail=f"{event.form}{f' - Items {event.items}' if event.items else ''}",
                href=event.source_url,
            )
        )

    for filing in governance_filings:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"governance-{filing.accession_number or filing.source_url}",
                date=filing.filing_date or filing.report_date,
                type="governance",
                badge=filing.form,
                title=filing.summary,
                detail=filing.accession_number or "Proxy filing",
                href=filing.source_url,
            )
        )

    for filing in beneficial_filings:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"ownership-{filing.accession_number or filing.source_url}",
                date=filing.filing_date or filing.report_date,
                type="ownership-change",
                badge=filing.form,
                title=filing.summary,
                detail="Amendment" if filing.is_amendment else "Initial stake disclosure",
                href=filing.source_url,
            )
        )

    for trade in insider_trades[:40]:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"insider-{trade.accession_number or f'{trade.name}-{trade.date}'}",
                date=trade.filing_date or trade.date,
                type="insider",
                badge=trade.action,
                title=f"{trade.name} {trade.action.lower()} activity",
                detail=f"{trade.role or 'Insider'}{f' - ${trade.value:,.0f}' if trade.value is not None else ''}",
                href=trade.source,
            )
        )

    for filing in form144_filings[:40]:
        title = "Form 144 planned sale filing"
        if filing.filer_name:
            title = f"{filing.filer_name} filed Form 144 planned sale"
        entries.append(
            ActivityFeedEntryPayload(
                id=f"form144-{filing.accession_number or filing.source_url}",
                date=filing.filing_date or filing.planned_sale_date or filing.report_date,
                type="form144",
                badge="144",
                title=title,
                detail=_build_form144_feed_detail(filing),
                href=filing.source_url,
            )
        )

    for holding in institutional_holdings[:40]:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"institutional-{holding.accession_number or f'{holding.fund_name}-{holding.reporting_date}'}",
                date=holding.filing_date or holding.reporting_date,
                type="institutional",
                badge=holding.base_form or holding.filing_form or "13F",
                title=f"{holding.fund_name} updated holdings",
                detail=(
                    f"{holding.shares_held:,.0f} shares"
                    if holding.shares_held is not None
                    else "Tracked 13F position"
                ),
                href=holding.source,
            )
        )

    entries.sort(
        key=lambda item: (
            item.date or DateType.min,
            item.id,
        ),
        reverse=True,
    )
    return entries[:220]


def _build_form144_feed_detail(filing: Form144FilingPayload) -> str:
    detail_parts: list[str] = []

    if filing.planned_sale_date is not None:
        detail_parts.append(f"Planned sale {filing.planned_sale_date.isoformat()}")
    if filing.filer_name:
        detail_parts.append(filing.filer_name)
    if filing.shares_to_be_sold is not None:
        detail_parts.append(f"{filing.shares_to_be_sold:,.0f} shares")
    if filing.aggregate_market_value is not None:
        detail_parts.append(f"${filing.aggregate_market_value:,.0f}")

    if detail_parts:
        return " | ".join(detail_parts)
    if filing.summary:
        return filing.summary
    return "Planned insider sale filing"


def _build_activity_alerts(
    *,
    beneficial_filings: list[BeneficialOwnershipFilingPayload],
    capital_filings: list[CapitalRaisePayload],
    insider_trades: list[InsiderTradePayload],
    institutional_holdings: list[InstitutionalHoldingPayload],
) -> list[AlertPayload]:
    alerts: list[AlertPayload] = []

    for filing in beneficial_filings[:30]:
        max_percent = max((party.percent_owned for party in filing.parties if party.percent_owned is not None), default=None)
        if max_percent is not None and max_percent >= 5:
            alerts.append(
                AlertPayload(
                    id=f"alert-activist-{filing.accession_number or filing.source_url}",
                    level="high" if max_percent >= 10 else "medium",
                    title="Large beneficial ownership stake reported",
                    detail=f"{filing.form} reported up to {max_percent:.2f}% beneficial ownership.",
                    source="beneficial-ownership",
                    date=filing.filing_date or filing.report_date,
                    href=filing.source_url,
                )
            )

    for filing in capital_filings[:40]:
        if filing.is_late_filer:
            alerts.append(
                AlertPayload(
                    id=f"alert-late-{filing.accession_number or filing.source_url}",
                    level="high",
                    title="Late filer notice",
                    detail=f"{filing.form} indicates a delayed periodic filing.",
                    source="capital-markets",
                    date=filing.filing_date or filing.report_date,
                    href=filing.source_url,
                )
            )
            continue

        if filing.event_type in {"Registration", "Prospectus"}:
            size_hint = filing.offering_amount or filing.shelf_size
            detail = "New financing-related filing detected."
            if size_hint is not None:
                detail = f"Potential financing of approximately ${size_hint:,.0f}."
            alerts.append(
                AlertPayload(
                    id=f"alert-financing-{filing.accession_number or filing.source_url}",
                    level="medium",
                    title="Potential dilution or financing activity",
                    detail=detail,
                    source="capital-markets",
                    date=filing.filing_date or filing.report_date,
                    href=filing.source_url,
                )
            )

    recent_buys = sum(1 for trade in insider_trades[:120] if (trade.action or "").upper() == "BUY")
    recent_sells = sum(1 for trade in insider_trades[:120] if (trade.action or "").upper() == "SELL")
    if recent_buys == 0 and recent_sells > 0:
        alerts.append(
            AlertPayload(
                id="alert-insider-buy-drought",
                level="medium",
                title="Insider buying drought",
                detail="Recent filings show sells without offsetting insider buys.",
                source="insider-trades",
                date=max((trade.filing_date or trade.date for trade in insider_trades if trade.filing_date or trade.date), default=None),
                href=None,
            )
        )

    for holding in institutional_holdings[:80]:
        if holding.percent_change is not None and holding.percent_change <= -20:
            alerts.append(
                AlertPayload(
                    id=f"alert-inst-exit-{holding.accession_number or f'{holding.fund_name}-{holding.reporting_date}'}",
                    level="medium",
                    title="Large institutional position reduction",
                    detail=f"{holding.fund_name} reported a {holding.percent_change:.2f}% position change.",
                    source="institutional-holdings",
                    date=holding.filing_date or holding.reporting_date,
                    href=holding.source,
                )
            )

    alerts.sort(
        key=lambda item: (
            0 if item.level == "high" else 1 if item.level == "medium" else 2,
            -(item.date.toordinal() if item.date else 0),
            item.id,
        )
    )
    return alerts[:30]


def _normalize_watchlist_tickers(raw_tickers: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_ticker in raw_tickers:
        ticker = _normalize_ticker(raw_ticker or "")
        if not ticker:
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        normalized.append(ticker)
    return normalized


def _build_watchlist_summary_item(
    session: Session,
    background_tasks: BackgroundTasks,
    ticker: str,
    *,
    snapshot: CompanyCacheSnapshot | None = None,
    coverage_counts: dict[str, int] | None = None,
) -> WatchlistSummaryItemPayload:
    snapshot = snapshot or _resolve_cached_company_snapshot(session, ticker)
    if snapshot is None:
        return _build_missing_watchlist_summary_item(background_tasks, ticker)

    refresh = _refresh_for_snapshot(background_tasks, snapshot)

    financial_periods = int((coverage_counts or {}).get("financial_periods", 0))
    price_points = int((coverage_counts or {}).get("price_points", 0))

    alerts: list[AlertPayload] = []
    entries: list[ActivityFeedEntryPayload] = []
    try:
        activity = _load_company_activity_data(session, snapshot, compact=True)
        alerts = _build_activity_alerts(
            beneficial_filings=activity["beneficial_filings"],
            capital_filings=activity["capital_filings"],
            insider_trades=activity["insider_trades"],
            institutional_holdings=activity["institutional_holdings"],
        )
        entries = _build_activity_feed_entries(
            filings=activity["filings"],
            filing_events=activity["filing_events"],
            governance_filings=activity["governance_filings"],
            beneficial_filings=activity["beneficial_filings"],
            insider_trades=activity["insider_trades"],
            form144_filings=activity["form144_filings"],
            institutional_holdings=activity["institutional_holdings"],
        )
    except Exception:
        logging.getLogger(__name__).exception("Unable to load watchlist activity summary for '%s'", snapshot.company.ticker)

    alert_summary = _build_alerts_summary(alerts)

    latest_alert = alerts[0] if alerts else None
    latest_activity = entries[0] if entries else None

    models: dict[str, ModelRun] = {}
    latest_price = None
    try:
        models = {
            model.model_name.lower(): model
            for model in get_company_models(
                session,
                snapshot.company.id,
                model_names=["dcf", "roic", "reverse_dcf", "capital_allocation", "ratios"],
            )
        }
        latest_price_series = get_company_price_history(session, snapshot.company.id)
        latest_price = latest_price_series[-1].close if latest_price_series else None
    except Exception:
        logging.getLogger(__name__).exception("Unable to load watchlist model metrics for '%s'", snapshot.company.ticker)

    dcf_result = models.get("dcf").result if models.get("dcf") is not None and isinstance(models.get("dcf").result, dict) else {}
    roic_result = models.get("roic").result if models.get("roic") is not None and isinstance(models.get("roic").result, dict) else {}
    reverse_result = models.get("reverse_dcf").result if models.get("reverse_dcf") is not None and isinstance(models.get("reverse_dcf").result, dict) else {}
    capital_result = models.get("capital_allocation").result if models.get("capital_allocation") is not None and isinstance(models.get("capital_allocation").result, dict) else {}
    ratios_result = models.get("ratios").result if models.get("ratios") is not None and isinstance(models.get("ratios").result, dict) else {}
    ratios_values = ratios_result.get("values") if isinstance(ratios_result.get("values"), dict) else {}
    fair_value_per_share = _coerce_number(dcf_result.get("fair_value_per_share"), None)
    dcf_status = str(dcf_result.get("model_status") or dcf_result.get("status") or "unknown")
    reverse_status = str(reverse_result.get("model_status") or reverse_result.get("status") or "unknown")
    fair_value_gap = None
    if dcf_status != "unsupported":
        fair_value_gap = (
            ((fair_value_per_share - float(latest_price)) / float(latest_price))
            if fair_value_per_share is not None and latest_price not in (None, 0)
            else None
        )

    return WatchlistSummaryItemPayload(
        ticker=snapshot.company.ticker,
        name=snapshot.company.name,
        sector=snapshot.company.sector,
        cik=snapshot.company.cik,
        last_checked=snapshot.last_checked,
        refresh=refresh,
        alert_summary=alert_summary,
        latest_alert=_serialize_watchlist_latest_alert(latest_alert),
        latest_activity=_serialize_watchlist_latest_activity(latest_activity),
        coverage=WatchlistCoveragePayload(
            financial_periods=financial_periods,
            price_points=price_points,
        ),
        fair_value_gap=fair_value_gap,
        roic=_coerce_number(roic_result.get("roic"), None),
        shareholder_yield=_coerce_number(capital_result.get("shareholder_yield"), None),
        implied_growth=_coerce_number(reverse_result.get("implied_growth"), None) if reverse_status != "unsupported" else None,
        fair_value_gap_status=dcf_status,
        implied_growth_status=reverse_status,
        valuation_band_percentile=_coerce_number(reverse_result.get("valuation_band_percentile"), None),
        balance_sheet_risk=_coerce_number(ratios_values.get("net_debt_to_fcf") if isinstance(ratios_values, dict) else None, None),
        market_context_status=get_cached_market_context_status(),
    )


def _build_missing_watchlist_summary_item(background_tasks: BackgroundTasks, ticker: str) -> WatchlistSummaryItemPayload:
    return WatchlistSummaryItemPayload(
        ticker=ticker,
        name=None,
        sector=None,
        cik=None,
        last_checked=None,
        refresh=_trigger_refresh(background_tasks, ticker, reason="missing"),
        alert_summary=AlertsSummaryPayload(total=0, high=0, medium=0, low=0),
        latest_alert=None,
        latest_activity=None,
        coverage=WatchlistCoveragePayload(financial_periods=0, price_points=0),
        fair_value_gap=None,
        roic=None,
        shareholder_yield=None,
        implied_growth=None,
        fair_value_gap_status=None,
        implied_growth_status=None,
        valuation_band_percentile=None,
        balance_sheet_risk=None,
        market_context_status=get_cached_market_context_status(),
    )


def _coerce_number(primary: Any, secondary: Any) -> Number:
    value = primary if primary is not None else secondary
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number == number:
        return None
    return number


def _serialize_watchlist_latest_alert(alert: AlertPayload | None) -> WatchlistLatestAlertPayload | None:
    if alert is None:
        return None
    return WatchlistLatestAlertPayload(
        id=alert.id,
        level=alert.level,
        title=alert.title,
        source=alert.source,
        date=alert.date,
        href=alert.href,
    )


def _serialize_watchlist_latest_activity(entry: ActivityFeedEntryPayload | None) -> WatchlistLatestActivityPayload | None:
    if entry is None:
        return None
    return WatchlistLatestActivityPayload(
        id=entry.id,
        type=entry.type,
        badge=entry.badge,
        title=entry.title,
        date=entry.date,
        href=entry.href,
    )


def _is_governance_form(form: str | None) -> bool:
    normalized = (form or "").upper()
    return normalized in {"DEF 14A", "DEFA14A"}


def _is_event_form(form: str | None) -> bool:
    normalized = (form or "").upper()
    return normalized == "8-K"


def _classify_filing_event(items: str | None, description: str | None) -> str:
    normalized_items = (items or "").replace(" ", "")
    item_tokens = {token for token in normalized_items.split(",") if token}
    description_text = (description or "").lower()

    if item_tokens & {"2.02", "7.01", "9.01"}:
        return "Earnings"
    if item_tokens & {"1.01", "2.01"}:
        return "Deal"
    if item_tokens & {"2.03", "2.04", "2.05", "2.06"}:
        return "Financing"
    if item_tokens & {"5.02", "5.03", "5.05"}:
        return "Leadership"
    if item_tokens & {"3.01", "3.02", "3.03"}:
        return "Capital Markets"
    if item_tokens & {"8.01"}:
        return "General Update"
    if "earnings" in description_text or "results" in description_text:
        return "Earnings"
    if "director" in description_text or "officer" in description_text or "chief executive" in description_text:
        return "Leadership"
    if "agreement" in description_text or "acquisition" in description_text or "merger" in description_text:
        return "Deal"
    if "debt" in description_text or "credit" in description_text or "financing" in description_text:
        return "Financing"
    return "Other"


def _extract_accession_number(source_url: str) -> str | None:
    if not source_url:
        return None
    companyfacts_match = re.search(r"#accn=([0-9-]+)$", source_url)
    if companyfacts_match:
        return companyfacts_match.group(1)
    archive_match = re.search(r"/([0-9]{10}-[0-9]{2}-[0-9]{6})/", source_url)
    if archive_match:
        return archive_match.group(1)
    return None


def _extract_primary_document_name(source_url: str) -> str | None:
    if not source_url or source_url.endswith(".json") or "#accn=" in source_url:
        return None
    document_name = source_url.rsplit("/", 1)[-1]
    return _normalize_optional_text(document_name)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _is_allowed_sec_embed_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    if parsed.scheme != "https":
        return False
    if parsed.netloc.lower() not in ALLOWED_SEC_EMBED_HOSTS:
        return False
    if parsed.netloc.lower().endswith("sec.gov") and not parsed.path:
        return False
    return True


def _is_allowed_sec_content_type(content_type: str | None, source_url: str) -> bool:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type and any(normalized_type.startswith(prefix) for prefix in ALLOWED_SEC_EMBED_MIME_PREFIXES):
        return True
    path = urlparse(source_url).path.lower()
    return any(path.endswith(ext) for ext in ALLOWED_SEC_EMBED_EXTENSIONS)


def _fetch_sec_document(client: EdgarClient, source_url: str) -> tuple[str, str]:
    with client.stream_document(source_url) as response:
        content_type = response.headers.get("content-type", "text/html")
        if not _is_allowed_sec_content_type(content_type, source_url):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Filing document type is not supported for embedded viewing. Open it directly on SEC instead.",
            )

        total = 0
        chunks: list[bytes] = []
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > MAX_SEC_EMBED_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Filing document exceeds the 5 MB embed limit. Open it directly on SEC instead.",
                )
            chunks.append(chunk)

        payload_bytes = b"".join(chunks)
        text = payload_bytes.decode(response.encoding or "utf-8", errors="replace")
        return text, content_type or "text/html"


def _build_embedded_filing_html(payload: str, source_url: str, content_type: str) -> str:
    normalized_type = content_type.lower()
    if "html" in normalized_type or re.search(r"\.(html?|xhtml)$", urlparse(source_url).path, flags=re.IGNORECASE):
        sanitized = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", payload)
        if re.search(r"(?is)<head[^>]*>", sanitized):
            base_tag = f'<base href="{html.escape(source_url, quote=True)}" target="_blank">'
            return re.sub(r"(?is)<head([^>]*)>", rf"<head\1>{base_tag}", sanitized, count=1)
        return (
            "<!doctype html><html><head>"
            f'<base href="{html.escape(source_url, quote=True)}" target="_blank">'
            "</head><body>"
            f"{sanitized}"
            "</body></html>"
        )

    escaped_payload = html.escape(payload)
    return (
        "<!doctype html><html><head>"
        '<meta charset="utf-8">'
        f'<base href="{html.escape(source_url, quote=True)}" target="_blank">'
        "<style>body{margin:0;background:#0c0c0c;color:#e5e7eb;font:14px/1.6 Inter,system-ui,sans-serif;}"
        ".shell{padding:20px;}pre{white-space:pre-wrap;word-break:break-word;font:13px/1.55 SFMono-Regular,Consolas,monospace;}"
        "a{color:#00e5ff;}</style></head><body><div class='shell'>"
        "<pre>"
        f"{escaped_payload}"
        "</pre></div></body></html>"
    )


def _render_unavailable_filing_view(source_url: str) -> str:
    escaped_url = html.escape(source_url, quote=True)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{margin:0;background:#0c0c0c;color:#e5e7eb;font:14px/1.6 Inter,system-ui,sans-serif;}"
        ".shell{padding:24px;max-width:760px;margin:0 auto;}"
        ".card{padding:18px;border-radius:16px;border:1px solid rgba(255,255,255,.08);background:#111111;}"
        "a{color:#00e5ff;text-decoration:none;}a:hover{text-decoration:underline;}</style></head><body>"
        "<div class='shell'><div class='card'><h1>Embedded viewer unavailable</h1>"
        "<p>This filing does not expose a directly embeddable SEC HTML document from the current source URL.</p>"
        f"<p><a href='{escaped_url}' target='_blank' rel='noreferrer'>Open the filing on SEC</a></p>"
        "</div></div></body></html>"
    )


def _parse_requested_models(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _parse_csv_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _normalize_ticker(value: str) -> str:
    return value.strip().replace("$", "").upper()


def _normalize_search_query(value: str) -> str:
    normalized = value.strip().replace("$", "")
    return re.sub(r"^cik\s*[:#-]?\s*", "", normalized, flags=re.IGNORECASE)


def _normalize_cik_query(value: str) -> str | None:
    digits = "".join(character for character in value if character.isdigit())
    if not digits or len(digits) > 10:
        return None
    return digits.zfill(10)


def _normalize_filing_form(form: str | None) -> tuple[str, bool]:
    if not form:
        return "", False
    normalized = form.upper().strip()
    amended = False
    for suffix in ("/A", "-A"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            amended = True
            break
    return normalized, amended


def _is_core_filing_form(form: str | None) -> bool:
    base_form, _ = _normalize_filing_form(form)
    return bool(base_form) and base_form in CORE_FILING_TIMELINE_FORMS


def _filings_cache_key(cik: str) -> str:
    return f"ft:filings:{cik}"


def _load_filings_from_cache(cik: str) -> list[FilingPayload] | None:
    # Prefer Redis for cross-worker cache
    if _redis_client is not None:
        try:
            cached = _redis_client.get(_filings_cache_key(cik))
            if cached:
                data = json.loads(cached)
                return [FilingPayload(**item) for item in data]
        except Exception:
            logging.getLogger(__name__).warning("Unable to read filings cache from Redis", exc_info=True)

    # Fallback to process-local cache
    cached_entry = _filings_timeline_cache.get(cik)
    if cached_entry:
        cached_age = time.monotonic() - cached_entry[0]
        if cached_age < FILINGS_TIMELINE_TTL_SECONDS:
            return cached_entry[1]

    return None


def _store_filings_in_cache(cik: str, filings: list[FilingPayload]) -> None:
    # Process-local cache
    _filings_timeline_cache[cik] = (time.monotonic(), filings)

    if _redis_client is None:
        return

    try:
        payload = json.dumps([filing.model_dump(mode="json") for filing in filings])
        _redis_client.setex(_filings_cache_key(cik), FILINGS_TIMELINE_TTL_SECONDS, payload)
    except Exception:
        logging.getLogger(__name__).warning("Unable to store filings cache in Redis", exc_info=True)


def _evict_filings_cache(cik: str) -> None:
    _filings_timeline_cache.pop(cik, None)
    if _redis_client is None:
        return
    try:
        _redis_client.delete(_filings_cache_key(cik))
    except Exception:
        logging.getLogger(__name__).warning("Unable to evict filings cache in Redis", exc_info=True)


def _looks_like_ticker(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,9}", value.strip().replace("$", "")))


def _merge_last_checked(*values: datetime | None) -> datetime | None:
    normalized_values = [value for value in values if value is not None]
    if not normalized_values:
        return None
    return min(normalized_values)
