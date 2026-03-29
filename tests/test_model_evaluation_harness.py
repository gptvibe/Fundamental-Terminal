from __future__ import annotations

import pytest

from app.services.model_evaluation import (
    FIXTURE_SUITE_KEY,
    build_baseline_payload,
    build_fixed_risk_free_provider,
    load_fixture_bundles,
    run_model_evaluation,
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
