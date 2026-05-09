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
    last_success_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    is_stale: bool = False
    used_by_paths: list[str] = []


class SourceRegistryErrorPayload(BaseModel):
    source_id: str
    source_tier: SourceTier
    display_label: str
    affected_dataset_ids: list[str]
    affected_company_count: int
    failure_count: int
    last_error: str
    last_error_at: datetime


class SourceRegistrySloPayload(BaseModel):
    key: Literal[
        "sec_companyfacts_freshness",
        "sec_submissions_freshness",
        "macro_freshness",
        "fallback_usage",
        "worker_queue_health",
    ]
    label: str
    status: Literal["healthy", "degraded", "stale", "unknown"]
    monitored_source_ids: list[str]
    source_count: int
    stale_count: int
    active_error_count: int
    last_success_at: datetime | None = None
    note: str | None = None


class SourceRegistryWorkerQueueHealthPayload(BaseModel):
    available: bool
    status: Literal["healthy", "degraded", "stale", "unknown"]
    active_job_count: int
    stalled_job_count: int
    datasets_with_failures: int
    failed_refresh_count: int | None = None
    recent_failed_jobs: int | None = None


class SourceRegistryHealthPayload(BaseModel):
    total_companies_cached: int
    average_data_age_seconds: float | None
    recent_error_window_hours: int
    sources_with_recent_errors: list[SourceRegistryErrorPayload]
    stale_source_count: int = 0
    sources_with_active_errors_count: int = 0
    fallback_source_count: int = 0
    fallback_sources_recently_used_count: int = 0
    last_successful_refresh_at: datetime | None = None
    worker_queue: SourceRegistryWorkerQueueHealthPayload | None = None
    slos: list[SourceRegistrySloPayload] = []


class SourceRegistryResponse(BaseModel):
    strict_official_mode: bool
    generated_at: datetime
    sources: list[SourceRegistryEntryPayload]
    health: SourceRegistryHealthPayload