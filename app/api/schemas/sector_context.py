from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, Number, ProvenanceEnvelope, RefreshState


class SectorChartPointPayload(BaseModel):
    label: str
    value: Number = None


class SectorChartSeriesPayload(BaseModel):
    series_key: str
    label: str
    unit: str
    points: list[SectorChartPointPayload] = Field(default_factory=list)


class SectorChartPayload(BaseModel):
    chart_id: str
    title: str
    subtitle: str | None = None
    unit: str
    series: list[SectorChartSeriesPayload] = Field(default_factory=list)


class SectorMetricPayload(BaseModel):
    metric_id: str
    label: str
    unit: str
    value: Number = None
    previous_value: Number = None
    change: Number = None
    change_percent: Number = None
    as_of: str | None = None
    status: str


class SectorDetailRowPayload(BaseModel):
    label: str
    unit: str
    current_value: Number = None
    prior_value: Number = None
    change: Number = None
    change_percent: Number = None
    as_of: str | None = None
    note: str | None = None


class SectorDetailViewPayload(BaseModel):
    title: str
    rows: list[SectorDetailRowPayload] = Field(default_factory=list)


class SectorRefreshPolicyPayload(BaseModel):
    cadence_label: str
    ttl_seconds: int
    notes: list[str] = Field(default_factory=list)


class SectorPluginPayload(BaseModel):
    plugin_id: str
    title: str
    description: str
    status: str
    relevance_reasons: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    refresh_policy: SectorRefreshPolicyPayload
    summary_metrics: list[SectorMetricPayload] = Field(default_factory=list)
    charts: list[SectorChartPayload] = Field(default_factory=list)
    detail_view: SectorDetailViewPayload
    confidence_flags: list[str] = Field(default_factory=list)
    as_of: str | None = None
    last_refreshed_at: str | None = None


class CompanySectorContextResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    status: str
    matched_plugin_ids: list[str] = Field(default_factory=list)
    plugins: list[SectorPluginPayload] = Field(default_factory=list)
    fetched_at: datetime
    refresh: RefreshState