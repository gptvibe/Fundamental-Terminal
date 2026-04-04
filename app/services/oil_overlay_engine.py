from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.model_engine.utils import json_number, safe_divide


OilOverlayModelStatus = Literal["supported", "partial", "insufficient_data", "unsupported"]
OilSupportStatus = Literal["supported", "partial", "unsupported"]
DiscountingConvention = Literal["year_end"]
OilSensitivitySourceKind = Literal["disclosed", "derived_from_official", "manual_override"]
RealizedSpreadMode = Literal["hold_current_spread", "mean_revert", "custom_spread", "benchmark_only"]

_LOW_CONFIDENCE_FLAGS = {
    "oil_sensitivity_low_confidence",
    "oil_curve_partial",
    "oil_curve_interpolated",
    "oil_support_partial",
}


@dataclass(frozen=True, slots=True)
class OilCurveYearPoint:
    year: int
    price: float


@dataclass(frozen=True, slots=True)
class OilOverlayDiscountAssumptions:
    annual_discount_rate: float
    discounting_convention: DiscountingConvention = "year_end"


@dataclass(frozen=True, slots=True)
class OilOverlayEngineInputs:
    base_fair_value_per_share: float | None
    official_base_curve: tuple[OilCurveYearPoint, ...]
    user_edited_short_term_curve: tuple[OilCurveYearPoint, ...]
    user_long_term_anchor: float | None
    fade_years: int
    annual_after_tax_oil_sensitivity: float | None
    diluted_shares: float | None
    sensitivity_source_kind: OilSensitivitySourceKind = "manual_override"
    current_share_price: float | None = None
    realized_spread_mode: RealizedSpreadMode = "benchmark_only"
    current_realized_spread: float | None = None
    custom_realized_spread: float | None = None
    mean_reversion_target_spread: float = 0.0
    mean_reversion_years: int = 3
    realized_spread_reference_benchmark: str | None = None
    discount_assumptions: OilOverlayDiscountAssumptions = field(
        default_factory=lambda: OilOverlayDiscountAssumptions(annual_discount_rate=0.1)
    )
    oil_support_status: OilSupportStatus = "supported"
    confidence_flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OilOverlayYearResult:
    year: int
    base_oil_price: float
    scenario_oil_price: float
    oil_price_delta: float
    base_realized_price: float
    scenario_realized_price: float
    realized_price_delta: float
    earnings_delta_after_tax: float
    per_share_delta: float
    present_value_per_share: float
    discount_factor: float


@dataclass(frozen=True, slots=True)
class OilOverlayEngineResult:
    status: OilOverlayModelStatus
    model_status: OilOverlayModelStatus
    reason: str
    base_fair_value_per_share: float | None
    eps_delta_per_dollar_oil: float | None
    overlay_pv_per_share: float | None
    scenario_fair_value_per_share: float | None
    delta_vs_base_per_share: float | None
    delta_vs_base_percent: float | None
    implied_upside_downside: float | None
    yearly_deltas: tuple[OilOverlayYearResult, ...] = field(default_factory=tuple)
    assumptions: dict[str, Any] = field(default_factory=dict)
    confidence_flags: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "model_status": self.model_status,
            "reason": self.reason,
            "base_fair_value_per_share": json_number(self.base_fair_value_per_share),
            "eps_delta_per_dollar_oil": json_number(self.eps_delta_per_dollar_oil),
            "overlay_pv_per_share": json_number(self.overlay_pv_per_share),
            "scenario_fair_value_per_share": json_number(self.scenario_fair_value_per_share),
            "delta_vs_base_per_share": json_number(self.delta_vs_base_per_share),
            "delta_vs_base_percent": json_number(self.delta_vs_base_percent),
            "implied_upside_downside": json_number(self.implied_upside_downside),
            "yearly_deltas": [
                {
                    "year": item.year,
                    "base_oil_price": json_number(item.base_oil_price),
                    "scenario_oil_price": json_number(item.scenario_oil_price),
                    "oil_price_delta": json_number(item.oil_price_delta),
                    "base_realized_price": json_number(item.base_realized_price),
                    "scenario_realized_price": json_number(item.scenario_realized_price),
                    "realized_price_delta": json_number(item.realized_price_delta),
                    "earnings_delta_after_tax": json_number(item.earnings_delta_after_tax),
                    "per_share_delta": json_number(item.per_share_delta),
                    "present_value_per_share": json_number(item.present_value_per_share),
                    "discount_factor": json_number(item.discount_factor),
                }
                for item in self.yearly_deltas
            ],
            "assumptions": self.assumptions,
            "confidence_flags": list(self.confidence_flags),
        }


def compute_oil_fair_value_overlay(inputs: OilOverlayEngineInputs) -> OilOverlayEngineResult:
    validation_error = _validate_inputs(inputs)
    if validation_error is not None:
        return OilOverlayEngineResult(
            status="insufficient_data",
            model_status="insufficient_data",
            reason=validation_error,
            base_fair_value_per_share=inputs.base_fair_value_per_share,
            eps_delta_per_dollar_oil=None,
            overlay_pv_per_share=None,
            scenario_fair_value_per_share=None,
            delta_vs_base_per_share=None,
            delta_vs_base_percent=None,
            implied_upside_downside=None,
            assumptions=_assumptions_payload(inputs),
            confidence_flags=tuple(sorted(set(inputs.confidence_flags) | {"oil_overlay_missing_inputs"})),
        )

    if inputs.oil_support_status == "unsupported":
        return OilOverlayEngineResult(
            status="unsupported",
            model_status="unsupported",
            reason="Oil overlay is disabled for unsupported oil-exposure profiles.",
            base_fair_value_per_share=inputs.base_fair_value_per_share,
            eps_delta_per_dollar_oil=None,
            overlay_pv_per_share=None,
            scenario_fair_value_per_share=None,
            delta_vs_base_per_share=None,
            delta_vs_base_percent=None,
            implied_upside_downside=None,
            assumptions=_assumptions_payload(inputs),
            confidence_flags=tuple(sorted(set(inputs.confidence_flags) | {"oil_overlay_unsupported"})),
        )

    base_curve = _dedupe_curve(inputs.official_base_curve)
    user_curve = _dedupe_curve(inputs.user_edited_short_term_curve)
    base_reference_spread = float(inputs.current_realized_spread) if inputs.current_realized_spread is not None else 0.0
    effective_spread_mode, spread_flags = _resolve_effective_spread_mode(inputs)
    start_year = min(min(base_curve), min(user_curve))
    end_year = max(max(base_curve), max(user_curve) + inputs.fade_years)

    yearly_deltas: list[OilOverlayYearResult] = []
    overlay_pv_per_share = 0.0
    for year_index, year in enumerate(range(start_year, end_year + 1), start=1):
        base_oil_price = _evaluate_base_curve(base_curve, year)
        scenario_oil_price = _evaluate_scenario_curve(
            year=year,
            base_curve=base_curve,
            user_curve=user_curve,
            long_term_anchor=float(inputs.user_long_term_anchor),
            fade_years=inputs.fade_years,
        )
        oil_price_delta = scenario_oil_price - base_oil_price
        scenario_spread = _scenario_realized_spread(
            year=year,
            start_year=start_year,
            inputs=inputs,
            effective_mode=effective_spread_mode,
            base_reference_spread=base_reference_spread,
        )
        base_realized_price = base_oil_price + base_reference_spread
        scenario_realized_price = scenario_oil_price + scenario_spread
        realized_price_delta = scenario_realized_price - base_realized_price
        earnings_price_delta = oil_price_delta if inputs.sensitivity_source_kind == "disclosed" else realized_price_delta
        earnings_delta_after_tax = float(inputs.annual_after_tax_oil_sensitivity) * earnings_price_delta
        per_share_delta = earnings_delta_after_tax / float(inputs.diluted_shares)
        discount_factor = (1 + inputs.discount_assumptions.annual_discount_rate) ** year_index
        present_value_per_share = per_share_delta / discount_factor
        overlay_pv_per_share += present_value_per_share
        yearly_deltas.append(
            OilOverlayYearResult(
                year=year,
                base_oil_price=base_oil_price,
                scenario_oil_price=scenario_oil_price,
                oil_price_delta=oil_price_delta,
                base_realized_price=base_realized_price,
                scenario_realized_price=scenario_realized_price,
                realized_price_delta=realized_price_delta,
                earnings_delta_after_tax=earnings_delta_after_tax,
                per_share_delta=per_share_delta,
                present_value_per_share=present_value_per_share,
                discount_factor=discount_factor,
            )
        )

    eps_delta_per_dollar_oil = safe_divide(inputs.annual_after_tax_oil_sensitivity, inputs.diluted_shares)
    scenario_fair_value_per_share = float(inputs.base_fair_value_per_share) + overlay_pv_per_share
    delta_vs_base_per_share = overlay_pv_per_share
    delta_vs_base_percent = safe_divide(delta_vs_base_per_share, inputs.base_fair_value_per_share)
    implied_upside_downside = (
        safe_divide(
            scenario_fair_value_per_share - inputs.current_share_price,
            inputs.current_share_price,
        )
        if inputs.current_share_price is not None
        else None
    )

    derived_flags = set(inputs.confidence_flags)
    derived_flags.update(spread_flags)
    if inputs.oil_support_status == "partial":
        derived_flags.add("oil_support_partial")
    if any(flag in _LOW_CONFIDENCE_FLAGS for flag in derived_flags):
        derived_flags.add("oil_overlay_low_confidence")
        model_status: OilOverlayModelStatus = "partial"
    else:
        model_status = "supported"

    return OilOverlayEngineResult(
        status=model_status,
        model_status=model_status,
        reason="Fair-value overlay computed as discounted per-share earnings deltas on top of the base model output.",
        base_fair_value_per_share=float(inputs.base_fair_value_per_share),
        eps_delta_per_dollar_oil=eps_delta_per_dollar_oil,
        overlay_pv_per_share=overlay_pv_per_share,
        scenario_fair_value_per_share=scenario_fair_value_per_share,
        delta_vs_base_per_share=delta_vs_base_per_share,
        delta_vs_base_percent=delta_vs_base_percent,
        implied_upside_downside=implied_upside_downside,
        yearly_deltas=tuple(yearly_deltas),
        assumptions=_assumptions_payload(inputs),
        confidence_flags=tuple(sorted(derived_flags)),
    )


def compute_oil_fair_value_overlay_payload(inputs: OilOverlayEngineInputs) -> dict[str, Any]:
    return compute_oil_fair_value_overlay(inputs).to_payload()


def _validate_inputs(inputs: OilOverlayEngineInputs) -> str | None:
    if inputs.base_fair_value_per_share is None:
        return "Base fair value per share is required for the overlay engine."
    if not inputs.official_base_curve:
        return "Official base oil curve is required for the overlay engine."
    if not inputs.user_edited_short_term_curve:
        return "User-edited short-term oil curve is required for the overlay engine."
    if inputs.user_long_term_anchor is None:
        return "User long-term oil anchor is required for the overlay engine."
    if inputs.fade_years < 0:
        return "Fade years must be zero or greater."
    if inputs.annual_after_tax_oil_sensitivity is None:
        return "Annual after-tax oil sensitivity is required for the overlay engine."
    if inputs.diluted_shares in (None, 0):
        return "Diluted shares are required for per-share overlay calculations."
    if inputs.mean_reversion_years < 0:
        return "Mean reversion years must be zero or greater."
    if inputs.realized_spread_mode == "custom_spread" and inputs.custom_realized_spread is None:
        return "Custom realized spread is required when custom spread mode is selected."
    if inputs.discount_assumptions.annual_discount_rate <= -1.0:
        return "Annual discount rate must be greater than -100%."
    return None


def _dedupe_curve(points: tuple[OilCurveYearPoint, ...]) -> dict[int, float]:
    deduped: dict[int, float] = {}
    for point in sorted(points, key=lambda item: item.year):
        deduped[int(point.year)] = float(point.price)
    return deduped


def _evaluate_base_curve(points: dict[int, float], year: int) -> float:
    return _interpolate_curve(points, year)


def _evaluate_scenario_curve(
    *,
    year: int,
    base_curve: dict[int, float],
    user_curve: dict[int, float],
    long_term_anchor: float,
    fade_years: int,
) -> float:
    first_user_year = min(user_curve)
    last_user_year = max(user_curve)
    if year < first_user_year:
        return _evaluate_base_curve(base_curve, year)
    if year <= last_user_year:
        return _interpolate_curve(user_curve, year)
    if fade_years == 0:
        return long_term_anchor
    fade_end_year = last_user_year + fade_years
    if year <= fade_end_year:
        start_price = _interpolate_curve(user_curve, last_user_year)
        fade_progress = (year - last_user_year) / fade_years
        return start_price + (long_term_anchor - start_price) * fade_progress
    return long_term_anchor


def _interpolate_curve(points: dict[int, float], year: int) -> float:
    if year in points:
        return points[year]

    ordered_years = sorted(points)
    if year <= ordered_years[0]:
        return points[ordered_years[0]]
    if year >= ordered_years[-1]:
        return points[ordered_years[-1]]

    previous_year = ordered_years[0]
    next_year = ordered_years[-1]
    for candidate in ordered_years:
        if candidate < year:
            previous_year = candidate
            continue
        next_year = candidate
        break

    previous_value = points[previous_year]
    next_value = points[next_year]
    span = next_year - previous_year
    if span <= 0:
        return previous_value
    progress = (year - previous_year) / span
    return previous_value + (next_value - previous_value) * progress


def _assumptions_payload(inputs: OilOverlayEngineInputs) -> dict[str, Any]:
    effective_spread_mode, _flags = _resolve_effective_spread_mode(inputs)
    return {
        "discount_rate": json_number(inputs.discount_assumptions.annual_discount_rate),
        "discounting_convention": inputs.discount_assumptions.discounting_convention,
        "fade_years": inputs.fade_years,
        "user_long_term_anchor": json_number(inputs.user_long_term_anchor),
        "annual_after_tax_oil_sensitivity": json_number(inputs.annual_after_tax_oil_sensitivity),
        "sensitivity_source_kind": inputs.sensitivity_source_kind,
        "earnings_delta_basis": "benchmark_price_delta" if inputs.sensitivity_source_kind == "disclosed" else "realized_price_delta",
        "diluted_shares": json_number(inputs.diluted_shares),
        "current_share_price": json_number(inputs.current_share_price),
        "realized_spread_mode": effective_spread_mode,
        "requested_realized_spread_mode": inputs.realized_spread_mode,
        "current_realized_spread": json_number(inputs.current_realized_spread),
        "custom_realized_spread": json_number(inputs.custom_realized_spread),
        "mean_reversion_target_spread": json_number(inputs.mean_reversion_target_spread),
        "mean_reversion_years": inputs.mean_reversion_years,
        "realized_spread_reference_benchmark": inputs.realized_spread_reference_benchmark,
        "oil_support_status": inputs.oil_support_status,
    }


def _resolve_effective_spread_mode(inputs: OilOverlayEngineInputs) -> tuple[RealizedSpreadMode, tuple[str, ...]]:
    mode = inputs.realized_spread_mode
    if mode == "custom_spread":
        return mode, tuple()
    if mode in {"hold_current_spread", "mean_revert"} and inputs.current_realized_spread is None:
        return "benchmark_only", ("realized_spread_fallback_benchmark_only", "realized_spread_not_available")
    return mode, tuple()


def _scenario_realized_spread(
    *,
    year: int,
    start_year: int,
    inputs: OilOverlayEngineInputs,
    effective_mode: RealizedSpreadMode,
    base_reference_spread: float,
) -> float:
    if effective_mode in {"benchmark_only", "hold_current_spread"}:
        return base_reference_spread
    if effective_mode == "custom_spread":
        return float(inputs.custom_realized_spread or 0.0)
    if inputs.mean_reversion_years == 0:
        return float(inputs.mean_reversion_target_spread)

    elapsed_years = max(0, year - start_year + 1)
    progress = min(1.0, elapsed_years / inputs.mean_reversion_years)
    return base_reference_spread + (float(inputs.mean_reversion_target_spread) - base_reference_spread) * progress