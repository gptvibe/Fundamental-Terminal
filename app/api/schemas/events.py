from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, Number, ProvenanceEnvelope, RefreshState


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
    plan_name: str | None = None
    registered_shares: Number = None
    shares_parse_confidence: str | None = None


class CompanyCapitalRaisesResponse(BaseModel):
    company: CompanyPayload | None
    filings: list[CapitalRaisePayload]
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
    error: str | None = None


class CapitalMarketsSummaryPayload(BaseModel):
    total_filings: int
    late_filer_notices: int
    registration_filings: int
    prospectus_filings: int
    equity_plan_registrations: int = 0
    latest_filing_date: DateType | None = None
    max_offering_amount: Number = None
    total_registered_equity_plan_shares: Number = None


class CompanyCapitalMarketsSummaryResponse(BaseModel):
    company: CompanyPayload | None
    summary: CapitalMarketsSummaryPayload
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
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
    exhibit_previews: list["FilingEventExhibitPreviewPayload"] = Field(default_factory=list)


class FilingEventExhibitPreviewPayload(BaseModel):
    accession_number: str
    item_code: str
    exhibit_filename: str
    exhibit_type: str | None = None
    filing_date: DateType | None = None
    source_url: str
    snippet: str


class CompanyEventsResponse(BaseModel):
    company: CompanyPayload | None
    events: list[FilingEventPayload]
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
    error: str | None = None


class CommentLetterPayload(BaseModel):
    accession_number: str
    filing_date: DateType | None = None
    description: str
    sec_url: str
    acceptance_datetime: datetime | None = None
    primary_document: str | None = None
    document_url: str | None = None
    document_format: str | None = None
    correspondent_role: str | None = None
    document_kind: str | None = None
    thread_key: str | None = None
    review_sequence: str | None = None
    topics: list[str] = Field(default_factory=list)
    has_document_text: bool = False
    document_text_excerpt: str | None = None


class CompanyCommentLettersResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    letters: list[CommentLetterPayload]
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
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
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


class CompanyActivityOverviewResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    entries: list[ActivityFeedEntryPayload]
    alerts: list[AlertPayload]
    summary: AlertsSummaryPayload
    market_context_status: dict[str, Any] | None = None
    refresh: RefreshState
    error: str | None = None
