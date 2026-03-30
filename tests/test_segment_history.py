from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.services.segment_history import build_segment_history


def _statement(
    statement_id: int,
    *,
    filing_type: str,
    period_end: date,
    accepted_at: datetime,
    revenue: float,
    segment_breakdown: list[dict],
):
    return SimpleNamespace(
        id=statement_id,
        filing_type=filing_type,
        statement_type="canonical_xbrl",
        period_start=date(period_end.year, 1, 1),
        period_end=period_end,
        source="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        last_updated=accepted_at,
        last_checked=accepted_at,
        filing_acceptance_at=accepted_at,
        fetch_timestamp=accepted_at,
        data={
            "revenue": revenue,
            "segment_breakdown": segment_breakdown,
        },
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
        regulated_entity=None,
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime(2026, 3, 27, 18, 0, tzinfo=timezone.utc))


def test_build_segment_history_returns_multi_year_periods_with_comparability_flags() -> None:
    latest = _statement(
        3,
        filing_type="10-K",
        period_end=date(2025, 12, 31),
        accepted_at=datetime(2026, 2, 20, 20, 0, tzinfo=timezone.utc),
        revenue=1_000.0,
        segment_breakdown=[
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_label": "Business Segments", "kind": "business", "revenue": 550.0, "operating_income": 180.0},
            {"segment_id": "services", "segment_name": "Services", "axis_label": "Business Segments", "kind": "business", "revenue": 250.0, "operating_income": None},
            {"segment_id": "platform", "segment_name": "Platform", "axis_label": "Business Segments", "kind": "business", "revenue": 200.0, "operating_income": 30.0},
        ],
    )
    previous = _statement(
        2,
        filing_type="10-K",
        period_end=date(2024, 12, 31),
        accepted_at=datetime(2025, 2, 18, 20, 0, tzinfo=timezone.utc),
        revenue=920.0,
        segment_breakdown=[
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_label": "Operating Segments", "kind": "business", "revenue": 470.0, "operating_income": 140.0},
            {"segment_id": "devices", "segment_name": "Devices", "axis_label": "Operating Segments", "kind": "business", "revenue": 230.0, "operating_income": 35.0},
            {"segment_id": "services", "segment_name": "Services", "axis_label": "Operating Segments", "kind": "business", "revenue": 220.0, "operating_income": 42.0},
        ],
    )
    older = _statement(
        1,
        filing_type="10-K",
        period_end=date(2023, 12, 31),
        accepted_at=datetime(2024, 2, 17, 20, 0, tzinfo=timezone.utc),
        revenue=860.0,
        segment_breakdown=[
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_label": "Operating Segments", "kind": "business", "revenue": 430.0, "operating_income": 125.0},
            {"segment_id": "devices", "segment_name": "Devices", "axis_label": "Operating Segments", "kind": "business", "revenue": 240.0, "operating_income": 36.0},
            {"segment_id": "services", "segment_name": "Services", "axis_label": "Operating Segments", "kind": "business", "revenue": 190.0, "operating_income": 38.0},
        ],
    )

    result = build_segment_history([latest, previous, older], kind="business", years=3)

    assert [period.fiscal_year for period in result.periods] == [2025, 2024, 2023]
    assert result.periods[0].segments[0]["name"] == "Cloud"
    assert result.periods[0].segments[0]["share_of_revenue"] == 0.55
    assert result.periods[0].segments[0]["operating_margin"] == 0.3273
    assert result.periods[0].comparability_flags == {
        "no_prior_comparable_disclosure": False,
        "segment_axis_changed": True,
        "partial_operating_income_disclosure": True,
        "new_or_removed_segments": True,
    }
    assert result.periods[2].comparability_flags["no_prior_comparable_disclosure"] is True


def test_build_segment_history_prefers_annual_periods_and_limits_years() -> None:
    quarterly = _statement(
        4,
        filing_type="10-Q",
        period_end=date(2026, 3, 31),
        accepted_at=datetime(2026, 5, 5, 20, 0, tzinfo=timezone.utc),
        revenue=260.0,
        segment_breakdown=[
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_label": "Business Segments", "kind": "business", "revenue": 170.0, "operating_income": 48.0},
            {"segment_id": "services", "segment_name": "Services", "axis_label": "Business Segments", "kind": "business", "revenue": 90.0, "operating_income": 15.0},
        ],
    )
    annual_2025 = _statement(
        3,
        filing_type="10-K",
        period_end=date(2025, 12, 31),
        accepted_at=datetime(2026, 2, 20, 20, 0, tzinfo=timezone.utc),
        revenue=1_000.0,
        segment_breakdown=[
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_label": "Business Segments", "kind": "business", "revenue": 600.0, "operating_income": 180.0},
            {"segment_id": "services", "segment_name": "Services", "axis_label": "Business Segments", "kind": "business", "revenue": 400.0, "operating_income": 70.0},
        ],
    )
    annual_2024 = _statement(
        2,
        filing_type="10-K",
        period_end=date(2024, 12, 31),
        accepted_at=datetime(2025, 2, 20, 20, 0, tzinfo=timezone.utc),
        revenue=900.0,
        segment_breakdown=[
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_label": "Business Segments", "kind": "business", "revenue": 530.0, "operating_income": 150.0},
            {"segment_id": "services", "segment_name": "Services", "axis_label": "Business Segments", "kind": "business", "revenue": 370.0, "operating_income": 60.0},
        ],
    )
    annual_2023 = _statement(
        1,
        filing_type="10-K",
        period_end=date(2023, 12, 31),
        accepted_at=datetime(2024, 2, 20, 20, 0, tzinfo=timezone.utc),
        revenue=820.0,
        segment_breakdown=[
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_label": "Business Segments", "kind": "business", "revenue": 470.0, "operating_income": 120.0},
            {"segment_id": "services", "segment_name": "Services", "axis_label": "Business Segments", "kind": "business", "revenue": 350.0, "operating_income": 55.0},
        ],
    )

    result = build_segment_history([quarterly, annual_2025, annual_2024, annual_2023], kind="business", years=2)

    assert [period.fiscal_year for period in result.periods] == [2025, 2024]
    assert all(period.kind == "business" for period in result.periods)


def test_segment_history_route_returns_periods_and_provenance(monkeypatch) -> None:
    latest = _statement(
        2,
        filing_type="10-K",
        period_end=date(2025, 12, 31),
        accepted_at=datetime(2026, 2, 20, 20, 0, tzinfo=timezone.utc),
        revenue=1_000.0,
        segment_breakdown=[
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_label": "Business Segments", "kind": "business", "revenue": 580.0, "operating_income": 175.0},
            {"segment_id": "services", "segment_name": "Services", "axis_label": "Business Segments", "kind": "business", "revenue": 420.0, "operating_income": None},
        ],
    )
    previous = _statement(
        1,
        filing_type="10-K",
        period_end=date(2024, 12, 31),
        accepted_at=datetime(2025, 2, 20, 20, 0, tzinfo=timezone.utc),
        revenue=910.0,
        segment_breakdown=[
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_label": "Operating Segments", "kind": "business", "revenue": 540.0, "operating_income": 150.0},
            {"segment_id": "services", "segment_name": "Services", "axis_label": "Operating Segments", "kind": "business", "revenue": 370.0, "operating_income": 62.0},
        ],
    )

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "_visible_financials_for_company", lambda *_args, **_kwargs: [latest, previous])
    monkeypatch.setattr(main_module, "_regulated_entity_payload", lambda *_args, **_kwargs: None)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/segment-history?years=2&kind=business")

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "business"
    assert payload["years"] == 2
    assert len(payload["periods"]) == 2
    assert payload["periods"][0]["segments"][0]["name"] == "Cloud"
    assert payload["periods"][0]["comparability_flags"] == {
        "no_prior_comparable_disclosure": False,
        "segment_axis_changed": True,
        "partial_operating_income_disclosure": True,
        "new_or_removed_segments": False,
    }
    assert {entry["source_id"] for entry in payload["provenance"]} == {"ft_snapshot_history", "sec_companyfacts"}
    assert payload["source_mix"]["official_only"] is True


def test_segment_history_openapi_contract_includes_params_and_response_fields() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()

    path_schema = schema["paths"]["/api/companies/{ticker}/segment-history"]["get"]
    parameter_names = {item["name"] for item in path_schema.get("parameters", [])}
    assert {"ticker", "years", "kind", "as_of"}.issubset(parameter_names)

    response_fields = _response_fields(schema, "/api/companies/{ticker}/segment-history")
    assert {
        "company",
        "kind",
        "years",
        "periods",
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