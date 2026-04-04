from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, Number, ProvenanceEnvelope, RefreshState


class OilCurvePointPayload(BaseModel):
    label: str
    value: Number = None
    units: str
    observation_date: str | None = None


class OilCurveSeriesPayload(BaseModel):
    series_id: str
    label: str
    units: str
    status: str
    points: list[OilCurvePointPayload] = Field(default_factory=list)
    latest_value: Number = None
    latest_observation_date: str | None = None


class OilScenarioCasePayload(BaseModel):
    scenario_id: str
    label: str
    benchmark_value: Number = None
    benchmark_delta_percent: Number = None
    revenue_delta_percent: Number = None
    operating_margin_delta_bps: Number = None
    free_cash_flow_delta_percent: Number = None
    confidence_flags: list[str] = Field(default_factory=list)


class OilSensitivityPayload(BaseModel):
    metric_basis: str
    lookback_quarters: int
    elasticity: Number = None
    r_squared: Number = None
    sample_size: int
    direction: str
    status: str
    confidence_flags: list[str] = Field(default_factory=list)


class OilExposureProfilePayload(BaseModel):
    profile_id: str
    label: str
    relevance_reasons: list[str] = Field(default_factory=list)
    hedging_signal: str
    pass_through_signal: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class CompanyOilScenarioOverlayResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    status: str
    fetched_at: datetime
    strict_official_mode: bool
    exposure_profile: OilExposureProfilePayload
    benchmark_series: list[OilCurveSeriesPayload] = Field(default_factory=list)
    scenarios: list[OilScenarioCasePayload] = Field(default_factory=list)
    sensitivity: OilSensitivityPayload | None = None
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
    refresh: RefreshState