from __future__ import annotations

from datetime import date

from app.services.filing_risk_signals import extract_filing_risk_signals
from app.services.sec_edgar import FilingMetadata


def test_extract_filing_risk_signals_detects_investor_relevant_categories() -> None:
    filing = FilingMetadata(
        accession_number="0000123456-26-000123",
        form="10-K",
        filing_date=date(2026, 2, 28),
    )
    filing_text = """
        Management concluded that a material weakness in internal control over financial reporting existed as of year end.
        The company disclosed substantial doubt about its ability to continue as a going concern for the next twelve months.
        One major customer accounted for 38% of annual revenue, which creates customer concentration risk.
        We depend on a sole source supplier for a critical component.
        The borrower was not in compliance with certain financial covenants and obtained a waiver of a covenant.
        During the quarter, the company recorded a goodwill impairment charge related to the reporting unit.
        The board approved a restructuring plan and workforce reduction program.
        After a ransomware attack and cybersecurity incident, certain systems were taken offline.
        Management determined prior period financial statements should no longer be relied upon and a restatement will be required.
        The issuer noted it was unable to timely file and referenced an NT 10-K notification of late filing.
    """

    signals = extract_filing_risk_signals(
        cik="0000123456",
        ticker="ACME",
        filing_metadata=filing,
        filing_text=filing_text,
        source="https://www.sec.gov/Archives/edgar/data/123456/filing.htm",
    )

    categories = {signal.signal_category for signal in signals}
    assert categories == {
        "material_weakness",
        "going_concern",
        "customer_concentration",
        "supplier_concentration",
        "covenant_risk",
        "impairment",
        "restructuring",
        "cybersecurity_incident",
        "restatement",
        "late_filing",
    }
    assert all(signal.accession_number == "0000123456-26-000123" for signal in signals)
    assert all(signal.form_type == "10-K" for signal in signals)
    assert all(signal.context_snippet for signal in signals)
    assert next(signal for signal in signals if signal.signal_category == "material_weakness").severity == "high"
    assert next(signal for signal in signals if signal.signal_category == "late_filing").severity == "high"


def test_extract_filing_risk_signals_ignores_unsupported_forms_and_empty_text() -> None:
    unsupported = FilingMetadata(accession_number="0000123456-26-000124", form="S-8", filing_date=date(2026, 3, 1))

    assert extract_filing_risk_signals(cik="0000123456", filing_metadata=unsupported, filing_text="material weakness") == []
    assert extract_filing_risk_signals(
        cik="0000123456",
        filing_metadata=FilingMetadata(accession_number="0000123456-26-000125", form="8-K", filing_date=date(2026, 3, 2)),
        filing_text="   ",
    ) == []