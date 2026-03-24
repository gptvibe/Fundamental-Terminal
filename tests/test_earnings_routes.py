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
