from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import RefreshState, app
from app.services.sec_edgar import FilingMetadata


def _snapshot(ticker: str = "AAPL", cik: str = "0000320193"):
    company = SimpleNamespace(
        ticker=ticker,
        cik=cik,
        name="Apple Inc.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Consumer Electronics",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime.now(timezone.utc))


class _FakeEdgarClient:
    def __init__(self, filings: dict[str, FilingMetadata]):
        self._filings = filings

    def get_submissions(self, cik: str):
        return {"cik": cik}

    def build_filing_index(self, submissions: dict):
        return self._filings

    def close(self):
        return None


def _install_common_overrides(monkeypatch, filings: dict[str, FilingMetadata]):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(main_module, "_trigger_refresh", lambda *_args, **_kwargs: RefreshState(triggered=True, reason="missing", ticker="AAPL", job_id="job-1"))
    monkeypatch.setattr(main_module, "_serialize_company", lambda *_args, **_kwargs: {
        "ticker": "AAPL",
        "cik": "0000320193",
        "name": "Apple Inc.",
        "sector": "Technology",
        "market_sector": "Technology",
        "market_industry": "Consumer Electronics",
        "last_checked": datetime.now(timezone.utc).isoformat(),
        "last_checked_financials": None,
        "last_checked_prices": None,
        "last_checked_insiders": None,
        "last_checked_institutional": None,
        "last_checked_filings": None,
        "cache_state": "fresh",
    })
    monkeypatch.setattr(main_module, "EdgarClient", lambda: _FakeEdgarClient(filings))


def test_events_route_classifies_item_codes(monkeypatch):
    filings = {
        "0001": FilingMetadata(
            accession_number="0001",
            form="8-K",
            filing_date=date(2026, 3, 1),
            report_date=date(2026, 2, 28),
            primary_document="a8k.htm",
            primary_doc_description="",
            items="2.02,9.01",
        )
    }
    _install_common_overrides(monkeypatch, filings)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/events")

    assert response.status_code == 200
    payload = response.json()
    assert payload["events"]
    assert payload["events"][0]["category"] == "Earnings"
    assert payload["events"][0]["form"] == "8-K"


def test_governance_route_filters_proxy_forms(monkeypatch):
    filings = {
        "0002": FilingMetadata(
            accession_number="0002",
            form="DEF 14A",
            filing_date=date(2026, 2, 15),
            report_date=date(2026, 2, 10),
            primary_document="proxy.htm",
            primary_doc_description="Definitive proxy statement",
            items=None,
        ),
        "0003": FilingMetadata(
            accession_number="0003",
            form="10-Q",
            filing_date=date(2026, 2, 1),
            report_date=date(2026, 1, 31),
            primary_document="10q.htm",
            primary_doc_description=None,
            items=None,
        ),
    }
    _install_common_overrides(monkeypatch, filings)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/governance")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["filings"]) == 1
    assert payload["filings"][0]["form"] == "DEF 14A"


def test_beneficial_ownership_route_flags_amendments(monkeypatch):
    filings = {
        "0004": FilingMetadata(
            accession_number="0004",
            form="SC 13D/A",
            filing_date=date(2026, 1, 20),
            report_date=date(2026, 1, 18),
            primary_document="sc13da.htm",
            primary_doc_description=None,
            items=None,
        )
    }
    _install_common_overrides(monkeypatch, filings)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/beneficial-ownership")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filings"]
    assert payload["filings"][0]["base_form"] == "SC 13D"
    assert payload["filings"][0]["is_amendment"] is True


def test_serialize_insider_trade_includes_filing_metadata_fields():
    trade = SimpleNamespace(
        insider_name="Jane Doe",
        role="Chief Executive Officer",
        transaction_date=date(2026, 3, 5),
        filing_date=date(2026, 3, 6),
        filing_type="4",
        accession_number="0000320193-26-000001",
        source="https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/xslF345X05/wk-form4.xml",
        action="BUY",
        transaction_code="P",
        shares=12500.0,
        price=182.5,
        value=2_281_250.0,
        ownership_after=950000.0,
        is_10b5_1=False,
    )

    payload = main_module._serialize_insider_trade(trade)

    assert payload.filing_date == date(2026, 3, 6)
    assert payload.filing_type == "4"
    assert payload.accession_number == "0000320193-26-000001"
    assert payload.source and payload.source.startswith("https://www.sec.gov/Archives")


def test_serialize_institutional_holding_includes_filing_metadata_fields():
    fund = SimpleNamespace(fund_name="Example Capital", fund_manager="Example Capital Management")
    holding = SimpleNamespace(
        fund=fund,
        accession_number="0000950123-26-001234",
        reporting_date=date(2025, 12, 31),
        filing_date=date(2026, 2, 14),
        shares_held=1_500_000.0,
        market_value=245_000_000.0,
        change_in_shares=50_000.0,
        percent_change=3.45,
        portfolio_weight=4.2,
        source="https://www.sec.gov/Archives/edgar/data/12345/000095012326001234/form13fInfoTable.xml",
    )

    payload = main_module._serialize_institutional_holding(holding)

    assert payload.accession_number == "0000950123-26-001234"
    assert payload.filing_date == date(2026, 2, 14)
    assert payload.source and payload.source.startswith("https://www.sec.gov/Archives")
