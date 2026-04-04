from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import settings
from app.models.company import Company
from app.services.oil_scenario_overlay_persistence import (
    read_company_oil_scenario_overlay_snapshot_with_meta,
    upsert_company_oil_scenario_overlay_snapshot,
)
from app.services.refresh_state import acquire_refresh_lock, cache_state_for_dataset, release_refresh_lock, release_refresh_lock_failed
from app.source_registry import SourceUsage, build_provenance_entries, build_source_mix


OilScenarioStatus = Literal["supported", "partial", "not_applicable", "insufficient_data"]


@dataclass(frozen=True, slots=True)
class OilCurvePointDTO:
    label: str
    value: float | None
    units: str
    observation_date: str | None = None


@dataclass(frozen=True, slots=True)
class OilCurveSeriesDTO:
    series_id: str
    label: str
    units: str
    status: str
    points: tuple[OilCurvePointDTO, ...] = field(default_factory=tuple)
    latest_value: float | None = None
    latest_observation_date: str | None = None


@dataclass(frozen=True, slots=True)
class OilScenarioCaseDTO:
    scenario_id: str
    label: str
    benchmark_value: float | None
    benchmark_delta_percent: float | None
    revenue_delta_percent: float | None
    operating_margin_delta_bps: float | None
    free_cash_flow_delta_percent: float | None
    confidence_flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OilSensitivityDTO:
    metric_basis: str
    lookback_quarters: int
    elasticity: float | None
    r_squared: float | None
    sample_size: int
    direction: str
    status: str
    confidence_flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OilScenarioOverlayDTO:
    status: OilScenarioStatus
    fetched_at: datetime
    as_of: str | None
    last_refreshed_at: datetime
    strict_official_mode: bool
    exposure_profile: dict[str, Any]
    benchmark_series: tuple[OilCurveSeriesDTO, ...] = field(default_factory=tuple)
    scenarios: tuple[OilScenarioCaseDTO, ...] = field(default_factory=tuple)
    sensitivity: OilSensitivityDTO | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    confidence_flags: tuple[str, ...] = field(default_factory=tuple)
    provenance: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    source_mix: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "fetched_at": self.fetched_at.isoformat(),
            "as_of": self.as_of,
            "last_refreshed_at": self.last_refreshed_at.isoformat(),
            "strict_official_mode": self.strict_official_mode,
            "exposure_profile": self.exposure_profile,
            "benchmark_series": [
                {
                    "series_id": series.series_id,
                    "label": series.label,
                    "units": series.units,
                    "status": series.status,
                    "points": [
                        {
                            "label": point.label,
                            "value": point.value,
                            "units": point.units,
                            "observation_date": point.observation_date,
                        }
                        for point in series.points
                    ],
                    "latest_value": series.latest_value,
                    "latest_observation_date": series.latest_observation_date,
                }
                for series in self.benchmark_series
            ],
            "scenarios": [
                {
                    "scenario_id": item.scenario_id,
                    "label": item.label,
                    "benchmark_value": item.benchmark_value,
                    "benchmark_delta_percent": item.benchmark_delta_percent,
                    "revenue_delta_percent": item.revenue_delta_percent,
                    "operating_margin_delta_bps": item.operating_margin_delta_bps,
                    "free_cash_flow_delta_percent": item.free_cash_flow_delta_percent,
                    "confidence_flags": list(item.confidence_flags),
                }
                for item in self.scenarios
            ],
            "sensitivity": None
            if self.sensitivity is None
            else {
                "metric_basis": self.sensitivity.metric_basis,
                "lookback_quarters": self.sensitivity.lookback_quarters,
                "elasticity": self.sensitivity.elasticity,
                "r_squared": self.sensitivity.r_squared,
                "sample_size": self.sensitivity.sample_size,
                "direction": self.sensitivity.direction,
                "status": self.sensitivity.status,
                "confidence_flags": list(self.sensitivity.confidence_flags),
            },
            "diagnostics": self.diagnostics,
            "confidence_flags": list(self.confidence_flags),
            "provenance": list(self.provenance),
            "source_mix": self.source_mix,
        }


def get_company_oil_scenario_overlay(
    session: Session,
    company_id: int,
) -> tuple[dict[str, Any] | None, Literal["fresh", "stale", "missing"]]:
    payload, is_stale = read_company_oil_scenario_overlay_snapshot_with_meta(session, company_id)
    if payload is None:
        return None, "missing"
    if is_stale:
        return payload, "stale"
    return payload, "fresh"


def get_company_oil_scenario_overlay_last_checked(
    session: Session,
    company_id: int,
) -> datetime | None:
    last_checked, _cache_state = cache_state_for_dataset(session, company_id, "oil_scenario_overlay")
    return last_checked


def build_company_oil_scenario_overlay_placeholder(
    company: Company,
    *,
    checked_at: datetime,
) -> dict[str, Any]:
    return _build_placeholder_overlay(company, checked_at=checked_at).to_payload()


def refresh_company_oil_scenario_overlay(
    session: Session,
    company: Company,
    *,
    checked_at: datetime,
    job_id: str | None = None,
) -> int:
    duplicate_job_id = acquire_refresh_lock(
        session,
        company_id=company.id,
        dataset="oil_scenario_overlay",
        job_id=job_id or f"oil-scenario-{company.id}",
        now=checked_at,
    )
    if duplicate_job_id is not None:
        return 0

    try:
        overlay = _build_placeholder_overlay(company, checked_at=checked_at)
        upsert_company_oil_scenario_overlay_snapshot(
            session,
            company_id=company.id,
            snapshot_date=checked_at.date(),
            payload=overlay.to_payload(),
            fetched_at=checked_at,
        )
        release_refresh_lock(
            session,
            company_id=company.id,
            dataset="oil_scenario_overlay",
            checked_at=checked_at,
        )
        return 1
    except Exception as exc:
        release_refresh_lock_failed(
            session,
            company_id=company.id,
            dataset="oil_scenario_overlay",
            checked_at=checked_at,
            error=str(exc),
        )
        raise


def _build_placeholder_overlay(company: Company, *, checked_at: datetime) -> OilScenarioOverlayDTO:
    strict_official_mode = settings.strict_official_mode
    exposure_label = _classify_exposure(company)
    usages = [
        SourceUsage(
            source_id="sec_edgar",
            role="primary",
            as_of=checked_at.date().isoformat(),
            last_refreshed_at=checked_at,
        ),
        SourceUsage(
            source_id="ft_oil_scenario_overlay",
            role="derived",
            as_of=checked_at.date().isoformat(),
            last_refreshed_at=checked_at,
        ),
    ]
    provenance = tuple(build_provenance_entries(usages))
    source_mix = build_source_mix(provenance)
    confidence_flags = ("strict_official_mode", "oil_curve_placeholder", "oil_sensitivity_placeholder")
    diagnostics = {
        "coverage_ratio": 0.0,
        "fallback_ratio": 0.0,
        "stale_flags": [],
        "parser_confidence": None,
        "missing_field_flags": ["official_oil_curve_missing", "sensitivity_not_computed"],
        "reconciliation_penalty": None,
        "reconciliation_disagreement_count": 0,
    }
    return OilScenarioOverlayDTO(
        status="partial" if exposure_label != "not_applicable" else "not_applicable",
        fetched_at=checked_at,
        as_of=checked_at.date().isoformat(),
        last_refreshed_at=checked_at,
        strict_official_mode=strict_official_mode,
        exposure_profile={
            "profile_id": exposure_label,
            "label": exposure_label.replace("_", " ").title(),
            "relevance_reasons": _relevance_reasons(company, exposure_label),
            "hedging_signal": "unknown",
            "pass_through_signal": "unknown",
            "evidence": [],
        },
        benchmark_series=(
            OilCurveSeriesDTO(
                series_id="eia_steo_brent_placeholder",
                label="Brent spot oil price",
                units="usd_per_barrel",
                status="placeholder",
                points=(
                    OilCurvePointDTO(label="base", value=None, units="usd_per_barrel", observation_date=None),
                ),
                latest_value=None,
                latest_observation_date=None,
            ),
            OilCurveSeriesDTO(
                series_id="eia_steo_wti_placeholder",
                label="WTI spot oil price",
                units="usd_per_barrel",
                status="placeholder",
                points=(
                    OilCurvePointDTO(label="base", value=None, units="usd_per_barrel", observation_date=None),
                ),
                latest_value=None,
                latest_observation_date=None,
            ),
        ),
        scenarios=(
            OilScenarioCaseDTO(
                scenario_id="bear",
                label="Bear",
                benchmark_value=None,
                benchmark_delta_percent=None,
                revenue_delta_percent=None,
                operating_margin_delta_bps=None,
                free_cash_flow_delta_percent=None,
                confidence_flags=("placeholder",),
            ),
            OilScenarioCaseDTO(
                scenario_id="base",
                label="Base",
                benchmark_value=None,
                benchmark_delta_percent=0.0,
                revenue_delta_percent=None,
                operating_margin_delta_bps=None,
                free_cash_flow_delta_percent=None,
                confidence_flags=("placeholder",),
            ),
            OilScenarioCaseDTO(
                scenario_id="bull",
                label="Bull",
                benchmark_value=None,
                benchmark_delta_percent=None,
                revenue_delta_percent=None,
                operating_margin_delta_bps=None,
                free_cash_flow_delta_percent=None,
                confidence_flags=("placeholder",),
            ),
        ),
        sensitivity=OilSensitivityDTO(
            metric_basis="operating_margin",
            lookback_quarters=8,
            elasticity=None,
            r_squared=None,
            sample_size=0,
            direction="unknown",
            status="placeholder",
            confidence_flags=("sensitivity_not_computed",),
        ),
        diagnostics=diagnostics,
        confidence_flags=confidence_flags,
        provenance=provenance,
        source_mix=source_mix,
    )


def _classify_exposure(company: Company) -> str:
    combined = " ".join(
        [
            (company.sector or "").lower(),
            (company.market_sector or "").lower(),
            (company.market_industry or "").lower(),
        ]
    )
    if any(token in combined for token in ("oil", "gas", "petroleum", "refining", "drilling", "pipeline")):
        return "oil_sensitive"
    if any(token in combined for token in ("airline", "transport", "logistics", "chemicals", "industrial")):
        return "cost_sensitive"
    return "not_applicable"


def _relevance_reasons(company: Company, exposure_label: str) -> list[str]:
    if exposure_label == "not_applicable":
        return []
    reasons: list[str] = []
    if company.sector:
        reasons.append(f"sector: {company.sector}")
    if company.market_sector:
        reasons.append(f"market sector: {company.market_sector}")
    if company.market_industry:
        reasons.append(f"industry: {company.market_industry}")
    return reasons