from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.source_registry import SourceTier

Number = int | float | None


class RefreshState(BaseModel):
    triggered: bool = Field(default=False)
    reason: Literal["manual", "missing", "stale", "fresh", "none"] = Field(default="none")
    ticker: str | None = Field(default=None)
    job_id: str | None = Field(default=None)


class DataQualityDiagnosticsPayload(BaseModel):
    coverage_ratio: Number = None
    fallback_ratio: Number = None
    stale_flags: list[str] = Field(default_factory=list)
    parser_confidence: Number = None
    missing_field_flags: list[str] = Field(default_factory=list)


class SourceMixPayload(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    source_tiers: list[SourceTier] = Field(default_factory=list)
    primary_source_ids: list[str] = Field(default_factory=list)
    fallback_source_ids: list[str] = Field(default_factory=list)
    official_only: bool = False


class ProvenanceEntryPayload(BaseModel):
    source_id: str
    source_tier: SourceTier
    display_label: str
    url: str
    default_freshness_ttl_seconds: int
    disclosure_note: str
    role: Literal["primary", "supplemental", "derived", "fallback"] = "primary"
    as_of: str | None = None
    last_refreshed_at: datetime | None = None


class ProvenanceEnvelope(BaseModel):
    provenance: list[ProvenanceEntryPayload] = Field(default_factory=list)
    as_of: str | None = None
    last_refreshed_at: datetime | None = None
    source_mix: SourceMixPayload = Field(default_factory=SourceMixPayload)
    confidence_flags: list[str] = Field(default_factory=list)


class CompanyPayload(BaseModel):
    ticker: str
    cik: str
    name: str
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None
    strict_official_mode: bool = False
    last_checked: datetime | None = None
    last_checked_financials: datetime | None = None
    last_checked_prices: datetime | None = None
    last_checked_insiders: datetime | None = None
    last_checked_institutional: datetime | None = None
    last_checked_filings: datetime | None = None
    earnings_last_checked: datetime | None = None
    cache_state: Literal["fresh", "stale", "missing"]
