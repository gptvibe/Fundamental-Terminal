from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, Number, ProvenanceEnvelope, RefreshState


class MarketCurvePointPayload(BaseModel):
    tenor: str
    rate: float
    observation_date: DateType


class MarketSlopePayload(BaseModel):
    label: str
    value: Number = None
    long_tenor: str
    short_tenor: str
    observation_date: DateType | None = None


class MarketFredSeriesPayload(BaseModel):
    series_id: str
    label: str
    category: str
    units: str
    value: Number = None
    observation_date: DateType | None = None
    state: str


class MacroHistoryPointPayload(BaseModel):
    date: str
    value: float


class MacroSeriesItemPayload(BaseModel):
    series_id: str
    label: str
    source_name: str
    source_url: str
    units: str
    value: Number = None
    previous_value: Number = None
    change: Number = None
    change_percent: Number = None
    observation_date: DateType | None = None
    release_date: DateType | None = None
    history: list[MacroHistoryPointPayload] = Field(default_factory=list)
    status: str


class CompanyMarketContextResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    status: str
    curve_points: list[MarketCurvePointPayload]
    slope_2s10s: MarketSlopePayload
    slope_3m10y: MarketSlopePayload
    fred_series: list[MarketFredSeriesPayload]
    provenance_details: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime
    refresh: RefreshState
    rates_credit: list[MacroSeriesItemPayload] = Field(default_factory=list)
    inflation_labor: list[MacroSeriesItemPayload] = Field(default_factory=list)
    growth_activity: list[MacroSeriesItemPayload] = Field(default_factory=list)
    relevant_series: list[str] = Field(default_factory=list)
    sector_exposure: list[str] = Field(default_factory=list)
    hqm_snapshot: dict[str, Any] | None = None
