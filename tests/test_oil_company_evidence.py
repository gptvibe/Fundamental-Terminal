from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from app.services.oil_company_evidence import collect_company_oil_evidence
from app.services.sec_edgar import FilingMetadata


FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = FIXTURES_DIR / "golden"


class _FakeClient:
    def __init__(self, payload_by_name: dict[str, str]):
        self._payload_by_name = payload_by_name

    def get_filing_document_text(self, cik: str, accession_number: str, document_name: str):
        return (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number.replace('-', '')}/{document_name}",
            self._payload_by_name[document_name],
        )


def test_oil_company_evidence_xom_golden_fixture() -> None:
    fixture = _load_golden("oil_company_evidence_xom.json")
    filing = fixture["filing"]
    payload = _load_text_fixture(fixture["source_fixture"])
    evidence = collect_company_oil_evidence(
        fixture["cik"],
        checked_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
        client=_FakeClient({filing["primary_document"]: payload}),
        companyfacts=fixture["companyfacts"],
        filing_index={
            filing["accession_number"]: FilingMetadata(
                accession_number=filing["accession_number"],
                form=filing["form"],
                filing_date=_parse_date(filing["filing_date"]),
                report_date=_parse_date(filing["report_date"]),
                primary_document=filing["primary_document"],
            )
        },
    )

    expected = fixture["expected"]
    assert evidence["status"] == expected["status"]
    assert evidence["disclosed_sensitivity"]["status"] == expected["disclosed_sensitivity"]["status"]
    assert evidence["disclosed_sensitivity"]["benchmark"] == expected["disclosed_sensitivity"]["benchmark"]
    assert evidence["disclosed_sensitivity"]["annual_after_tax_sensitivity"] == expected["disclosed_sensitivity"]["annual_after_tax_sensitivity"]
    assert evidence["diluted_shares"]["status"] == expected["diluted_shares"]["status"]
    assert evidence["diluted_shares"]["value"] == expected["diluted_shares"]["value"]
    assert evidence["diluted_shares"]["tag"] == expected["diluted_shares"]["tag"]
    assert evidence["realized_price_comparison"]["status"] == expected["realized_price_comparison"]["status"]


def test_oil_company_evidence_oxy_golden_fixture() -> None:
    fixture = _load_golden("oil_company_evidence_oxy.json")
    filing = fixture["filing"]
    payload = _load_text_fixture(fixture["source_fixture"])
    evidence = collect_company_oil_evidence(
        fixture["cik"],
        checked_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
        client=_FakeClient({filing["primary_document"]: payload}),
        companyfacts=fixture["companyfacts"],
        filing_index={
            filing["accession_number"]: FilingMetadata(
                accession_number=filing["accession_number"],
                form=filing["form"],
                filing_date=_parse_date(filing["filing_date"]),
                report_date=_parse_date(filing["report_date"]),
                primary_document=filing["primary_document"],
            )
        },
    )

    expected = fixture["expected"]
    assert evidence["status"] == expected["status"]
    assert evidence["disclosed_sensitivity"]["status"] == expected["disclosed_sensitivity"]["status"]
    assert evidence["diluted_shares"]["status"] == expected["diluted_shares"]["status"]
    assert evidence["diluted_shares"]["value"] == expected["diluted_shares"]["value"]
    assert evidence["diluted_shares"]["tag"] == expected["diluted_shares"]["tag"]
    assert evidence["realized_price_comparison"]["status"] == expected["realized_price_comparison"]["status"]
    assert evidence["realized_price_comparison"]["benchmark"] == expected["realized_price_comparison"]["benchmark"]
    first_row = evidence["realized_price_comparison"]["rows"][0]
    assert first_row["period_label"] == expected["realized_price_comparison"]["first_row"]["period_label"]
    assert first_row["realized_price"] == expected["realized_price_comparison"]["first_row"]["realized_price"]
    assert first_row["benchmark_price"] == expected["realized_price_comparison"]["first_row"]["benchmark_price"]
    assert first_row["realized_percent_of_benchmark"] == expected["realized_price_comparison"]["first_row"]["realized_percent_of_benchmark"]


def test_oil_company_evidence_marks_ambiguous_sensitivity_not_available() -> None:
    filing_index = {
        "0000034088-26-000013": FilingMetadata(
            accession_number="0000034088-26-000013",
            form="10-K",
            filing_date=date(2026, 2, 25),
            report_date=date(2025, 12, 31),
            primary_document="ambiguous.htm",
        )
    }
    payload = """
    <html><body>
      <p>A $1 per barrel change in Brent crude prices would impact annual after-tax earnings by about $650 million.</p>
      <p>A $1 per barrel change in Brent crude prices would impact annual after-tax earnings by about $400 million.</p>
    </body></html>
    """

    evidence = collect_company_oil_evidence(
        "0000034088",
        checked_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
        client=_FakeClient({"ambiguous.htm": payload}),
        companyfacts={},
        filing_index=filing_index,
    )

    assert evidence["disclosed_sensitivity"]["status"] == "not_available"
    assert "oil_sensitivity_ambiguous" in evidence["disclosed_sensitivity"]["confidence_flags"]


def _load_golden(name: str) -> dict:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))


def _load_text_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)