from __future__ import annotations

from datetime import date

from app.services.beneficial_ownership import collect_beneficial_ownership_reports
from app.services.sec_edgar import FilingMetadata


class _FakeClient:
    def __init__(self, payload: str):
        self.payload = payload

    def get_filing_document_text(self, cik: str, accession_number: str, document_name: str):
        if document_name.lower().endswith(".txt"):
            return (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number.replace('-', '')}/{document_name}",
                self.payload,
            )
        return (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number.replace('-', '')}/{document_name}",
            self.payload,
        )


def test_collect_beneficial_ownership_reports_extracts_party_details_from_xml():
    filing_index = {
        "0001000000-26-000001": FilingMetadata(
            accession_number="0001000000-26-000001",
            form="SC 13D",
            filing_date=date(2026, 3, 17),
            report_date=date(2026, 3, 15),
            primary_document="sc13d.xml",
            primary_doc_description="",
            items=None,
        )
    }
    payload = """
    <ownershipDocument>
      <nameOfReportingPerson>Example Capital LP</nameOfReportingPerson>
      <cik>1234567</cik>
      <amountBeneficiallyOwned>1250000</amountBeneficiallyOwned>
      <percentOfClassRepresentedByAmountInRow11>6.4</percentOfClassRepresentedByAmountInRow11>
      <dateOfEventWhichRequiresFilingOfThisStatement>2026-03-15</dateOfEventWhichRequiresFilingOfThisStatement>
      <purposeOfTransaction>Item 4 text describing strategic review intent.</purposeOfTransaction>
    </ownershipDocument>
    """

    rows = collect_beneficial_ownership_reports("0001000000", filing_index, client=_FakeClient(payload))

    assert len(rows) == 1
    assert len(rows[0].parties) == 1
    party = rows[0].parties[0]
    assert party.party_name == "Example Capital LP"
    assert party.filer_cik == "0001234567"
    assert party.shares_owned == 1250000.0
    assert party.percent_owned == 6.4
    assert party.event_date == date(2026, 3, 15)
    assert party.purpose == "Item 4 text describing strategic review intent."


def test_collect_beneficial_ownership_reports_keeps_empty_parties_when_parse_fails():
    filing_index = {
        "0001000000-26-000002": FilingMetadata(
            accession_number="0001000000-26-000002",
            form="SC 13G/A",
            filing_date=date(2026, 3, 18),
            report_date=date(2026, 3, 16),
            primary_document="sc13ga.htm",
            primary_doc_description="Amendment filing",
            items=None,
        )
    }

    rows = collect_beneficial_ownership_reports("0001000000", filing_index, client=_FakeClient("not xml"))

    assert len(rows) == 1
    assert rows[0].is_amendment is True
    assert rows[0].parties == ()


def test_collect_beneficial_ownership_reports_supports_schedule_and_plain_form_variants():
    filing_index = {
        "0001000000-26-000003": FilingMetadata(
            accession_number="0001000000-26-000003",
            form="13D",
            filing_date=date(2026, 3, 10),
            report_date=date(2026, 3, 9),
            primary_document="13d.htm",
            primary_doc_description="",
            items=None,
        ),
        "0001000000-26-000004": FilingMetadata(
            accession_number="0001000000-26-000004",
            form="Schedule 13G/A",
            filing_date=date(2026, 3, 11),
            report_date=date(2026, 3, 10),
            primary_document="13ga.htm",
            primary_doc_description="",
            items=None,
        ),
    }

    rows = collect_beneficial_ownership_reports("0001000000", filing_index)

    assert len(rows) == 2
    assert rows[0].form == "SC 13G/A"
    assert rows[0].base_form == "SC 13G"
    assert rows[0].is_amendment is True
    assert rows[1].form == "SC 13D"
    assert rows[1].base_form == "SC 13D"
    assert rows[1].is_amendment is False


def test_collect_beneficial_ownership_reports_parses_mmddyyyy_event_date_from_text():
    filing_index = {
        "0001000000-26-000005": FilingMetadata(
            accession_number="0001000000-26-000005",
            form="SC 13D",
            filing_date=date(2026, 3, 19),
            report_date=date(2026, 3, 18),
            primary_document="sc13d.htm",
            primary_doc_description="",
            items=None,
        )
    }
    payload = """
    <html><body>
    NAME OF REPORTING PERSON: Atlas Capital Partners LP
    CIK NUMBER: 1234567
    AGGREGATE AMOUNT BENEFICIALLY OWNED BY EACH REPORTING PERSON: 1,250,000
    PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW (11): 6.3%
    DATE OF EVENT WHICH REQUIRES FILING OF THIS STATEMENT: 03/15/2026
    ITEM 4. PURPOSE OF TRANSACTION The reporting person seeks constructive engagement.
    ITEM 5.
    </body></html>
    """

    rows = collect_beneficial_ownership_reports("0001000000", filing_index, client=_FakeClient(payload))

    assert len(rows) == 1
    assert len(rows[0].parties) == 1
    party = rows[0].parties[0]
    assert party.party_name == "Atlas Capital Partners LP"
    assert party.event_date == date(2026, 3, 15)
    assert party.percent_owned == 6.3


def test_collect_beneficial_ownership_reports_assigns_chain_key_and_previous_accession():
    filing_index = {
        "0001000000-26-000006": FilingMetadata(
            accession_number="0001000000-26-000006",
            form="SC 13D",
            filing_date=date(2026, 3, 10),
            report_date=date(2026, 3, 9),
            primary_document="sc13d_early.xml",
            primary_doc_description="",
            items=None,
        ),
        "0001000000-26-000007": FilingMetadata(
            accession_number="0001000000-26-000007",
            form="SC 13D/A",
            filing_date=date(2026, 3, 17),
            report_date=date(2026, 3, 16),
            primary_document="sc13da_late.xml",
            primary_doc_description="",
            items=None,
        ),
    }
    payload = """
    <ownershipDocument>
      <nameOfReportingPerson>Example Capital LP</nameOfReportingPerson>
      <cik>1234567</cik>
      <amountBeneficiallyOwned>1250000</amountBeneficiallyOwned>
      <percentOfClassRepresentedByAmountInRow11>6.4</percentOfClassRepresentedByAmountInRow11>
    </ownershipDocument>
    """

    rows = collect_beneficial_ownership_reports("0001000000", filing_index, client=_FakeClient(payload))

    assert len(rows) == 2
    latest = rows[0]
    earliest = rows[1]
    assert latest.accession_number == "0001000000-26-000007"
    assert earliest.accession_number == "0001000000-26-000006"

    assert latest.amendment_chain_key is not None
    assert latest.amendment_chain_key == earliest.amendment_chain_key
    assert earliest.amendment_sequence == 1
    assert earliest.amendment_chain_size == 2
    assert earliest.previous_accession_number is None
    assert latest.amendment_sequence == 2
    assert latest.amendment_chain_size == 2
    assert latest.previous_accession_number == "0001000000-26-000006"


def test_collect_beneficial_ownership_reports_extracts_filer_from_submission_text_fallback():
    filing_index = {
        "0001000000-26-000008": FilingMetadata(
            accession_number="0001000000-26-000008",
            form="SC 13G/A",
            filing_date=date(2026, 3, 19),
            report_date=date(2026, 3, 18),
            primary_document="sc13ga.htm",
            primary_doc_description="",
            items=None,
        )
    }
    submission_payload = """
    <SEC-DOCUMENT>
    FILED BY:
    COMPANY CONFORMED NAME:   SAMPLE CAPITAL MANAGEMENT, LP
    CENTRAL INDEX KEY:        1581123
    </SEC-DOCUMENT>
    """

    rows = collect_beneficial_ownership_reports("0001000000", filing_index, client=_FakeClient(submission_payload))

    assert len(rows) == 1
    assert len(rows[0].parties) == 1
    assert rows[0].parties[0].party_name == "SAMPLE CAPITAL MANAGEMENT, LP"
    assert rows[0].parties[0].filer_cik == "0001581123"
