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


class OilCurveYearPointPayload(BaseModel):
    year: int
    price: Number = None


class OilScenarioBenchmarkOptionPayload(BaseModel):
    value: str
    label: str


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


class OilScenarioEligibilityPayload(BaseModel):
    eligible: bool
    status: str
    oil_exposure_type: str = "non_oil"
    reasons: list[str] = Field(default_factory=list)


class OilScenarioOfficialBaseCurvePayload(BaseModel):
    benchmark_id: str | None = None
    label: str | None = None
    units: str = "usd_per_barrel"
    points: list[OilCurveYearPointPayload] = Field(default_factory=list)
    available_benchmarks: list[OilScenarioBenchmarkOptionPayload] = Field(default_factory=list)


class OilScenarioUserEditableDefaultsPayload(BaseModel):
    benchmark_id: str | None = None
    benchmark_options: list[OilScenarioBenchmarkOptionPayload] = Field(default_factory=list)
    short_term_curve: list[OilCurveYearPointPayload] = Field(default_factory=list)
    long_term_anchor: Number = None
    fade_years: int = 0
    annual_after_tax_sensitivity: Number = None
    base_fair_value_per_share: Number = None
    diluted_shares: Number = None
    current_share_price: Number = None
    current_share_price_source: str = "manual_required"
    current_oil_price: Number = None
    current_oil_price_source: str | None = None


class OilScenarioSensitivitySourcePayload(BaseModel):
    kind: str
    value: Number = None
    metric_basis: str | None = None
    status: str | None = None
    confidence_flags: list[str] = Field(default_factory=list)


class OilScenarioOverlayYearResultPayload(BaseModel):
    year: int
    base_oil_price: Number = None
    scenario_oil_price: Number = None
    oil_price_delta: Number = None
    earnings_delta_after_tax: Number = None
    per_share_delta: Number = None
    present_value_per_share: Number = None
    discount_factor: Number = None


class OilScenarioOverlayOutputsPayload(BaseModel):
    status: str
    model_status: str
    reason: str
    base_fair_value_per_share: Number = None
    eps_delta_per_dollar_oil: Number = None
    overlay_pv_per_share: Number = None
    scenario_fair_value_per_share: Number = None
    delta_vs_base_per_share: Number = None
    delta_vs_base_percent: Number = None
    implied_upside_downside: Number = None
    yearly_deltas: list[OilScenarioOverlayYearResultPayload] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    confidence_flags: list[str] = Field(default_factory=list)


class OilScenarioRequirementsPayload(BaseModel):
    strict_official_mode: bool
    manual_price_required: bool
    manual_price_reason: str | None = None
    manual_sensitivity_required: bool
    manual_sensitivity_reason: str | None = None
    price_input_mode: str


class OilScenarioDirectEvidenceFieldPayload(BaseModel):
    status: str
    reason: str | None = None
    source_url: str | None = None
    accession_number: str | None = None
    filing_form: str | None = None
    confidence_flags: list[str] = Field(default_factory=list)
    provenance_sources: list[str] = Field(default_factory=list)


class OilScenarioDisclosedSensitivityEvidencePayload(OilScenarioDirectEvidenceFieldPayload):
    benchmark: str | None = None
    oil_price_change_per_bbl: Number = None
    annual_after_tax_earnings_change: Number = None
    annual_after_tax_sensitivity: Number = None
    metric_basis: str | None = None


class OilScenarioDilutedSharesEvidencePayload(OilScenarioDirectEvidenceFieldPayload):
    value: Number = None
    unit: str | None = None
    taxonomy: str | None = None
    tag: str | None = None


class OilScenarioRealizedBenchmarkRowPayload(BaseModel):
    period_label: str
    benchmark: str | None = None
    realized_price: Number = None
    benchmark_price: Number = None
    realized_percent_of_benchmark: Number = None
    premium_discount: Number = None


class OilScenarioRealizedPriceComparisonEvidencePayload(OilScenarioDirectEvidenceFieldPayload):
    benchmark: str | None = None
    rows: list[OilScenarioRealizedBenchmarkRowPayload] = Field(default_factory=list)


class OilScenarioDirectCompanyEvidencePayload(BaseModel):
    status: str
    checked_at: datetime | None = None
    parser_confidence_flags: list[str] = Field(default_factory=list)
    disclosed_sensitivity: OilScenarioDisclosedSensitivityEvidencePayload
    diluted_shares: OilScenarioDilutedSharesEvidencePayload
    realized_price_comparison: OilScenarioRealizedPriceComparisonEvidencePayload


class OilExposureProfilePayload(BaseModel):
    profile_id: str
    label: str
    oil_exposure_type: str = "non_oil"
    oil_support_status: str = "unsupported"
    oil_support_reasons: list[str] = Field(default_factory=list)
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


class CompanyOilScenarioResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    status: str
    fetched_at: datetime
    strict_official_mode: bool
    exposure_profile: OilExposureProfilePayload
    eligibility: OilScenarioEligibilityPayload
    benchmark_series: list[OilCurveSeriesPayload] = Field(default_factory=list)
    official_base_curve: OilScenarioOfficialBaseCurvePayload
    user_editable_defaults: OilScenarioUserEditableDefaultsPayload
    scenarios: list[OilScenarioCasePayload] = Field(default_factory=list)
    sensitivity: OilSensitivityPayload | None = None
    sensitivity_source: OilScenarioSensitivitySourcePayload
    overlay_outputs: OilScenarioOverlayOutputsPayload
    requirements: OilScenarioRequirementsPayload
    direct_company_evidence: OilScenarioDirectCompanyEvidencePayload
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
    refresh: RefreshState