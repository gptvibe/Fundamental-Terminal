from __future__ import annotations

from datetime import date

from app.services.sec_edgar import FilingMetadata, _parse_form144_filings


def test_parse_form144_filings_extracts_xml_fields():
    payload = """
    <edgarSubmission>
      <issuerName>Acme Corp</issuerName>
      <nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>Jane Insider</nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>
      <relationshipToIssuer>Officer</relationshipToIssuer>
      <titleOfTheClassOfSecuritiesToBeSold>Common Stock</titleOfTheClassOfSecuritiesToBeSold>
      <approximateDateOfSale>2026-03-25</approximateDateOfSale>
      <numberOfSharesOrOtherUnitsToBeSold>12,500</numberOfSharesOrOtherUnitsToBeSold>
      <aggregateMarketValue>2500000</aggregateMarketValue>
      <numberOfSharesOrOtherUnitsOutstanding>490000</numberOfSharesOrOtherUnitsOutstanding>
      <nameOfEachBrokerThroughWhomTheSecuritiesAreToBeOfferedOrSold>Alpha Brokerage LLC</nameOfEachBrokerThroughWhomTheSecuritiesAreToBeOfferedOrSold>
    </edgarSubmission>
    """

    filing = FilingMetadata(
        accession_number="0001000000-26-000090",
        form="144",
        filing_date=date(2026, 3, 19),
        report_date=date(2026, 3, 19),
        primary_document="x144.xml",
        primary_doc_description=None,
        items=None,
    )

    rows = _parse_form144_filings(
        payload=payload,
        source_url="https://www.sec.gov/Archives/edgar/data/1000000/000100000026000090/x144.xml",
        filing_metadata=filing,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.form == "144"
    assert row.filer_name == "Jane Insider"
    assert row.relationship_to_issuer == "Officer"
    assert row.issuer_name == "Acme Corp"
    assert row.security_title == "Common Stock"
    assert row.planned_sale_date == date(2026, 3, 25)
    assert row.shares_to_be_sold == 12500.0
    assert row.aggregate_market_value == 2500000.0
    assert row.shares_owned_after_sale == 490000.0
    assert row.broker_name == "Alpha Brokerage LLC"


def test_parse_form144_filings_falls_back_to_text_patterns():
    payload = """
    Name of Person for Whose Account the Securities Are to Be Sold: John Holder
    Relationship to Issuer: Director
    Issuer Name: Example Industries
    Title of the Class of Securities to be Sold: Common Stock
    Approximate Date of Sale: 03/28/2026
    Number of Shares or Other Units to Be Sold: 4,250
    Aggregate Market Value: $510,000
    """

    filing = FilingMetadata(
        accession_number="0001000000-26-000091",
        form="144",
        filing_date=date(2026, 3, 20),
        report_date=date(2026, 3, 20),
        primary_document="x144.txt",
        primary_doc_description=None,
        items=None,
    )

    rows = _parse_form144_filings(
        payload=payload,
        source_url="https://www.sec.gov/Archives/edgar/data/1000000/000100000026000091/x144.txt",
        filing_metadata=filing,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.filer_name == "John Holder"
    assert row.relationship_to_issuer == "Director"
    assert row.issuer_name == "Example Industries"
    assert row.security_title == "Common Stock"
    assert row.planned_sale_date == date(2026, 3, 28)
    assert row.shares_to_be_sold == 4250.0
    assert row.aggregate_market_value == 510000.0
