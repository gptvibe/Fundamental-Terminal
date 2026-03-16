from __future__ import annotations

from datetime import date

from app.services.sec_edgar import FilingMetadata, _parse_form4_transactions


def test_parse_form4_transactions_extracts_extended_metadata_fields():
    xml_payload = """
    <ownershipDocument>
      <periodOfReport>2026-03-08</periodOfReport>
      <reportingOwner>
        <reportingOwnerId>
          <rptOwnerName>Doe, Jane</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
          <isOfficer>1</isOfficer>
          <officerTitle>Chief Financial Officer</officerTitle>
        </reportingOwnerRelationship>
      </reportingOwner>
      <derivativeTable>
        <derivativeTransaction>
          <securityTitle><value>Call Option</value></securityTitle>
          <transactionDate><value>2026-03-07</value></transactionDate>
          <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
          <footnoteId id="F1"/>
          <transactionAmounts>
            <transactionShares><value>1000</value></transactionShares>
            <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
          </transactionAmounts>
          <postTransactionAmounts>
            <sharesOwnedFollowingTransaction><value>5000</value></sharesOwnedFollowingTransaction>
            <ownershipNature>
              <directOrIndirectOwnership><value>I</value></directOrIndirectOwnership>
            </ownershipNature>
          </postTransactionAmounts>
          <conversionOrExercisePrice><value>45.12</value></conversionOrExercisePrice>
          <expirationDate><value>2028-01-15</value></expirationDate>
        </derivativeTransaction>
      </derivativeTable>
      <footnotes>
        <footnote id="F1">Transaction executed pursuant to a Rule 10b5-1 trading plan and covers an option exercise.</footnote>
      </footnotes>
    </ownershipDocument>
    """

    filing = FilingMetadata(
      accession_number="0000000000-26-000001",
      form="4",
      filing_date=date(2026, 3, 9),
      report_date=date(2026, 3, 8),
      primary_document="x.xml",
      primary_doc_description=None,
      items=None,
    )

    trades = _parse_form4_transactions(
      xml_payload=xml_payload,
      source_url="https://www.sec.gov/Archives/edgar/data/1/1/x.xml",
      filing_metadata=filing,
    )

    assert len(trades) == 1
    trade = trades[0]
    assert trade.security_title == "Call Option"
    assert trade.is_derivative is True
    assert trade.ownership_nature == "indirect"
    assert trade.exercise_price == 45.12
    assert trade.expiration_date == date(2028, 1, 15)
    assert trade.footnote_tags is not None
    assert "10b5-1" in trade.footnote_tags
    assert "option-exercise" in trade.footnote_tags
