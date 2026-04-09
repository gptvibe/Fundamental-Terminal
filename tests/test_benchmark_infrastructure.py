from __future__ import annotations

from scripts.benchmark_hot_endpoints import build_cases
from scripts.benchmark_model_computation import benchmark_models, build_benchmark_dataset
from scripts.run_performance_regression_gate import build_baseline_payload, evaluate_summary_against_baseline


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


def test_performance_regression_baseline_builder_tracks_hot_routes_and_brief_budget() -> None:
    summary = {
        "suites": [
            {
                "suite": "hot_endpoints",
                "config": {"rounds": 12},
                "results": [
                    {
                        "name": "company_search",
                        "request_count": 12,
                        "status_codes": [200],
                        "latency_ms": {"p50": 4.0, "p95": 7.5},
                        "payload_bytes": {"avg": 640.0},
                    }
                ],
            },
            {
                "suite": "company_brief_concurrency",
                "config": {"concurrency": 6, "requests_per_worker": 4, "total_requests": 24},
                "results": [
                    {
                        "name": "company_brief_ready",
                        "request_count": 24,
                        "status_codes": [200],
                        "latency_ms": {"p50": 11.0, "p95": 18.0},
                        "payload_bytes": {"avg": 3200.0},
                    }
                ],
            },
        ]
    }

    baseline = build_baseline_payload(summary)

    assert baseline["suites"]["hot_endpoints"]["cases"]["company_search"]["request_count"] == {"expected": 12}
    assert baseline["suites"]["company_brief_concurrency"]["cases"]["company_brief_ready"]["request_count"] == {"expected": 24}
    assert baseline["suites"]["company_brief_concurrency"]["cases"]["company_brief_ready"]["latency_ms"]["p95"]["budget"] >= 18.0


def test_performance_regression_evaluator_flags_significant_latency_regression() -> None:
    summary = {
        "suites": [
            {
                "suite": "company_brief_concurrency",
                "config": {"concurrency": 6, "requests_per_worker": 4, "total_requests": 24},
                "results": [
                    {
                        "name": "company_brief_ready",
                        "request_count": 24,
                        "status_codes": [200],
                        "latency_ms": {"p50": 10.0, "p95": 16.0},
                        "payload_bytes": {"avg": 3200.0},
                    }
                ],
            }
        ]
    }
    baseline = build_baseline_payload(summary)
    summary["suites"][0]["results"][0]["latency_ms"]["p95"] = 40.0

    evaluation = evaluate_summary_against_baseline(summary, baseline)

    assert evaluation["status"] == "regression"
    assert any(item["metric"] == "latency_ms.p95" for item in evaluation["failures"])