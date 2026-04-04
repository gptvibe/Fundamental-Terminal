from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, Number, ProvenanceEnvelope, RefreshState
from app.api.schemas.events import AlertsSummaryPayload


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
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
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
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
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
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
    error: str | None = None


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


class WatchlistCalendarEventPayload(BaseModel):
    id: str
    date: DateType
    event_type: Literal["expected_filing", "sec_event", "institutional_deadline"]
    source: Literal["historical_cadence", "sec_rss", "fixed_calendar"]
    ticker: str | None = None
    company_name: str | None = None
    title: str
    form: str | None = None
    detail: str | None = None
    href: str | None = None
    period_end: DateType | None = None


class WatchlistCalendarResponse(BaseModel):
    tickers: list[str]
    window_start: DateType
    window_end: DateType
    events: list[WatchlistCalendarEventPayload]
