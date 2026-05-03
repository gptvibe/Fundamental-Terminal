from __future__ import annotations

from datetime import date as DateType, datetime as DateTimeType
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, RefreshState


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
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
    error: str | None = None


class FilingRiskSignalPayload(BaseModel):
    ticker: str
    cik: str
    accession_number: str
    form_type: str
    filed_date: DateType | None = None
    signal_category: str
    matched_phrase: str
    context_snippet: str
    confidence: str
    severity: str
    source: str
    provenance: str
    last_updated: DateTimeType | None = None
    last_checked: DateTimeType | None = None


class FilingRiskSignalSummaryPayload(BaseModel):
    total_signals: int
    high_severity_count: int
    medium_severity_count: int
    latest_filed_date: DateType | None = None


class CompanyFilingRiskSignalsResponse(BaseModel):
    company: CompanyPayload | None
    summary: FilingRiskSignalSummaryPayload
    signals: list[FilingRiskSignalPayload]
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
