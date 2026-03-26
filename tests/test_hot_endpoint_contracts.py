from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_hot_endpoint_openapi_contracts_include_diagnostics_fields() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()

    endpoint_expectations = {
        "/api/companies/{ticker}/financials": {"company", "financials", "price_history", "refresh", "diagnostics"},
        "/api/companies/{ticker}/models": {"company", "requested_models", "models", "refresh", "diagnostics"},
        "/api/companies/{ticker}/earnings/workspace": {
            "company",
            "earnings_releases",
            "summary",
            "model_points",
            "backtests",
            "peer_context",
            "alerts",
            "refresh",
            "diagnostics",
        },
        "/api/companies/{ticker}/filing-insights": {"company", "insights", "refresh", "diagnostics"},
    }

    for path, expected_fields in endpoint_expectations.items():
        response_ref = schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        response_name = response_ref.rsplit("/", 1)[-1]
        response_schema = schema["components"]["schemas"][response_name]
        response_fields = set(response_schema.get("properties", {}).keys())
        assert expected_fields.issubset(response_fields), path


def test_frontend_types_include_matching_hot_endpoint_diagnostics_and_job_metadata() -> None:
    frontend_types = Path("frontend/lib/types.ts").read_text(encoding="utf-8")

    for interface_name in (
        "CompanyFinancialsResponse",
        "CompanyModelsResponse",
        "CompanyEarningsWorkspaceResponse",
        "CompanyFilingInsightsResponse",
    ):
        assert f"interface {interface_name}" in frontend_types

    assert "diagnostics: DataQualityDiagnosticsPayload;" in frontend_types
    assert "trace_id: string;" in frontend_types
    assert "ticker: string;" in frontend_types
    assert "kind: string;" in frontend_types