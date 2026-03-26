from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app



def test_metrics_timeseries_openapi_contract_matches_frontend_shape():
    client = TestClient(app)
    schema = client.get("/openapi.json").json()

    path_schema = schema["paths"]["/api/companies/{ticker}/metrics-timeseries"]["get"]
    parameter_names = {item["name"] for item in path_schema.get("parameters", [])}
    assert {"ticker", "cadence", "max_points"}.issubset(parameter_names)

    response_ref = path_schema["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    response_name = response_ref.rsplit("/", 1)[-1]
    response_schema = schema["components"]["schemas"][response_name]
    response_fields = set(response_schema.get("properties", {}).keys())

    expected_response_fields = {
        "company",
        "series",
        "last_financials_check",
        "last_price_check",
        "staleness_reason",
        "refresh",
        "diagnostics",
    }
    assert expected_response_fields.issubset(response_fields)

    point_schema = schema["components"]["schemas"]["MetricsTimeseriesPointPayload"]
    point_fields = set(point_schema.get("properties", {}).keys())
    assert {"cadence", "period_start", "period_end", "filing_type", "metrics", "provenance", "quality"}.issubset(point_fields)

    frontend_types = Path("frontend/lib/types.ts").read_text(encoding="utf-8")
    for field in expected_response_fields:
        assert field in frontend_types
    assert "interface CompanyMetricsTimeseriesResponse" in frontend_types


def test_metrics_mart_openapi_contract_matches_frontend_shape():
    client = TestClient(app)
    schema = client.get("/openapi.json").json()

    metrics_schema = schema["paths"]["/api/companies/{ticker}/metrics"]["get"]
    summary_schema = schema["paths"]["/api/companies/{ticker}/metrics/summary"]["get"]

    metrics_parameter_names = {item["name"] for item in metrics_schema.get("parameters", [])}
    assert {"ticker", "period_type", "max_periods"}.issubset(metrics_parameter_names)

    summary_parameter_names = {item["name"] for item in summary_schema.get("parameters", [])}
    assert {"ticker", "period_type"}.issubset(summary_parameter_names)

    frontend_types = Path("frontend/lib/types.ts").read_text(encoding="utf-8")
    assert "interface CompanyDerivedMetricsResponse" in frontend_types
    assert "interface CompanyDerivedMetricsSummaryResponse" in frontend_types
