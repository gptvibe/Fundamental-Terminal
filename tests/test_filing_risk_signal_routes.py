from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.handlers import _shared as shared_handlers
from app.api.handlers import filings as filings_handlers
from app.db import get_db_session
from app.main import RefreshState, app
from app.services.filing_parser import ParsedFilingInsight
from app.services.sec_edgar import FilingMetadata, _build_filing_risk_signal_payloads


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
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc))


@contextmanager
def _client():
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def _patch_handler_namespaces(monkeypatch, name: str, value) -> None:
    monkeypatch.setattr(main_module, name, value)
    if hasattr(shared_handlers, name):
        monkeypatch.setattr(shared_handlers, name, value)
    if hasattr(filings_handlers, name):
        monkeypatch.setattr(filings_handlers, name, value)


def test_build_filing_risk_signal_payloads_uses_parser_output() -> None:
    company = SimpleNamespace(id=7, ticker="ACME", cik="0000000007")
    checked_at = datetime(2026, 5, 3, 9, 30, tzinfo=timezone.utc)
    parsed_insight = ParsedFilingInsight(
        accession_number="0000000007-26-000010",
        filing_type="10-K",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        source="https://www.sec.gov/Archives/edgar/data/7/000000000726000010/form10k.htm",
        data={
            "risk_signals": [
                {
                    "ticker": "ACME",
                    "cik": "0000000007",
                    "accession_number": "0000000007-26-000010",
                    "form_type": "10-K",
                    "filed_date": date(2026, 2, 28),
                    "signal_category": "going_concern",
                    "matched_phrase": "substantial doubt",
                    "context_snippet": "Management concluded substantial doubt exists about the company's ability to continue as a going concern.",
                    "confidence": "high",
                    "severity": "high",
                    "source": "https://www.sec.gov/Archives/edgar/data/7/000000000726000010/form10k.htm",
                    "provenance": "sec_filing_text",
                }
            ]
        },
    )

    payloads = _build_filing_risk_signal_payloads(company, [parsed_insight], checked_at)

    assert payloads == [
        {
            "company_id": 7,
            "ticker": "ACME",
            "cik": "0000000007",
            "accession_number": "0000000007-26-000010",
            "form_type": "10-K",
            "filed_date": date(2026, 2, 28),
            "signal_category": "going_concern",
            "matched_phrase": "substantial doubt",
            "context_snippet": "Management concluded substantial doubt exists about the company's ability to continue as a going concern.",
            "confidence": "high",
            "severity": "high",
            "source": "https://www.sec.gov/Archives/edgar/data/7/000000000726000010/form10k.htm",
            "provenance": "sec_filing_text",
            "last_updated": checked_at,
            "last_checked": checked_at,
        }
    ]


def test_build_filing_risk_signal_payloads_includes_nt_repeat_signal_from_filing_index() -> None:
    company = SimpleNamespace(id=7, ticker="ACME", cik="0000000007")
    checked_at = datetime(2026, 5, 3, 9, 30, tzinfo=timezone.utc)
    filing_index = {
        "nt-q": FilingMetadata(
            accession_number="0000000007-26-000090",
            form="NT 10-Q",
            filing_date=date(2026, 4, 10),
            report_date=date(2026, 4, 10),
            primary_document="nt10q.htm",
        ),
        "nt-k": FilingMetadata(
            accession_number="0000000007-26-000060",
            form="NT 10-K",
            filing_date=date(2026, 2, 20),
            report_date=date(2026, 2, 20),
            primary_document="nt10k.htm",
        ),
    }

    payloads = _build_filing_risk_signal_payloads(
        company,
        [],
        checked_at,
        filing_index=filing_index,
    )

    categories = {payload["signal_category"] for payload in payloads}
    assert "nt_non_timely_10q" in categories
    assert "nt_non_timely_10k" in categories
    assert "nt_non_timely_repeat" in categories
    repeated = next(payload for payload in payloads if payload["signal_category"] == "nt_non_timely_repeat")
    assert repeated["severity"] == "high"


def test_company_filing_risk_signals_route_exposes_recent_cached_signals(monkeypatch) -> None:
    signal = SimpleNamespace(
        ticker="AAPL",
        cik="0000320193",
        accession_number="0000320193-26-000010",
        form_type="10-K",
        filed_date=date(2026, 2, 1),
        signal_category="material_weakness",
        matched_phrase="material weakness",
        context_snippet="Management identified a material weakness in internal control over financial reporting.",
        confidence="high",
        severity="high",
        source="https://www.sec.gov/Archives/edgar/data/320193/000032019326000010/form10k.htm",
        provenance="sec_filing_text",
        last_updated=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
        last_checked=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
    )

    _patch_handler_namespaces(monkeypatch, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    _patch_handler_namespaces(
        monkeypatch,
        "get_company_filing_risk_signals_cache_status",
        lambda *_args, **_kwargs: (datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc), "fresh"),
    )
    _patch_handler_namespaces(monkeypatch, "get_company_filing_risk_signals", lambda *_args, **_kwargs: [signal])

    with _client() as client:
        response = client.get("/api/companies/AAPL/filing-risk-signals")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total_signals": 1,
        "high_severity_count": 1,
        "medium_severity_count": 0,
        "latest_filed_date": "2026-02-01",
    }
    assert payload["signals"][0]["signal_category"] == "material_weakness"
    assert payload["signals"][0]["matched_phrase"] == "material weakness"
    assert payload["refresh"] == {
        "triggered": False,
        "reason": "fresh",
        "ticker": "AAPL",
        "job_id": None,
    }


def test_company_filing_risk_signals_openapi_contract() -> None:
    with _client() as client:
        schema = client.get("/openapi.json").json()

    response_schema = schema["paths"]["/api/companies/{ticker}/filing-risk-signals"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    component_name = response_schema["$ref"].split("/")[-1]
    fields = set(schema["components"]["schemas"][component_name]["properties"].keys())

    assert {"company", "summary", "signals", "refresh", "diagnostics"}.issubset(fields)