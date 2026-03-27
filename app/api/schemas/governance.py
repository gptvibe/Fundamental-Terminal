from __future__ import annotations

from datetime import date as DateType

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, RefreshState


class GovernanceVoteOutcomePayload(BaseModel):
    proposal_number: int
    title: str | None = None
    for_votes: int | None = None
    against_votes: int | None = None
    abstain_votes: int | None = None
    broker_non_votes: int | None = None


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
    vote_outcomes: list[GovernanceVoteOutcomePayload] = Field(default_factory=list)


class CompanyGovernanceResponse(BaseModel):
    company: CompanyPayload | None
    filings: list[GovernanceFilingPayload]
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
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
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
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
    source: str
    refresh: RefreshState
    error: str | None = None
