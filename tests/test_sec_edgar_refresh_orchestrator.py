from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.services.sec_edgar as sec_edgar


class _FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


class _SessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self

    def __enter__(self) -> _FakeSession:
        return self.session

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _Reporter:
    def __init__(self) -> None:
        self.steps: list[tuple[str, str]] = []
        self.completed: list[str] = []
        self.failed: list[str] = []

    def step(self, stage: str, message: str) -> None:
        self.steps.append((stage, message))

    def complete(self, message: str) -> None:
        self.completed.append(message)

    def fail(self, message: str) -> None:
        self.failed.append(message)


def _make_service() -> sec_edgar.EdgarIngestionService:
    service = object.__new__(sec_edgar.EdgarIngestionService)
    service.client = SimpleNamespace()
    service.market_data = SimpleNamespace()
    service.normalizer = SimpleNamespace()
    service.filing_parser = SimpleNamespace()
    return service


def _settings(strict_official_mode: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        sec_cache_prune_max_entries=0,
        sec_cache_prune_interval_seconds=3600,
        freshness_window_hours=24,
        strict_official_mode=strict_official_mode,
    )


def _company() -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        cik="0000789019",
        ticker="MSFT",
        name="Microsoft",
        sector="Technology",
        market_sector=None,
        market_industry=None,
    )


def test_refresh_company_skips_when_cached_data_is_fresh(monkeypatch):
    service = _make_service()
    session = _FakeSession()
    company = _company()
    reporter = _Reporter()
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    cache_steps: list[str] = []

    monkeypatch.setattr(sec_edgar, "settings", _settings())
    monkeypatch.setattr(sec_edgar, "get_engine", lambda: None)
    monkeypatch.setattr(sec_edgar, "SessionLocal", _SessionFactory(session))
    monkeypatch.setattr(sec_edgar, "_find_local_company", lambda *_args, **_kwargs: company)
    monkeypatch.setattr(sec_edgar, "_latest_company_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "get_company_price_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_insider_trade_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_form144_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_earnings_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "get_company_institutional_holdings_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_beneficial_ownership_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_statement_has_segment_breakdown_key", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        sec_edgar,
        "_refresh_derived_metrics_cache",
        lambda *_args, **_kwargs: cache_steps.append("derived"),
    )
    monkeypatch.setattr(
        sec_edgar,
        "_refresh_capital_structure_cache",
        lambda *_args, **_kwargs: cache_steps.append("capital-structure"),
    )
    monkeypatch.setattr(
        sec_edgar,
        "_refresh_oil_scenario_overlay_cache",
        lambda *_args, **_kwargs: cache_steps.append("oil-scenario"),
    )
    monkeypatch.setattr(
        sec_edgar,
        "_refresh_earnings_model_cache",
        lambda *_args, **_kwargs: cache_steps.append("earnings-model"),
    )
    monkeypatch.setattr(
        service.client,
        "resolve_company",
        lambda *_args, **_kwargs: pytest.fail("SEC lookup should be skipped for fresh cached data"),
        raising=False,
    )

    result = service.refresh_company("MSFT", reporter=reporter)

    assert result.status == "skipped"
    assert result.fetched_from_sec is False
    assert result.detail == "Freshness window still valid"
    assert cache_steps == ["derived", "capital-structure", "oil-scenario", "earnings-model"]
    assert reporter.completed == ["Using fresh cached data."]
    assert session.commit_count == 1


def test_refresh_company_uses_cached_partial_insider_refresh(monkeypatch):
    service = _make_service()
    session = _FakeSession()
    company = _company()
    reporter = _Reporter()
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    stale = datetime.now(timezone.utc) - timedelta(days=3)
    submissions_seen: list[str] = []

    monkeypatch.setattr(sec_edgar, "settings", _settings())
    monkeypatch.setattr(sec_edgar, "get_engine", lambda: None)
    monkeypatch.setattr(sec_edgar, "SessionLocal", _SessionFactory(session))
    monkeypatch.setattr(sec_edgar, "_find_local_company", lambda *_args, **_kwargs: company)
    monkeypatch.setattr(sec_edgar, "_latest_company_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "get_company_price_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_insider_trade_last_checked", lambda *_args, **_kwargs: stale)
    monkeypatch.setattr(sec_edgar, "_latest_form144_last_checked", lambda *_args, **_kwargs: stale)
    monkeypatch.setattr(sec_edgar, "_latest_earnings_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "get_company_institutional_holdings_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_beneficial_ownership_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_statement_has_segment_breakdown_key", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        service.client,
        "get_submissions",
        lambda cik: submissions_seen.append(cik) or {"recent": {}},
        raising=False,
    )
    monkeypatch.setattr(service.client, "build_filing_index", lambda *_args, **_kwargs: {"a": object()}, raising=False)
    monkeypatch.setattr(
        service.client,
        "resolve_company",
        lambda *_args, **_kwargs: pytest.fail("Full SEC refresh should not run for partial cached refresh"),
        raising=False,
    )
    monkeypatch.setattr(service, "refresh_insiders", lambda **_kwargs: 2)
    monkeypatch.setattr(service, "refresh_form144", lambda **_kwargs: 1)

    result = service.refresh_company("MSFT", reporter=reporter)

    assert result.status == "fetched"
    assert result.fetched_from_sec is True
    assert result.statements_written == 0
    assert result.insider_trades_written == 2
    assert result.form144_filings_written == 1
    assert result.detail == "Cached 2 insider trades and 1 Form 144 filings"
    assert submissions_seen == [company.cik]
    assert reporter.completed == ["Refresh and compute complete."]
    assert session.commit_count >= 2


def test_refresh_company_isolates_optional_dataset_failures(monkeypatch):
    service = _make_service()
    session = _FakeSession()
    company = _company()
    reporter = _Reporter()

    monkeypatch.setattr(sec_edgar, "settings", _settings())
    monkeypatch.setattr(sec_edgar, "get_engine", lambda: None)
    monkeypatch.setattr(sec_edgar, "SessionLocal", _SessionFactory(session))
    monkeypatch.setattr(sec_edgar, "_find_local_company", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        service.client,
        "resolve_company",
        lambda identifier: SimpleNamespace(
            cik="0000789019",
            ticker=identifier,
            name="Microsoft",
            exchange="NASDAQ",
            sector="Technology",
            sic="3571",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        service.client,
        "get_submissions",
        lambda *_args, **_kwargs: {
            "tickers": ["MSFT"],
            "name": "Microsoft",
            "exchanges": ["NASDAQ"],
            "sicDescription": "Technology",
            "sic": "3571",
        },
        raising=False,
    )
    monkeypatch.setattr(service.client, "build_filing_index", lambda *_args, **_kwargs: {}, raising=False)
    monkeypatch.setattr(service.client, "get_companyfacts", lambda *_args, **_kwargs: {}, raising=False)
    monkeypatch.setattr(
        service.filing_parser,
        "parse_financial_insights",
        lambda *_args, **_kwargs: [],
        raising=False,
    )
    monkeypatch.setattr(
        service.market_data,
        "get_market_profile",
        lambda *_args, **_kwargs: sec_edgar.MarketProfile(sector="Technology", industry="Software"),
        raising=False,
    )
    monkeypatch.setattr(sec_edgar, "_upsert_company", lambda *_args, **_kwargs: company)
    monkeypatch.setattr(service, "refresh_statements", lambda **_kwargs: 3)
    monkeypatch.setattr(
        service,
        "refresh_insiders",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(service, "refresh_form144", lambda **_kwargs: 4)
    monkeypatch.setattr(service, "refresh_institutional", lambda **_kwargs: 5)
    monkeypatch.setattr(service, "refresh_beneficial_ownership", lambda **_kwargs: 6)
    monkeypatch.setattr(service, "refresh_earnings", lambda **_kwargs: 7)
    monkeypatch.setattr(service, "refresh_events", lambda **_kwargs: 8)
    monkeypatch.setattr(service, "refresh_capital_markets", lambda **_kwargs: 9)
    monkeypatch.setattr(service, "refresh_prices", lambda **_kwargs: 10)
    monkeypatch.setattr(sec_edgar, "_refresh_derived_metrics_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_capital_structure_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_oil_scenario_overlay_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_earnings_model_cache", lambda *_args, **_kwargs: None)

    result = service.refresh_company("MSFT", reporter=reporter)

    assert result.status == "fetched"
    assert result.fetched_from_sec is True
    assert result.statements_written == 3
    assert result.insider_trades_written == 0
    assert result.form144_filings_written == 4
    assert result.institutional_holdings_written == 5
    assert result.beneficial_ownership_written == 6
    assert result.earnings_releases_written == 7
    assert result.price_points_written == 10
    assert "Insider refresh failed: boom" in result.detail
    assert "Cached 4 Form 144 planned sale filing rows" in result.detail
    assert ("insider", "Insider refresh failed: boom") in reporter.steps
    assert reporter.completed == ["Refresh and compute complete."]
    assert session.rollback_count == 1
