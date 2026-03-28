from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.earnings_release import collect_earnings_releases
from app.services.sec_edgar import FilingMetadata

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class _FakeEarningsClient:
    def __init__(self, payload_by_name: dict[str, str], directory_items: list[dict[str, str]]):
        self._payload_by_name = payload_by_name
        self._directory_items = directory_items

    def get_filing_directory_index(self, cik: str, accession_number: str):
        return {"directory": {"item": self._directory_items}}

    def get_filing_document_text(self, cik: str, accession_number: str, document_name: str):
        payload = self._payload_by_name[document_name]
        source_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number.replace('-', '')}/{document_name}"
        return source_url, payload


def test_collect_earnings_releases_prefers_exhibit_and_extracts_guidance():
    filing_index = {
        "0001": FilingMetadata(
            accession_number="0001",
            form="8-K",
            filing_date=date(2026, 4, 28),
            report_date=date(2026, 3, 31),
            primary_document="omega-8k.htm",
            primary_doc_description="Item 2.02 Results of Operations and Financial Condition",
            items="2.02,9.01",
        )
    }
    client = _FakeEarningsClient(
        payload_by_name={
            "omega-99-1.htm": load_fixture("form_8k_earnings_guidance.html"),
            "omega-8k.htm": load_fixture("form_8k_earnings.html"),
        },
        directory_items=[
            {"name": "omega-8k.htm", "type": "8-K"},
            {"name": "omega-99-1.htm", "type": "EX-99.1"},
            {"name": "omega-99-2.htm", "type": "EX-99.2"},
        ],
    )

    releases = collect_earnings_releases("0000000001", filing_index, client=client)

    assert len(releases) == 1
    release = releases[0]
    assert release.parse_state == "parsed"
    assert release.exhibit_document == "omega-99-1.htm"
    assert release.exhibit_type == "99.1"
    assert release.reported_period_label == "first quarter 2026"
    assert release.reported_period_end == date(2026, 3, 31)
    assert release.revenue == 3_250_000_000.0
    assert release.operating_income == 610_000_000.0
    assert release.net_income == 455_000_000.0
    assert release.diluted_eps == 1.32
    assert release.revenue_guidance_low == 3_400_000_000.0
    assert release.revenue_guidance_high == 3_550_000_000.0
    assert release.eps_guidance_low == 1.4
    assert release.eps_guidance_high == 1.52
    assert release.share_repurchase_amount == 500_000_000.0
    assert release.dividend_per_share == 0.25
    assert release.highlights
    assert release.source_url.endswith("/omega-99-1.htm")


def test_collect_earnings_releases_falls_back_to_primary_document():
    filing_index = {
        "0002": FilingMetadata(
            accession_number="0002",
            form="8-K",
            filing_date=date(2026, 1, 28),
            report_date=date(2025, 12, 31),
            primary_document="acme-8k.htm",
            primary_doc_description="Item 2.02 Results of Operations and Financial Condition",
            items="2.02,9.01",
        )
    }
    client = _FakeEarningsClient(
        payload_by_name={"acme-8k.htm": load_fixture("form_8k_earnings.html")},
        directory_items=[],
    )

    releases = collect_earnings_releases("0000000002", filing_index, client=client)

    assert len(releases) == 1
    release = releases[0]
    assert release.parse_state == "parsed"
    assert release.exhibit_document is None
    assert release.exhibit_type is None
    assert release.source_url.endswith("/acme-8k.htm")
    assert release.revenue == 2_850_000_000.0
    assert release.diluted_eps == 1.87


def test_collect_earnings_releases_returns_metadata_only_without_document_payload():
    filing_index = {
        "0003": FilingMetadata(
            accession_number="0003",
            form="8-K",
            filing_date=date(2026, 2, 1),
            report_date=date(2026, 1, 31),
            primary_document="fallback.htm",
            primary_doc_description="Item 2.02 Results of Operations and Financial Condition",
            items="2.02,9.01",
        )
    }

    releases = collect_earnings_releases("0000000003", filing_index, client=None)

    assert len(releases) == 1
    release = releases[0]
    assert release.parse_state == "metadata_only"
    assert release.highlights == ()
    assert release.exhibit_document is None


def test_collect_earnings_releases_skips_binary_exhibit_and_falls_back_to_primary_document():
    filing_index = {
        "0004": FilingMetadata(
            accession_number="0004",
            form="8-K",
            filing_date=date(2026, 2, 15),
            report_date=date(2025, 12, 31),
            primary_document="acme-8k.htm",
            primary_doc_description="Item 2.02 Results of Operations and Financial Condition",
            items="2.02,9.01",
        )
    }
    client = _FakeEarningsClient(
        payload_by_name={
            "g123ex99_1logo.jpg": "\ufffd\ufffd\ufffd\ufffd\x00\x10JFIF\x00\x01\x02",
            "acme-8k.htm": load_fixture("form_8k_earnings.html"),
        },
        directory_items=[
            {"name": "g123ex99_1logo.jpg", "type": "EX-99.1", "description": "Exhibit 99.1 earnings release image"},
            {"name": "acme-8k.htm", "type": "8-K"},
        ],
    )

    releases = collect_earnings_releases("0000000004", filing_index, client=client)

    assert len(releases) == 1
    release = releases[0]
    assert release.parse_state == "parsed"
    assert release.exhibit_document is None
    assert release.exhibit_type is None
    assert release.source_url.endswith("/acme-8k.htm")
    assert release.revenue == 2_850_000_000.0
    assert all("\x00" not in highlight for highlight in release.highlights)


def test_collect_earnings_releases_sanitizes_highlights_control_characters():
    filing_index = {
        "0005": FilingMetadata(
            accession_number="0005",
            form="8-K",
            filing_date=date(2026, 2, 20),
            report_date=date(2025, 12, 31),
            primary_document="clean.htm",
            primary_doc_description="Item 2.02 Results of Operations and Financial Condition",
            items="2.02,9.01",
        )
    }
    client = _FakeEarningsClient(
        payload_by_name={
            "clean.htm": "<html><body><p>Revenue was $1.2 million.\x00 Guidance remains unchanged.</p></body></html>",
        },
        directory_items=[],
    )

    releases = collect_earnings_releases("0000000005", filing_index, client=client)

    assert len(releases) == 1
    release = releases[0]
    assert release.highlights
    assert all("\x00" not in highlight for highlight in release.highlights)
