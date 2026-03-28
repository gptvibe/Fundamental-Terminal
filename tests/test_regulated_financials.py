from __future__ import annotations

from types import SimpleNamespace

from app.services.regulated_financials import build_regulated_entity_payload, map_fdic_financial_row


def test_map_fdic_financial_row_builds_canonical_bank_fields() -> None:
    statement = map_fdic_financial_row(
        {
            "REPDTE": "2025-12-31",
            "CERT": "3511",
            "RSSDID": "451965",
            "ASSET": "1000",
            "EQTOT": "100",
            "NETINC": "12",
            "NIM": "30",
            "NONII": "5",
            "NONIX": "20",
            "PTAXNETINC": "10",
            "DEP": "700",
            "COREDEP": "500",
            "DEPUNINS": "100",
            "LNLSNET": "600",
            "NIMY": "3.5",
            "NPERFV": "1.2",
            "IDT1CER": "11.1",
            "IDT1RWAJR": "12.2",
            "RBC1AAJ": "14.3",
            "ROA": "1.0",
            "ROE": "10.0",
            "CHBAL": "50",
        },
        source="https://api.fdic.gov/banks/financials",
        issuer_type="bank",
        confidence_score=0.94,
        confidence_flags=["matched_by_cert"],
        sec_overlay={
            "goodwill_and_intangibles": 20.0,
            "shares_outstanding": 10.0,
            "weighted_average_diluted_shares": 10.0,
        },
    )

    assert statement is not None
    assert statement.filing_type == "CALL"
    assert statement.data["net_interest_income"] == 30000.0
    assert statement.data["provision_for_credit_losses"] == 5000.0
    assert statement.data["net_interest_margin"] == 0.035
    assert statement.data["common_equity_tier1_ratio"] == 0.111
    assert statement.data["tangible_common_equity"] == 99980.0
    assert statement.data["regulated_bank_source_id"] == "fdic_bankfind_financials"
    assert statement.selected_facts["regulated_bank"]["raw_identifiers"]["cert"] == "3511"


def test_build_regulated_entity_payload_prefers_detected_reporting_basis() -> None:
    company = SimpleNamespace(
        name="Example Bancorp",
        sector="Financials",
        market_sector="Financials",
        market_industry="Banks",
    )
    financials = [
        SimpleNamespace(source="https://www.federalreserve.gov/apps/reportingforms/Report/Index/FR_Y-9C"),
    ]

    payload = build_regulated_entity_payload(company, financials)

    assert payload is not None
    assert payload["issuer_type"] == "bank_holding_company"
    assert payload["reporting_basis"] == "fr_y9c"
    assert payload["confidence_score"] == 1.0