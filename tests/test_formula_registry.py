from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

import app.model_engine.models.dcf as dcf_model
import app.model_engine.models.reverse_dcf as reverse_dcf_model
import app.model_engine.models.roic as roic_model
from app.model_engine.registry import MODEL_REGISTRY
from app.services.derived_metrics import METRIC_KEYS, build_metrics_timeseries
from app.services.formula_registry import formula_id_for_derived_metric, get_formula_metadata
from tests.test_calculation_audit_goldens import _build_company_dataset, _build_price_rows, _build_statement_rows, _case_index


def _mock_risk_free(*_args, **_kwargs):
    return type(
        "RiskFreeSnapshot",
        (),
        {
            "source_name": "U.S. Treasury Daily Par Yield Curve",
            "tenor": "10y",
            "observation_date": date(2026, 3, 20),
            "rate_used": 0.042,
            "fetched_at": datetime(2026, 3, 21, tzinfo=timezone.utc),
        },
    )()


@pytest.fixture(autouse=True)
def _fixed_risk_free(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)
    monkeypatch.setattr(reverse_dcf_model, "get_latest_risk_free_rate", _mock_risk_free)
    monkeypatch.setattr(roic_model, "get_latest_risk_free_rate", _mock_risk_free)


def _assert_metadata_complete(formula_id: str) -> None:
    metadata = get_formula_metadata(formula_id)
    assert metadata is not None, f"missing metadata for {formula_id}"
    assert metadata.formula_id == formula_id
    assert metadata.formula_version
    assert metadata.human_readable_formula
    assert metadata.input_fields
    assert metadata.source_periods
    assert metadata.proxy_fallback_flags
    assert metadata.missing_input_behavior


def test_all_derived_metric_keys_have_complete_formula_metadata() -> None:
    for metric_key in METRIC_KEYS:
        _assert_metadata_complete(formula_id_for_derived_metric(metric_key))


def test_emitted_derived_metric_formula_ids_resolve_to_complete_metadata() -> None:
    case = _case_index()["standard_tech"]
    series = build_metrics_timeseries(_build_statement_rows(case), _build_price_rows(case))

    emitted_formula_ids = {
        formula_id
        for point in series
        for formula_id in (point.get("provenance") or {}).get("formula_ids", {}).values()
        if isinstance(formula_id, str) and formula_id
    }

    assert emitted_formula_ids
    for formula_id in emitted_formula_ids:
        _assert_metadata_complete(formula_id)


def test_emitted_model_formula_ids_resolve_to_complete_metadata() -> None:
    case = _case_index()["standard_tech"]
    dataset = _build_company_dataset(case)

    for model_name, definition in MODEL_REGISTRY.items():
        result = definition.compute(dataset)
        formula_ids = result.get("formula_ids")
        assert isinstance(formula_ids, dict)
        assert formula_ids, f"expected formula ids for {model_name}"
        for formula_id in formula_ids.values():
            assert isinstance(formula_id, str) and formula_id
            _assert_metadata_complete(formula_id)


def test_model_formula_ids_only_cover_explainable_outputs() -> None:
    case = _case_index()["standard_tech"]
    dataset = _build_company_dataset(case)

    dcf_result = MODEL_REGISTRY["dcf"].compute(dataset)
    dcf_keys = set((dcf_result.get("formula_ids") or {}).keys())
    assert "base_period_end" not in dcf_keys
    assert "value_basis" not in dcf_keys
    assert "applicability" not in dcf_keys

    ratios_result = MODEL_REGISTRY["ratios"].compute(dataset)
    ratios_keys = set((ratios_result.get("formula_ids") or {}).keys())
    assert ratios_keys
    assert all(key.startswith("values.") for key in ratios_keys)

    residual_income_result = MODEL_REGISTRY["residual_income"].compute(dataset)
    residual_income_keys = set((residual_income_result.get("formula_ids") or {}).keys())
    assert residual_income_keys
    assert all(key.startswith("intrinsic_value.") for key in residual_income_keys)