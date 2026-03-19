from __future__ import annotations

from datetime import date

from app.services.capital_markets import collect_capital_markets_events
from app.services.sec_edgar import FilingMetadata


def test_collect_capital_markets_events_extracts_registration_fields():
    filing_index = {
        "0000001": FilingMetadata(
            accession_number="0000001",
            form="S-3",
            filing_date=date(2026, 3, 20),
            report_date=date(2026, 3, 20),
            primary_document="s3.htm",
            primary_doc_description="Shelf registration statement for up to $500,000,000 of common stock.",
            items=None,
        )
    }

    rows = collect_capital_markets_events("0001000000", filing_index)

    assert len(rows) == 1
    row = rows[0]
    assert row.form == "S-3"
    assert row.event_type == "Registration"
    assert row.security_type == "Common Equity"
    assert row.offering_amount == 500000000.0
    assert row.shelf_size == 500000000.0
    assert row.is_late_filer is False


def test_collect_capital_markets_events_marks_late_filer_notices():
    filing_index = {
        "0000002": FilingMetadata(
            accession_number="0000002",
            form="NT 10-Q",
            filing_date=date(2026, 3, 21),
            report_date=date(2026, 3, 21),
            primary_document="nt10q.htm",
            primary_doc_description="Notification of inability to timely file quarterly report.",
            items=None,
        )
    }

    rows = collect_capital_markets_events("0001000000", filing_index)

    assert len(rows) == 1
    row = rows[0]
    assert row.event_type == "Late Filing Notice"
    assert row.is_late_filer is True
