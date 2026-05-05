from __future__ import annotations

from scripts.benchmark_refresh_bootstrap_parallelism import benchmark_refresh_bootstrap_parallelism
from scripts.benchmark_derived_metrics_price_matching import benchmark_price_matching
from scripts.benchmark_incremental_price_refresh import benchmark_incremental_price_refresh
from scripts.benchmark_hot_endpoints import build_cases
from scripts.benchmark_market_profile_cache import benchmark_market_profile_cache
from scripts.benchmark_model_computation import benchmark_models, build_benchmark_dataset
from scripts.benchmark_refresh_service_reuse import benchmark_refresh_service_reuse
from scripts.run_performance_regression_gate import build_baseline_payload, evaluate_summary_against_baseline, run_performance_benchmarks


def test_hot_endpoint_benchmark_cases_cover_core_cached_routes() -> None:
    case_names = {case.name for case in build_cases("aapl")}
    assert {
        "company_search",
        "financials_payload",
        "models_payload",
        "peers_payload",
        "metrics_timeseries_payload",
        "beneficial_ownership_summary",
        "governance_summary",
        "filing_events_summary",
        "capital_markets_summary",
        "earnings_summary",
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


def test_incremental_price_refresh_benchmark_reports_noop_and_write_paths() -> None:
    payload = benchmark_incremental_price_refresh(rounds=2, bar_count=4)

    assert payload["rounds"] == 2
    assert payload["bar_count"] == 4
    assert {result["name"] for result in payload["results"]} == {
        "always_write_unchanged_tail",
        "no_op_unchanged_tail",
        "changed_tail_write",
    }
    for result in payload["results"]:
        assert result["latency_ms"]["avg"] >= 0
        assert result["execute_count"]["min"] >= 1


def test_market_profile_cache_benchmark_reports_request_reduction() -> None:
    payload = benchmark_market_profile_cache(rounds=5, ttl_seconds=3600)

    assert payload["rounds"] == 5
    assert payload["ttl_seconds"] == 3600
    assert {result["name"] for result in payload["results"]} == {"uncached", "cached"}
    result_by_name = {result["name"]: result for result in payload["results"]}
    assert result_by_name["uncached"]["request_count"] == 5
    assert result_by_name["cached"]["request_count"] == 1
    assert result_by_name["cached"]["request_reduction_percent"] > 0


def test_refresh_service_reuse_benchmark_reports_construction_reduction() -> None:
    payload = benchmark_refresh_service_reuse(rounds=5)

    assert payload["rounds"] == 5
    assert {result["name"] for result in payload["results"]} == {
        "fresh_service_per_job",
        "reused_service_for_burst",
    }
    result_by_name = {result["name"]: result for result in payload["results"]}
    assert result_by_name["fresh_service_per_job"]["service_constructions"] == 5
    assert result_by_name["reused_service_for_burst"]["service_constructions"] == 1
    assert result_by_name["reused_service_for_burst"]["latency_ms_per_job_equivalent"] >= 0


def test_refresh_bootstrap_parallelism_benchmark_reports_serial_and_parallel_paths() -> None:
    payload = benchmark_refresh_bootstrap_parallelism(rounds=2)

    assert payload["rounds"] == 2
    assert {result["name"] for result in payload["results"]} == {
        "serial_market_profile_lookup",
        "parallel_market_profile_prefetch",
    }
    for result in payload["results"]:
        assert result["latency_ms"]["avg"] >= 0


def test_derived_metrics_price_matching_benchmark_reports_equivalence_and_lower_index_operations() -> None:
    payload = benchmark_price_matching(financial_rows=40, price_rows=2000, rounds=2)

    assert payload["equivalent_output"] is True
    assert payload["optimized"]["price_index_build_operations"] < payload["baseline_legacy"]["price_index_build_operations"]
    assert payload["comparison"]["index_operation_reduction_pct"] > 0


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


def test_performance_regression_benchmarks_include_company_brief_suite() -> None:
    summary = run_performance_benchmarks(
        hot_rounds=1,
        brief_concurrency=2,
        brief_requests_per_worker=2,
    )

    suites = {suite["suite"]: suite for suite in summary["suites"]}
    assert "company_brief_concurrency" in suites
    hot_case_names = {result["name"] for result in suites["hot_endpoints"]["results"]}
    assert "beneficial_ownership_summary" in hot_case_names
    assert suites["company_brief_concurrency"]["results"][0]["name"] == "company_brief_ready"
    assert suites["company_brief_concurrency"]["results"][0]["request_count"] == 4
