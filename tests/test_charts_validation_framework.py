from __future__ import annotations

import json

from app.services.charts_validation import (
    GOLDEN_SNAPSHOT_PATH,
    build_validation_basket,
    build_validation_summary,
    compute_golden_snapshot,
    validate_accounting_identities,
    validate_labeling_consistency,
    validate_override_clipping,
    validate_sensitivity_matrix,
)


EXPECTED_CATEGORIES = {
    "megacap_tech",
    "cyclical_industrial",
    "retailer",
    "capital_light_software",
    "bank_financial",
    "biotech_high_volatility",
}


def test_validation_basket_covers_required_segments() -> None:
    basket = build_validation_basket()
    categories = {case.category for case in basket}
    assert categories == EXPECTED_CATEGORIES


def test_golden_regression_snapshot_matches_current_engine_outputs() -> None:
    expected = json.loads(GOLDEN_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    observed = compute_golden_snapshot(build_validation_basket())
    assert observed == expected


def test_reported_vs_projected_labeling_consistency() -> None:
    basket = build_validation_basket()
    for case in basket:
        assert validate_labeling_consistency(case) == []


def test_accounting_identity_and_fcf_consistency_for_non_regulated_cases() -> None:
    basket = [case for case in build_validation_basket() if case.category != "bank_financial"]
    for case in basket:
        assert validate_accounting_identities(case) == []


def test_override_clipping_behavior_is_enforced() -> None:
    basket = [case for case in build_validation_basket() if case.category != "bank_financial"]
    for case in basket:
        assert validate_override_clipping(case) == []


def test_sensitivity_matrix_shape_and_monotonicity() -> None:
    basket = build_validation_basket()
    for case in basket:
        assert validate_sensitivity_matrix(case) == []


def test_benchmark_summary_contains_naive_baseline_comparisons() -> None:
    summary = build_validation_summary()
    rows = summary["benchmarks"]
    assert rows

    for row in rows:
        assert "model" in row
        assert "baselines" in row
        assert "last_value_carry_forward" in row["baselines"]
        assert "trailing_cagr" in row["baselines"]
        assert "management_guidance" in row["baselines"]

    benchmark_summary = summary["benchmark_summary"]
    assert benchmark_summary["non_regulated_case_count"] >= 5
