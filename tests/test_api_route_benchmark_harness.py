from __future__ import annotations

from scripts.benchmark_api_routes import (
    BenchmarkCase,
    _build_url,
    _infer_cache_states,
    _percentile,
    _summarize_case,
    build_focus_cases,
)


def test_build_focus_cases_covers_requested_routes() -> None:
    cases = build_focus_cases("aapl", "aapl,msft")
    case_names = {case.name for case in cases}

    assert {
        "company_overview",
        "company_financials",
        "company_charts",
        "derived_metrics",
        "company_models",
        "company_compare",
        "screener_search",
        "source_registry",
        "source_registry_status",
    }.issubset(case_names)


def test_build_url_adds_nonce_for_cold_mode() -> None:
    case = BenchmarkCase(name="financials", method="GET", path="/api/companies/AAPL/financials", params={"view": "full"})

    warm_url = _build_url("http://127.0.0.1:8000", case, cache_mode="warm", nonce="abc")
    cold_url = _build_url("http://127.0.0.1:8000", case, cache_mode="cold", nonce="abc")

    assert "__bench_nonce" not in warm_url
    assert "__bench_nonce=abc" in cold_url


def test_infer_cache_states_reads_common_header_values() -> None:
    states = _infer_cache_states(
        {
            "x-cache": "HIT",
            "cache-status": "origin; fwd=stale",
            "x-ft-cache-status": "fresh",
        }
    )

    assert states == {"hit", "stale", "fresh"}


def test_percentile_uses_sorted_values() -> None:
    values = [7.0, 1.0, 5.0, 2.0, 9.0]

    assert _percentile(values, 0.5) == 5.0
    assert _percentile(values, 0.95) == 9.0
    assert _percentile(values, 0.99) == 9.0


def test_summarize_case_includes_p99_and_status_counts() -> None:
    case = BenchmarkCase(name="overview", method="GET", path="/api/companies/AAPL/overview", params={})
    summary = _summarize_case(
        case=case,
        cache_mode="warm",
        rounds=3,
        responses=[
            {
                "duration_ms": 10.0,
                "status_code": 200,
                "payload_bytes": 100,
                "cache_headers": {"x-cache": "HIT"},
                "cache_states": ["hit"],
            },
            {
                "duration_ms": 20.0,
                "status_code": 200,
                "payload_bytes": 120,
                "cache_headers": {"x-cache": "MISS"},
                "cache_states": [],
            },
            {
                "duration_ms": 30.0,
                "status_code": 304,
                "payload_bytes": 0,
                "cache_headers": {"x-cache": "HIT"},
                "cache_states": ["hit"],
            },
        ],
    )

    assert summary["latency_ms"]["p99"] == 30.0
    assert summary["status_code_counts"] == {"200": 2, "304": 1}
    assert summary["cache_headers"]["state_counts"]["hit"] == 2
