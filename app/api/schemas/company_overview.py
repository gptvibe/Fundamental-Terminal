from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, Number, ProvenanceEnvelope, RefreshState
from app.api.schemas.equity_claim_risk import EquityClaimRiskSummaryPayload
from app.api.schemas.events import CompanyActivityOverviewResponse, CompanyCapitalMarketsSummaryResponse
from app.api.schemas.filings import FilingTimelineItemPayload
from app.api.schemas.financials import CompanyCapitalStructureResponse, CompanyChangesSinceLastFilingResponse, CompanyFinancialsResponse
from app.api.schemas.governance import CompanyGovernanceSummaryResponse
from app.api.schemas.models import CompanyModelsResponse
from app.api.schemas.ownership import CompanyBeneficialOwnershipSummaryResponse
from app.api.schemas.workspace import CompanyEarningsSummaryResponse


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


class CompanyPeersResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    peer_basis: str
    available_companies: list[PeerOptionPayload]
    selected_tickers: list[str]
    peers: list[PeerMetricsPayload]
    notes: dict[str, str]
    refresh: RefreshState


class ResearchBriefSnapshotSummaryPayload(BaseModel):
    latest_filing_type: str | None = None
    latest_period_end: DateType | None = None
    annual_statement_count: int = 0
    price_history_points: int = 0
    latest_revenue: Number = None
    latest_free_cash_flow: Number = None
    top_segment_name: str | None = None
    top_segment_share_of_revenue: Number = None
    alert_count: int = 0


class ResearchBriefBusinessQualitySummaryPayload(BaseModel):
    latest_period_end: DateType | None = None
    previous_period_end: DateType | None = None
    annual_statement_count: int = 0
    revenue_growth: Number = None
    operating_margin: Number = None
    free_cash_flow_margin: Number = None
    share_dilution: Number = None


class CompanyResearchBriefSnapshotSection(ProvenanceEnvelope):
    summary: ResearchBriefSnapshotSummaryPayload = Field(default_factory=ResearchBriefSnapshotSummaryPayload)


class CompanyResearchBriefWhatChangedSection(ProvenanceEnvelope):
    activity_overview: CompanyActivityOverviewResponse
    changes: CompanyChangesSinceLastFilingResponse
    earnings_summary: CompanyEarningsSummaryResponse


class CompanyResearchBriefBusinessQualitySection(ProvenanceEnvelope):
    summary: ResearchBriefBusinessQualitySummaryPayload = Field(default_factory=ResearchBriefBusinessQualitySummaryPayload)


class CompanyResearchBriefCapitalAndRiskSection(ProvenanceEnvelope):
    capital_structure: CompanyCapitalStructureResponse
    capital_markets_summary: CompanyCapitalMarketsSummaryResponse
    governance_summary: CompanyGovernanceSummaryResponse
    ownership_summary: CompanyBeneficialOwnershipSummaryResponse
    equity_claim_risk_summary: EquityClaimRiskSummaryPayload = Field(default_factory=EquityClaimRiskSummaryPayload)


class CompanyResearchBriefValuationSection(ProvenanceEnvelope):
    models: CompanyModelsResponse
    peers: CompanyPeersResponse


class CompanyResearchBriefMonitorSection(ProvenanceEnvelope):
    activity_overview: CompanyActivityOverviewResponse


class ResearchBriefSummaryCardPayload(BaseModel):
    key: str
    title: str
    value: str
    detail: str | None = None


class ResearchBriefSectionStatusPayload(BaseModel):
    id: str
    title: str
    state: Literal["building", "partial", "ready"]
    available: bool = True
    detail: str | None = None


class CompanyResearchBriefResponse(BaseModel):
    company: CompanyPayload | None
    schema_version: str
    generated_at: datetime
    as_of: str | None = None
    refresh: RefreshState
    build_state: Literal["building", "partial", "ready"] = "ready"
    build_status: str = "Research brief ready."
    available_sections: list[str] = Field(default_factory=list)
    section_statuses: list[ResearchBriefSectionStatusPayload] = Field(default_factory=list)
    filing_timeline: list[FilingTimelineItemPayload] = Field(default_factory=list)
    stale_summary_cards: list[ResearchBriefSummaryCardPayload] = Field(default_factory=list)
    snapshot: CompanyResearchBriefSnapshotSection
    what_changed: CompanyResearchBriefWhatChangedSection
    business_quality: CompanyResearchBriefBusinessQualitySection
    capital_and_risk: CompanyResearchBriefCapitalAndRiskSection
    valuation: CompanyResearchBriefValuationSection
    monitor: CompanyResearchBriefMonitorSection


class CompanyOverviewResponse(BaseModel):
    company: CompanyPayload | None
    financials: CompanyFinancialsResponse
    brief: CompanyResearchBriefResponse
