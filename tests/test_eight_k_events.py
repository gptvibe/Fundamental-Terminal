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
