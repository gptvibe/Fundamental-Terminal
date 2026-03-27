from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import RefreshState, app
from app.services.sec_edgar import EdgarNormalizer, FilingMetadata, _build_financial_restatement_payloads


FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = FIXTURES_DIR / "golden"


def test_amended_financial_restatement_golden_fixture() -> None:
    fixture = json.loads((GOLDEN_DIR / "financial_restatement_amendment.json").read_text(encoding="utf-8"))
    filing_index = {
        item["accession_number"]: FilingMetadata(
            accession_number=item["accession_number"],
            form=item["form"],
            filing_date=_parse_date(item["filing_date"]),
            report_date=_parse_date(item["report_date"]),
            acceptance_datetime=_parse_datetime(item["acceptance_datetime"]),
            primary_document=item["primary_document"],
        )
        for item in fixture["filings"]
    }

    statements = EdgarNormalizer().normalize(fixture["cik"], fixture["companyfacts"], filing_index)
    payloads = _build_financial_restatement_payloads(
        company_id=1,
        normalized_statements=statements,
        checked_at=datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc),
    )

    assert len(payloads) == 1
    payload = payloads[0]
    expected = fixture["expected"]
    assert payload["detection_kind"] == expected["detection_kind"]
    assert payload["accession_number"] == expected["accession_number"]
    assert payload["previous_accession_number"] == expected["previous_accession_number"]
    assert payload["changed_metric_keys"] == expected["changed_metric_keys"]

    revenue_change = next(item for item in payload["normalized_data_changes"] if item["metric_key"] == "revenue")
    assert revenue_change["previous_value"] == expected["revenue_previous"]
    assert revenue_change["current_value"] == expected["revenue_current"]
    assert revenue_change["delta"] == expected["revenue_delta"]

    revenue_fact_change = next(item for item in payload["companyfacts_changes"] if item["metric_key"] == "revenue")
    assert revenue_fact_change["previous_fact"]["form"] == "10-K"
    assert revenue_fact_change["current_fact"]["form"] == "10-K/A"
    assert payload["confidence_impact"]["severity"] == "high"


def test_financial_restatements_route_exposes_summary_and_provenance(monkeypatch) -> None:
    snapshot = SimpleNamespace(
        company=SimpleNamespace(
            id=1,
            ticker="AAPL",
            cik="0000320193",
            name="Apple Inc.",
            sector="Technology",
            market_sector="Technology",
            market_industry="Consumer Electronics",
        ),
        cache_state="fresh",
        last_checked=datetime(2026, 3, 27, 12, 30, tzinfo=timezone.utc),
    )
    restatement = SimpleNamespace(
        accession_number="0000123456-26-000011",
        previous_accession_number="0000123456-26-000010",
        filing_type="10-K",
        form="10-K/A",
        is_amendment=True,
        detection_kind="amended_filing",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        filing_date=date(2026, 3, 20),
        previous_filing_date=date(2026, 2, 20),
        filing_acceptance_at=datetime(2026, 3, 20, 21, 15, tzinfo=timezone.utc),
        previous_filing_acceptance_at=datetime(2026, 2, 20, 20, 30, tzinfo=timezone.utc),
        source="https://www.sec.gov/Archives/edgar/data/123456/000012345626000011/amended10k.htm",
        previous_source="https://www.sec.gov/Archives/edgar/data/123456/000012345626000010/original10k.htm",
        changed_metric_keys=["revenue", "net_income"],
        normalized_data_changes=[
            {
                "metric_key": "revenue",
                "previous_value": 1000,
                "current_value": 950,
                "delta": -50,
                "relative_change": -0.05,
                "direction": "decrease",
            }
        ],
        companyfacts_changes=[
            {
                "metric_key": "revenue",
                "previous_fact": {
                    "accession_number": "0000123456-26-000010",
                    "form": "10-K",
                    "taxonomy": "us-gaap",
                    "tag": "Revenues",
                    "unit": "USD",
                    "filed_at": date(2026, 2, 20),
                    "period_start": date(2025, 1, 1),
                    "period_end": date(2025, 12, 31),
                    "value": 1000,
                },
                "current_fact": {
                    "accession_number": "0000123456-26-000011",
                    "form": "10-K/A",
                    "taxonomy": "us-gaap",
                    "tag": "Revenues",
                    "unit": "USD",
                    "filed_at": date(2026, 3, 20),
                    "period_start": date(2025, 1, 1),
                    "period_end": date(2025, 12, 31),
                    "value": 950,
                },
                "value_changed": True,
            }
        ],
        confidence_impact={
            "severity": "high",
            "flags": ["restatement_detected", "amended_sec_filing", "core_metric_changed"],
            "largest_relative_change": 0.05,
            "changed_metric_count": 2,
        },
        last_updated=datetime(2026, 3, 27, 12, 30, tzinfo=timezone.utc),
        last_checked=datetime(2026, 3, 27, 12, 30, tzinfo=timezone.utc),
    )

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "_refresh_for_snapshot", lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None))
    monkeypatch.setattr(main_module, "get_company_financial_restatements", lambda *_args, **_kwargs: [restatement])

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/financial-restatements?as_of=2026-03-20")

    assert response.status_code == 200
    payload = response.json()
    assert payload["as_of"] == "2026-03-20"
    assert payload["summary"]["total_restatements"] == 1
    assert payload["summary"]["amended_metric_keys"] == ["net_income", "revenue"]
    assert payload["restatements"][0]["form"] == "10-K/A"
    assert {entry["source_id"] for entry in payload["provenance"]} == {"sec_companyfacts", "sec_edgar"}
    assert "amended_sec_filing" in payload["confidence_flags"]


def test_financial_restatements_openapi_contract_includes_as_of() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()

    path_schema = schema["paths"]["/api/companies/{ticker}/financial-restatements"]["get"]
    parameter_names = {item["name"] for item in path_schema.get("parameters", [])}
    assert {"ticker", "as_of"}.issubset(parameter_names)

    response_fields = _response_fields(schema, "/api/companies/{ticker}/financial-restatements")
    assert {"company", "summary", "restatements", "refresh", "provenance", "as_of", "last_refreshed_at", "source_mix", "confidence_flags"}.issubset(response_fields)


def _response_fields(schema: dict, path: str) -> set[str]:
    response_schema = schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    if "$ref" not in response_schema:
        return set(response_schema.get("properties", {}).keys())
    component_name = response_schema["$ref"].split("/")[-1]
    return set(schema["components"]["schemas"][component_name]["properties"].keys())


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))