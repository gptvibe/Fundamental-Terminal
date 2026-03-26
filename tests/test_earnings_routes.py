from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import RefreshState, app


def _snapshot():
    company = SimpleNamespace(
        id=1,
        ticker="AAPL",
        cik="0000320193",
        name="Apple Inc.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Consumer Electronics",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime.now(timezone.utc))


def _install_earnings_overrides(monkeypatch, releases):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda *_args, **_kwargs: RefreshState(triggered=True, reason="stale", ticker="AAPL", job_id="job-1"),
    )
    monkeypatch.setattr(main_module, "get_company_earnings_releases", lambda *_args, **_kwargs: releases)
    monkeypatch.setattr(
        main_module,
        "get_company_earnings_cache_status",
        lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"),
    )


def test_earnings_route_returns_cached_rows(monkeypatch):
    _install_earnings_overrides(
        monkeypatch,
        [
            SimpleNamespace(
                accession_number="0001",
                form="8-K",
                filing_date=datetime(2026, 4, 28, tzinfo=timezone.utc).date(),
                report_date=datetime(2026, 3, 31, tzinfo=timezone.utc).date(),
                source_url="https://www.sec.gov/Archives/edgar/data/1/1/omega-99-1.htm",
                primary_document="omega-8k.htm",
                exhibit_document="omega-99-1.htm",
                exhibit_type="99.1",
                reported_period_label="first quarter 2026",
                reported_period_end=datetime(2026, 3, 31, tzinfo=timezone.utc).date(),
                revenue=3_250_000_000.0,
                operating_income=610_000_000.0,
                net_income=455_000_000.0,
                diluted_eps=1.32,
                revenue_guidance_low=3_400_000_000.0,
                revenue_guidance_high=3_550_000_000.0,
                eps_guidance_low=1.4,
                eps_guidance_high=1.52,
                share_repurchase_amount=500_000_000.0,
                dividend_per_share=0.25,
                highlights=["Revenue grew 8% year over year."],
                parse_state="parsed",
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/earnings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["ticker"] == "AAPL"
    assert payload["earnings_releases"][0]["exhibit_type"] == "99.1"
    assert payload["earnings_releases"][0]["revenue_guidance_high"] == 3550000000.0
    assert payload["refresh"]["triggered"] is False


def test_earnings_summary_route_aggregates_releases(monkeypatch):
    _install_earnings_overrides(
        monkeypatch,
        [
            SimpleNamespace(
                accession_number="0001",
                form="8-K",
                filing_date=datetime(2026, 4, 28, tzinfo=timezone.utc).date(),
                report_date=datetime(2026, 3, 31, tzinfo=timezone.utc).date(),
                source_url="https://www.sec.gov/Archives/edgar/data/1/1/omega-99-1.htm",
                primary_document="omega-8k.htm",
                exhibit_document="omega-99-1.htm",
                exhibit_type="99.1",
                reported_period_label="first quarter 2026",
                reported_period_end=datetime(2026, 3, 31, tzinfo=timezone.utc).date(),
                revenue=3_250_000_000.0,
                operating_income=610_000_000.0,
                net_income=455_000_000.0,
                diluted_eps=1.32,
                revenue_guidance_low=3_400_000_000.0,
                revenue_guidance_high=3_550_000_000.0,
                eps_guidance_low=1.4,
                eps_guidance_high=1.52,
                share_repurchase_amount=500_000_000.0,
                dividend_per_share=0.25,
                highlights=["Revenue grew 8% year over year."],
                parse_state="parsed",
            ),
            SimpleNamespace(
                accession_number="0002",
                form="8-K",
                filing_date=datetime(2026, 1, 28, tzinfo=timezone.utc).date(),
                report_date=datetime(2025, 12, 31, tzinfo=timezone.utc).date(),
                source_url="https://www.sec.gov/Archives/edgar/data/1/2/acme-8k.htm",
                primary_document="acme-8k.htm",
                exhibit_document=None,
                exhibit_type=None,
                reported_period_label=None,
                reported_period_end=datetime(2025, 12, 31, tzinfo=timezone.utc).date(),
                revenue=2_850_000_000.0,
                operating_income=520_000_000.0,
                net_income=410_000_000.0,
                diluted_eps=1.87,
                revenue_guidance_low=None,
                revenue_guidance_high=None,
                eps_guidance_low=None,
                eps_guidance_high=None,
                share_repurchase_amount=None,
                dividend_per_share=None,
                highlights=["Revenue and EPS were both up year over year."],
                parse_state="metadata_only",
            ),
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_earnings_cache_status",
        lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/earnings/summary")

    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]
    assert summary["total_releases"] == 2
    assert summary["parsed_releases"] == 1
    assert summary["metadata_only_releases"] == 1
    assert summary["releases_with_guidance"] == 1
    assert summary["releases_with_buybacks"] == 1
    assert summary["releases_with_dividends"] == 1
    assert summary["latest_revenue"] == 3250000000.0


def test_earnings_route_triggers_refresh_when_cache_is_stale(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(
        main_module,
        "get_company_earnings_releases",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_earnings_cache_status",
        lambda *_args, **_kwargs: (datetime.now(timezone.utc), "stale"),
    )
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda *_args, **_kwargs: RefreshState(triggered=True, reason="stale", ticker="AAPL", job_id="job-stale"),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/earnings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh"]["triggered"] is True
    assert payload["refresh"]["reason"] == "stale"


def test_earnings_workspace_route_returns_models_backtests_peer_and_alerts(monkeypatch):
    _install_earnings_overrides(
        monkeypatch,
        [
            SimpleNamespace(
                id=10,
                accession_number="0001",
                form="8-K",
                filing_date=datetime(2026, 4, 28, tzinfo=timezone.utc).date(),
                report_date=datetime(2026, 3, 31, tzinfo=timezone.utc).date(),
                source_url="https://www.sec.gov/Archives/edgar/data/1/1/omega-99-1.htm",
                primary_document="omega-8k.htm",
                exhibit_document="omega-99-1.htm",
                exhibit_type="99.1",
                reported_period_label="first quarter 2026",
                reported_period_end=datetime(2026, 3, 31, tzinfo=timezone.utc).date(),
                revenue=3_250_000_000.0,
                operating_income=610_000_000.0,
                net_income=455_000_000.0,
                diluted_eps=1.32,
                revenue_guidance_low=3_400_000_000.0,
                revenue_guidance_high=3_550_000_000.0,
                eps_guidance_low=1.4,
                eps_guidance_high=1.52,
                share_repurchase_amount=500_000_000.0,
                dividend_per_share=0.25,
                highlights=["Revenue grew 8% year over year."],
                parse_state="parsed",
            )
        ],
    )
    monkeypatch.setattr(main_module, "get_company_earnings_model_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "get_company_earnings_model_points",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                period_start=datetime(2026, 1, 1, tzinfo=timezone.utc).date(),
                period_end=datetime(2026, 3, 31, tzinfo=timezone.utc).date(),
                filing_type="10-Q",
                quality_score=68.0,
                quality_score_delta=4.0,
                eps_drift=0.2,
                earnings_momentum_drift=0.05,
                segment_contribution_delta=0.09,
                release_statement_coverage_ratio=0.75,
                fallback_ratio=0.2,
                stale_period_warning=False,
                quality_flags=["ok"],
                source_statement_ids=[101, 102],
                source_release_ids=[10],
                explainability={
                    "formula_version": "sec_earnings_intel_v1",
                    "period_end": "2026-03-31",
                    "filing_type": "10-Q",
                    "inputs": [
                        {
                            "field": "revenue",
                            "value": 3250000000.0,
                            "period_end": "2026-03-31",
                            "sec_tags": ["us-gaap:Revenues"],
                        }
                    ],
                    "component_values": {},
                    "proxy_usage": {},
                    "segment_deltas": [],
                    "release_statement_coverage": {},
                    "quality_formula": "q",
                    "eps_drift_formula": "e",
                    "momentum_formula": "m",
                },
            )
        ],
    )
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "build_earnings_directional_backtest",
        lambda *_args, **_kwargs: {
            "window_sessions": 3,
            "quality_directional_consistency": 0.5,
            "quality_total_windows": 2,
            "quality_consistent_windows": 1,
            "eps_directional_consistency": 1.0,
            "eps_total_windows": 1,
            "eps_consistent_windows": 1,
            "windows": [],
        },
    )
    monkeypatch.setattr(
        main_module,
        "build_earnings_peer_percentiles",
        lambda *_args, **_kwargs: {
            "peer_group_basis": "market_sector",
            "peer_group_size": 8,
            "quality_percentile": 0.75,
            "eps_drift_percentile": 0.65,
            "sector_group_size": 12,
            "sector_quality_percentile": 0.7,
            "sector_eps_drift_percentile": 0.6,
        },
    )
    monkeypatch.setattr(
        main_module,
        "build_earnings_alerts",
        lambda *_args, **_kwargs: [
            {
                "id": "quality-regime:2026-03-31",
                "type": "quality_regime_shift",
                "level": "high",
                "title": "Quality score regime shift",
                "detail": "Shifted to low quality regime",
                "period_end": datetime(2026, 3, 31, tzinfo=timezone.utc).date(),
            }
        ],
    )
    monkeypatch.setattr(
        main_module,
        "build_sector_alert_profile",
        lambda *_args, **_kwargs: {
            "quality_mid_threshold": 45.0,
            "quality_high_threshold": 65.0,
            "segment_change_threshold": 0.08,
        },
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/earnings/workspace")

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["ticker"] == "AAPL"
    assert payload["summary"]["total_releases"] == 1
    assert payload["model_points"][0]["quality_score"] == 68.0
    assert payload["peer_context"]["quality_percentile"] == 0.75
    assert payload["alerts"][0]["type"] == "quality_regime_shift"
    assert payload["refresh"]["triggered"] is False


def test_earnings_workspace_triggers_refresh_when_model_cache_missing(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_earnings_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(main_module, "get_company_earnings_model_cache_status", lambda *_args, **_kwargs: (None, "missing"))
    monkeypatch.setattr(main_module, "get_company_earnings_releases", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_earnings_model_points", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "build_earnings_directional_backtest",
        lambda *_args, **_kwargs: {
            "window_sessions": 3,
            "quality_directional_consistency": None,
            "quality_total_windows": 0,
            "quality_consistent_windows": 0,
            "eps_directional_consistency": None,
            "eps_total_windows": 0,
            "eps_consistent_windows": 0,
            "windows": [],
        },
    )
    monkeypatch.setattr(
        main_module,
        "build_earnings_peer_percentiles",
        lambda *_args, **_kwargs: {
            "peer_group_basis": "market_sector",
            "peer_group_size": 0,
            "quality_percentile": None,
            "eps_drift_percentile": None,
            "sector_group_size": 0,
            "sector_quality_percentile": None,
            "sector_eps_drift_percentile": None,
        },
    )
    monkeypatch.setattr(main_module, "build_earnings_alerts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "build_sector_alert_profile",
        lambda *_args, **_kwargs: {
            "quality_mid_threshold": 45.0,
            "quality_high_threshold": 65.0,
            "segment_change_threshold": 0.08,
        },
    )
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda *_args, **_kwargs: RefreshState(triggered=True, reason="missing", ticker="AAPL", job_id="job-model-missing"),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/earnings/workspace")

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh"]["triggered"] is True
    assert payload["refresh"]["reason"] == "missing"


def test_earnings_workspace_triggers_refresh_when_model_cache_stale(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_earnings_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(main_module, "get_company_earnings_model_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "stale"))
    monkeypatch.setattr(main_module, "get_company_earnings_releases", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_earnings_model_points", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "build_earnings_directional_backtest",
        lambda *_args, **_kwargs: {
            "window_sessions": 3,
            "quality_directional_consistency": None,
            "quality_total_windows": 0,
            "quality_consistent_windows": 0,
            "eps_directional_consistency": None,
            "eps_total_windows": 0,
            "eps_consistent_windows": 0,
            "windows": [],
        },
    )
    monkeypatch.setattr(
        main_module,
        "build_earnings_peer_percentiles",
        lambda *_args, **_kwargs: {
            "peer_group_basis": "market_sector",
            "peer_group_size": 0,
            "quality_percentile": None,
            "eps_drift_percentile": None,
            "sector_group_size": 0,
            "sector_quality_percentile": None,
            "sector_eps_drift_percentile": None,
        },
    )
    monkeypatch.setattr(main_module, "build_earnings_alerts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "build_sector_alert_profile",
        lambda *_args, **_kwargs: {
            "quality_mid_threshold": 45.0,
            "quality_high_threshold": 65.0,
            "segment_change_threshold": 0.08,
        },
    )
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda *_args, **_kwargs: RefreshState(triggered=True, reason="stale", ticker="AAPL", job_id="job-model-stale"),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/earnings/workspace")

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh"]["triggered"] is True
    assert payload["refresh"]["reason"] == "stale"
