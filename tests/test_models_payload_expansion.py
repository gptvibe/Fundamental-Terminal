from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.handlers import _shared as _shared_handlers
from app.main import RefreshState, app


def _snapshot() -> SimpleNamespace:
    company = SimpleNamespace(
        id=1,
        ticker="AAPL",
        cik="0000320193",
        name="Apple Inc.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Consumer Electronics",
    )
    return SimpleNamespace(company=company, cache_state="stale", last_checked=datetime.now(timezone.utc))


def _model_run() -> SimpleNamespace:
    return SimpleNamespace(
        model_name="dcf",
        model_version="v2",
        calculation_version="dcf_ev_bridge_v2",
        created_at=datetime(2026, 4, 13, tzinfo=timezone.utc),
        input_periods={
            "period_end": "2025-12-31",
            "historical_free_cash_flow": [
                {"period_end": f"202{index}-12-31", "free_cash_flow": 90_000_000_000 + index * 1_000_000_000}
                for index in range(6)
            ],
            "projected_free_cash_flow": [
                {
                    "year": year,
                    "growth_rate": 0.05 - year * 0.0025,
                    "free_cash_flow": 110_000_000_000 + year * 4_000_000_000,
                    "present_value": 95_000_000_000 + year * 2_500_000_000,
                }
                for year in range(1, 6)
            ],
            "assumptions": {
                "discount_rate": 0.093,
                "terminal_growth_rate": 0.025,
                "projection_years": 5,
            },
        },
        result={
            "model_status": "supported",
            "calculation_version": "dcf_ev_bridge_v2",
            "base_period_end": "2025-12-31",
            "enterprise_value": 2_500_000_000_000,
            "equity_value": 2_420_000_000_000,
            "fair_value_per_share": 210.0,
        },
    )


def _model_run_without_calculation_version_attr() -> SimpleNamespace:
    payload = _model_run().__dict__.copy()
    payload.pop("calculation_version", None)
    return SimpleNamespace(**payload)


class _AsyncScope:
    async def __aenter__(self) -> object:
        return SimpleNamespace(commit=lambda: None)

    async def __aexit__(self, *_args) -> bool:
        return False


def _patch_main_and_shared(monkeypatch, name: str, value) -> None:
    monkeypatch.setattr(main_module, name, value)
    monkeypatch.setattr(_shared_handlers, name, value)


@contextmanager
def _client(monkeypatch):
    _patch_main_and_shared(monkeypatch, "_session_scope", lambda: _AsyncScope())
    _patch_main_and_shared(monkeypatch, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    _patch_main_and_shared(monkeypatch, "_refresh_for_snapshot", lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None))
    _patch_main_and_shared(monkeypatch, "get_company_financials", lambda *_args, **_kwargs: [])
    _patch_main_and_shared(monkeypatch, "_visible_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 4, 13, tzinfo=timezone.utc), "fresh"))
    _patch_main_and_shared(monkeypatch, "get_company_models", lambda *_args, **_kwargs: [_model_run()])
    _patch_main_and_shared(monkeypatch, "_get_hot_cached_payload", _no_hot_cache)
    _patch_main_and_shared(monkeypatch, "_fill_hot_cached_payload", _fill_without_cache)
    with TestClient(app) as client:
        yield client


async def _no_hot_cache(*_args, **_kwargs):
    return None


async def _fill_without_cache(_key, *, fill, **_kwargs):
    return await fill()


def test_models_route_omits_input_periods_by_default_and_reduces_payload(monkeypatch):
    with _client(monkeypatch) as client:
        default_response = client.get("/api/companies/AAPL/models?model=dcf")
        expanded_response = client.get("/api/companies/AAPL/models?model=dcf&expand=input_periods")
        formula_response = client.get("/api/companies/AAPL/models?model=dcf&expand=formula_details")

    assert default_response.status_code == 200
    assert expanded_response.status_code == 200
    assert formula_response.status_code == 200

    default_payload = default_response.json()
    expanded_payload = expanded_response.json()
    formula_payload = formula_response.json()

    assert default_payload["models"][0]["input_periods"] is None
    assert default_payload["models"][0]["calculation_version"] == "dcf_ev_bridge_v2"
    assert "formula_ids" in default_payload["models"][0]["result"]
    assert "fair_value_per_share" in default_payload["models"][0]["result"]["formula_ids"]
    assert default_payload["models"][0]["formula_details"] is None
    assert expanded_payload["models"][0]["input_periods"]["period_end"] == "2025-12-31"
    assert expanded_payload["models"][0]["result"]["calculation_version"] == "dcf_ev_bridge_v2"
    assert "fair_value_per_share" in formula_payload["models"][0]["formula_details"]
    assert formula_payload["models"][0]["formula_details"]["fair_value_per_share"]["formula_id"].startswith("model.dcf")
    assert len(default_response.content) < len(expanded_response.content)


def test_models_route_serializes_mocked_model_without_calculation_version_attribute(monkeypatch):
    _patch_main_and_shared(monkeypatch, "_session_scope", lambda: _AsyncScope())
    _patch_main_and_shared(monkeypatch, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    _patch_main_and_shared(monkeypatch, "_refresh_for_snapshot", lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None))
    _patch_main_and_shared(monkeypatch, "get_company_financials", lambda *_args, **_kwargs: [])
    _patch_main_and_shared(monkeypatch, "_visible_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 4, 13, tzinfo=timezone.utc), "fresh"))
    _patch_main_and_shared(monkeypatch, "get_company_models", lambda *_args, **_kwargs: [_model_run_without_calculation_version_attr()])
    _patch_main_and_shared(monkeypatch, "_get_hot_cached_payload", _no_hot_cache)
    _patch_main_and_shared(monkeypatch, "_fill_hot_cached_payload", _fill_without_cache)

    with TestClient(app) as client:
        response = client.get("/api/companies/AAPL/models?model=dcf")

    assert response.status_code == 200
    assert response.json()["models"][0]["calculation_version"] == "dcf_ev_bridge_v2"


def test_models_route_rejects_unknown_expansion(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/api/companies/AAPL/models?expand=foo")

    assert response.status_code == 400
    assert response.json()["detail"] == "expand must be one of: formula_details, input_periods"


def test_formula_endpoints_return_metadata(monkeypatch):
    with _client(monkeypatch) as client:
        summary_response = client.get("/api/formulas")
        details_response = client.get(
            "/api/formulas/model.dcf.fair_value_per_share.model_output_v1"
        )

    assert summary_response.status_code == 200
    assert summary_response.json()["schema_version"] == "formula_registry_v1"
    assert summary_response.json()["include_details"] is False
    assert any(
        item["formula_id"] == "model.dcf.fair_value_per_share.model_output_v1"
        for item in summary_response.json()["formulas"]
    )

    assert details_response.status_code == 200
    assert details_response.json()["formula_id"] == "model.dcf.fair_value_per_share.model_output_v1"
    assert details_response.json()["input_fields"]


def test_formula_endpoint_supports_lazy_batch_lookup(monkeypatch):
    with _client(monkeypatch) as client:
        model_response = client.get("/api/companies/AAPL/models?model=dcf")

        assert model_response.status_code == 200
        formula_ids = list(model_response.json()["models"][0]["result"]["formula_ids"].values())

        details_response = client.get(
            "/api/formulas",
            params={"ids": ",".join(formula_ids), "include_details": True},
        )

    assert details_response.status_code == 200
    payload = details_response.json()
    assert payload["include_details"] is True
    assert {item["formula_id"] for item in payload["formulas"]} == set(formula_ids)
    assert all(item["input_fields"] for item in payload["formulas"])
    assert all(item["source_periods"] for item in payload["formulas"])


def test_models_route_recomputes_missing_current_model_when_legacy_row_is_filtered(monkeypatch):
    _patch_main_and_shared(monkeypatch, "_session_scope", lambda: _AsyncScope())
    _patch_main_and_shared(monkeypatch, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    _patch_main_and_shared(monkeypatch, "_refresh_for_snapshot", lambda *_args, **_kwargs: RefreshState(triggered=False, reason="stale", ticker="AAPL", job_id=None))
    _patch_main_and_shared(monkeypatch, "get_company_financials", lambda *_args, **_kwargs: [])
    _patch_main_and_shared(monkeypatch, "_visible_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 4, 13, tzinfo=timezone.utc), "fresh"))
    _patch_main_and_shared(monkeypatch, "_get_hot_cached_payload", _no_hot_cache)
    _patch_main_and_shared(monkeypatch, "_fill_hot_cached_payload", _fill_without_cache)

    call_count = {"get_company_models": 0}
    observed_compute: list[list[str] | None] = []

    def _get_company_models(*_args, **_kwargs):
        call_count["get_company_models"] += 1
        if call_count["get_company_models"] == 1:
            return []
        return [_model_run()]

    class _FakeModelEngine:
        def __init__(self, _session):
            pass

        def compute_models(self, company_id, *, model_names=None, force=False, reporter=None):
            assert company_id == 1
            assert force is False
            assert reporter is None
            observed_compute.append(model_names)
            return [SimpleNamespace(cached=False)]

    _patch_main_and_shared(monkeypatch, "get_company_models", _get_company_models)
    _patch_main_and_shared(monkeypatch, "ModelEngine", _FakeModelEngine)

    with TestClient(app) as client:
        response = client.get("/api/companies/AAPL/models?model=dcf")

    assert response.status_code == 200
    assert observed_compute == [["dcf"]]
    assert response.json()["models"][0]["calculation_version"] == "dcf_ev_bridge_v2"
