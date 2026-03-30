from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.api.schemas.common import Number, ProvenanceEnvelope


class ScreenerMetricSnapshotPayload(BaseModel):
    value: Number = None
    unit: str
    is_proxy: bool = False
    source_key: str
    quality_flags: list[str] = Field(default_factory=list)


class ScreenerRankingComponentPayload(BaseModel):
    component_key: str
    label: str
    source_key: str
    value: Number = None
    unit: str
    weight: float
    directionality: Literal["higher_increases_score", "lower_increases_score"]
    component_score: Number = None
    is_proxy: bool = False
    confidence_notes: list[str] = Field(default_factory=list)


class ScreenerRankingPayload(BaseModel):
    score_key: Literal["quality", "value", "capital_allocation", "dilution_risk", "filing_risk"]
    label: str
    score: Number = None
    rank: int | None = None
    percentile: Number = None
    universe_size: int = 0
    universe_basis: Literal["candidate_universe_pre_filter"] = "candidate_universe_pre_filter"
    score_directionality: Literal["higher_is_better", "higher_is_worse"]
    confidence_notes: list[str] = Field(default_factory=list)
    components: list[ScreenerRankingComponentPayload] = Field(default_factory=list)


class ScreenerRankingsPayload(BaseModel):
    quality: ScreenerRankingPayload
    value: ScreenerRankingPayload
    capital_allocation: ScreenerRankingPayload
    dilution_risk: ScreenerRankingPayload
    filing_risk: ScreenerRankingPayload


class ScreenerRankingDefinitionComponentPayload(BaseModel):
    component_key: str
    label: str
    source_key: str
    unit: str
    weight: float
    directionality: Literal["higher_increases_score", "lower_increases_score"]
    notes: list[str] = Field(default_factory=list)


class ScreenerRankingDefinitionPayload(BaseModel):
    score_key: Literal["quality", "value", "capital_allocation", "dilution_risk", "filing_risk"]
    label: str
    description: str
    score_directionality: Literal["higher_is_better", "higher_is_worse"]
    universe_basis: Literal["candidate_universe_pre_filter"] = "candidate_universe_pre_filter"
    method_summary: str
    components: list[ScreenerRankingDefinitionComponentPayload] = Field(default_factory=list)
    confidence_notes_policy: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ScreenerMetricsPayload(BaseModel):
    revenue_growth: ScreenerMetricSnapshotPayload
    operating_margin: ScreenerMetricSnapshotPayload
    fcf_margin: ScreenerMetricSnapshotPayload
    leverage_ratio: ScreenerMetricSnapshotPayload
    dilution: ScreenerMetricSnapshotPayload
    sbc_burden: ScreenerMetricSnapshotPayload
    shareholder_yield: ScreenerMetricSnapshotPayload


class ScreenerFilingQualityPayload(BaseModel):
    filing_lag_days: ScreenerMetricSnapshotPayload
    stale_period_flag: ScreenerMetricSnapshotPayload
    restatement_flag: ScreenerMetricSnapshotPayload
    restatement_count: int = 0
    latest_restatement_filing_date: DateType | None = None
    latest_restatement_period_end: DateType | None = None
    aggregated_quality_flags: list[str] = Field(default_factory=list)


class ScreenerCompanyPayload(BaseModel):
    ticker: str
    cik: str
    name: str
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None
    cache_state: Literal["fresh", "stale", "missing"] = "missing"


class ScreenerResultPayload(BaseModel):
    company: ScreenerCompanyPayload
    period_type: Literal["quarterly", "annual", "ttm"]
    period_end: DateType | None = None
    filing_type: str | None = None
    last_metrics_check: datetime | None = None
    last_model_check: datetime | None = None
    metrics: ScreenerMetricsPayload
    filing_quality: ScreenerFilingQualityPayload
    rankings: ScreenerRankingsPayload


class ScreenerCoverageSummaryPayload(BaseModel):
    candidate_count: int = 0
    matched_count: int = 0
    returned_count: int = 0
    fresh_count: int = 0
    stale_count: int = 0
    missing_shareholder_yield_count: int = 0
    restatement_flagged_count: int = 0
    stale_period_flagged_count: int = 0


class ScreenerSortPayload(BaseModel):
    field: Literal[
        "ticker",
        "period_end",
        "revenue_growth",
        "operating_margin",
        "fcf_margin",
        "leverage_ratio",
        "dilution",
        "sbc_burden",
        "shareholder_yield",
        "filing_lag_days",
        "restatement_count",
        "quality_score",
        "value_score",
        "capital_allocation_score",
        "dilution_risk_score",
        "filing_risk_score",
    ] = "revenue_growth"
    direction: Literal["asc", "desc"] = "desc"


class ScreenerFilterInputPayload(BaseModel):
    revenue_growth_min: Number = None
    operating_margin_min: Number = None
    fcf_margin_min: Number = None
    leverage_ratio_max: Number = None
    dilution_max: Number = None
    sbc_burden_max: Number = None
    shareholder_yield_min: Number = None
    max_filing_lag_days: Number = None
    exclude_restatements: bool = False
    exclude_stale_periods: bool = False
    excluded_quality_flags: list[str] = Field(default_factory=list)

    @field_validator("excluded_quality_flags")
    @classmethod
    def _normalize_quality_flags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            text = str(value).strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized


class OfficialScreenerSearchRequest(BaseModel):
    period_type: Literal["quarterly", "annual", "ttm"] = "ttm"
    ticker_universe: list[str] = Field(default_factory=list)
    filters: ScreenerFilterInputPayload = Field(default_factory=ScreenerFilterInputPayload)
    sort: ScreenerSortPayload = Field(default_factory=ScreenerSortPayload)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    @field_validator("ticker_universe")
    @classmethod
    def _normalize_ticker_universe(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            ticker = str(value).strip().upper()
            if ticker and ticker not in normalized:
                normalized.append(ticker)
        return normalized


class OfficialScreenerQueryPayload(BaseModel):
    period_type: Literal["quarterly", "annual", "ttm"]
    ticker_universe: list[str] = Field(default_factory=list)
    filters: ScreenerFilterInputPayload = Field(default_factory=ScreenerFilterInputPayload)
    sort: ScreenerSortPayload = Field(default_factory=ScreenerSortPayload)
    limit: int
    offset: int
    strict_official_only: bool = True


class ScreenerFilterDefinitionPayload(BaseModel):
    field: str
    label: str
    description: str
    comparator: Literal["min", "max", "boolean", "exclude_any"]
    source_kind: Literal["derived_metric", "model_result", "restatement_record", "quality_flag"]
    source_key: str
    unit: str | None = None
    official_only: bool = True
    notes: list[str] = Field(default_factory=list)
    suggested_values: list[str] = Field(default_factory=list)


class OfficialScreenerMetadataResponse(ProvenanceEnvelope):
    strict_official_only: bool = True
    default_period_type: Literal["quarterly", "annual", "ttm"] = "ttm"
    period_types: list[Literal["quarterly", "annual", "ttm"]] = Field(default_factory=lambda: ["quarterly", "annual", "ttm"])
    default_sort: ScreenerSortPayload = Field(default_factory=ScreenerSortPayload)
    filters: list[ScreenerFilterDefinitionPayload] = Field(default_factory=list)
    rankings: list[ScreenerRankingDefinitionPayload] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class OfficialScreenerSearchResponse(ProvenanceEnvelope):
    query: OfficialScreenerQueryPayload
    coverage: ScreenerCoverageSummaryPayload
    results: list[ScreenerResultPayload] = Field(default_factory=list)