from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_hot_endpoint_openapi_contracts_include_diagnostics_fields() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()

    provenance_fields = {"provenance", "as_of", "last_refreshed_at", "source_mix", "confidence_flags"}
    endpoint_expectations = {
        "/api/companies/{ticker}/financials": {"company", "financials", "price_history", "refresh", "diagnostics", *provenance_fields},
        "/api/companies/{ticker}/capital-structure": {
            "company",
            "latest",
            "history",
            "last_capital_structure_check",
            "refresh",
            "diagnostics",
            *provenance_fields,
        },
        "/api/companies/{ticker}/oil-scenario-overlay": {
            "company",
            "status",
            "fetched_at",
            "strict_official_mode",
            "exposure_profile",
            "benchmark_series",
            "scenarios",
            "sensitivity",
            "refresh",
            "diagnostics",
            *provenance_fields,
        },
        "/api/companies/{ticker}/changes-since-last-filing": {
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
            *provenance_fields,
        },
        "/api/companies/{ticker}/models": {"company", "requested_models", "models", "refresh", "diagnostics", *provenance_fields},
        "/api/companies/{ticker}/market-context": {
            "company",
            "status",
            "curve_points",
            "fred_series",
            "provenance_details",
            "cyclical_demand",
            "cyclical_costs",
            "relevant_indicators",
            "refresh",
            *provenance_fields,
        },
        "/api/companies/{ticker}/sector-context": {
            "company",
            "status",
            "matched_plugin_ids",
            "plugins",
            "fetched_at",
            "refresh",
            *provenance_fields,
        },
        "/api/companies/{ticker}/peers": {
            "company",
            "peer_basis",
            "available_companies",
            "selected_tickers",
            "peers",
            "notes",
            "refresh",
            *provenance_fields,
        },
        "/api/companies/{ticker}/activity-overview": {
            "company",
            "entries",
            "alerts",
            "summary",
            "market_context_status",
            "refresh",
            "error",
            *provenance_fields,
        },
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

    financial_payload_fields = set(schema["components"]["schemas"]["FinancialPayload"].get("properties", {}).keys())
    assert "reconciliation" in financial_payload_fields
    company_financial_fields = set(schema["components"]["schemas"]["CompanyFinancialsResponse"].get("properties", {}).keys())
    assert "segment_analysis" in company_financial_fields


def test_hot_endpoint_openapi_contracts_include_point_in_time_query_params() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()

    for path in (
        "/api/companies/{ticker}/financials",
        "/api/companies/{ticker}/capital-structure",
        "/api/companies/{ticker}/changes-since-last-filing",
        "/api/companies/{ticker}/models",
        "/api/companies/{ticker}/peers",
    ):
        parameter_names = {item["name"] for item in schema["paths"][path]["get"].get("parameters", [])}
        assert "as_of" in parameter_names, path


def test_frontend_types_include_matching_hot_endpoint_diagnostics_and_job_metadata() -> None:
    frontend_types = Path("frontend/lib/types.ts").read_text(encoding="utf-8")

    for interface_name in (
        "ProvenanceEnvelope",
        "CompanyFinancialsResponse",
        "CompanyCapitalStructureResponse",
        "CompanyOilScenarioOverlayResponse",
        "CompanyChangesSinceLastFilingResponse",
        "CompanyModelsResponse",
        "CompanyMarketContextResponse",
        "CompanySectorContextResponse",
        "CompanyPeersResponse",
        "CompanyActivityOverviewResponse",
        "CompanyEarningsWorkspaceResponse",
        "CompanyFilingInsightsResponse",
    ):
        assert f"interface {interface_name}" in frontend_types

    assert "provenance: ProvenanceEntryPayload[];" in frontend_types
    assert "source_mix: SourceMixPayload;" in frontend_types
    assert "confidence_flags: string[];" in frontend_types
    assert "strict_official_mode: boolean;" in frontend_types
    assert "provenance_details: Record<string, unknown>;" in frontend_types
    assert "cyclical_demand?: MacroSeriesItemPayload[];" in frontend_types
    assert "cyclical_costs?: MacroSeriesItemPayload[];" in frontend_types
    assert "relevant_indicators?: MacroSeriesItemPayload[];" in frontend_types
    assert "interface SectorPluginPayload" in frontend_types
    assert "interface CompanySectorContextResponse" in frontend_types
    assert "interface OilExposureProfilePayload" in frontend_types
    assert "interface OilCurveSeriesPayload" in frontend_types
    assert "interface OilScenarioCasePayload" in frontend_types
    assert "interface OilSensitivityPayload" in frontend_types
    assert "diagnostics: DataQualityDiagnosticsPayload;" in frontend_types
    assert "interface FinancialReconciliationPayload" in frontend_types
    assert "interface FinancialFactReferencePayload" in frontend_types
    assert "reconciliation: FinancialReconciliationPayload | null;" in frontend_types
    assert "interface SegmentAnalysisPayload" in frontend_types
    assert "interface SegmentLensPayload" in frontend_types
    assert "segment_analysis?: SegmentAnalysisPayload | null;" in frontend_types
    assert "reconciliation_penalty: number | null;" in frontend_types
    assert "reconciliation_disagreement_count: number;" in frontend_types
    assert "trace_id: string;" in frontend_types
    assert "ticker: string;" in frontend_types
    assert "kind: string;" in frontend_types
    assert "interface ModelEvaluationResponse" in frontend_types


def test_model_evaluation_endpoint_openapi_contract_includes_provenance_fields() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()

    provenance_fields = {"provenance", "as_of", "last_refreshed_at", "source_mix", "confidence_flags"}
    response_ref = schema["paths"]["/api/model-evaluations/latest"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    response_name = response_ref.rsplit("/", 1)[-1]
    response_schema = schema["components"]["schemas"][response_name]
    response_fields = set(response_schema.get("properties", {}).keys())

    assert {"run", *provenance_fields}.issubset(response_fields)
