from __future__ import annotations

from datetime import datetime, timedelta, timezone
from datetime import date
from types import SimpleNamespace

import pytest

import app.services.sec_edgar as sec_edgar


class _FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0
        self.statements = []
        self.objects: dict[tuple[object, int], object] = {}

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def get(self, model, key):
        return self.objects.get((model, key))


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
        exchange="NASDAQ",
        name="Microsoft",
        sector="Technology",
        market_sector=None,
        market_industry=None,
        sic="3571",
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
    monkeypatch.setattr(sec_edgar, "_latest_filing_event_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_capital_markets_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_comment_letter_last_checked", lambda *_args, **_kwargs: recent)
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
        sec_edgar,
        "_refresh_company_research_brief_cache",
        lambda *_args, **_kwargs: None,
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
    brief_refresh_steps: list[str] = []

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
    monkeypatch.setattr(sec_edgar, "_latest_filing_event_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_capital_markets_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_comment_letter_last_checked", lambda *_args, **_kwargs: recent)
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
    monkeypatch.setattr(
        sec_edgar,
        "_refresh_company_research_brief_cache",
        lambda *_args, **_kwargs: brief_refresh_steps.append("brief"),
    )

    result = service.refresh_company("MSFT", reporter=reporter)

    assert result.status == "fetched"
    assert result.fetched_from_sec is True
    assert result.statements_written == 0
    assert result.insider_trades_written == 2
    assert result.form144_filings_written == 1
    assert result.detail == "Cached 2 insider trades and 1 Form 144 filings"
    assert submissions_seen == [company.cik]
    assert brief_refresh_steps == ["brief"]
    assert reporter.completed == ["Refresh and compute complete."]
    assert session.commit_count >= 2


def test_refresh_company_rebuilds_brief_after_cached_earnings_refresh(monkeypatch):
    service = _make_service()
    session = _FakeSession()
    company = _company()
    reporter = _Reporter()
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    stale = datetime.now(timezone.utc) - timedelta(days=3)
    cache_steps: list[str] = []

    monkeypatch.setattr(sec_edgar, "settings", _settings())
    monkeypatch.setattr(sec_edgar, "get_engine", lambda: None)
    monkeypatch.setattr(sec_edgar, "SessionLocal", _SessionFactory(session))
    monkeypatch.setattr(sec_edgar, "_find_local_company", lambda *_args, **_kwargs: company)
    monkeypatch.setattr(sec_edgar, "_latest_company_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "get_company_price_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_insider_trade_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_form144_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_earnings_last_checked", lambda *_args, **_kwargs: stale)
    monkeypatch.setattr(sec_edgar, "get_company_institutional_holdings_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_beneficial_ownership_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_filing_event_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_capital_markets_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_comment_letter_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_statement_has_segment_breakdown_key", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(service.client, "get_submissions", lambda cik: {"recent": {}, "cik": cik}, raising=False)
    monkeypatch.setattr(service.client, "build_filing_index", lambda *_args, **_kwargs: {"a": object()}, raising=False)
    monkeypatch.setattr(
        service.client,
        "resolve_company",
        lambda *_args, **_kwargs: pytest.fail("Full SEC refresh should not run for cached earnings refresh"),
        raising=False,
    )
    monkeypatch.setattr(service, "refresh_earnings", lambda **_kwargs: 3)
    monkeypatch.setattr(
        sec_edgar,
        "_refresh_earnings_model_cache",
        lambda *_args, **_kwargs: cache_steps.append("earnings-model"),
    )
    monkeypatch.setattr(
        sec_edgar,
        "_refresh_company_research_brief_cache",
        lambda *_args, **_kwargs: cache_steps.append("brief"),
    )

    result = service.refresh_company("MSFT", reporter=reporter)

    assert result.status == "fetched"
    assert result.fetched_from_sec is True
    assert result.earnings_releases_written == 3
    assert cache_steps == ["earnings-model", "brief"]
    assert reporter.completed == ["Refresh and compute complete."]


def test_refresh_company_uses_cached_partial_filing_events_refresh(monkeypatch):
    service = _make_service()
    session = _FakeSession()
    company = _company()
    reporter = _Reporter()
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    stale = datetime.now(timezone.utc) - timedelta(days=3)
    submissions_seen: list[str] = []
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
    monkeypatch.setattr(sec_edgar, "_latest_filing_event_last_checked", lambda *_args, **_kwargs: stale)
    monkeypatch.setattr(sec_edgar, "_latest_capital_markets_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_comment_letter_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_statement_has_segment_breakdown_key", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        service.client,
        "get_submissions",
        lambda cik: submissions_seen.append(cik) or {"recent": {}, "cik": cik},
        raising=False,
    )
    monkeypatch.setattr(service.client, "build_filing_index", lambda *_args, **_kwargs: {"a": object()}, raising=False)
    monkeypatch.setattr(
        service.client,
        "resolve_company",
        lambda *_args, **_kwargs: pytest.fail("Full SEC refresh should not run for cached filing-events refresh"),
        raising=False,
    )
    monkeypatch.setattr(service, "refresh_events", lambda **_kwargs: 4)
    monkeypatch.setattr(
        sec_edgar,
        "_refresh_company_research_brief_cache",
        lambda *_args, **_kwargs: cache_steps.append("brief"),
    )

    result = service.refresh_company("MSFT", reporter=reporter)

    assert result.status == "fetched"
    assert result.fetched_from_sec is True
    assert result.statements_written == 0
    assert result.detail == "Cached 4 filing event rows"
    assert submissions_seen == [company.cik]
    assert cache_steps == ["brief"]
    assert reporter.completed == ["Refresh and compute complete."]


def test_refresh_company_uses_cached_partial_capital_markets_refresh(monkeypatch):
    service = _make_service()
    session = _FakeSession()
    company = _company()
    reporter = _Reporter()
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    stale = datetime.now(timezone.utc) - timedelta(days=3)
    submissions_seen: list[str] = []
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
    monkeypatch.setattr(sec_edgar, "_latest_filing_event_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_capital_markets_last_checked", lambda *_args, **_kwargs: stale)
    monkeypatch.setattr(sec_edgar, "_latest_comment_letter_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_statement_has_segment_breakdown_key", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        service.client,
        "get_submissions",
        lambda cik: submissions_seen.append(cik) or {"recent": {}, "cik": cik},
        raising=False,
    )
    monkeypatch.setattr(service.client, "build_filing_index", lambda *_args, **_kwargs: {"a": object()}, raising=False)
    monkeypatch.setattr(
        service.client,
        "resolve_company",
        lambda *_args, **_kwargs: pytest.fail("Full SEC refresh should not run for cached capital-markets refresh"),
        raising=False,
    )
    monkeypatch.setattr(service, "refresh_capital_markets", lambda **_kwargs: 3)
    monkeypatch.setattr(
        sec_edgar,
        "_refresh_company_research_brief_cache",
        lambda *_args, **_kwargs: cache_steps.append("brief"),
    )

    result = service.refresh_company("MSFT", reporter=reporter)

    assert result.status == "fetched"
    assert result.fetched_from_sec is True
    assert result.statements_written == 0
    assert result.detail == "Cached 3 capital markets rows"
    assert submissions_seen == [company.cik]
    assert cache_steps == ["brief"]
    assert reporter.completed == ["Refresh and compute complete."]


def test_refresh_company_uses_cached_partial_comment_letters_refresh(monkeypatch):
    service = _make_service()
    session = _FakeSession()
    company = _company()
    reporter = _Reporter()
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    stale = datetime.now(timezone.utc) - timedelta(days=3)
    submissions_seen: list[str] = []
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
    monkeypatch.setattr(sec_edgar, "_latest_filing_event_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_capital_markets_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_comment_letter_last_checked", lambda *_args, **_kwargs: stale)
    monkeypatch.setattr(sec_edgar, "_latest_statement_has_segment_breakdown_key", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        service.client,
        "get_submissions",
        lambda cik: submissions_seen.append(cik) or {"recent": {}, "cik": cik},
        raising=False,
    )
    monkeypatch.setattr(service.client, "build_filing_index", lambda *_args, **_kwargs: {"a": object()}, raising=False)
    monkeypatch.setattr(
        service.client,
        "resolve_company",
        lambda *_args, **_kwargs: pytest.fail("Full SEC refresh should not run for cached comment-letter refresh"),
        raising=False,
    )
    monkeypatch.setattr(service, "refresh_comment_letters", lambda **_kwargs: 2)
    monkeypatch.setattr(
        sec_edgar,
        "_refresh_company_research_brief_cache",
        lambda *_args, **_kwargs: cache_steps.append("brief"),
    )

    result = service.refresh_company("MSFT", reporter=reporter)

    assert result.status == "fetched"
    assert result.fetched_from_sec is True
    assert result.statements_written == 0
    assert result.detail == "Cached 2 SEC correspondence filings"
    assert submissions_seen == [company.cik]
    assert cache_steps == ["brief"]
    assert reporter.completed == ["Refresh and compute complete."]


def test_refresh_company_uses_full_sec_refresh_when_core_financials_are_stale(monkeypatch):
    service = _make_service()
    session = _FakeSession()
    company = _company()
    reporter = _Reporter()
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    stale = datetime.now(timezone.utc) - timedelta(days=3)
    resolved: list[str] = []

    monkeypatch.setattr(sec_edgar, "settings", _settings())
    monkeypatch.setattr(sec_edgar, "get_engine", lambda: None)
    monkeypatch.setattr(sec_edgar, "SessionLocal", _SessionFactory(session))
    monkeypatch.setattr(sec_edgar, "_find_local_company", lambda *_args, **_kwargs: company)
    monkeypatch.setattr(sec_edgar, "_latest_company_last_checked", lambda *_args, **_kwargs: stale)
    monkeypatch.setattr(sec_edgar, "get_company_price_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_insider_trade_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_form144_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_earnings_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "get_company_institutional_holdings_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_beneficial_ownership_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_filing_event_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_capital_markets_last_checked", lambda *_args, **_kwargs: recent)
    monkeypatch.setattr(sec_edgar, "_latest_comment_letter_last_checked", lambda *_args, **_kwargs: stale)
    monkeypatch.setattr(sec_edgar, "_latest_statement_has_segment_breakdown_key", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        service.client,
        "resolve_company",
        lambda identifier: resolved.append(identifier) or SimpleNamespace(
            cik=company.cik,
            ticker=identifier,
            name=company.name,
            exchange=company.exchange,
            sector=company.sector,
            sic=company.sic,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        service.client,
        "get_submissions",
        lambda *_args, **_kwargs: {
            "tickers": [company.ticker],
            "name": company.name,
            "exchanges": [company.exchange],
            "sicDescription": company.sector,
            "sic": company.sic,
        },
        raising=False,
    )
    monkeypatch.setattr(service.client, "build_filing_index", lambda *_args, **_kwargs: {}, raising=False)
    monkeypatch.setattr(service.client, "get_companyfacts", lambda *_args, **_kwargs: {}, raising=False)
    monkeypatch.setattr(service.filing_parser, "parse_financial_insights", lambda *_args, **_kwargs: [], raising=False)
    monkeypatch.setattr(
        service.market_data,
        "get_market_profile",
        lambda *_args, **_kwargs: sec_edgar.MarketProfile(sector="Technology", industry="Software"),
        raising=False,
    )
    monkeypatch.setattr(sec_edgar, "_upsert_company", lambda *_args, **_kwargs: company)
    monkeypatch.setattr(service, "refresh_statements", lambda **_kwargs: 1)
    monkeypatch.setattr(service, "refresh_insiders", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_form144", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_institutional", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_beneficial_ownership", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_earnings", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_events", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_capital_markets", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_comment_letters", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_prices", lambda **_kwargs: 0)
    monkeypatch.setattr(sec_edgar, "get_dataset_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_derived_metrics_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_capital_structure_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_oil_scenario_overlay_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_earnings_model_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_company_research_brief_cache", lambda *_args, **_kwargs: None)

    result = service.refresh_company("MSFT", reporter=reporter)

    assert resolved == ["MSFT"]
    assert result.status == "fetched"
    assert result.fetched_from_sec is True
    assert result.statements_written == 1
    assert "Normalized 1 filings" in result.detail
    assert reporter.completed == ["Refresh and compute complete."]


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
    monkeypatch.setattr(service, "refresh_comment_letters", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_prices", lambda **_kwargs: 10)
    monkeypatch.setattr(sec_edgar, "get_dataset_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_derived_metrics_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_capital_structure_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_oil_scenario_overlay_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_earnings_model_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_company_research_brief_cache", lambda *_args, **_kwargs: None)

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


def test_refresh_prices_marks_prices_checked_when_symbol_has_no_yahoo_history(monkeypatch):
    service = _make_service()
    reporter = _Reporter()
    company = _company()
    checked_at = datetime.now(timezone.utc)
    touched: list[tuple[int, datetime]] = []

    monkeypatch.setattr(sec_edgar, "settings", _settings())
    monkeypatch.setattr(
        service.market_data,
        "get_price_history",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(sec_edgar.MarketDataUnavailableError("OXYWS", "Yahoo Finance has no chart history for OXYWS.")),
        raising=False,
    )
    monkeypatch.setattr(sec_edgar, "upsert_price_history", lambda **_kwargs: pytest.fail("price upsert should not run when the symbol is unavailable"))
    monkeypatch.setattr(sec_edgar, "get_dataset_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "touch_company_price_history", lambda _session, company_id, timestamp, **_kwargs: touched.append((company_id, timestamp)))

    written = service.refresh_prices(
        session=SimpleNamespace(),
        company=company,
        checked_at=checked_at,
        reporter=reporter,
    )

    assert written == 0
    assert touched == [(company.id, checked_at)]
    assert reporter.steps[-1] == ("market", "Yahoo Finance has no chart history for OXYWS. Marking prices checked without cached bars.")


def test_refresh_company_reuses_cached_financials_when_sec_inputs_are_unchanged(monkeypatch):
    service = _make_service()
    session = _FakeSession()
    company = _company()
    reporter = _Reporter()

    filing_index = {
        "0001": sec_edgar.FilingMetadata(
            accession_number="0001",
            form="10-K",
            filing_date=date(2026, 1, 31),
            report_date=date(2025, 12, 31),
            primary_document="annual.htm",
            primary_doc_description="Annual report",
        )
    }

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
    monkeypatch.setattr(service.client, "build_filing_index", lambda *_args, **_kwargs: filing_index, raising=False)
    monkeypatch.setattr(service.client, "get_companyfacts", lambda *_args, **_kwargs: {"facts": {"us-gaap": {}}}, raising=False)
    monkeypatch.setattr(service.market_data, "get_market_profile", lambda *_args, **_kwargs: sec_edgar.MarketProfile(sector="Technology", industry="Software"), raising=False)
    monkeypatch.setattr(sec_edgar, "_build_financials_refresh_fingerprint", lambda *_args, **_kwargs: "fingerprint-1")
    monkeypatch.setattr(sec_edgar, "get_dataset_state", lambda *_args, **_kwargs: SimpleNamespace(payload_version_hash="fingerprint-1"))
    monkeypatch.setattr(sec_edgar, "_upsert_company", lambda *_args, **_kwargs: company)
    monkeypatch.setattr(
        service.filing_parser,
        "parse_financial_insights",
        lambda *_args, **_kwargs: pytest.fail("filing parser should be skipped when financial inputs are unchanged"),
        raising=False,
    )
    monkeypatch.setattr(service, "refresh_statements", lambda **_kwargs: pytest.fail("statement normalization should be skipped when financial inputs are unchanged"))
    monkeypatch.setattr(service, "refresh_insiders", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_form144", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_institutional", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_beneficial_ownership", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_earnings", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_events", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_capital_markets", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_comment_letters", lambda **_kwargs: 0)
    monkeypatch.setattr(service, "refresh_prices", lambda **_kwargs: 0)
    monkeypatch.setattr(sec_edgar, "_refresh_derived_metrics_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_capital_structure_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_oil_scenario_overlay_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_earnings_model_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "_refresh_company_research_brief_cache", lambda *_args, **_kwargs: None)

    result = service.refresh_company("MSFT", reporter=reporter)

    assert result.status == "fetched"
    assert result.fetched_from_sec is True
    assert result.statements_written == 0
    assert ("normalize", "SEC financial inputs unchanged; reusing cached normalized statements.") in reporter.steps
    assert reporter.completed == ["Refresh and compute complete."]


def test_refresh_prices_marks_prices_checked_when_yahoo_returns_no_bars(monkeypatch):
    service = _make_service()
    reporter = _Reporter()
    company = _company()
    checked_at = datetime.now(timezone.utc)
    touched: list[tuple[int, datetime]] = []

    monkeypatch.setattr(sec_edgar, "settings", _settings())
    monkeypatch.setattr(service.market_data, "get_price_history", lambda *_args, **_kwargs: [], raising=False)
    monkeypatch.setattr(sec_edgar, "upsert_price_history", lambda **_kwargs: pytest.fail("price upsert should not run when Yahoo returns no bars"))
    monkeypatch.setattr(sec_edgar, "get_dataset_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec_edgar, "touch_company_price_history", lambda _session, company_id, timestamp, **_kwargs: touched.append((company_id, timestamp)))

    written = service.refresh_prices(
        session=SimpleNamespace(),
        company=company,
        checked_at=checked_at,
        reporter=reporter,
    )

    assert written == 0
    assert touched == [(company.id, checked_at)]
    assert reporter.steps[-1] == ("market", "No Yahoo price history returned for MSFT; marking prices checked without cached bars.")


@pytest.mark.parametrize(
    ("builder_name", "helper_name", "dataset", "recompute_name", "expected_stage"),
    [
        (
            "_build_derived_metrics_inputs_fingerprint",
            "_refresh_derived_metrics_cache",
            "derived_metrics",
            "recompute_and_persist_company_derived_metrics",
            "metrics",
        ),
        (
            "_build_capital_structure_inputs_fingerprint",
            "_refresh_capital_structure_cache",
            "capital_structure",
            "recompute_and_persist_company_capital_structure",
            "capital_structure",
        ),
        (
            "_build_earnings_models_inputs_fingerprint",
            "_refresh_earnings_model_cache",
            "earnings_models",
            "recompute_and_persist_company_earnings_model_points",
            "earnings_models",
        ),
    ],
)
def test_downstream_recompute_skips_when_input_fingerprint_matches(
    monkeypatch,
    builder_name: str,
    helper_name: str,
    dataset: str,
    recompute_name: str,
    expected_stage: str,
):
    session = _FakeSession()
    reporter = _Reporter()
    checked_at = datetime.now(timezone.utc)
    marks: list[dict[str, object]] = []

    monkeypatch.setattr(sec_edgar, "settings", _settings())
    fingerprint = "matched-input-fingerprint"

    monkeypatch.setattr(sec_edgar, builder_name, lambda *_args, **_kwargs: fingerprint)

    def _fake_get_dataset_state(_session, _company_id, requested_dataset):
        if requested_dataset == dataset:
            return SimpleNamespace(payload_version_hash=fingerprint)
        return SimpleNamespace(payload_version_hash="upstream-hash")

    monkeypatch.setattr(sec_edgar, "get_dataset_state", _fake_get_dataset_state)
    monkeypatch.setattr(
        sec_edgar,
        "mark_dataset_checked",
        lambda _session, company_id, dataset_name, **kwargs: marks.append(
            {
                "company_id": company_id,
                "dataset": dataset_name,
                **kwargs,
            }
        ),
    )
    monkeypatch.setattr(
        sec_edgar,
        recompute_name,
        lambda *_args, **_kwargs: pytest.fail("recompute should be skipped when input fingerprint matches"),
    )

    written = getattr(sec_edgar, helper_name)(session, 7, checked_at, reporter)

    assert written == 0
    assert reporter.steps[-1][0] == expected_stage
    assert "Skipping" in reporter.steps[-1][1]
    assert marks == [
        {
            "company_id": 7,
            "dataset": dataset,
            "checked_at": checked_at,
            "success": True,
            "payload_version_hash": fingerprint,
            "invalidate_hot_cache": False,
        }
    ]


@pytest.mark.parametrize(
    ("builder_name", "helper_name", "dataset", "recompute_name", "expected_stage"),
    [
        (
            "_build_derived_metrics_inputs_fingerprint",
            "_refresh_derived_metrics_cache",
            "derived_metrics",
            "recompute_and_persist_company_derived_metrics",
            "metrics",
        ),
        (
            "_build_capital_structure_inputs_fingerprint",
            "_refresh_capital_structure_cache",
            "capital_structure",
            "recompute_and_persist_company_capital_structure",
            "capital_structure",
        ),
        (
            "_build_earnings_models_inputs_fingerprint",
            "_refresh_earnings_model_cache",
            "earnings_models",
            "recompute_and_persist_company_earnings_model_points",
            "earnings_models",
        ),
    ],
)
def test_downstream_recompute_runs_when_input_fingerprint_changes(
    monkeypatch,
    builder_name: str,
    helper_name: str,
    dataset: str,
    recompute_name: str,
    expected_stage: str,
):
    session = _FakeSession()
    reporter = _Reporter()
    checked_at = datetime.now(timezone.utc)
    seen_hashes: list[str | None] = []

    monkeypatch.setattr(sec_edgar, "settings", _settings())
    fingerprint = "new-input-fingerprint"

    monkeypatch.setattr(sec_edgar, builder_name, lambda *_args, **_kwargs: fingerprint)

    def _fake_get_dataset_state(_session, _company_id, requested_dataset):
        if requested_dataset == dataset:
            return SimpleNamespace(payload_version_hash="stale-fingerprint")
        return SimpleNamespace(payload_version_hash="upstream-hash")

    monkeypatch.setattr(sec_edgar, "get_dataset_state", _fake_get_dataset_state)
    monkeypatch.setattr(
        sec_edgar,
        recompute_name,
        lambda *_args, **kwargs: seen_hashes.append(kwargs.get("payload_version_hash")) or 11,
    )

    written = getattr(sec_edgar, helper_name)(session, 7, checked_at, reporter)

    assert written == 11
    assert seen_hashes == [fingerprint]
    assert reporter.steps[0][0] == expected_stage
    assert reporter.steps[0][1].startswith("Recomputing")


def test_company_research_brief_recompute_skips_when_input_fingerprint_matches(monkeypatch):
    session = _FakeSession()
    session.objects[(sec_edgar.Company, 7)] = _company()
    reporter = _Reporter()
    checked_at = datetime.now(timezone.utc)
    marks: list[dict[str, object]] = []

    monkeypatch.setattr(sec_edgar, "settings", _settings())
    monkeypatch.setattr(sec_edgar, "_build_company_research_brief_inputs_fingerprint", lambda *_args, **_kwargs: "brief-fingerprint")
    monkeypatch.setattr(sec_edgar, "get_dataset_state", lambda *_args, **_kwargs: SimpleNamespace(payload_version_hash="brief-fingerprint"))
    monkeypatch.setattr(
        sec_edgar,
        "mark_dataset_checked",
        lambda _session, company_id, dataset_name, **kwargs: marks.append(
            {
                "company_id": company_id,
                "dataset": dataset_name,
                **kwargs,
            }
        ),
    )

    def _fail(*_args, **_kwargs):
        raise AssertionError("brief recompute should be skipped")

    monkeypatch.setattr(
        "app.services.company_research_brief.recompute_and_persist_company_research_brief",
        _fail,
        raising=False,
    )

    written = sec_edgar._refresh_company_research_brief_cache(session, 7, checked_at, reporter)

    assert written == 0
    assert reporter.steps[-1] == (
        "company_research_brief",
        "Skipping company research brief recompute; dependent inputs are unchanged.",
    )
    assert marks == [
        {
            "company_id": 7,
            "dataset": "company_research_brief",
            "checked_at": checked_at,
            "success": True,
            "payload_version_hash": "brief-fingerprint",
            "invalidate_hot_cache": False,
        }
    ]


def test_company_research_brief_recompute_runs_when_input_fingerprint_changes(monkeypatch):
    session = _FakeSession()
    session.objects[(sec_edgar.Company, 7)] = _company()
    reporter = _Reporter()
    checked_at = datetime.now(timezone.utc)
    seen_hashes: list[str | None] = []

    monkeypatch.setattr(sec_edgar, "settings", _settings())
    monkeypatch.setattr(sec_edgar, "_build_company_research_brief_inputs_fingerprint", lambda *_args, **_kwargs: "brief-fingerprint-new")
    monkeypatch.setattr(sec_edgar, "get_dataset_state", lambda *_args, **_kwargs: SimpleNamespace(payload_version_hash="brief-fingerprint-old"))

    def _recompute(_session, _company_id, **kwargs):
        seen_hashes.append(kwargs.get("payload_version_hash"))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.company_research_brief.recompute_and_persist_company_research_brief",
        _recompute,
        raising=False,
    )

    written = sec_edgar._refresh_company_research_brief_cache(session, 7, checked_at, reporter)

    assert written == 1
    assert seen_hashes == ["brief-fingerprint-new"]
    assert reporter.steps[0] == ("company_research_brief", "Recomputing company research brief cache...")
