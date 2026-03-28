from __future__ import annotations

from app.api.schemas.financials import FinancialPayload
from app.services.segment_analysis import build_segment_analysis


def _financial_payload(*, period_end: str, revenue: int, operating_income: int | None, segment_breakdown: list[dict]) -> FinancialPayload:
    return FinancialPayload(
        filing_type="10-K",
        statement_type="canonical_xbrl",
        period_start=f"{period_end[:4]}-01-01",
        period_end=period_end,
        source="https://data.sec.gov/api/xbrl/companyfacts/CIK0000123456.json",
        last_updated="2026-03-28T00:00:00Z",
        last_checked="2026-03-28T00:00:00Z",
        revenue=revenue,
        gross_profit=None,
        operating_income=operating_income,
        net_income=None,
        total_assets=None,
        current_assets=None,
        total_liabilities=None,
        current_liabilities=None,
        retained_earnings=None,
        sga=None,
        research_and_development=None,
        interest_expense=None,
        income_tax_expense=None,
        inventory=None,
        cash_and_cash_equivalents=None,
        short_term_investments=None,
        cash_and_short_term_investments=None,
        accounts_receivable=None,
        accounts_payable=None,
        goodwill_and_intangibles=None,
        current_debt=None,
        long_term_debt=None,
        stockholders_equity=None,
        lease_liabilities=None,
        operating_cash_flow=None,
        depreciation_and_amortization=None,
        capex=None,
        acquisitions=None,
        debt_changes=None,
        dividends=None,
        share_buybacks=None,
        free_cash_flow=None,
        eps=None,
        shares_outstanding=None,
        stock_based_compensation=None,
        weighted_average_diluted_shares=None,
        segment_breakdown=segment_breakdown,
        reconciliation=None,
    )


def test_build_segment_analysis_returns_mix_margin_concentration_and_disclosures() -> None:
    latest = _financial_payload(
        period_end="2025-12-31",
        revenue=1_000,
        operating_income=260,
        segment_breakdown=[
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 520, "share_of_revenue": 0.52, "operating_income": 170, "assets": None},
            {"segment_id": "devices", "segment_name": "Devices", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 300, "share_of_revenue": 0.30, "operating_income": 45, "assets": None},
            {"segment_id": "services", "segment_name": "Services", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 180, "share_of_revenue": 0.18, "operating_income": 45, "assets": None},
            {"segment_id": "us", "segment_name": "United States", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 610, "share_of_revenue": 0.61, "operating_income": None, "assets": None},
            {"segment_id": "emea", "segment_name": "EMEA", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 210, "share_of_revenue": 0.21, "operating_income": None, "assets": None},
            {"segment_id": "apac", "segment_name": "APAC", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 180, "share_of_revenue": 0.18, "operating_income": None, "assets": None},
        ],
    )
    previous = _financial_payload(
        period_end="2024-12-31",
        revenue=900,
        operating_income=220,
        segment_breakdown=[
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 410, "share_of_revenue": 0.4556, "operating_income": 125, "assets": None},
            {"segment_id": "devices", "segment_name": "Devices", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 340, "share_of_revenue": 0.3778, "operating_income": 55, "assets": None},
            {"segment_id": "services", "segment_name": "Services", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 150, "share_of_revenue": 0.1667, "operating_income": 40, "assets": None},
            {"segment_id": "us", "segment_name": "United States", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 520, "share_of_revenue": 0.5778, "operating_income": None, "assets": None},
            {"segment_id": "emea", "segment_name": "EMEA", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 190, "share_of_revenue": 0.2111, "operating_income": None, "assets": None},
            {"segment_id": "apac", "segment_name": "APAC", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 190, "share_of_revenue": 0.2111, "operating_income": None, "assets": None},
        ],
    )

    payload = build_segment_analysis([latest, previous])

    assert payload is not None
    business = payload["business"]
    geographic = payload["geographic"]
    assert business["as_of"].isoformat() == "2025-12-31"
    assert business["top_mix_movers"][0]["segment_name"] == "Devices"
    assert business["top_margin_contributors"][0]["segment_name"] == "Cloud"
    assert business["concentration"]["top_two_share"] == 0.82
    assert geographic["concentration"]["top_segment_name"] == "United States"
    assert any(item["code"] == "geographic_revenue_only" for item in geographic["unusual_disclosures"])
    assert "Mix shifted most in Devices" in business["summary"]
