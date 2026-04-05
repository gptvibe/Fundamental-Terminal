from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.source_registry import SourceTier


class SourceRegistryEntryPayload(BaseModel):
    source_id: str
    source_tier: SourceTier
    display_label: str
    url: str
    default_freshness_ttl_seconds: int
    disclosure_note: str
    strict_official_mode_state: Literal["available", "disabled"]
    strict_official_mode_note: str


class SourceRegistryErrorPayload(BaseModel):
    source_id: str
    source_tier: SourceTier
    display_label: str
    affected_dataset_ids: list[str]
    affected_company_count: int
    failure_count: int
    last_error: str
    last_error_at: datetime


class SourceRegistryHealthPayload(BaseModel):
    total_companies_cached: int
    average_data_age_seconds: float | None
    recent_error_window_hours: int
    sources_with_recent_errors: list[SourceRegistryErrorPayload]


class SourceRegistryResponse(BaseModel):
    strict_official_mode: bool
    generated_at: datetime
    sources: list[SourceRegistryEntryPayload]
    health: SourceRegistryHealthPayload