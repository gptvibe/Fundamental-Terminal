from __future__ import annotations

from datetime import date

from app.services.filing_risk_signals import build_non_timely_filing_signals, extract_filing_risk_signals
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


def test_build_non_timely_filing_signals_emits_single_nt_notice() -> None:
    filing_index = {
        "0000001": FilingMetadata(
            accession_number="0000123456-26-000201",
            form="NT 10-Q",
            filing_date=date(2026, 3, 20),
            report_date=date(2026, 3, 20),
        )
    }

    signals = build_non_timely_filing_signals(
        cik="0000123456",
        ticker="ACME",
        filing_index=filing_index,
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.signal_category == "nt_non_timely_10q"
    assert signal.form_type == "NT 10-Q"
    assert signal.matched_phrase == "NT 10-Q"
    assert signal.severity == "medium"


def test_build_non_timely_filing_signals_escalates_repeated_notices() -> None:
    filing_index = {
        "0000001": FilingMetadata(
            accession_number="0000123456-26-000201",
            form="NT 10-Q",
            filing_date=date(2026, 4, 12),
            report_date=date(2026, 4, 12),
        ),
        "0000002": FilingMetadata(
            accession_number="0000123456-26-000175",
            form="NT 10-K",
            filing_date=date(2025, 12, 15),
            report_date=date(2025, 12, 15),
        ),
        "0000003": FilingMetadata(
            accession_number="0000123456-25-000100",
            form="NT 10-Q",
            filing_date=date(2024, 12, 15),
            report_date=date(2024, 12, 15),
        ),
    }

    signals = build_non_timely_filing_signals(
        cik="0000123456",
        ticker="ACME",
        filing_index=filing_index,
        repeat_lookback_days=365,
    )

    categories = {signal.signal_category for signal in signals}
    assert categories == {"nt_non_timely_10q", "nt_non_timely_10k", "nt_non_timely_repeat"}
    repeated = next(signal for signal in signals if signal.signal_category == "nt_non_timely_repeat")
    assert repeated.severity == "high"
    assert repeated.form_type in {"NT 10-K", "NT 10-Q"}
    assert "NT 10-K: 1" in repeated.context_snippet
    assert "NT 10-Q: 1" in repeated.context_snippet