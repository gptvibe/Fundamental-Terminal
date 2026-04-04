from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
import app.services.oil_scenario as oil_scenario_service
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
        "status": "supported",
        "fetched_at": "2026-04-04T00:00:00+00:00",
        "as_of": "2026-04-04",
        "last_refreshed_at": "2026-04-04T00:00:00+00:00",
        "strict_official_mode": False,
        "exposure_profile": {
            "profile_id": "integrated",
            "label": "Integrated",
            "oil_exposure_type": "integrated",
            "oil_support_status": "supported",
            "oil_support_reasons": ["integrated_upstream_supported"],
            "relevance_reasons": ["integrated_upstream_supported"],
            "hedging_signal": "unknown",
            "pass_through_signal": "unknown",
            "evidence": [],
        },
        "benchmark_series": [
            {
                "series_id": "wti_spot_history",
                "label": "WTI spot history",
                "units": "usd_per_barrel",
                "status": "ok",
                "points": [
                    {"label": "2026-04-03", "value": 83.4, "units": "usd_per_barrel", "observation_date": "2026-04-03"},
                ],
                "latest_value": 83.4,
                "latest_observation_date": "2026-04-03",
            },
            {
                "series_id": "wti_short_term_baseline",
                "label": "WTI short-term official baseline",
                "units": "usd_per_barrel",
                "status": "ok",
                "points": [
                    {"label": "2026-01", "value": 80.0, "units": "usd_per_barrel", "observation_date": "2026-01"},
                    {"label": "2027-01", "value": 78.0, "units": "usd_per_barrel", "observation_date": "2027-01"},
                    {"label": "2028-01", "value": 76.0, "units": "usd_per_barrel", "observation_date": "2028-01"},
                ],
                "latest_value": 76.0,
                "latest_observation_date": "2028-01",
            }
        ],
        "scenarios": [],
        "sensitivity": None,
        "diagnostics": {
            "coverage_ratio": 0.0,
            "fallback_ratio": 0.0,
            "stale_flags": [],
            "parser_confidence": None,
            "missing_field_flags": ["sensitivity_not_computed"],
            "reconciliation_penalty": None,
            "reconciliation_disagreement_count": 0,
        },
        "confidence_flags": [],
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
            {
                "source_id": "eia_petroleum_spot_prices",
                "source_tier": "official_statistical",
                "display_label": "EIA Petroleum Spot Prices",
                "url": "https://www.eia.gov/",
                "default_freshness_ttl_seconds": 86400,
                "disclosure_note": "Official EIA petroleum spot-price history used for WTI and Brent benchmark normalization.",
                "role": "primary",
                "as_of": "2026-04-03",
                "last_refreshed_at": "2026-04-04T00:00:00+00:00",
            },
            {
                "source_id": "eia_steo",
                "source_tier": "official_statistical",
                "display_label": "EIA Short-Term Energy Outlook",
                "url": "https://www.eia.gov/outlooks/steo/",
                "default_freshness_ttl_seconds": 86400,
                "disclosure_note": "Official EIA short-term oil price baseline scenarios.",
                "role": "primary",
                "as_of": "2026-04",
                "last_refreshed_at": "2026-04-04T00:00:00+00:00",
            },
        ],
        "source_mix": {
            "source_ids": ["eia_petroleum_spot_prices", "eia_steo", "ft_oil_scenario_overlay", "sec_edgar"],
            "source_tiers": ["official_statistical", "derived_from_official", "official_regulator"],
            "primary_source_ids": ["eia_petroleum_spot_prices", "eia_steo", "sec_edgar"],
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


def test_oil_scenario_reads_cached_payload_without_live_fetch(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay", lambda *_args, **_kwargs: (_overlay_payload(), "fresh"))
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay_last_checked", lambda *_args, **_kwargs: datetime(2026, 4, 4, tzinfo=timezone.utc))
    monkeypatch.setattr(main_module, "queue_company_refresh", lambda *_args, **_kwargs: pytest.fail("refresh should not queue for fresh cache"))
    monkeypatch.setattr(main_module, "EdgarClient", lambda: pytest.fail("hot read path should not instantiate SEC client"))
    monkeypatch.setattr(
        oil_scenario_service,
        "get_company_models",
        lambda *_args, **_kwargs: [SimpleNamespace(model_name="dcf", result={"fair_value_per_share": 100.0}, created_at=datetime(2026, 4, 4, tzinfo=timezone.utc))],
    )
    monkeypatch.setattr(
        oil_scenario_service,
        "get_company_financials",
        lambda *_args, **_kwargs: [SimpleNamespace(weighted_average_diluted_shares=10.0, shares_outstanding=10.0)],
    )
    monkeypatch.setattr(
        oil_scenario_service,
        "get_company_price_history",
        lambda *_args, **_kwargs: [SimpleNamespace(close=90.0, trade_date=date(2026, 4, 4))],
    )

    with _client() as client:
        response = client.get("/api/companies/XOM/oil-scenario")

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh"] == {"triggered": False, "reason": "fresh", "ticker": "XOM", "job_id": None}
    assert payload["eligibility"]["eligible"] is True
    assert payload["official_base_curve"]["benchmark_id"] == "wti_short_term_baseline"
    assert payload["user_editable_defaults"]["current_share_price"] == 90.0
    assert payload["user_editable_defaults"]["current_oil_price"] == 83.4
    assert payload["user_editable_defaults"]["current_oil_price_source"] == "wti_spot_history"
    assert payload["overlay_outputs"]["status"] == "insufficient_data"


def test_oil_scenario_returns_stale_payload_and_queues_revalidation(monkeypatch):
    queued: list[tuple[str, bool]] = []

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay", lambda *_args, **_kwargs: (_overlay_payload(), "stale"))
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay_last_checked", lambda *_args, **_kwargs: datetime(2026, 4, 3, tzinfo=timezone.utc))
    monkeypatch.setattr(
        main_module,
        "queue_company_refresh",
        lambda _background_tasks, ticker, force=False: queued.append((ticker, force)) or "job-oil-scenario-stale",
    )
    monkeypatch.setattr(oil_scenario_service, "get_company_models", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(oil_scenario_service, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(oil_scenario_service, "get_company_price_history", lambda *_args, **_kwargs: [])

    with _client() as client:
        response = client.get("/api/companies/XOM/oil-scenario")

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh"] == {"triggered": True, "reason": "stale", "ticker": "XOM", "job_id": "job-oil-scenario-stale"}
    assert "refresh_stale_queued" in payload["diagnostics"]["stale_flags"]
    assert queued == [("XOM", False)]


def test_oil_scenario_returns_placeholder_shell_when_dataset_missing(monkeypatch):
    queued: list[tuple[str, bool]] = []

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay", lambda *_args, **_kwargs: (None, "missing"))
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay_last_checked", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        main_module,
        "queue_company_refresh",
        lambda _background_tasks, ticker, force=False: queued.append((ticker, force)) or "job-oil-scenario-missing",
    )
    monkeypatch.setattr(oil_scenario_service, "get_company_models", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(oil_scenario_service, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(oil_scenario_service, "get_company_price_history", lambda *_args, **_kwargs: [])

    with _client() as client:
        response = client.get("/api/companies/XOM/oil-scenario")

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh"] == {"triggered": True, "reason": "missing", "ticker": "XOM", "job_id": "job-oil-scenario-missing"}
    assert payload["status"] == "supported"
    assert payload["requirements"]["manual_sensitivity_required"] is True
    assert "oil_scenario_overlay_missing" in payload["diagnostics"]["missing_field_flags"]
    assert queued == [("XOM", False)]


def test_oil_scenario_strict_official_mode_omits_fallback_price_sources(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay", lambda *_args, **_kwargs: (_overlay_payload(), "fresh"))
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay_last_checked", lambda *_args, **_kwargs: datetime(2026, 4, 4, tzinfo=timezone.utc))
    monkeypatch.setattr(main_module, "queue_company_refresh", lambda *_args, **_kwargs: pytest.fail("refresh should not queue for fresh cache"))
    monkeypatch.setattr(oil_scenario_service, "settings", SimpleNamespace(strict_official_mode=True))
    monkeypatch.setattr(
        oil_scenario_service,
        "get_company_models",
        lambda *_args, **_kwargs: [SimpleNamespace(model_name="dcf", result={"fair_value_per_share": 100.0}, created_at=datetime(2026, 4, 4, tzinfo=timezone.utc))],
    )
    monkeypatch.setattr(
        oil_scenario_service,
        "get_company_financials",
        lambda *_args, **_kwargs: [SimpleNamespace(weighted_average_diluted_shares=10.0, shares_outstanding=10.0)],
    )
    monkeypatch.setattr(
        oil_scenario_service,
        "get_company_price_history",
        lambda *_args, **_kwargs: pytest.fail("strict official mode should not read fallback-backed price history"),
    )

    with _client() as client:
        response = client.get("/api/companies/XOM/oil-scenario")

    assert response.status_code == 200
    payload = response.json()
    assert payload["strict_official_mode"] is True
    assert payload["requirements"]["manual_price_required"] is True
    assert payload["user_editable_defaults"]["current_share_price"] is None
    assert "yahoo_finance" not in payload["source_mix"]["source_ids"]
    assert payload["source_mix"]["official_only"] is True


def test_oil_scenario_prefers_sec_disclosed_sensitivity_and_matching_benchmark(monkeypatch):
    payload = _overlay_payload()
    payload["benchmark_series"].extend(
        [
            {
                "series_id": "brent_spot_history",
                "label": "Brent spot history",
                "units": "usd_per_barrel",
                "status": "ok",
                "points": [
                    {"label": "2026-04-03", "value": 85.0, "units": "usd_per_barrel", "observation_date": "2026-04-03"},
                ],
                "latest_value": 85.0,
                "latest_observation_date": "2026-04-03",
            },
            {
                "series_id": "brent_short_term_baseline",
                "label": "Brent short-term official baseline",
                "units": "usd_per_barrel",
                "status": "ok",
                "points": [
                    {"label": "2026-01", "value": 84.0, "units": "usd_per_barrel", "observation_date": "2026-01"},
                    {"label": "2027-01", "value": 82.0, "units": "usd_per_barrel", "observation_date": "2027-01"},
                ],
                "latest_value": 82.0,
                "latest_observation_date": "2027-01",
            },
        ]
    )
    payload["sensitivity"] = {
        "metric_basis": "annual_after_tax_earnings_usd",
        "lookback_quarters": 8,
        "elasticity": 300000000.0,
        "r_squared": 0.61,
        "sample_size": 8,
        "direction": "positive_with_higher_oil",
        "status": "ok",
        "confidence_flags": ["derived_from_official"],
    }
    payload["direct_company_evidence"] = {
        "status": "partial",
        "checked_at": "2026-04-04T00:00:00+00:00",
        "parser_confidence_flags": ["oil_sensitivity_disclosed", "realized_vs_benchmark_available"],
        "disclosed_sensitivity": {
            "status": "available",
            "benchmark": "brent",
            "oil_price_change_per_bbl": 1.0,
            "annual_after_tax_earnings_change": 650000000.0,
            "annual_after_tax_sensitivity": 650000000.0,
            "metric_basis": "annual_after_tax_earnings_usd",
            "source_url": "https://www.sec.gov/Archives/edgar/data/34088/xom.htm",
            "accession_number": "0000034088-26-000012",
            "filing_form": "10-K",
            "confidence_flags": ["oil_sensitivity_disclosed"],
            "provenance_sources": ["sec_edgar"],
        },
        "diluted_shares": {
            "status": "available",
            "value": 4200000000.0,
            "unit": "shares",
            "taxonomy": "us-gaap",
            "tag": "WeightedAverageNumberOfDilutedSharesOutstanding",
            "confidence_flags": ["weighted_average_diluted_shares_companyfacts"],
            "provenance_sources": ["sec_companyfacts"],
        },
        "realized_price_comparison": {
            "status": "available",
            "benchmark": "brent",
            "rows": [
                {
                    "period_label": "2025",
                    "benchmark": "brent",
                    "realized_price": 71.25,
                    "benchmark_price": 74.0,
                    "realized_percent_of_benchmark": 96.3,
                    "premium_discount": -2.75,
                }
            ],
            "confidence_flags": ["realized_vs_benchmark_available"],
            "provenance_sources": ["sec_edgar"],
        },
    }

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay", lambda *_args, **_kwargs: (payload, "fresh"))
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay_last_checked", lambda *_args, **_kwargs: datetime(2026, 4, 4, tzinfo=timezone.utc))
    monkeypatch.setattr(main_module, "queue_company_refresh", lambda *_args, **_kwargs: pytest.fail("refresh should not queue for fresh cache"))
    monkeypatch.setattr(
        oil_scenario_service,
        "get_company_models",
        lambda *_args, **_kwargs: [SimpleNamespace(model_name="dcf", result={"fair_value_per_share": 100.0}, created_at=datetime(2026, 4, 4, tzinfo=timezone.utc))],
    )
    monkeypatch.setattr(
        oil_scenario_service,
        "get_company_financials",
        lambda *_args, **_kwargs: [SimpleNamespace(weighted_average_diluted_shares=10.0, shares_outstanding=10.0)],
    )
    monkeypatch.setattr(
        oil_scenario_service,
        "get_company_price_history",
        lambda *_args, **_kwargs: [SimpleNamespace(close=90.0, trade_date=date(2026, 4, 4))],
    )

    with _client() as client:
        response = client.get("/api/companies/XOM/oil-scenario")

    assert response.status_code == 200
    resolved = response.json()
    assert resolved["user_editable_defaults"]["benchmark_id"] == "brent_short_term_baseline"
    assert resolved["user_editable_defaults"]["current_oil_price_source"] == "brent_spot_history"
    assert resolved["sensitivity_source"]["kind"] == "disclosed"
    assert resolved["user_editable_defaults"]["annual_after_tax_sensitivity"] == 650000000.0
    assert resolved["requirements"]["realized_spread_supported"] is True
    assert resolved["user_editable_defaults"]["current_realized_spread"] == pytest.approx(-2.75)


def test_oil_scenario_labels_benchmark_only_fallback_when_realized_spread_is_unavailable(monkeypatch):
    payload = _overlay_payload()
    payload["direct_company_evidence"] = {
        "status": "partial",
        "checked_at": "2026-04-04T00:00:00+00:00",
        "parser_confidence_flags": ["realized_vs_benchmark_not_available"],
        "disclosed_sensitivity": {
            "status": "not_available",
            "reason": "No explicit annual oil sensitivity was disclosed.",
            "confidence_flags": ["oil_sensitivity_not_available"],
            "provenance_sources": ["sec_edgar"],
        },
        "diluted_shares": {
            "status": "available",
            "value": 4200000000.0,
            "unit": "shares",
            "taxonomy": "us-gaap",
            "tag": "WeightedAverageNumberOfDilutedSharesOutstanding",
            "confidence_flags": ["weighted_average_diluted_shares_companyfacts"],
            "provenance_sources": ["sec_companyfacts"],
        },
        "realized_price_comparison": {
            "status": "not_available",
            "reason": "No clear SEC realized-price-versus-benchmark table is cached for this producer yet.",
            "benchmark": "wti",
            "rows": [],
            "confidence_flags": ["realized_vs_benchmark_not_available"],
            "provenance_sources": ["sec_edgar"],
        },
    }

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay", lambda *_args, **_kwargs: (payload, "fresh"))
    monkeypatch.setattr(main_module, "get_company_oil_scenario_overlay_last_checked", lambda *_args, **_kwargs: datetime(2026, 4, 4, tzinfo=timezone.utc))
    monkeypatch.setattr(main_module, "queue_company_refresh", lambda *_args, **_kwargs: pytest.fail("refresh should not queue for fresh cache"))
    monkeypatch.setattr(oil_scenario_service, "get_company_models", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(oil_scenario_service, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(oil_scenario_service, "get_company_price_history", lambda *_args, **_kwargs: [])

    with _client() as client:
        response = client.get("/api/companies/XOM/oil-scenario")

    assert response.status_code == 200
    resolved = response.json()
    assert resolved["requirements"]["realized_spread_supported"] is False
    assert resolved["requirements"]["realized_spread_fallback_label"] == "Benchmark-only fallback"
    assert "No clear SEC realized-price-versus-benchmark table" in resolved["requirements"]["realized_spread_reason"]
