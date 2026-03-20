from __future__ import annotations

from datetime import date

from app.services.eight_k_events import collect_filing_events
from app.services.sec_edgar import FilingMetadata


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
