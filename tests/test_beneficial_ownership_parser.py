from __future__ import annotations

from datetime import date

from app.services.beneficial_ownership import collect_beneficial_ownership_reports
from app.services.sec_edgar import FilingMetadata


class _FakeClient:
    def __init__(self, payload: str):
        self.payload = payload

    def get_filing_document_text(self, cik: str, accession_number: str, document_name: str):
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
