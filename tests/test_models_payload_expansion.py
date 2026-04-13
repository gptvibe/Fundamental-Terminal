from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
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
            "base_period_end": "2025-12-31",
            "enterprise_value": 2_500_000_000_000,
            "equity_value": 2_420_000_000_000,
            "fair_value_per_share": 210.0,
        },
    )


class _AsyncScope:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args) -> bool:
        return False


@contextmanager
def _client(monkeypatch):
    monkeypatch.setattr(main_module, "_session_scope", lambda: _AsyncScope())
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "_refresh_for_snapshot", lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None))
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "_visible_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 4, 13, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(main_module, "get_company_models", lambda *_args, **_kwargs: [_model_run()])
    monkeypatch.setattr(main_module, "_get_hot_cached_payload", _no_hot_cache)
    monkeypatch.setattr(main_module, "_fill_hot_cached_payload", _fill_without_cache)
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

    assert default_response.status_code == 200
    assert expanded_response.status_code == 200

    default_payload = default_response.json()
    expanded_payload = expanded_response.json()

    assert default_payload["models"][0]["input_periods"] is None
    assert expanded_payload["models"][0]["input_periods"]["period_end"] == "2025-12-31"
    assert len(default_response.content) < len(expanded_response.content)


def test_models_route_rejects_unknown_expansion(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/api/companies/AAPL/models?expand=foo")

    assert response.status_code == 400
    assert response.json()["detail"] == "expand must be one of: input_periods"
