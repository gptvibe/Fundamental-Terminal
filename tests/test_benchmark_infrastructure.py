from __future__ import annotations

from scripts.benchmark_hot_endpoints import build_cases
from scripts.benchmark_model_computation import benchmark_models, build_benchmark_dataset


def test_hot_endpoint_benchmark_cases_cover_core_cached_routes() -> None:
    case_names = {case.name for case in build_cases("aapl")}
    assert {
        "company_search",
        "financials_payload",
        "models_payload",
        "peers_payload",
        "metrics_timeseries_payload",
    }.issubset(case_names)


def test_model_benchmark_returns_latency_summary_and_status() -> None:
    dataset = build_benchmark_dataset()
    payload = benchmark_models(["dcf", "roic"], rounds=2)

    assert dataset.ticker == "ACME"
    assert payload["ticker"] == "ACME"
    assert payload["rounds"] == 2
    assert len(payload["results"]) == 2
    for result in payload["results"]:
        assert result["latency_ms"]["min"] >= 0
        assert result["latency_ms"]["p50"] >= 0
        assert result["model_status"] in {"supported", "partial", "proxy", "insufficient_data", "unsupported"}