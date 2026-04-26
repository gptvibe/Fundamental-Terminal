from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import app.model_engine.models.dcf as dcf_model
import app.model_engine.models.reverse_dcf as reverse_dcf_model
import app.model_engine.models.roic as roic_model
from app.model_engine.calculation_versions import (
    DCF_CALCULATION_VERSION,
    PIOTROSKI_CALCULATION_VERSION,
    REVERSE_DCF_CALCULATION_VERSION,
)
from app.model_engine.registry import MODEL_REGISTRY
from app.model_engine.types import CompanyDataset, FinancialPoint, MarketSnapshot
from app.services.derived_metrics import FORMULA_VERSION as DERIVED_METRICS_FORMULA_VERSION
from app.services.derived_metrics import build_metrics_timeseries


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "calculations" / "calculation_audit_v1.json"
MODEL_NAMES = ["dcf", "reverse_dcf", "roic", "ratios", "piotroski", "altman_z"]
FLOAT_ABS_TOLERANCE = 1e-9


def _mock_risk_free(*_args, **_kwargs):
    return SimpleNamespace(
        source_name="U.S. Treasury Daily Par Yield Curve",
        tenor="10y",
        observation_date=date(2026, 3, 20),
        rate_used=0.042,
        fetched_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
    )


@pytest.fixture(autouse=True)
def _fixed_risk_free(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)
    monkeypatch.setattr(reverse_dcf_model, "get_latest_risk_free_rate", _mock_risk_free)
    monkeypatch.setattr(roic_model, "get_latest_risk_free_rate", _mock_risk_free)


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def _build_company_dataset(case: dict[str, Any]) -> CompanyDataset:
    company = case["company"]
    snapshot_payload = case.get("market_snapshot")
    market_snapshot = None
    if snapshot_payload is not None:
        market_snapshot = MarketSnapshot(
            latest_price=snapshot_payload.get("latest_price"),
            price_date=_parse_date(snapshot_payload.get("price_date")),
            price_source=snapshot_payload.get("price_source"),
        )

    financials: list[FinancialPoint] = []
    for row in case["financials"]:
        financials.append(
            FinancialPoint(
                statement_id=int(row["statement_id"]),
                filing_type=row["filing_type"],
                period_start=date.fromisoformat(row["period_start"]),
                period_end=date.fromisoformat(row["period_end"]),
                source="fixture",
                last_updated=datetime(2026, 3, 21, tzinfo=timezone.utc),
                data=dict(row["data"]),
            )
        )

    ordered = tuple(sorted(financials, key=lambda item: item.period_end, reverse=True))
    return CompanyDataset(
        company_id=1,
        ticker=company["ticker"],
        name=company["name"],
        sector=company.get("sector"),
        market_sector=company.get("market_sector"),
        market_industry=company.get("market_industry"),
        market_snapshot=market_snapshot,
        financials=ordered,
    )


def _build_statement_rows(case: dict[str, Any]) -> list[SimpleNamespace]:
    statement_type = case.get("statement_type", "canonical_xbrl")
    rows: list[SimpleNamespace] = []
    for row in case["financials"]:
        rows.append(
            SimpleNamespace(
                id=int(row["statement_id"]),
                period_start=date.fromisoformat(row["period_start"]),
                period_end=date.fromisoformat(row["period_end"]),
                filing_type=row["filing_type"],
                statement_type=statement_type,
                source="fixture",
                last_updated=datetime(2026, 3, 21, tzinfo=timezone.utc),
                data=dict(row["data"]),
            )
        )
    return rows


def _build_price_rows(case: dict[str, Any]) -> list[SimpleNamespace]:
    rows: list[SimpleNamespace] = []
    for row in case.get("price_history", []):
        rows.append(
            SimpleNamespace(
                trade_date=date.fromisoformat(row["trade_date"]),
                close=float(row["close"]),
                source=row.get("source", "fixture"),
            )
        )
    return rows


def _assert_subset(actual: Any, expected: Any, *, context: str) -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{context}: expected dict but got {type(actual).__name__}"
        for key, expected_value in expected.items():
            assert key in actual, f"{context}: missing key '{key}'"
            _assert_subset(actual[key], expected_value, context=f"{context}.{key}")
        return

    if isinstance(expected, list):
        assert actual == expected, f"{context}: expected list {expected} but got {actual}"
        return

    if isinstance(expected, float):
        assert actual == pytest.approx(expected, abs=FLOAT_ABS_TOLERANCE), (
            f"{context}: expected {expected} but got {actual}"
        )
        return

    assert actual == expected, f"{context}: expected {expected!r} but got {actual!r}"


def _case_index() -> dict[str, dict[str, Any]]:
    return {case["id"]: case for case in _load_fixture()["cases"]}


def _project_model_result(model_name: str, observed: dict[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {"model_status": observed.get("model_status")}
    if model_name == "dcf":
        projected.update(
            {
                "fair_value_per_share": observed.get("fair_value_per_share"),
                "value_basis": observed.get("value_basis"),
                "capital_structure_proxied": observed.get("capital_structure_proxied"),
                "calculation_version": observed.get("calculation_version"),
            }
        )
    elif model_name == "reverse_dcf":
        projected.update(
            {
                "implied_growth": observed.get("implied_growth"),
                "target_value_basis": observed.get("target_value_basis"),
                "calculation_version": observed.get("calculation_version"),
            }
        )
    elif model_name == "roic":
        projected.update(
            {
                "roic": observed.get("roic"),
                "spread_vs_capital_cost_proxy": observed.get("spread_vs_capital_cost_proxy"),
            }
        )
    elif model_name == "ratios":
        values = observed.get("values") if isinstance(observed.get("values"), dict) else {}
        projected.update(
            {
                "cadence": observed.get("cadence"),
                "gross_margin": values.get("gross_margin"),
                "return_on_assets": values.get("return_on_assets"),
            }
        )
    elif model_name == "piotroski":
        projected.update(
            {
                "score": observed.get("score"),
                "available_criteria": observed.get("available_criteria"),
                "calculation_version": observed.get("calculation_version"),
            }
        )
    elif model_name == "altman_z":
        projected.update(
            {
                "z_score_approximate": observed.get("z_score_approximate"),
                "variant": observed.get("variant"),
            }
        )
    return projected


def test_formula_versions_match_fixture_contract() -> None:
    fixture = _load_fixture()
    expected = fixture["formula_versions"]

    observed = {
        "derived_metrics": DERIVED_METRICS_FORMULA_VERSION,
        "dcf": DCF_CALCULATION_VERSION,
        "reverse_dcf": REVERSE_DCF_CALCULATION_VERSION,
        "piotroski": PIOTROSKI_CALCULATION_VERSION,
        "roic_model_version": MODEL_REGISTRY["roic"].version,
        "ratios_model_version": MODEL_REGISTRY["ratios"].version,
        "altman_z_model_version": MODEL_REGISTRY["altman_z"].version,
    }

    assert observed == expected


def test_model_happy_path_goldens() -> None:
    case = _case_index()["standard_tech"]
    dataset = _build_company_dataset(case)

    for model_name in MODEL_NAMES:
        expected = case["expected"]["models"][model_name]
        observed = MODEL_REGISTRY[model_name].compute(dataset)
        projected = _project_model_result(model_name, observed)
        _assert_subset(projected, expected, context=f"standard_tech.{model_name}")


@pytest.mark.parametrize(
    "case_id,model_name",
    [
        ("bank", "dcf"),
        ("bank", "reverse_dcf"),
        ("bank", "roic"),
        ("bank", "ratios"),
        ("bank", "piotroski"),
        ("bank", "altman_z"),
        ("reit", "piotroski"),
        ("negative_fcf", "dcf"),
        ("negative_fcf", "reverse_dcf"),
        ("negative_fcf", "roic"),
        ("adr_foreign_cadence", "ratios"),
    ],
)
def test_model_edge_case_goldens(case_id: str, model_name: str) -> None:
    case = _case_index()[case_id]
    dataset = _build_company_dataset(case)
    expected = case["expected"]["models"][model_name]

    observed = MODEL_REGISTRY[model_name].compute(dataset)
    projected = _project_model_result(model_name, observed)
    _assert_subset(projected, expected, context=f"{case_id}.{model_name}")


def test_each_model_has_happy_and_edge_coverage() -> None:
    edge_pairs = {
        "dcf": ["bank", "negative_fcf"],
        "reverse_dcf": ["bank", "negative_fcf"],
        "roic": ["bank", "negative_fcf"],
        "ratios": ["bank", "adr_foreign_cadence"],
        "piotroski": ["bank", "reit"],
        "altman_z": ["bank"],
    }

    case_map = _case_index()
    happy_case = case_map["standard_tech"]
    for model_name in MODEL_NAMES:
        assert model_name in happy_case["expected"]["models"]
        assert edge_pairs[model_name]
        for case_id in edge_pairs[model_name]:
            assert model_name in case_map[case_id]["expected"]["models"]


def test_derived_metrics_happy_path_golden() -> None:
    case = _case_index()["standard_tech"]
    expected = case["expected"]["derived_metrics"]

    series = build_metrics_timeseries(_build_statement_rows(case), _build_price_rows(case))
    cadences = sorted({item["cadence"] for item in series})
    latest = series[-1]

    observed = {
        "cadences": cadences,
        "latest_formula_version": latest["provenance"]["formula_version"],
        "latest_flags": latest["quality"]["flags"],
    }
    _assert_subset(observed, expected, context="derived.standard_tech")


@pytest.mark.parametrize(
    "case_id",
    ["bank", "missing_quarter", "restated_filing", "adr_foreign_cadence"],
)
def test_derived_metrics_edge_case_goldens(case_id: str) -> None:
    case = _case_index()[case_id]
    expected = case["expected"]["derived_metrics"]

    series = build_metrics_timeseries(_build_statement_rows(case), _build_price_rows(case))
    cadences = sorted({item["cadence"] for item in series})
    latest = series[-1] if series else None
    latest_quarterly = [item for item in series if item["cadence"] == "quarterly"]
    latest_ttm = [item for item in series if item["cadence"] == "ttm"]

    observed = {
        "cadences": cadences,
        "latest_formula_version": latest["provenance"]["formula_version"] if latest else None,
        "latest_flags": latest["quality"]["flags"] if latest else [],
        "latest_quarterly_revenue_growth": latest_quarterly[-1]["metrics"].get("revenue_growth") if latest_quarterly else None,
        "latest_ttm_validation_status": latest_ttm[-1]["provenance"].get("ttm_validation_status") if latest_ttm else None,
        "latest_ttm_construction": latest_ttm[-1]["provenance"].get("ttm_construction") if latest_ttm else None,
    }

    _assert_subset(observed, expected, context=f"derived.{case_id}")
