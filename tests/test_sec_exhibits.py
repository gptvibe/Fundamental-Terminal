"""Tests for SEC exhibit extraction and the /api/companies/{ticker}/exhibits endpoint."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.handlers import _shared as shared_handlers
from app.api.handlers import filings as filings_handlers
from app.db import get_db_session
from app.main import app
from app.services.sec.exhibits import (
    ExhibitMetadata,
    extract_exhibits_from_index,
    tag_for_exhibit,
    tag_label,
)


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

FIXTURE_DIRECTORY_INDEX = {
    "directory": {
        "name": "0000320193-26-000001",
        "parent-href": "/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193",
        "item": [
            {
                "name": "aapl-20260101_htm.xml",
                "type": "XML",
                "size": "112345",
                "description": "XBRL Instance Document",
            },
            {
                "name": "aapl-20260101.htm",
                "type": "10-K",
                "size": "3456789",
                "description": "Annual Report",
            },
            {
                "name": "ex-99d1.htm",
                "type": "EX-99.1",
                "size": "45678",
                "description": "Earnings Release",
            },
            {
                "name": "ex-21.htm",
                "type": "EX-21",
                "size": "12345",
                "description": "Subsidiaries of the Registrant",
            },
            {
                "name": "ex-31d1.htm",
                "type": "EX-31.1",
                "size": "8765",
                "description": "Certification of CEO",
            },
            {
                "name": "ex-31d2.htm",
                "type": "EX-31.2",
                "size": "8765",
                "description": "Certification of CFO",
            },
            {
                "name": "ex-32d1.htm",
                "type": "EX-32.1",
                "size": "5432",
                "description": "Section 906 Certification",
            },
            {
                "name": "ex-10d1.htm",
                "type": "EX-10.1",
                "size": "98765",
                "description": "Material Contract",
            },
            {
                "name": "ex-23d1.htm",
                "type": "EX-23.1",
                "size": "3210",
                "description": "Consent of Independent Registered Public Accounting Firm",
            },
        ],
    }
}


# ---------------------------------------------------------------------------
# Unit tests: tag_for_exhibit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exhibit_number,expected_tag",
    [
        ("EX-99.1", "earnings_release"),
        ("EX-99.2", "press_release"),
        ("EX-99", "press_release"),
        ("EX-10", "material_contract"),
        ("EX-10.1", "material_contract"),
        ("EX-10.15", "material_contract"),
        ("EX-21", "subsidiaries"),
        ("EX-21.1", "subsidiaries"),
        ("EX-31", "certification_302"),
        ("EX-31.1", "certification_302"),
        ("EX-31.2", "certification_302"),
        ("EX-32", "certification_906"),
        ("EX-32.1", "certification_906"),
        ("EX-23", "auditor_consent"),
        ("EX-23.1", "auditor_consent"),
        ("EX-101.INS", "xbrl_data"),
        ("EX-4.2", "instrument_defining_rights"),
        ("EX-3.1", "charter_bylaws"),
        ("EX-14.1", "code_of_ethics"),
        ("EX-16.1", "auditor_letter"),
        ("EX-99.X", "press_release"),
    ],
)
def test_tag_for_exhibit_known_types(exhibit_number: str, expected_tag: str) -> None:
    assert tag_for_exhibit(exhibit_number) == expected_tag


def test_tag_for_exhibit_unknown_returns_none() -> None:
    assert tag_for_exhibit("EX-2") is None
    assert tag_for_exhibit("EX-50") is None
    assert tag_for_exhibit("10-K") is None


def test_tag_label_maps_known_tags() -> None:
    assert tag_label("earnings_release") == "Earnings Release"
    assert tag_label("material_contract") == "Material Contract"
    assert tag_label("subsidiaries") == "List of Subsidiaries"
    assert tag_label("certification_302") == "SOX 302 Certification"
    assert tag_label("certification_906") == "SOX 906 Certification"
    assert tag_label(None) is None
    assert tag_label("unknown_tag") is None


# ---------------------------------------------------------------------------
# Unit tests: extract_exhibits_from_index
# ---------------------------------------------------------------------------


def test_extract_exhibits_filters_non_exhibit_items() -> None:
    """Items without EX- prefix must be excluded."""
    exhibits = extract_exhibits_from_index(
        cik="0000320193",
        accession_number="0000320193-26-000001",
        filing_type="10-K",
        filing_date=date(2026, 1, 29),
        directory_index=FIXTURE_DIRECTORY_INDEX,
    )
    exhibit_numbers = [ex.exhibit_number for ex in exhibits]
    assert "10-K" not in exhibit_numbers
    assert "XML" not in exhibit_numbers


def test_extract_exhibits_returns_all_ex_items() -> None:
    exhibits = extract_exhibits_from_index(
        cik="0000320193",
        accession_number="0000320193-26-000001",
        filing_type="10-K",
        filing_date=date(2026, 1, 29),
        directory_index=FIXTURE_DIRECTORY_INDEX,
    )
    # 7 EX- items in fixture
    assert len(exhibits) == 7


def test_extract_exhibits_source_urls_point_to_sec() -> None:
    exhibits = extract_exhibits_from_index(
        cik="0000320193",
        accession_number="0000320193-26-000001",
        filing_type="10-K",
        filing_date=date(2026, 1, 29),
        directory_index=FIXTURE_DIRECTORY_INDEX,
    )
    for ex in exhibits:
        assert ex.source_url.startswith("https://www.sec.gov/Archives/edgar/data/"), (
            f"source_url must point to SEC EDGAR, got: {ex.source_url}"
        )
        assert ex.source_url.endswith(ex.document)


def test_extract_exhibits_tags_are_applied() -> None:
    exhibits = extract_exhibits_from_index(
        cik="0000320193",
        accession_number="0000320193-26-000001",
        filing_type="10-K",
        filing_date=date(2026, 1, 29),
        directory_index=FIXTURE_DIRECTORY_INDEX,
    )
    by_number = {ex.exhibit_number: ex for ex in exhibits}

    assert by_number["EX-99.1"].tag == "earnings_release"
    assert by_number["EX-21"].tag == "subsidiaries"
    assert by_number["EX-31.1"].tag == "certification_302"
    assert by_number["EX-31.2"].tag == "certification_302"
    assert by_number["EX-32.1"].tag == "certification_906"
    assert by_number["EX-10.1"].tag == "material_contract"
    assert by_number["EX-23.1"].tag == "auditor_consent"


def test_extract_exhibits_attaches_filing_metadata() -> None:
    filing_date = date(2026, 1, 29)
    exhibits = extract_exhibits_from_index(
        cik="0000320193",
        accession_number="0000320193-26-000001",
        filing_type="10-K",
        filing_date=filing_date,
        directory_index=FIXTURE_DIRECTORY_INDEX,
    )
    for ex in exhibits:
        assert ex.accession_number == "0000320193-26-000001"
        assert ex.filing_type == "10-K"
        assert ex.filing_date == filing_date


def test_extract_exhibits_empty_directory() -> None:
    exhibits = extract_exhibits_from_index(
        cik="0000320193",
        accession_number="0000320193-26-000001",
        filing_type="10-K",
        filing_date=None,
        directory_index={"directory": {"item": []}},
    )
    assert exhibits == []


def test_extract_exhibits_malformed_index_returns_empty() -> None:
    exhibits = extract_exhibits_from_index(
        cik="0000320193",
        accession_number="0000320193-26-000001",
        filing_type="10-K",
        filing_date=None,
        directory_index={},
    )
    assert exhibits == []


def test_extract_exhibits_skips_items_missing_name() -> None:
    index = {
        "directory": {
            "item": [
                {"type": "EX-99.1", "size": "1234", "description": "Missing name"},
            ]
        }
    }
    exhibits = extract_exhibits_from_index(
        cik="0000320193",
        accession_number="0000320193-26-000001",
        filing_type="8-K",
        filing_date=None,
        directory_index=index,
    )
    assert exhibits == []


# ---------------------------------------------------------------------------
# Route integration tests: GET /api/companies/{ticker}/exhibits
# ---------------------------------------------------------------------------


def _make_snapshot(ticker: str = "AAPL", cik: str = "0000320193"):
    company = SimpleNamespace(
        id=1,
        ticker=ticker,
        cik=cik,
        name="Apple Inc.",
        sector="Technology",
        market_sector=None,
        market_industry=None,
        oil_exposure_type="non_oil",
        oil_support_status="unsupported",
        oil_support_reasons=[],
        regulated_entity=None,
        strict_official_mode=False,
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=None)


@contextmanager
def _client_ctx():
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def _patch(monkeypatch, name: str, value) -> None:
    monkeypatch.setattr(main_module, name, value, raising=False)
    if hasattr(shared_handlers, name):
        monkeypatch.setattr(shared_handlers, name, value)
    if hasattr(filings_handlers, name):
        monkeypatch.setattr(filings_handlers, name, value)


class _MockEdgarClient:
    """Minimal EdgarClient stub for route tests."""

    def __init__(self) -> None:
        self._submissions_called = False

    def get_submissions(self, cik: str) -> dict:
        self._submissions_called = True
        return {
            "filings": {
                "recent": {
                    "accessionNumber": ["0000320193-26-000001"],
                    "form": ["8-K"],
                    "filingDate": ["2026-02-01"],
                    "reportDate": ["2026-02-01"],
                    "acceptanceDateTime": ["2026-02-01T08:00:00.000000Z"],
                    "primaryDocument": ["d12345d8k.htm"],
                    "primaryDocDescription": ["8-K"],
                    "items": ["2.02"],
                },
                "files": [],
            }
        }

    def build_filing_index(self, submissions: dict) -> dict:
        from app.services.sec_edgar import FilingMetadata, _parse_date

        return {
            "0000320193-26-000001": FilingMetadata(
                accession_number="0000320193-26-000001",
                form="8-K",
                filing_date=date(2026, 2, 1),
                primary_document="d12345d8k.htm",
            )
        }

    def get_filing_directory_index(self, cik: str, accession_number: str) -> dict:
        return FIXTURE_DIRECTORY_INDEX

    def close(self) -> None:
        pass


def test_company_exhibits_returns_exhibits(monkeypatch) -> None:
    snapshot = _make_snapshot()
    _patch(monkeypatch, "_resolve_cached_company_snapshot", lambda session, ticker: snapshot)
    _patch(monkeypatch, "EdgarClient", _MockEdgarClient)

    with _client_ctx() as client:
        response = client.get("/api/companies/AAPL/exhibits")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "sec_edgar"
    assert isinstance(body["exhibits"], list)
    assert len(body["exhibits"]) > 0
    # All exhibits must be EX- prefixed
    for exhibit in body["exhibits"]:
        assert exhibit["exhibit_number"].startswith("EX-")
        assert exhibit["source_url"].startswith("https://www.sec.gov/")
        assert exhibit["filing_index_url"].startswith("https://www.sec.gov/")
        assert "accession_number" in exhibit
        assert "filing_type" in exhibit


def test_company_exhibits_filter_by_exhibit_type(monkeypatch) -> None:
    snapshot = _make_snapshot()
    _patch(monkeypatch, "_resolve_cached_company_snapshot", lambda session, ticker: snapshot)
    _patch(monkeypatch, "EdgarClient", _MockEdgarClient)

    with _client_ctx() as client:
        response = client.get("/api/companies/AAPL/exhibits?exhibit_type=EX-99.1")

    assert response.status_code == 200
    body = response.json()
    for exhibit in body["exhibits"]:
        assert exhibit["exhibit_number"].startswith("EX-99.1")


def test_company_exhibits_filter_by_filing_type(monkeypatch) -> None:
    snapshot = _make_snapshot()
    _patch(monkeypatch, "_resolve_cached_company_snapshot", lambda session, ticker: snapshot)
    _patch(monkeypatch, "EdgarClient", _MockEdgarClient)

    with _client_ctx() as client:
        response = client.get("/api/companies/AAPL/exhibits?filing_type=10-K")

    assert response.status_code == 200
    body = response.json()
    # No 10-K filings in our mock index (only 8-K), so exhibits should be empty
    assert body["exhibits"] == []


def test_company_exhibits_unknown_ticker_returns_404(monkeypatch) -> None:
    _patch(monkeypatch, "_resolve_cached_company_snapshot", lambda session, ticker: None)

    with _client_ctx() as client:
        response = client.get("/api/companies/UNKN/exhibits")

    assert response.status_code == 404


def test_company_exhibits_tags_earnings_release(monkeypatch) -> None:
    snapshot = _make_snapshot()
    _patch(monkeypatch, "_resolve_cached_company_snapshot", lambda session, ticker: snapshot)
    _patch(monkeypatch, "EdgarClient", _MockEdgarClient)

    with _client_ctx() as client:
        response = client.get("/api/companies/AAPL/exhibits?exhibit_type=EX-99.1")

    assert response.status_code == 200
    body = response.json()
    for exhibit in body["exhibits"]:
        if exhibit["exhibit_number"] == "EX-99.1":
            assert exhibit["tag"] == "earnings_release"
            assert exhibit["tag_label"] == "Earnings Release"


def test_company_exhibits_provenance_is_sec_edgar(monkeypatch) -> None:
    snapshot = _make_snapshot()
    _patch(monkeypatch, "_resolve_cached_company_snapshot", lambda session, ticker: snapshot)
    _patch(monkeypatch, "EdgarClient", _MockEdgarClient)

    with _client_ctx() as client:
        response = client.get("/api/companies/AAPL/exhibits")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "sec_edgar"
    assert len(body["provenance"]) > 0
    for note in body["provenance"]:
        assert "SEC EDGAR" in note
