from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, Number, ProvenanceEnvelope, RefreshState


class PeerOptionPayload(BaseModel):
    ticker: str
    name: str
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None
    last_checked: datetime | None = None
    cache_state: Literal["fresh", "stale", "missing"]
    is_focus: bool = False


class PeerRevenuePointPayload(BaseModel):
    period_end: DateType
    revenue: Number = None
    revenue_growth: Number = None


class PeerMetricsPayload(BaseModel):
    ticker: str
    name: str
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None
    is_focus: bool = False
    cache_state: Literal["fresh", "stale", "missing"]
    last_checked: datetime | None = None
    period_end: DateType | None = None
    price_date: DateType | None = None
    latest_price: Number = None
    pe: Number = None
    ev_to_ebit: Number = None
    price_to_free_cash_flow: Number = None
    roe: Number = None
    revenue_growth: Number = None
    piotroski_score: Number = None
    altman_z_score: Number = None
    fair_value_gap: Number = None
    roic: Number = None
    shareholder_yield: Number = None
    implied_growth: Number = None
    dcf_model_status: str | None = None
    reverse_dcf_model_status: str | None = None
    valuation_band_percentile: Number = None
    revenue_history: list[PeerRevenuePointPayload] = Field(default_factory=list)


class CompanyPeersResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    peer_basis: str
    available_companies: list[PeerOptionPayload]
    selected_tickers: list[str]
    peers: list[PeerMetricsPayload]
    notes: dict[str, str]
    refresh: RefreshState
