from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import RefreshState, app
from app.services.filing_changes import build_changes_since_last_filing


def _statement(
    statement_id: int,
    *,
    filing_type: str,
    period_start: date,
    period_end: date,
    acceptance_at: datetime,
    data: dict,
):
    return SimpleNamespace(
        id=statement_id,
        filing_type=filing_type,
        statement_type="canonical_xbrl",
        period_start=period_start,
        period_end=period_end,
        source=f"https://www.sec.gov/Archives/edgar/data/123456/{statement_id:010d}-26-000001/form.htm",
        last_updated=acceptance_at,
        last_checked=acceptance_at,
        filing_acceptance_at=acceptance_at,
        fetch_timestamp=acceptance_at,
        data=data,
    )


def _snapshot():
    company = SimpleNamespace(
        id=1,
        ticker="AAPL",
        cik="0000320193",
        name="Apple Inc.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Consumer Electronics",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime(2026, 3, 27, 18, 0, tzinfo=timezone.utc))


def _restatement(period_start: date, period_end: date, *, filing_type: str = "10-Q"):
    return SimpleNamespace(
        id=1,
        accession_number="0000123456-26-000099",
        previous_accession_number="0000123456-26-000088",
        filing_type=filing_type,
        form="10-Q/A",
        is_amendment=True,
        detection_kind="amended_filing",
        period_start=period_start,
        period_end=period_end,
        filing_date=date(2026, 3, 20),
        previous_filing_date=date(2025, 8, 10),
        filing_acceptance_at=datetime(2026, 3, 20, 20, 0, tzinfo=timezone.utc),
        previous_filing_acceptance_at=datetime(2025, 8, 10, 20, 0, tzinfo=timezone.utc),
        source="https://www.sec.gov/Archives/edgar/data/123456/000012345626000099/amended10q.htm",
        previous_source="https://www.sec.gov/Archives/edgar/data/123456/000012345626000088/original10q.htm",
        changed_metric_keys=["revenue"],
        normalized_data_changes=[
            {
                "metric_key": "revenue",
                "previous_value": 100.0,
                "current_value": 102.0,
                "delta": 2.0,
                "relative_change": 0.02,
                "direction": "increase",
            }
        ],
        companyfacts_changes=[],
        confidence_impact={"severity": "medium", "flags": ["amended_sec_filing"], "largest_relative_change": 0.02, "changed_metric_count": 1},
        last_updated=datetime(2026, 3, 27, 18, 0, tzinfo=timezone.utc),
        last_checked=datetime(2026, 3, 27, 18, 0, tzinfo=timezone.utc),
    )


def test_build_changes_since_last_filing_summarizes_deltas_and_amendments() -> None:
    current = _statement(
        3,
        filing_type="10-Q",
        period_start=date(2025, 7, 1),
        period_end=date(2025, 9, 30),
        acceptance_at=datetime(2025, 11, 2, 20, 0, tzinfo=timezone.utc),
        data={
            "revenue": 120.0,
            "gross_profit": 55.0,
            "operating_income": 14.0,
            "net_income": 11.0,
            "operating_cash_flow": 18.0,
            "free_cash_flow": -4.0,
            "eps": 1.1,
            "current_assets": 48.0,
            "current_liabilities": 52.0,
            "current_debt": 18.0,
            "long_term_debt": 88.0,
            "stockholders_equity": 60.0,
            "shares_outstanding": 108.0,
            "weighted_average_diluted_shares": 110.0,
            "cash_and_short_term_investments": 20.0,
            "lease_liabilities": 9.0,
            "segment_breakdown": [
                {"segment_id": "products", "segment_name": "Products", "kind": "business", "revenue": 84.0, "share_of_revenue": 0.7},
                {"segment_id": "services", "segment_name": "Services", "kind": "business", "revenue": 36.0, "share_of_revenue": 0.3},
            ],
        },
    )
    previous = _statement(
        2,
        filing_type="10-Q",
        period_start=date(2025, 4, 1),
        period_end=date(2025, 6, 30),
        acceptance_at=datetime(2025, 8, 10, 20, 0, tzinfo=timezone.utc),
        data={
            "revenue": 102.0,
            "gross_profit": 48.0,
            "operating_income": 18.0,
            "net_income": 12.0,
            "operating_cash_flow": 16.0,
            "free_cash_flow": 6.0,
            "eps": 1.2,
            "current_assets": 60.0,
            "current_liabilities": 50.0,
            "current_debt": 12.0,
            "long_term_debt": 70.0,
            "stockholders_equity": 70.0,
            "shares_outstanding": 100.0,
            "weighted_average_diluted_shares": 102.0,
            "cash_and_short_term_investments": 26.0,
            "lease_liabilities": 7.0,
            "segment_breakdown": [
                {"segment_id": "products", "segment_name": "Products", "kind": "business", "revenue": 61.2, "share_of_revenue": 0.6},
                {"segment_id": "services", "segment_name": "Services", "kind": "business", "revenue": 40.8, "share_of_revenue": 0.4},
            ],
        },
    )
    older = _statement(
        1,
        filing_type="10-Q",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 3, 31),
        acceptance_at=datetime(2025, 5, 10, 20, 0, tzinfo=timezone.utc),
        data={
            "revenue": 98.0,
            "operating_income": 19.0,
            "current_assets": 62.0,
            "current_liabilities": 49.0,
            "current_debt": 10.0,
            "long_term_debt": 69.0,
            "stockholders_equity": 71.0,
            "shares_outstanding": 99.0,
            "weighted_average_diluted_shares": 100.0,
            "free_cash_flow": 7.0,
            "segment_breakdown": [
                {"segment_id": "products", "segment_name": "Products", "kind": "business", "revenue": 58.8, "share_of_revenue": 0.6},
                {"segment_id": "services", "segment_name": "Services", "kind": "business", "revenue": 39.2, "share_of_revenue": 0.4},
            ],
        },
    )

    comparison = build_changes_since_last_filing([current, previous, older], [_restatement(previous.period_start, previous.period_end)])

    assert comparison["summary"]["filing_type"] == "10-Q"
    assert comparison["summary"]["metric_delta_count"] >= 4
    assert any(item["metric_key"] == "revenue" for item in comparison["metric_deltas"])
    assert any(item["indicator_key"] == "negative_free_cash_flow" for item in comparison["new_risk_indicators"])
    assert any(item["segment_id"] == "products" for item in comparison["segment_shifts"])
    assert any(item["metric_key"] == "shares_outstanding" for item in comparison["share_count_changes"])
    assert any(item["metric_key"] == "long_term_debt" for item in comparison["capital_structure_changes"])
    assert comparison["amended_prior_values"][0]["metric_key"] == "revenue"
    assert "prior_values_amended" in comparison["confidence_flags"]


def test_changes_since_last_filing_route_exposes_provenance_and_as_of(monkeypatch) -> None:
    current = _statement(
        2,
        filing_type="10-K",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        acceptance_at=datetime(2026, 2, 20, 20, 0, tzinfo=timezone.utc),
        data={"revenue": 120.0, "free_cash_flow": 10.0, "shares_outstanding": 101.0, "segment_breakdown": []},
    )
    previous = _statement(
        1,
        filing_type="10-K",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        acceptance_at=datetime(2025, 2, 20, 20, 0, tzinfo=timezone.utc),
        data={"revenue": 100.0, "free_cash_flow": 8.0, "shares_outstanding": 100.0, "segment_breakdown": []},
    )
    restatement = _restatement(previous.period_start, previous.period_end, filing_type="10-K")

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "_refresh_for_snapshot", lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None))
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [current, previous])
    monkeypatch.setattr(main_module, "get_company_financial_restatements", lambda *_args, **_kwargs: [restatement])

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/changes-since-last-filing?as_of=2026-03-20")

    assert response.status_code == 200
    payload = response.json()
    assert payload["as_of"] == "2026-03-20"
    assert payload["summary"]["filing_type"] == "10-K"
    assert payload["current_filing"]["filing_type"] == "10-K"
    assert {entry["source_id"] for entry in payload["provenance"]} == {
        "ft_changes_since_last_filing",
        "sec_companyfacts",
        "sec_edgar",
    }
    assert "prior_values_amended" in payload["confidence_flags"]


def test_changes_since_last_filing_openapi_contract_includes_as_of() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()

    path_schema = schema["paths"]["/api/companies/{ticker}/changes-since-last-filing"]["get"]
    parameter_names = {item["name"] for item in path_schema.get("parameters", [])}
    assert {"ticker", "as_of"}.issubset(parameter_names)

    response_fields = _response_fields(schema, "/api/companies/{ticker}/changes-since-last-filing")
    assert {
        "company",
        "current_filing",
        "previous_filing",
        "summary",
        "metric_deltas",
        "new_risk_indicators",
        "segment_shifts",
        "share_count_changes",
        "capital_structure_changes",
        "amended_prior_values",
        "refresh",
        "diagnostics",
        "provenance",
        "as_of",
        "last_refreshed_at",
        "source_mix",
        "confidence_flags",
    }.issubset(response_fields)


def _response_fields(schema: dict, path: str) -> set[str]:
    response_schema = schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    if "$ref" not in response_schema:
        return set(response_schema.get("properties", {}).keys())
    component_name = response_schema["$ref"].split("/")[-1]
    return set(schema["components"]["schemas"][component_name]["properties"].keys())