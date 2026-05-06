from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.handlers import _shared as shared_handlers
from app.api.handlers import filings as filings_handlers
from app.api.handlers import financials as financials_handlers
from app.db import get_db_session
from app.main import RefreshState, app


def _snapshot(ticker: str = "AAPL", cik: str = "0000320193"):
    company = SimpleNamespace(
        id=1,
        ticker=ticker,
        cik=cik,
        name="Apple Inc.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Consumer Electronics",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc))


@contextmanager
def _client():
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def _patch_handler_namespaces(monkeypatch, name: str, value) -> None:
    if hasattr(main_module, name):
        monkeypatch.setattr(main_module, name, value)
    if hasattr(shared_handlers, name):
        monkeypatch.setattr(shared_handlers, name, value)
    if hasattr(filings_handlers, name):
        monkeypatch.setattr(filings_handlers, name, value)
    if hasattr(financials_handlers, name):
        monkeypatch.setattr(financials_handlers, name, value)


def test_company_filings_returns_stale_cached_payload_and_queues_refresh_without_live_sec(monkeypatch) -> None:
    _patch_handler_namespaces(monkeypatch, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    _patch_handler_namespaces(
        monkeypatch,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    _patch_handler_namespaces(monkeypatch, "_load_filings_from_cache", lambda *_args, **_kwargs: None)
    _patch_handler_namespaces(monkeypatch, "_filings_cache_last_checked", lambda *_args, **_kwargs: None)
    _patch_handler_namespaces(monkeypatch, "_diagnostics_for_filings_timeline", lambda *_args, **_kwargs: {"stale_flags": []})
    _patch_handler_namespaces(monkeypatch, "get_company_financials", lambda *_args, **_kwargs: [object()])
    _patch_handler_namespaces(
        monkeypatch,
        "_serialize_cached_statement_filings",
        lambda *_args, **_kwargs: [
            {
                "accession_number": "0000320193-26-000111",
                "form": "10-Q",
                "filing_date": "2026-04-30",
                "report_date": "2026-03-31",
                "primary_document": "q1.htm",
                "primary_doc_description": "Quarterly report",
                "items": None,
                "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000111/q1.htm",
            }
        ],
    )
    _patch_handler_namespaces(
        monkeypatch,
        "_trigger_refresh",
        lambda *_args, **_kwargs: RefreshState(triggered=True, reason="missing", ticker="AAPL", job_id="job-filings-missing"),
    )

    class _FailEdgarClient:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("live EdgarClient fetch should not run for company filings route")

    _patch_handler_namespaces(monkeypatch, "EdgarClient", _FailEdgarClient)

    with _client() as client:
        response = client.get("/api/companies/AAPL/filings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["timeline_source"] == "cached_financials"
    assert payload["filings"]
    assert payload["refresh"] == {
        "triggered": True,
        "reason": "missing",
        "ticker": "AAPL",
        "job_id": "job-filings-missing",
    }
    assert payload["response_metadata"] == {
        "freshness": "missing",
        "source": "cached_financials",
        "isStale": True,
        "refreshQueued": True,
        "jobId": "job-filings-missing",
    }


def test_company_financial_history_returns_stale_empty_payload_and_queues_refresh_without_live_sec(monkeypatch) -> None:
    _patch_handler_namespaces(monkeypatch, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    _patch_handler_namespaces(
        monkeypatch,
        "_trigger_refresh",
        lambda *_args, **_kwargs: RefreshState(triggered=True, reason="missing", ticker="AAPL", job_id="job-facts-missing"),
    )

    class _FailEdgarClient:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("live EdgarClient fetch should not run for company financial-history route")

    _patch_handler_namespaces(monkeypatch, "EdgarClient", _FailEdgarClient)

    class _NoCache:
        @staticmethod
        def get_stale(*_args, **_kwargs):
            return None

    _patch_handler_namespaces(monkeypatch, "sec_http_cache", _NoCache())

    with _client() as client:
        response = client.get("/api/companies/AAPL/financial-history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["facts"] == {}
    assert payload["refresh"] == {
        "triggered": True,
        "reason": "missing",
        "ticker": "AAPL",
        "job_id": "job-facts-missing",
    }
    assert payload["response_metadata"] == {
        "freshness": "missing",
        "source": "none",
        "isStale": True,
        "refreshQueued": True,
        "jobId": "job-facts-missing",
    }
