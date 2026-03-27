from __future__ import annotations

from datetime import date as DateType
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
