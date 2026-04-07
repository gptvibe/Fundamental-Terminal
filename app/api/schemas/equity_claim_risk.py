from __future__ import annotations

from datetime import date as DateType
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, Number, ProvenanceEnvelope, RefreshState
from app.api.schemas.financials import CapitalStructureNetDilutionBridgePayload


RiskLevel = Literal["low", "medium", "high"]
ReportingSeverity = Literal["none", "low", "medium", "high"]


class EquityClaimRiskEvidencePayload(BaseModel):
    category: Literal["capital_structure", "capital_markets", "filing_event", "restatement"]
    title: str
    detail: str
    form: str | None = None
    filing_date: DateType | None = None
    accession_number: str | None = None
    source_url: str | None = None
    source_id: str


class EquityClaimRiskSummaryPayload(BaseModel):
    headline: str = ""
    overall_risk_level: RiskLevel = "low"
    dilution_risk_level: RiskLevel = "low"
    financing_risk_level: RiskLevel = "low"
    reporting_risk_level: RiskLevel = "low"
    latest_period_end: DateType | None = None
    net_dilution_ratio: Number = None
    sbc_to_revenue: Number = None
    shelf_capacity_remaining: Number = None
    recent_atm_activity: bool = False
    recent_warrant_or_convertible_activity: bool = False
    debt_due_next_twenty_four_months: Number = None
    restatement_severity: ReportingSeverity = "none"
    internal_control_flag_count: int = 0
    key_points: list[str] = Field(default_factory=list)


class EquityClaimRiskShareCountBridgePayload(BaseModel):
    latest_period_end: DateType | None = None
    bridge: CapitalStructureNetDilutionBridgePayload = Field(default_factory=CapitalStructureNetDilutionBridgePayload)
    evidence: list[EquityClaimRiskEvidencePayload] = Field(default_factory=list)


class EquityClaimRiskShelfCapacityPayload(BaseModel):
    status: Literal["none", "available", "partially_used", "likely_exhausted"] = "none"
    latest_shelf_form: str | None = None
    latest_shelf_filing_date: DateType | None = None
    gross_capacity: Number = None
    utilized_capacity: Number = None
    remaining_capacity: Number = None
    evidence: list[EquityClaimRiskEvidencePayload] = Field(default_factory=list)


class EquityClaimRiskAtmDependencyPayload(BaseModel):
    atm_detected: bool = False
    recent_atm_filing_count: int = 0
    latest_atm_filing_date: DateType | None = None
    financing_dependency_level: RiskLevel = "low"
    negative_free_cash_flow: bool = False
    cash_runway_years: Number = None
    debt_due_next_twelve_months: Number = None
    evidence: list[EquityClaimRiskEvidencePayload] = Field(default_factory=list)


class EquityClaimRiskHybridSecuritiesPayload(BaseModel):
    warrant_filing_count: int = 0
    convertible_filing_count: int = 0
    latest_security_filing_date: DateType | None = None
    evidence: list[EquityClaimRiskEvidencePayload] = Field(default_factory=list)


class EquityClaimRiskSbcAndDilutionPayload(BaseModel):
    latest_stock_based_compensation: Number = None
    sbc_to_revenue: Number = None
    current_net_dilution_ratio: Number = None
    trailing_three_period_net_dilution_ratio: Number = None
    weighted_average_diluted_shares_growth: Number = None
    evidence: list[EquityClaimRiskEvidencePayload] = Field(default_factory=list)


class EquityClaimRiskDebtMaturityWallPayload(BaseModel):
    total_debt: Number = None
    debt_due_next_twelve_months: Number = None
    debt_due_year_two: Number = None
    debt_due_next_twenty_four_months: Number = None
    debt_due_next_twenty_four_months_ratio: Number = None
    interest_coverage_proxy: Number = None
    evidence: list[EquityClaimRiskEvidencePayload] = Field(default_factory=list)


class EquityClaimRiskKeywordSignalPayload(BaseModel):
    level: RiskLevel = "low"
    match_count: int = 0
    matched_terms: list[str] = Field(default_factory=list)
    evidence: list[EquityClaimRiskEvidencePayload] = Field(default_factory=list)


class EquityClaimRiskReportingPayload(BaseModel):
    restatement_count: int = 0
    restatement_severity: ReportingSeverity = "none"
    high_impact_restatements: int = 0
    latest_restatement_date: DateType | None = None
    internal_control_flag_count: int = 0
    internal_control_terms: list[str] = Field(default_factory=list)
    evidence: list[EquityClaimRiskEvidencePayload] = Field(default_factory=list)


class CompanyEquityClaimRiskResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    summary: EquityClaimRiskSummaryPayload = Field(default_factory=EquityClaimRiskSummaryPayload)
    share_count_bridge: EquityClaimRiskShareCountBridgePayload = Field(default_factory=EquityClaimRiskShareCountBridgePayload)
    shelf_registration: EquityClaimRiskShelfCapacityPayload = Field(default_factory=EquityClaimRiskShelfCapacityPayload)
    atm_and_financing_dependency: EquityClaimRiskAtmDependencyPayload = Field(default_factory=EquityClaimRiskAtmDependencyPayload)
    warrants_and_convertibles: EquityClaimRiskHybridSecuritiesPayload = Field(default_factory=EquityClaimRiskHybridSecuritiesPayload)
    sbc_and_dilution: EquityClaimRiskSbcAndDilutionPayload = Field(default_factory=EquityClaimRiskSbcAndDilutionPayload)
    debt_maturity_wall: EquityClaimRiskDebtMaturityWallPayload = Field(default_factory=EquityClaimRiskDebtMaturityWallPayload)
    covenant_risk_signals: EquityClaimRiskKeywordSignalPayload = Field(default_factory=EquityClaimRiskKeywordSignalPayload)
    reporting_and_controls: EquityClaimRiskReportingPayload = Field(default_factory=EquityClaimRiskReportingPayload)
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)