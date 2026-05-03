from __future__ import annotations

from datetime import date as DateType
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, Number, RefreshState


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
    sale_context: Literal["planned", "discretionary", "unknown"] | None = None
    plan_adoption_date: DateType | None = None
    plan_modification: Literal["amendment", "termination", "amendment_or_termination"] | None = None
    plan_modification_date: DateType | None = None
    plan_signal_confidence: Literal["high", "medium", "low"] | None = None
    plan_signal_provenance: list[str] | None = None


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
