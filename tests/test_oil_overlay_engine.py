from __future__ import annotations

import pytest

from app.services.oil_overlay_engine import (
    OilCurveYearPoint,
    OilOverlayDiscountAssumptions,
    OilOverlayEngineInputs,
    compute_oil_fair_value_overlay_payload,
)


def test_oil_overlay_engine_discounts_yearly_deltas_and_fades_to_anchor() -> None:
    payload = compute_oil_fair_value_overlay_payload(
        OilOverlayEngineInputs(
            base_fair_value_per_share=100.0,
            official_base_curve=(
                OilCurveYearPoint(year=2026, price=80.0),
                OilCurveYearPoint(year=2027, price=78.0),
                OilCurveYearPoint(year=2028, price=76.0),
            ),
            user_edited_short_term_curve=(
                OilCurveYearPoint(year=2026, price=90.0),
            ),
            user_long_term_anchor=84.0,
            fade_years=2,
            annual_after_tax_oil_sensitivity=10.0,
            diluted_shares=10.0,
            current_share_price=90.0,
            discount_assumptions=OilOverlayDiscountAssumptions(annual_discount_rate=0.10),
        )
    )

    expected_pv = (10.0 / 1.1) + (9.0 / 1.21) + (8.0 / 1.331)

    assert payload["model_status"] == "supported"
    assert payload["eps_delta_per_dollar_oil"] == 1.0
    assert payload["yearly_deltas"][0]["earnings_delta_after_tax"] == 100.0
    assert payload["yearly_deltas"][1]["scenario_oil_price"] == 87.0
    assert payload["yearly_deltas"][2]["scenario_oil_price"] == 84.0
    assert payload["overlay_pv_per_share"] == pytest.approx(expected_pv)
    assert payload["scenario_fair_value_per_share"] == pytest.approx(100.0 + expected_pv)
    assert payload["delta_vs_base_per_share"] == pytest.approx(expected_pv)
    assert payload["implied_upside_downside"] == pytest.approx(((100.0 + expected_pv) - 90.0) / 90.0)


def test_oil_overlay_engine_preserves_negative_sign_for_inverse_oil_exposure() -> None:
    payload = compute_oil_fair_value_overlay_payload(
        OilOverlayEngineInputs(
            base_fair_value_per_share=50.0,
            official_base_curve=(OilCurveYearPoint(year=2026, price=70.0),),
            user_edited_short_term_curve=(OilCurveYearPoint(year=2026, price=80.0),),
            user_long_term_anchor=80.0,
            fade_years=0,
            annual_after_tax_oil_sensitivity=-5.0,
            diluted_shares=5.0,
            discount_assumptions=OilOverlayDiscountAssumptions(annual_discount_rate=0.0),
        )
    )

    assert payload["model_status"] == "supported"
    assert payload["eps_delta_per_dollar_oil"] == -1.0
    assert payload["yearly_deltas"][0]["oil_price_delta"] == 10.0
    assert payload["yearly_deltas"][0]["earnings_delta_after_tax"] == -50.0
    assert payload["yearly_deltas"][0]["per_share_delta"] == -10.0
    assert payload["overlay_pv_per_share"] == -10.0
    assert payload["scenario_fair_value_per_share"] == 40.0


def test_oil_overlay_engine_returns_unsupported_for_unsupported_profiles() -> None:
    payload = compute_oil_fair_value_overlay_payload(
        OilOverlayEngineInputs(
            base_fair_value_per_share=75.0,
            official_base_curve=(OilCurveYearPoint(year=2026, price=80.0),),
            user_edited_short_term_curve=(OilCurveYearPoint(year=2026, price=85.0),),
            user_long_term_anchor=85.0,
            fade_years=0,
            annual_after_tax_oil_sensitivity=3.0,
            diluted_shares=10.0,
            oil_support_status="unsupported",
        )
    )

    assert payload["model_status"] == "unsupported"
    assert payload["overlay_pv_per_share"] is None
    assert payload["scenario_fair_value_per_share"] is None
    assert payload["yearly_deltas"] == []
    assert "oil_overlay_unsupported" in payload["confidence_flags"]


def test_oil_overlay_engine_marks_partial_when_confidence_is_low() -> None:
    payload = compute_oil_fair_value_overlay_payload(
        OilOverlayEngineInputs(
            base_fair_value_per_share=90.0,
            official_base_curve=(OilCurveYearPoint(year=2026, price=75.0),),
            user_edited_short_term_curve=(OilCurveYearPoint(year=2026, price=77.0),),
            user_long_term_anchor=77.0,
            fade_years=0,
            annual_after_tax_oil_sensitivity=4.0,
            diluted_shares=8.0,
            oil_support_status="partial",
            confidence_flags=("oil_sensitivity_low_confidence",),
            discount_assumptions=OilOverlayDiscountAssumptions(annual_discount_rate=0.0),
        )
    )

    assert payload["model_status"] == "partial"
    assert payload["overlay_pv_per_share"] == 1.0
    assert "oil_overlay_low_confidence" in payload["confidence_flags"]
    assert "oil_support_partial" in payload["confidence_flags"]


def test_oil_overlay_engine_applies_custom_realized_spread_for_non_disclosed_sensitivity() -> None:
    payload = compute_oil_fair_value_overlay_payload(
        OilOverlayEngineInputs(
            base_fair_value_per_share=100.0,
            official_base_curve=(OilCurveYearPoint(year=2026, price=80.0),),
            user_edited_short_term_curve=(OilCurveYearPoint(year=2026, price=90.0),),
            user_long_term_anchor=90.0,
            fade_years=0,
            annual_after_tax_oil_sensitivity=10.0,
            diluted_shares=10.0,
            sensitivity_source_kind="manual_override",
            realized_spread_mode="custom_spread",
            current_realized_spread=-4.0,
            custom_realized_spread=-1.0,
            discount_assumptions=OilOverlayDiscountAssumptions(annual_discount_rate=0.0),
        )
    )

    assert payload["yearly_deltas"][0]["oil_price_delta"] == 10.0
    assert payload["yearly_deltas"][0]["realized_price_delta"] == 13.0
    assert payload["yearly_deltas"][0]["earnings_delta_after_tax"] == 130.0
    assert payload["overlay_pv_per_share"] == 13.0


def test_oil_overlay_engine_mean_reverts_current_realized_spread() -> None:
    payload = compute_oil_fair_value_overlay_payload(
        OilOverlayEngineInputs(
            base_fair_value_per_share=100.0,
            official_base_curve=(
                OilCurveYearPoint(year=2026, price=80.0),
                OilCurveYearPoint(year=2027, price=80.0),
            ),
            user_edited_short_term_curve=(OilCurveYearPoint(year=2026, price=90.0),),
            user_long_term_anchor=90.0,
            fade_years=0,
            annual_after_tax_oil_sensitivity=10.0,
            diluted_shares=10.0,
            sensitivity_source_kind="manual_override",
            realized_spread_mode="mean_revert",
            current_realized_spread=-4.0,
            mean_reversion_target_spread=0.0,
            mean_reversion_years=2,
            discount_assumptions=OilOverlayDiscountAssumptions(annual_discount_rate=0.0),
        )
    )

    assert payload["yearly_deltas"][0]["realized_price_delta"] == 12.0
    assert payload["yearly_deltas"][1]["realized_price_delta"] == 14.0


def test_oil_overlay_engine_falls_back_to_benchmark_only_when_current_spread_missing() -> None:
    payload = compute_oil_fair_value_overlay_payload(
        OilOverlayEngineInputs(
            base_fair_value_per_share=100.0,
            official_base_curve=(OilCurveYearPoint(year=2026, price=80.0),),
            user_edited_short_term_curve=(OilCurveYearPoint(year=2026, price=90.0),),
            user_long_term_anchor=90.0,
            fade_years=0,
            annual_after_tax_oil_sensitivity=10.0,
            diluted_shares=10.0,
            sensitivity_source_kind="manual_override",
            realized_spread_mode="hold_current_spread",
            current_realized_spread=None,
            discount_assumptions=OilOverlayDiscountAssumptions(annual_discount_rate=0.0),
        )
    )

    assert payload["yearly_deltas"][0]["realized_price_delta"] == 10.0
    assert "realized_spread_fallback_benchmark_only" in payload["confidence_flags"]