from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from app.services.sec_edgar import EdgarClient, FilingMetadata, NormalizedCommentLetter

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class _FakeCommentLetterClient(EdgarClient):
    def __init__(self, payload_by_name: dict[str, str], directory_items: list[dict[str, str]]):
        super().__init__()
        self._payload_by_name = payload_by_name
        self._directory_items = directory_items

    def get_filing_directory_index(self, cik: str, accession_number: str):
        return {"directory": {"item": self._directory_items}}

    def get_filing_document_text(self, cik: str, accession_number: str, document_name: str):
        payload = self._payload_by_name[document_name]
        source_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number.replace('-', '')}/{document_name}"
        return source_url, payload


def test_enrich_correspondence_filing_extracts_role_topics_and_thread() -> None:
    client = _FakeCommentLetterClient(
        payload_by_name={
            "staff-letter.htm": load_fixture("sec_comment_letter_staff.html"),
            "response-letter.htm": load_fixture("sec_comment_letter_issuer.html"),
        },
        directory_items=[
            {"name": "staff-letter.htm", "type": "CORRESP"},
            {"name": "response-letter.htm", "type": "CORRESP"},
        ],
    )
    metadata = FilingMetadata(
        accession_number="0000123456-26-000777",
        form="CORRESP",
        filing_date=date(2026, 3, 12),
        acceptance_datetime=datetime(2026, 3, 12, 15, 30, tzinfo=timezone.utc),
        primary_document="staff-letter.htm",
        primary_doc_description="SEC comment letter regarding revenue recognition",
    )
    normalized = NormalizedCommentLetter(
        accession_number=metadata.accession_number,
        filing_date=metadata.filing_date,
        description="SEC comment letter regarding revenue recognition",
        sec_url="https://www.sec.gov/Archives/edgar/data/123456/000012345626000777/staff-letter.htm",
    )

    enriched = client.enrich_correspondence_filing("0000123456", metadata, normalized, checked_at=datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc))

    assert enriched.document_format == "html"
    assert enriched.document_url and enriched.document_url.endswith("/staff-letter.htm")
    assert enriched.correspondent_role == "sec_staff"
    assert enriched.document_kind == "comment_letter"
    assert enriched.thread_key == "review-date:2026-03-05"
    assert "revenue_recognition" in enriched.topics
    assert "non_gaap" in enriched.topics
    assert enriched.document_text is not None
    assert "We have reviewed your filing" in enriched.document_text
    assert enriched.document_text_sha256 is not None
    assert enriched.parser_version == "corresp-parser-v1"


def test_enrich_correspondence_filing_tracks_unsupported_pdf_without_text() -> None:
    client = _FakeCommentLetterClient(
        payload_by_name={},
        directory_items=[
            {"name": "letter.pdf", "type": "CORRESP"},
        ],
    )
    metadata = FilingMetadata(
        accession_number="0000123456-26-000778",
        form="CORRESP",
        filing_date=date(2026, 3, 20),
        acceptance_datetime=datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc),
        primary_document="letter.pdf",
        primary_doc_description="Response letter upload",
    )
    normalized = NormalizedCommentLetter(
        accession_number=metadata.accession_number,
        filing_date=metadata.filing_date,
        description="Response letter upload",
        sec_url="https://www.sec.gov/Archives/edgar/data/123456/000012345626000778/letter.pdf",
    )

    enriched = client.enrich_correspondence_filing("0000123456", metadata, normalized)

    assert enriched.document_format == "pdf"
    assert enriched.document_url and enriched.document_url.endswith("/letter.pdf")
    assert enriched.document_text is None
    assert enriched.correspondent_role == "issuer"
    assert enriched.document_kind == "response_letter"
    assert enriched.parser_version == "corresp-parser-v1"