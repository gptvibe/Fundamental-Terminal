from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
import app.services.oil_scenario_overlay as overlay_service
from app.db import get_db_session
from app.main import app


def _snapshot(ticker: str = "XOM"):
    company = SimpleNamespace(
        id=7,
        ticker=ticker,
        cik="0000034088",
        name="Exxon Mobil Corporation",
        sector="Energy",
        market_sector="Energy",
        market_industry="Oil & Gas Integrated",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime(2026, 4, 4, tzinfo=timezone.utc))


def _overlay_payload() -> dict[str, object]:
    return {
        "status": "partial",
        "fetched_at": "2026-04-04T00:00:00+00:00",
        "as_of": "2026-04-04",
        "last_refreshed_at": "2026-04-04T00:00:00+00:00",
        "strict_official_mode": True,
        "exposure_profile": {
            "profile_id": "oil_sensitive",
            "label": "Oil Sensitive",
            "oil_exposure_type": "integrated",
            "oil_support_status": "supported",
            "oil_support_reasons": ["market_sector:Energy", "market_industry:Oil & Gas Integrated", "sector:Energy", "integrated_oil_supported_v1"],
            "relevance_reasons": ["sector: Energy"],
            "hedging_signal": "unknown",
            "pass_through_signal": "unknown",
            "evidence": [],
        },
        "benchmark_series": [
            {
                "series_id": "eia_steo_brent_placeholder",
                "label": "Brent spot oil price",
                "units": "usd_per_barrel",
                "status": "placeholder",
                "points": [{"label": "base", "value": None, "units": "usd_per_barrel", "observation_date": None}],
                "latest_value": None,
                "latest_observation_date": None,
            }
        ],
        "scenarios": [
            {
                "scenario_id": "base",
                "label": "Base",
                "benchmark_value": None,
                "benchmark_delta_percent": 0.0,
                "revenue_delta_percent": None,
                "operating_margin_delta_bps": None,
                "free_cash_flow_delta_percent": None,
                "confidence_flags": ["placeholder"],
            }
        ],
        "sensitivity": {
            "metric_basis": "operating_margin",
            "lookback_quarters": 8,
            "elasticity": None,
            "r_squared": None,
            "sample_size": 0,
            "direction": "unknown",
            "status": "placeholder",
            "confidence_flags": ["sensitivity_not_computed"],
        },
        "diagnostics": {
            "coverage_ratio": 0.0,
            "fallback_ratio": 0.0,
            "stale_flags": [],
            "parser_confidence": None,
            "missing_field_flags": ["official_oil_curve_missing", "sensitivity_not_computed"],
            "reconciliation_penalty": None,
            "reconciliation_disagreement_count": 0,
        },
        "confidence_flags": ["strict_official_mode", "oil_curve_placeholder", "oil_sensitivity_placeholder"],
        "provenance": [
            {
                "source_id": "sec_edgar",
                "source_tier": "official_regulator",
                "display_label": "SEC EDGAR",
                "url": "https://www.sec.gov/edgar.shtml",
                "default_freshness_ttl_seconds": 86400,
                "disclosure_note": "Official SEC filing data for issuer disclosures and filing-linked metadata.",
                "role": "primary",
                "as_of": "2026-04-04",
                "last_refreshed_at": "2026-04-04T00:00:00+00:00",
            },
            {
                "source_id": "ft_oil_scenario_overlay",
                "source_tier": "derived_from_official",
                "display_label": "Fundamental Terminal Oil Scenario Overlay",
                "url": "https://github.com/fungk/Fundamental-Terminal",
                "default_freshness_ttl_seconds": 21600,
                "disclosure_note": "Persisted oil exposure overlays derived from official company metadata and official energy scenario inputs when available.",
                "role": "derived",
                "as_of": "2026-04-04",
                "last_refreshed_at": "2026-04-04T00:00:00+00:00",
            },
        ],
        "source_mix": {
            "source_ids": ["ft_oil_scenario_overlay", "sec_edgar"],
            "source_tiers": ["derived_from_official", "official_regulator"],
            "primary_source_ids": ["sec_edgar"],
            "fallback_source_ids": [],
            "official_only": True,
        },
    }


@contextmanager
def _client():
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        main_module._hot_response_cache.clear()


def test_oil_scenario_overlay_reads_cached_payload_without_live_fetch(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay", lambda *_args, **_kwargs: (_overlay_payload(), "fresh"))
    monkeypatch.setattr(
        main_module,
        "get_company_oil_scenario_overlay_last_checked",
        lambda *_args, **_kwargs: datetime(2026, 4, 4, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(main_module, "queue_company_refresh", lambda *_args, **_kwargs: pytest.fail("refresh should not queue for fresh cache"))
    monkeypatch.setattr(main_module, "EdgarClient", lambda: pytest.fail("hot read path should not instantiate SEC client"))

    with _client() as client:
        response = client.get("/api/companies/XOM/oil-scenario-overlay")

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh"] == {"triggered": False, "reason": "fresh", "ticker": "XOM", "job_id": None}
    assert payload["company"]["ticker"] == "XOM"
    assert payload["company"]["oil_exposure_type"] == "integrated"
    assert payload["company"]["oil_support_status"] == "supported"
    assert payload["benchmark_series"][0]["series_id"] == "eia_steo_brent_placeholder"
    assert payload["exposure_profile"]["oil_exposure_type"] == "integrated"
    assert payload["exposure_profile"]["oil_support_status"] == "supported"


def test_oil_scenario_overlay_returns_stale_payload_and_queues_revalidation(monkeypatch):
    queued: list[tuple[str, bool]] = []

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay", lambda *_args, **_kwargs: (_overlay_payload(), "stale"))
    monkeypatch.setattr(
        main_module,
        "get_company_oil_scenario_overlay_last_checked",
        lambda *_args, **_kwargs: datetime(2026, 4, 3, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        main_module,
        "queue_company_refresh",
        lambda _background_tasks, ticker, force=False: queued.append((ticker, force)) or "job-oil-stale",
    )

    with _client() as client:
        response = client.get("/api/companies/XOM/oil-scenario-overlay")

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh"] == {"triggered": True, "reason": "stale", "ticker": "XOM", "job_id": "job-oil-stale"}
    assert "refresh_stale_queued" in payload["diagnostics"]["stale_flags"]
    assert "stale_data" in payload["confidence_flags"]
    assert queued == [("XOM", False)]


def test_oil_scenario_overlay_returns_placeholder_shell_when_dataset_missing(monkeypatch):
    queued: list[tuple[str, bool]] = []

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay", lambda *_args, **_kwargs: (None, "missing"))
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay_last_checked", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        main_module,
        "queue_company_refresh",
        lambda _background_tasks, ticker, force=False: queued.append((ticker, force)) or "job-oil-missing",
    )

    with _client() as client:
        response = client.get("/api/companies/XOM/oil-scenario-overlay")

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh"] == {"triggered": True, "reason": "missing", "ticker": "XOM", "job_id": "job-oil-missing"}
    assert payload["status"] == "supported"
    assert payload["company"]["ticker"] == "XOM"
    assert payload["benchmark_series"]
    assert "oil_scenario_overlay_missing" in payload["diagnostics"]["missing_field_flags"]
    assert queued == [("XOM", False)]


def test_oil_scenario_overlay_refresh_dedupes_when_dataset_lock_exists(monkeypatch):
    checked_at = datetime(2026, 4, 4, tzinfo=timezone.utc)
    company = SimpleNamespace(
        id=7,
        ticker="XOM",
        cik="0000034088",
        name="Exxon Mobil Corporation",
        sector="Energy",
        market_sector="Energy",
        market_industry="Oil & Gas Integrated",
    )

    monkeypatch.setattr(overlay_service, "acquire_refresh_lock", lambda *_args, **_kwargs: "job-existing")
    monkeypatch.setattr(
        overlay_service,
        "upsert_company_oil_scenario_overlay_snapshot",
        lambda *_args, **_kwargs: pytest.fail("duplicate refresh should not write payloads"),
    )

    written = overlay_service.refresh_company_oil_scenario_overlay(
        object(),
        company,
        checked_at=checked_at,
        job_id="job-new",
    )

    assert written == 0