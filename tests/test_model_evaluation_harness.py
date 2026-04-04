from __future__ import annotations

import pytest

from app.services.model_evaluation import (
    FIXTURE_SUITE_KEY,
    OIL_OVERLAY_ADJUSTED_MODEL,
    OIL_OVERLAY_BASE_MODEL,
    OIL_OVERLAY_FIXTURE_SUITE_KEY,
    build_baseline_payload,
    build_fixed_risk_free_provider,
    load_fixture_bundles,
    load_oil_overlay_fixture_bundles,
    run_model_evaluation,
    run_oil_overlay_point_in_time_evaluation,
)


def test_fixture_model_evaluation_produces_metrics_for_requested_models() -> None:
    result = run_model_evaluation(
        bundles=load_fixture_bundles(FIXTURE_SUITE_KEY),
        suite_key=FIXTURE_SUITE_KEY,
        candidate_label="pytest",
        risk_free_rate_provider=build_fixed_risk_free_provider(),
    )

    assert set(result["metrics"]) == {"dcf", "reverse_dcf", "residual_income", "roic", "earnings"}
    assert result["summary"]["company_count"] == 2
    assert result["summary"]["snapshot_count"] > 0
    assert result["summary"]["provenance_mode"] == "synthetic_fixture"
    assert result["summary"]["latest_as_of"] is not None
    assert result["metrics"]["dcf"]["sample_count"] > 0
    assert result["metrics"]["reverse_dcf"]["mean_absolute_error"] is not None
    assert result["metrics"]["earnings"]["calibration"] is not None


def test_fixture_model_evaluation_reports_deltas_against_baseline() -> None:
    baseline_result = run_model_evaluation(
        bundles=load_fixture_bundles(FIXTURE_SUITE_KEY),
        suite_key=FIXTURE_SUITE_KEY,
        candidate_label="baseline",
        risk_free_rate_provider=build_fixed_risk_free_provider(),
    )
    baseline = build_baseline_payload(baseline_result)
    baseline["metrics"]["dcf"]["mean_absolute_error"] = round(baseline["metrics"]["dcf"]["mean_absolute_error"] - 0.01, 6)

    candidate_result = run_model_evaluation(
        bundles=load_fixture_bundles(FIXTURE_SUITE_KEY),
        suite_key=FIXTURE_SUITE_KEY,
        candidate_label="candidate",
        baseline=baseline,
        risk_free_rate_provider=build_fixed_risk_free_provider(),
    )

    assert candidate_result["deltas_present"] is True
    assert candidate_result["deltas"]["dcf"]["mean_absolute_error"] == pytest.approx(0.01, rel=1e-6)


def test_oil_overlay_fixture_evaluation_produces_point_in_time_summary_and_artifacts() -> None:
    result = run_oil_overlay_point_in_time_evaluation(
        bundles=load_oil_overlay_fixture_bundles(OIL_OVERLAY_FIXTURE_SUITE_KEY),
        suite_key=OIL_OVERLAY_FIXTURE_SUITE_KEY,
        candidate_label="pytest_oil_overlay",
    )

    assert set(result["metrics"]) == {OIL_OVERLAY_BASE_MODEL, OIL_OVERLAY_ADJUSTED_MODEL}
    assert result["summary"]["evaluation_focus"] == "oil_overlay"
    assert result["summary"]["provenance_mode"] == "synthetic_fixture"
    assert result["summary"]["snapshot_count"] > 0
    assert result["summary"]["comparison"]["sample_count"] == result["summary"]["snapshot_count"]
    assert result["artifacts"]["comparison"]["sample_count"] == result["summary"]["snapshot_count"]
    assert set(result["artifacts"]["company_summaries"]) == {"OXYF", "XOMF"}
    assert result["artifacts"]["company_summaries"]["XOMF"]["latest_as_of"] is not None
    assert result["metrics"][OIL_OVERLAY_ADJUSTED_MODEL]["sample_count"] > 0


def test_oil_overlay_fixture_evaluation_reports_deltas_against_baseline() -> None:
    baseline_result = run_oil_overlay_point_in_time_evaluation(
        bundles=load_oil_overlay_fixture_bundles(OIL_OVERLAY_FIXTURE_SUITE_KEY),
        suite_key=OIL_OVERLAY_FIXTURE_SUITE_KEY,
        candidate_label="baseline_oil_overlay",
    )
    baseline = build_baseline_payload(baseline_result)
    baseline["metrics"][OIL_OVERLAY_ADJUSTED_MODEL]["mean_absolute_error"] = round(
        baseline["metrics"][OIL_OVERLAY_ADJUSTED_MODEL]["mean_absolute_error"] - 0.02,
        6,
    )

    candidate_result = run_oil_overlay_point_in_time_evaluation(
        bundles=load_oil_overlay_fixture_bundles(OIL_OVERLAY_FIXTURE_SUITE_KEY),
        suite_key=OIL_OVERLAY_FIXTURE_SUITE_KEY,
        candidate_label="candidate_oil_overlay",
        baseline=baseline,
    )

    assert candidate_result["deltas_present"] is True
    assert candidate_result["deltas"][OIL_OVERLAY_ADJUSTED_MODEL]["mean_absolute_error"] == pytest.approx(0.02, rel=1e-6)
