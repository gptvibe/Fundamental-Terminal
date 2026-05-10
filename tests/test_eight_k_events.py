from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.eight_k_events import (
    collect_filing_events,
    _classify_non_8k_event,
    _build_non_8k_summary,
    _is_amendment_form,
)
from app.services.sec_edgar import FilingMetadata

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class _FakeExhibitClient:
    def __init__(self, payload_by_name: dict[str, str], directory_items: list[dict[str, str]]):
        self._payload_by_name = payload_by_name
        self._directory_items = directory_items

    def get_filing_directory_index(self, cik: str, accession_number: str):
        return {"directory": {"item": self._directory_items}}

    def get_filing_document_text(self, cik: str, accession_number: str, document_name: str):
        payload = self._payload_by_name[document_name]
        source_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number.replace('-', '')}/{document_name}"
        return source_url, payload


def test_collect_filing_events_expands_item_codes_and_amounts():
    filing_index = {
        "0000001": FilingMetadata(
            accession_number="0000001",
            form="8-K",
            filing_date=date(2026, 3, 18),
            report_date=date(2026, 3, 17),
            primary_document="a8k.htm",
            primary_doc_description="Company entered a financing agreement for $250,000,000 and disclosed Item 2.03 and Item 8.01.",
            items="2.03, 8.01",
        )
    }

    rows = collect_filing_events("0001000000", filing_index)

    assert len(rows) == 2
    assert rows[0].item_code in {"2.03", "8.01"}
    assert rows[1].item_code in {"2.03", "8.01"}
    assert rows[0].category in {"Financing", "General Update"}
    assert rows[0].key_amounts
    assert rows[0].key_amounts[0] == 250000000.0


def test_collect_filing_events_uses_unspecified_when_items_missing():
    filing_index = {
        "0000002": FilingMetadata(
            accession_number="0000002",
            form="8-K",
            filing_date=date(2026, 3, 19),
            report_date=date(2026, 3, 19),
            primary_document="b8k.htm",
            primary_doc_description="General corporate update.",
            items=None,
        )
    }

    rows = collect_filing_events("0001000000", filing_index)

    assert len(rows) == 1
    assert rows[0].item_code == "UNSPECIFIED"
    assert rows[0].category == "Other"


def test_collect_filing_events_supports_new_item_codes_and_categories():
    filing_index = {
        "0000003": FilingMetadata(
            accession_number="0000003",
            form="8-K",
            filing_date=date(2026, 3, 19),
            report_date=date(2026, 3, 19),
            primary_document="c8k.htm",
            primary_doc_description="Registrant disclosed accounting and governance updates.",
            items="4.01, 4.02, 5.03, 2.04",
        )
    }

    rows = collect_filing_events("0001000000", filing_index)

    assert len(rows) == 4
    by_item = {row.item_code: row for row in rows}
    assert by_item["2.04"].category == "Financing"
    assert by_item["4.01"].category == "Accounting"
    assert by_item["4.02"].category == "Accounting"
    assert by_item["5.03"].category == "Leadership"


def test_collect_filing_events_extracts_item_901_exhibit_references():
    filing_index = {
        "0000004": FilingMetadata(
            accession_number="0000004",
            form="8-K",
            filing_date=date(2026, 3, 19),
            report_date=date(2026, 3, 18),
            primary_document="d8k.htm",
            primary_doc_description="Item 9.01 Financial Statements and Exhibits. Exhibit 99.1 and Exhibit 10.1 were furnished.",
            items="9.01",
        )
    }

    rows = collect_filing_events("0001000000", filing_index)

    assert len(rows) == 1
    assert rows[0].item_code == "9.01"
    assert rows[0].exhibit_references == ("99.1", "10.1")


def test_collect_filing_events_extracts_exhibit_preview_for_earnings_adjacent_items():
    filing_index = {
        "0000005": FilingMetadata(
            accession_number="0000005",
            form="8-K",
            filing_date=date(2026, 4, 29),
            report_date=date(2026, 3, 31),
            primary_document="acme-8k.htm",
            primary_doc_description="Item 2.02, Item 7.01, and Item 8.01 current report.",
            items="2.02,7.01,8.01,9.01",
        )
    }
    client = _FakeExhibitClient(
        payload_by_name={
            "acme-ex99-1.htm": _load_fixture("form_8k_earnings_guidance.html"),
        },
        directory_items=[
            {"name": "acme-8k.htm", "type": "8-K"},
            {"name": "acme-ex99-1.htm", "type": "EX-99.1", "description": "Earnings release exhibit"},
        ],
    )

    rows = collect_filing_events("0001000000", filing_index, client=client)

    by_item = {row.item_code: row for row in rows}
    for target_item in ("2.02", "7.01", "8.01"):
        previews = by_item[target_item].exhibit_previews
        assert previews
        preview = previews[0]
        assert preview["accession_number"] == "0000005"
        assert preview["item_code"] == target_item
        assert preview["exhibit_filename"] == "acme-ex99-1.htm"
        assert preview["exhibit_type"] == "99.1"
        assert preview["filing_date"] == "2026-04-29"
        assert "sec.gov/Archives/edgar/data/1000000/0000005/acme-ex99-1.htm" in (preview["source_url"] or "")
        assert "Omega Corporation" in (preview["snippet"] or "")

    assert by_item["9.01"].exhibit_previews == ()


# --- new multi-form-type tests ---


def test_collect_filing_events_includes_annual_10k():
    filing_index = {
        "0000010": FilingMetadata(
            accession_number="0000010",
            form="10-K",
            filing_date=date(2026, 2, 15),
            report_date=date(2025, 12, 31),
            primary_document="10k.htm",
            primary_doc_description="Annual report on Form 10-K.",
            items=None,
        )
    }
    rows = collect_filing_events("0001000000", filing_index)
    assert len(rows) == 1
    row = rows[0]
    assert row.form == "10-K"
    assert row.category == "Annual Filing"
    assert row.is_amendment is False
    assert row.is_late_filing is False
    assert row.item_code == "10-K"


def test_collect_filing_events_flags_10k_amendment():
    filing_index = {
        "0000011": FilingMetadata(
            accession_number="0000011",
            form="10-K/A",
            filing_date=date(2026, 3, 1),
            report_date=date(2025, 12, 31),
            primary_document="10ka.htm",
            primary_doc_description=None,
            items=None,
        )
    }
    rows = collect_filing_events("0001000000", filing_index)
    assert len(rows) == 1
    row = rows[0]
    assert row.form == "10-K/A"
    assert row.is_amendment is True
    assert row.is_late_filing is False
    assert row.category == "Annual Filing"


def test_collect_filing_events_includes_quarterly_10q():
    filing_index = {
        "0000012": FilingMetadata(
            accession_number="0000012",
            form="10-Q",
            filing_date=date(2026, 5, 10),
            report_date=date(2026, 3, 31),
            primary_document="10q.htm",
            primary_doc_description=None,
            items=None,
        )
    }
    rows = collect_filing_events("0001000000", filing_index)
    assert len(rows) == 1
    row = rows[0]
    assert row.form == "10-Q"
    assert row.category == "Quarterly Filing"
    assert row.is_amendment is False


def test_collect_filing_events_includes_proxy_def14a():
    filing_index = {
        "0000013": FilingMetadata(
            accession_number="0000013",
            form="DEF 14A",
            filing_date=date(2026, 4, 1),
            report_date=None,
            primary_document="proxy.htm",
            primary_doc_description=None,
            items=None,
        )
    }
    rows = collect_filing_events("0001000000", filing_index)
    assert len(rows) == 1
    row = rows[0]
    assert row.form == "DEF 14A"
    assert row.category == "Proxy"
    assert row.is_amendment is False
    assert row.is_late_filing is False


def test_collect_filing_events_includes_form4_insider():
    filing_index = {
        "0000014": FilingMetadata(
            accession_number="0000014",
            form="4",
            filing_date=date(2026, 4, 15),
            report_date=None,
            primary_document="form4.xml",
            primary_doc_description=None,
            items=None,
        )
    }
    rows = collect_filing_events("0001000000", filing_index)
    assert len(rows) == 1
    row = rows[0]
    assert row.form == "4"
    assert row.category == "Insider"
    assert row.is_amendment is False
    assert row.is_late_filing is False


def test_collect_filing_events_includes_nt10k_as_late_filing():
    filing_index = {
        "0000015": FilingMetadata(
            accession_number="0000015",
            form="NT 10-K",
            filing_date=date(2026, 3, 16),
            report_date=date(2025, 12, 31),
            primary_document="nt10k.htm",
            primary_doc_description=None,
            items=None,
        )
    }
    rows = collect_filing_events("0001000000", filing_index)
    assert len(rows) == 1
    row = rows[0]
    assert row.form == "NT 10-K"
    assert row.category == "Late Filing Notice"
    assert row.is_late_filing is True
    assert row.is_amendment is False


def test_collect_filing_events_flags_8k_amendment():
    filing_index = {
        "0000016": FilingMetadata(
            accession_number="0000016",
            form="8-K/A",
            filing_date=date(2026, 4, 5),
            report_date=date(2026, 4, 1),
            primary_document="8ka.htm",
            primary_doc_description="Amendment to prior 8-K.",
            items="2.02",
        )
    }
    rows = collect_filing_events("0001000000", filing_index)
    assert len(rows) == 1
    row = rows[0]
    assert row.form == "8-K/A"
    assert row.is_amendment is True
    assert row.is_late_filing is False


def test_is_amendment_form():
    assert _is_amendment_form("10-K/A") is True
    assert _is_amendment_form("8-K/A") is True
    assert _is_amendment_form("10-K") is False
    assert _is_amendment_form("8-K") is False


def test_classify_non_8k_event():
    assert _classify_non_8k_event("10-K") == "Annual Filing"
    assert _classify_non_8k_event("10-K/A") == "Annual Filing"
    assert _classify_non_8k_event("20-F") == "Annual Filing"
    assert _classify_non_8k_event("10-Q") == "Quarterly Filing"
    assert _classify_non_8k_event("10-Q/A") == "Quarterly Filing"
    assert _classify_non_8k_event("DEF 14A") == "Proxy"
    assert _classify_non_8k_event("4") == "Insider"
    assert _classify_non_8k_event("5") == "Insider"
    assert _classify_non_8k_event("NT 10-K") == "Late Filing Notice"
    assert _classify_non_8k_event("NT 10-Q") == "Late Filing Notice"


def test_build_non_8k_summary_uses_description_when_present():
    summary = _build_non_8k_summary("10-K", "Custom description text.")
    assert summary == "Custom description text."


def test_build_non_8k_summary_generates_default_for_10k():
    summary = _build_non_8k_summary("10-K", None)
    assert "10-K" in summary
    assert "Annual Report" in summary


def test_build_non_8k_summary_generates_amendment_suffix():
    summary = _build_non_8k_summary("10-K/A", None)
    assert "Amendment" in summary

