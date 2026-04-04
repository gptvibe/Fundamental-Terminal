from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import RefreshState, app
from app.services.oil_exposure import classify_oil_exposure


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

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "_refresh_for_snapshot", lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="XOM", job_id=None))
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (None, "fresh"))
    monkeypatch.setattr(
        main_module,
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