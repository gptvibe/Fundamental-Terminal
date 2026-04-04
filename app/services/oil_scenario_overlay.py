from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import settings
from app.models.company import Company
from app.services.official_oil_inputs import fetch_official_oil_inputs
from app.services.oil_company_evidence import collect_company_oil_evidence
from app.services.oil_exposure import classify_company_oil_exposure
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
    direct_company_evidence: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    confidence_flags: tuple[str, ...] = field(default_factory=tuple)
    provenance: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    source_mix: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return _json_safe(
            {
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
            "direct_company_evidence": self.direct_company_evidence,
            "diagnostics": self.diagnostics,
            "confidence_flags": list(self.confidence_flags),
            "provenance": list(self.provenance),
            "source_mix": self.source_mix,
            }
        )


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


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
        overlay = _build_refreshed_overlay(company, checked_at=checked_at)
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
    oil_classification = classify_company_oil_exposure(company, strict_official_mode=strict_official_mode)
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
    confidence_flags = ["oil_curve_placeholder", "oil_sensitivity_placeholder"]
    if strict_official_mode:
        confidence_flags.append("strict_official_mode")
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
        status=(
            "supported"
            if oil_classification.oil_support_status == "supported"
            else "partial"
            if oil_classification.oil_support_status == "partial"
            else "not_applicable"
        ),
        fetched_at=checked_at,
        as_of=checked_at.date().isoformat(),
        last_refreshed_at=checked_at,
        strict_official_mode=strict_official_mode,
        exposure_profile={
            "profile_id": oil_classification.oil_exposure_type,
            "label": oil_classification.oil_exposure_type.replace("_", " ").title(),
            "oil_exposure_type": oil_classification.oil_exposure_type,
            "oil_support_status": oil_classification.oil_support_status,
            "oil_support_reasons": list(oil_classification.oil_support_reasons),
            "relevance_reasons": _relevance_reasons(company, oil_classification),
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
        direct_company_evidence={
            "status": "not_available",
            "checked_at": checked_at.isoformat(),
            "parser_confidence_flags": ["oil_company_evidence_not_available"],
            "disclosed_sensitivity": {
                "status": "not_available",
                "reason": "Direct SEC oil evidence is not cached yet.",
                "confidence_flags": ["oil_sensitivity_not_available"],
                "provenance_sources": ["sec_edgar"],
            },
            "diluted_shares": {
                "status": "not_available",
                "reason": "Direct SEC oil evidence is not cached yet.",
                "confidence_flags": ["diluted_shares_not_available"],
                "provenance_sources": ["sec_companyfacts"],
            },
            "realized_price_comparison": {
                "status": "not_available",
                "reason": "Direct SEC oil evidence is not cached yet.",
                "benchmark": None,
                "rows": [],
                "confidence_flags": ["realized_vs_benchmark_not_available"],
                "provenance_sources": ["sec_edgar"],
            },
        },
        diagnostics=diagnostics,
        confidence_flags=tuple(confidence_flags),
        provenance=provenance,
        source_mix=source_mix,
    )


def _build_refreshed_overlay(company: Company, *, checked_at: datetime) -> OilScenarioOverlayDTO:
    strict_official_mode = settings.strict_official_mode
    oil_classification = classify_company_oil_exposure(company, strict_official_mode=strict_official_mode)
    official_oil_inputs = fetch_official_oil_inputs(now=checked_at)
    direct_company_evidence = collect_company_oil_evidence(company.cik, checked_at=checked_at)
    benchmark_series = _benchmark_series_from_official_inputs(official_oil_inputs)
    sensitivity = _sensitivity_from_direct_evidence(direct_company_evidence)
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
    if direct_company_evidence.get("diluted_shares", {}).get("status") == "available":
        usages.append(
            SourceUsage(
                source_id="sec_companyfacts",
                role="supplemental",
                as_of=checked_at.date().isoformat(),
                last_refreshed_at=checked_at,
            )
        )

    provenance = _merge_provenance_entries(list(official_oil_inputs.provenance), usages)
    source_mix = build_source_mix(provenance)
    confidence_flags = {
        *[str(flag) for flag in official_oil_inputs.confidence_flags],
        *[str(flag) for flag in (direct_company_evidence.get("parser_confidence_flags") or []) if isinstance(flag, str)],
    }
    if sensitivity is None:
        confidence_flags.add("oil_sensitivity_placeholder")
        confidence_flags.add("sensitivity_not_computed")
    if strict_official_mode:
        confidence_flags.add("strict_official_mode")

    baseline_series = [series for series in benchmark_series if "short_term_baseline" in series.series_id]
    diagnostics_missing_flags: list[str] = []
    if not baseline_series:
        diagnostics_missing_flags.append("official_oil_curve_missing")
    if sensitivity is None:
        diagnostics_missing_flags.append("sensitivity_not_computed")
    if direct_company_evidence.get("disclosed_sensitivity", {}).get("status") != "available":
        diagnostics_missing_flags.append("oil_sensitivity_disclosure_not_available")
    if direct_company_evidence.get("realized_price_comparison", {}).get("status") != "available":
        diagnostics_missing_flags.append("realized_vs_benchmark_not_available")
    if direct_company_evidence.get("diluted_shares", {}).get("status") != "available":
        diagnostics_missing_flags.append("diluted_shares_not_available")

    return OilScenarioOverlayDTO(
        status=(
            "supported"
            if oil_classification.oil_support_status == "supported"
            else "partial"
            if oil_classification.oil_support_status == "partial"
            else "not_applicable"
        ),
        fetched_at=checked_at,
        as_of=official_oil_inputs.as_of or checked_at.date().isoformat(),
        last_refreshed_at=checked_at,
        strict_official_mode=strict_official_mode,
        exposure_profile={
            "profile_id": oil_classification.oil_exposure_type,
            "label": oil_classification.oil_exposure_type.replace("_", " ").title(),
            "oil_exposure_type": oil_classification.oil_exposure_type,
            "oil_support_status": oil_classification.oil_support_status,
            "oil_support_reasons": list(oil_classification.oil_support_reasons),
            "relevance_reasons": _relevance_reasons(company, oil_classification),
            "hedging_signal": "unknown",
            "pass_through_signal": "unknown",
            "evidence": [],
        },
        benchmark_series=tuple(benchmark_series) if benchmark_series else _build_placeholder_overlay(company, checked_at=checked_at).benchmark_series,
        scenarios=(
            OilScenarioCaseDTO(
                scenario_id="bear",
                label="Bear",
                benchmark_value=None,
                benchmark_delta_percent=None,
                revenue_delta_percent=None,
                operating_margin_delta_bps=None,
                free_cash_flow_delta_percent=None,
                confidence_flags=("scenario_inputs_pending",),
            ),
            OilScenarioCaseDTO(
                scenario_id="base",
                label="Base",
                benchmark_value=None,
                benchmark_delta_percent=0.0,
                revenue_delta_percent=None,
                operating_margin_delta_bps=None,
                free_cash_flow_delta_percent=None,
                confidence_flags=("scenario_inputs_pending",),
            ),
            OilScenarioCaseDTO(
                scenario_id="bull",
                label="Bull",
                benchmark_value=None,
                benchmark_delta_percent=None,
                revenue_delta_percent=None,
                operating_margin_delta_bps=None,
                free_cash_flow_delta_percent=None,
                confidence_flags=("scenario_inputs_pending",),
            ),
        ),
        sensitivity=sensitivity
        if sensitivity is not None
        else OilSensitivityDTO(
            metric_basis="annual_after_tax_earnings_usd",
            lookback_quarters=0,
            elasticity=None,
            r_squared=None,
            sample_size=0,
            direction="unknown",
            status="not_available",
            confidence_flags=tuple(
                str(flag)
                for flag in (direct_company_evidence.get("disclosed_sensitivity", {}).get("confidence_flags") or ["sensitivity_not_computed"])
                if isinstance(flag, str)
            ),
        ),
        direct_company_evidence=direct_company_evidence,
        diagnostics={
            "coverage_ratio": 0.0,
            "fallback_ratio": 0.0,
            "stale_flags": list(official_oil_inputs.freshness.get("stale_flags") or []),
            "parser_confidence": None,
            "missing_field_flags": diagnostics_missing_flags,
            "reconciliation_penalty": None,
            "reconciliation_disagreement_count": 0,
        },
        confidence_flags=tuple(sorted(confidence_flags)),
        provenance=tuple(provenance),
        source_mix=source_mix,
    )


def _benchmark_series_from_official_inputs(official_oil_inputs: Any) -> list[OilCurveSeriesDTO]:
    output: list[OilCurveSeriesDTO] = []
    for series in (*tuple(official_oil_inputs.spot_history), *tuple(official_oil_inputs.short_term_baseline)):
        output.append(
            OilCurveSeriesDTO(
                series_id=series.series_id,
                label=series.label,
                units=series.units,
                status=series.status,
                points=tuple(
                    OilCurvePointDTO(
                        label=point.label,
                        value=point.value,
                        units=point.units,
                        observation_date=point.observation_date,
                    )
                    for point in series.points
                ),
                latest_value=series.latest_value,
                latest_observation_date=series.latest_observation_date,
            )
        )
    return output


def _sensitivity_from_direct_evidence(direct_company_evidence: dict[str, Any]) -> OilSensitivityDTO | None:
    disclosed = direct_company_evidence.get("disclosed_sensitivity") if isinstance(direct_company_evidence, dict) else None
    if not isinstance(disclosed, dict) or disclosed.get("status") != "available":
        return None
    elasticity = disclosed.get("annual_after_tax_sensitivity")
    return OilSensitivityDTO(
        metric_basis=str(disclosed.get("metric_basis") or "annual_after_tax_earnings_usd"),
        lookback_quarters=0,
        elasticity=float(elasticity) if isinstance(elasticity, (int, float)) else None,
        r_squared=None,
        sample_size=1,
        direction="positive_with_higher_oil",
        status="disclosed",
        confidence_flags=tuple(
            str(flag) for flag in (disclosed.get("confidence_flags") or []) if isinstance(flag, str)
        ),
    )


def _merge_provenance_entries(existing_entries: list[dict[str, Any]], usages: list[SourceUsage]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in existing_entries:
        if not isinstance(entry, dict):
            continue
        source_id = str(entry.get("source_id") or "").strip()
        if not source_id or source_id in seen:
            continue
        merged.append(entry)
        seen.add(source_id)
    for entry in build_provenance_entries(usages):
        source_id = str(entry.get("source_id") or "").strip()
        if not source_id or source_id in seen:
            continue
        merged.append(entry)
        seen.add(source_id)
    return merged


def _relevance_reasons(company: Company, oil_classification: Any) -> list[str]:
    reasons = [str(reason) for reason in oil_classification.oil_support_reasons if reason]
    return reasons