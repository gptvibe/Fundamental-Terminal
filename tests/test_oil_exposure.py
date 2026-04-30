from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.handlers import _shared as _shared_handlers
from app.main import RefreshState, app
from app.services.oil_exposure import classify_oil_exposure


def _patch_main_and_shared(monkeypatch, name: str, value) -> None:
    monkeypatch.setattr(main_module, name, value)
    monkeypatch.setattr(_shared_handlers, name, value)


async def _no_hot_cache(*_args, **_kwargs):
    return None


async def _fill_without_cache(_key, *, fill, **_kwargs):
    return await fill()


def test_classify_oil_exposure_support_matrix() -> None:
    assert classify_oil_exposure(sector="Energy", market_sector="Energy", market_industry="Exploration & Production").oil_exposure_type == "upstream"
    assert classify_oil_exposure(sector="Energy", market_sector="Energy", market_industry="Exploration & Production").oil_support_status == "supported"

    assert classify_oil_exposure(sector="Energy", market_sector="Energy", market_industry="Oil & Gas Integrated").oil_exposure_type == "integrated"
    assert classify_oil_exposure(sector="Energy", market_sector="Energy", market_industry="Oil & Gas Integrated").oil_support_status == "supported"

    assert classify_oil_exposure(sector="Energy", market_sector="Energy", market_industry="Refining & Marketing").oil_exposure_type == "refiner"
    assert classify_oil_exposure(sector="Energy", market_sector="Energy", market_industry="Refining & Marketing").oil_support_status == "partial"

    assert classify_oil_exposure(sector="Energy", market_sector="Energy", market_industry="Pipeline Transportation").oil_exposure_type == "midstream"
    assert classify_oil_exposure(sector="Energy", market_sector="Energy", market_industry="Pipeline Transportation").oil_support_status == "unsupported"

    assert classify_oil_exposure(sector="Energy", market_sector="Energy", market_industry="Oil & Gas Services").oil_exposure_type == "services"
    assert classify_oil_exposure(sector="Energy", market_sector="Energy", market_industry="Oil & Gas Services").oil_support_status == "unsupported"

    assert classify_oil_exposure(sector="Technology", market_sector="Technology", market_industry="Consumer Electronics").oil_exposure_type == "non_oil"
    assert classify_oil_exposure(sector="Technology", market_sector="Technology", market_industry="Consumer Electronics").oil_support_status == "unsupported"


def test_models_route_exposes_oil_classification_metadata(monkeypatch) -> None:
    snapshot = SimpleNamespace(
        company=SimpleNamespace(
            id=7,
            ticker="XOM",
            cik="0000034088",
            name="Exxon Mobil Corporation",
            sector="Energy",
            market_sector="Energy",
            market_industry="Oil & Gas Integrated",
        ),
        cache_state="fresh",
        last_checked=datetime(2026, 4, 4, tzinfo=timezone.utc),
    )

    _patch_main_and_shared(monkeypatch, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "get_company_financials", lambda *_args, **_kwargs: [])
    _patch_main_and_shared(monkeypatch, "_refresh_for_snapshot", lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="XOM", job_id=None))
    _patch_main_and_shared(monkeypatch, "get_company_price_cache_status", lambda *_args, **_kwargs: (None, "fresh"))
    _patch_main_and_shared(monkeypatch, "_visible_price_cache_status", lambda *_args, **_kwargs: (None, "fresh"))
    _patch_main_and_shared(monkeypatch, "_get_hot_cached_payload", _no_hot_cache)
    _patch_main_and_shared(monkeypatch, "_fill_hot_cached_payload", _fill_without_cache)
    _patch_main_and_shared(
        monkeypatch,
        "get_company_models",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                model_name="dcf",
                model_version="v1",
                created_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
                input_periods={"period_end": "2025-12-31"},
                result={"model_status": "supported", "base_period_end": "2025-12-31"},
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/XOM/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["oil_exposure_type"] == "integrated"
    assert payload["company"]["oil_support_status"] == "supported"
    assert "integrated_oil_supported_v1" in payload["company"]["oil_support_reasons"]
    assert payload["models"][0]["result"]["sector_suitability"]["classification"]["oil_exposure_type"] == "integrated"
    assert payload["models"][0]["result"]["sector_suitability"]["classification"]["oil_support_status"] == "supported"