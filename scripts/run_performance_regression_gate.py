from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
from urllib.parse import urlencode
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.main as main_module
from app.db import get_db_session
from app.main import app
from scripts.benchmark_hot_endpoints import build_cases


DEFAULT_TOLERANCES = {
    "latency_ms.p50": {"max_regression_pct": 60.0, "budget_multiplier": 1.8, "min_budget_delta": 3.0},
    "latency_ms.p95": {"max_regression_pct": 60.0, "budget_multiplier": 2.0, "min_budget_delta": 6.0},
    "payload_bytes.avg": {"max_regression_pct": 20.0, "budget_multiplier": 1.25, "min_budget_delta": 256.0},
}


def build_baseline_payload(summary: dict[str, Any]) -> dict[str, Any]:
    suites: dict[str, Any] = {}
    for suite in summary["suites"]:
        cases: dict[str, Any] = {}
        for result in suite["results"]:
            cases[result["name"]] = {
                "status_codes": [200],
                "request_count": {"expected": result["request_count"]},
                "latency_ms": {
                    "p50": _metric_budget(result["latency_ms"]["p50"], DEFAULT_TOLERANCES["latency_ms.p50"]),
                    "p95": _metric_budget(result["latency_ms"]["p95"], DEFAULT_TOLERANCES["latency_ms.p95"]),
                },
                "payload_bytes": {
                    "avg": _metric_budget(result["payload_bytes"]["avg"], DEFAULT_TOLERANCES["payload_bytes.avg"]),
                },
            }
        suites[suite["suite"]] = {
            "config": dict(suite["config"]),
            "cases": cases,
        }
    return {
        "schema_version": "performance_regression_baseline_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suites": suites,
    }


def evaluate_summary_against_baseline(summary: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    baseline_suites = baseline.get("suites") or {}

    for suite in summary.get("suites", []):
        baseline_suite = baseline_suites.get(suite["suite"])
        if baseline_suite is None:
            failures.append(
                {
                    "suite": suite["suite"],
                    "case": None,
                    "metric": "suite",
                    "message": f"Missing baseline suite '{suite['suite']}'",
                }
            )
            continue

        baseline_cases = baseline_suite.get("cases") or {}
        for result in suite.get("results", []):
            case_budget = baseline_cases.get(result["name"])
            if case_budget is None:
                failures.append(
                    {
                        "suite": suite["suite"],
                        "case": result["name"],
                        "metric": "case",
                        "message": f"Missing baseline case '{result['name']}'",
                    }
                )
                continue
            failures.extend(_evaluate_case(suite["suite"], result, case_budget))

    return {
        "status": "regression" if failures else "ok",
        "failure_count": len(failures),
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic backend performance regression benchmarks and compare them with a checked-in baseline")
    parser.add_argument("--baseline-file", default="", help="Optional JSON baseline file with explicit regression budgets")
    parser.add_argument("--write-baseline", default="", help="Write the current benchmark summary as a baseline JSON file")
    parser.add_argument("--json-out", default="", help="Optional path to write the benchmark summary JSON artifact")
    parser.add_argument("--markdown-out", default="", help="Optional path to write the benchmark summary Markdown artifact")
    parser.add_argument("--fail-on-regression", action="store_true", help="Exit non-zero when the benchmark exceeds the baseline budgets")
    parser.add_argument("--hot-rounds", type=int, default=12, help="Warm-cache requests per hot endpoint")
    parser.add_argument("--brief-concurrency", type=int, default=6, help="Concurrent workers for the company brief route")
    parser.add_argument("--brief-requests-per-worker", type=int, default=4, help="Requests per concurrent worker for the company brief route")
    args = parser.parse_args(argv)

    if args.fail_on_regression and not args.baseline_file:
        parser.error("--fail-on-regression requires --baseline-file")

    baseline = _load_json(Path(args.baseline_file)) if args.baseline_file else None
    summary = run_performance_benchmarks(
        hot_rounds=args.hot_rounds,
        brief_concurrency=args.brief_concurrency,
        brief_requests_per_worker=args.brief_requests_per_worker,
        baseline_file=args.baseline_file or None,
    )

    evaluation = evaluate_summary_against_baseline(summary, baseline) if baseline is not None else {"status": "ok", "failure_count": 0, "failures": []}
    summary["evaluation"] = evaluation

    if args.write_baseline:
        _write_json(Path(args.write_baseline), build_baseline_payload(summary))
    if args.json_out:
        _write_json(Path(args.json_out), summary)
    if args.markdown_out:
        _write_text(Path(args.markdown_out), render_markdown_summary(summary))

    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.fail_on_regression and evaluation["status"] != "ok":
        return 1
    return 0


def run_performance_benchmarks(
    *,
    hot_rounds: int,
    brief_concurrency: int,
    brief_requests_per_worker: int,
    baseline_file: str | None = None,
) -> dict[str, Any]:
    suites: list[dict[str, Any]] = []
    with _synthetic_benchmark_environment(), _muted_benchmark_loggers():
        suites.append(_run_hot_endpoint_suite(rounds=hot_rounds))
        suites.append(
            _run_company_brief_suite(
                concurrency=brief_concurrency,
                requests_per_worker=brief_requests_per_worker,
            )
        )

    return {
        "schema_version": "performance_regression_summary_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_file": baseline_file,
        "suites": suites,
    }


def render_markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# Backend Performance Regression Summary",
        "",
        f"Generated at: {summary['generated_at']}",
    ]
    if summary.get("baseline_file"):
        lines.append(f"Baseline: {summary['baseline_file']}")
    evaluation = summary.get("evaluation") or {}
    lines.extend(
        [
            f"Overall status: {evaluation.get('status', 'ok')}",
            "",
        ]
    )

    for suite in summary.get("suites", []):
        lines.extend(
            [
                f"## {suite['title']}",
                "",
                f"Config: `{json.dumps(suite['config'], sort_keys=True)}`",
                "",
                "| Case | Requests | p50 (ms) | p95 (ms) | Avg bytes | Status codes |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for result in suite.get("results", []):
            lines.append(
                "| {name} | {count} | {p50:.2f} | {p95:.2f} | {bytes_avg:.0f} | {codes} |".format(
                    name=result["name"],
                    count=result["request_count"],
                    p50=result["latency_ms"]["p50"],
                    p95=result["latency_ms"]["p95"],
                    bytes_avg=result["payload_bytes"]["avg"],
                    codes=", ".join(str(item) for item in result["status_codes"]),
                )
            )
        lines.append("")

    failures = evaluation.get("failures") or []
    if failures:
        lines.extend(["## Regressions", ""])
        for failure in failures:
            case = failure.get("case") or "<suite>"
            lines.append(f"- {failure['suite']} / {case} / {failure['metric']}: {failure['message']}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _metric_budget(observed: float, policy: dict[str, float]) -> dict[str, float]:
    return {
        "baseline": round(observed, 2),
        "budget": round(max(observed * policy["budget_multiplier"], observed + policy["min_budget_delta"]), 2),
        "max_regression_pct": policy["max_regression_pct"],
    }


def _evaluate_case(suite_name: str, result: dict[str, Any], budget: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    expected_status_codes = sorted(int(item) for item in budget.get("status_codes", []))
    actual_status_codes = sorted(int(item) for item in result.get("status_codes", []))
    if expected_status_codes and actual_status_codes != expected_status_codes:
        failures.append(
            {
                "suite": suite_name,
                "case": result["name"],
                "metric": "status_codes",
                "message": f"expected {expected_status_codes}, observed {actual_status_codes}",
            }
        )

    request_budget = budget.get("request_count") or {}
    expected_count = request_budget.get("expected")
    if expected_count is not None and int(result.get("request_count", 0)) != int(expected_count):
        failures.append(
            {
                "suite": suite_name,
                "case": result["name"],
                "metric": "request_count",
                "message": f"expected {expected_count}, observed {result['request_count']}",
            }
        )

    failures.extend(
        _evaluate_metric_budget(
            suite_name,
            result["name"],
            "latency_ms.p50",
            float(result["latency_ms"]["p50"]),
            ((budget.get("latency_ms") or {}).get("p50") or {}),
        )
    )
    failures.extend(
        _evaluate_metric_budget(
            suite_name,
            result["name"],
            "latency_ms.p95",
            float(result["latency_ms"]["p95"]),
            ((budget.get("latency_ms") or {}).get("p95") or {}),
        )
    )
    failures.extend(
        _evaluate_metric_budget(
            suite_name,
            result["name"],
            "payload_bytes.avg",
            float(result["payload_bytes"]["avg"]),
            ((budget.get("payload_bytes") or {}).get("avg") or {}),
        )
    )
    return failures


def _evaluate_metric_budget(
    suite_name: str,
    case_name: str,
    metric_name: str,
    observed: float,
    budget: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    max_budget = budget.get("budget")
    if max_budget is not None and observed > float(max_budget):
        failures.append(
            {
                "suite": suite_name,
                "case": case_name,
                "metric": metric_name,
                "message": f"observed {observed:.2f}, explicit budget {float(max_budget):.2f}",
            }
        )
        return failures

    baseline = budget.get("baseline")
    regression_pct = budget.get("max_regression_pct")
    if max_budget is None and baseline is not None and regression_pct is not None:
        allowed = float(baseline) * (1.0 + (float(regression_pct) / 100.0))
        if observed > allowed:
            failures.append(
                {
                    "suite": suite_name,
                    "case": case_name,
                    "metric": metric_name,
                    "message": f"observed {observed:.2f}, allowed regression ceiling {allowed:.2f} from baseline {float(baseline):.2f}",
                }
            )
    return failures


def _run_hot_endpoint_suite(*, rounds: int) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    with _override_db_session():
        for case in build_cases("AAPL"):
            request_path = _case_request_path(case.path, case.params)
            _clear_benchmark_caches()
            with TestClient(app) as client:
                response = client.get(request_path)
                if response.status_code >= 500:
                    raise RuntimeError(f"Warm-up request failed for {case.name} with status {response.status_code}")
                results.append(_run_sequential_case(client, case.name, request_path, rounds=rounds))
    return {
        "suite": "hot_endpoints",
        "title": "Warm-Cache Hot Read Routes",
        "config": {"rounds": rounds, "ticker": "AAPL"},
        "results": results,
    }


def _run_company_brief_suite(*, concurrency: int, requests_per_worker: int) -> dict[str, Any]:
    request_path = "/api/companies/AAPL/brief"
    _clear_benchmark_caches()
    with _override_db_session():
        with TestClient(app) as client:
            response = client.get(request_path)
            if response.status_code >= 500:
                raise RuntimeError(f"Warm-up request failed for company brief with status {response.status_code}")

        worker_results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(_brief_worker, request_path, requests_per_worker) for _ in range(concurrency)]
            for future in futures:
                worker_results.append(future.result())

    combined = _combine_measurements(worker_results)
    combined["name"] = "company_brief_ready"
    combined["path"] = request_path
    return {
        "suite": "company_brief_concurrency",
        "title": "Company Brief Simulated Concurrency",
        "config": {
            "ticker": "AAPL",
            "concurrency": concurrency,
            "requests_per_worker": requests_per_worker,
            "total_requests": concurrency * requests_per_worker,
        },
        "results": [combined],
    }


def _brief_worker(path: str, requests_per_worker: int) -> dict[str, Any]:
    with TestClient(app) as client:
        return _run_client_loop(client, path, requests=requests_per_worker)


def _run_sequential_case(client: TestClient, name: str, path: str, *, rounds: int) -> dict[str, Any]:
    measurements = _run_client_loop(client, path, requests=rounds)
    measurements["name"] = name
    measurements["path"] = path
    return measurements


def _run_client_loop(client: TestClient, path: str, *, requests: int) -> dict[str, Any]:
    durations_ms: list[float] = []
    payload_sizes: list[int] = []
    status_codes: list[int] = []
    for _ in range(requests):
        started = time.perf_counter()
        response = client.get(path)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        durations_ms.append(elapsed_ms)
        payload_sizes.append(len(response.content))
        status_codes.append(int(response.status_code))
    return _summarize_measurements(durations_ms, payload_sizes, status_codes)


def _combine_measurements(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    all_durations: list[float] = []
    all_payload_sizes: list[int] = []
    all_status_codes: list[int] = []
    request_count = 0
    for measurement in measurements:
        all_durations.extend(float(item) for item in measurement.get("_raw_durations_ms", []))
        all_payload_sizes.extend(int(item) for item in measurement.get("_raw_payload_sizes", []))
        all_status_codes.extend(int(item) for item in measurement.get("_raw_status_codes", []))
        request_count += int(measurement.get("request_count", 0))
    combined = _summarize_measurements(all_durations, all_payload_sizes, all_status_codes)
    combined["request_count"] = request_count
    return combined


def _summarize_measurements(durations_ms: list[float], payload_sizes: list[int], status_codes: list[int]) -> dict[str, Any]:
    ordered = sorted(durations_ms)
    return {
        "request_count": len(durations_ms),
        "status_codes": sorted(set(status_codes)),
        "latency_ms": {
            "min": round(min(durations_ms), 2),
            "p50": round(statistics.median(durations_ms), 2),
            "p95": round(_percentile(ordered, 0.95), 2),
            "max": round(max(durations_ms), 2),
            "avg": round(statistics.fmean(durations_ms), 2),
        },
        "payload_bytes": {
            "min": min(payload_sizes),
            "avg": round(statistics.fmean(payload_sizes), 2),
            "max": max(payload_sizes),
        },
        "_raw_durations_ms": [round(item, 4) for item in durations_ms],
        "_raw_payload_sizes": payload_sizes,
        "_raw_status_codes": status_codes,
    }


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, round((len(values) - 1) * quantile)))
    return values[index]


def _case_request_path(path: str, params: dict[str, str]) -> str:
    if not params:
        return path
    return f"{path}?{urlencode(params)}"


@contextmanager
def _muted_benchmark_loggers() -> Iterator[None]:
    logger_names = (
        "httpx",
        "httpcore",
        "app.main",
        "app.services.hot_cache",
    )
    saved_levels = {name: logging.getLogger(name).level for name in logger_names}
    try:
        for name in logger_names:
            logging.getLogger(name).setLevel(logging.WARNING)
        yield
    finally:
        for name, level in saved_levels.items():
            logging.getLogger(name).setLevel(level)


@contextmanager
def _override_db_session() -> Iterator[None]:
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@contextmanager
def _synthetic_benchmark_environment() -> Iterator[None]:
    snapshot = _snapshot()
    financial_statement = _financial_statement()
    price_point = _price_point()
    filing_timeline = [_filing_timeline_item()]
    brief_payload = _build_brief_payload(snapshot, financial_statement, price_point, filing_timeline)
    model_payload = _model_payload()

    peer_payload = {
        "company": SimpleNamespace(company=snapshot.company, cache_state="fresh", last_checked=datetime(2026, 4, 4, tzinfo=timezone.utc)),
        "peer_basis": "Technology peers",
        "available_companies": [],
        "selected_tickers": ["MSFT"],
        "peers": [
            {
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "sector": "Technology",
                "market_sector": "Technology",
                "market_industry": "Consumer Electronics",
                "is_focus": True,
                "cache_state": "fresh",
                "last_checked": "2026-04-04T00:00:00Z",
                "period_end": "2025-12-31",
                "price_date": "2026-03-21",
                "latest_price": 190.5,
                "pe": 28.0,
                "ev_to_ebit": 20.0,
                "price_to_free_cash_flow": 30.0,
                "roe": 0.24,
                "revenue_growth": 0.08,
                "piotroski_score": 8,
                "altman_z_score": 4.2,
                "fair_value_gap": 0.07,
                "roic": 0.19,
                "shareholder_yield": 0.03,
                "implied_growth": 0.05,
                "dcf_model_status": "supported",
                "reverse_dcf_model_status": "supported",
                "valuation_band_percentile": 0.58,
                "revenue_history": [],
            }
        ],
        "notes": {"ev_to_ebit": "proxy"},
        "source_hints": {
            "financial_statement_sources": ["sec_companyfacts"],
            "price_sources": ["yahoo_finance"],
            "risk_free_sources": ["U.S. Treasury Daily Par Yield Curve"],
        },
    }
    metrics_timeseries_payload = [
        {
            "cadence": "ttm",
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
            "filing_type": "TTM",
            "metrics": {
                "revenue_growth": 0.12,
                "gross_margin": 0.42,
                "operating_margin": 0.31,
            },
            "provenance": {
                "statement_type": "canonical_xbrl",
                "statement_source": "https://data.sec.gov/example",
                "price_source": "yahoo_finance",
                "formula_version": "sec_metrics_v1",
            },
            "quality": {
                "available_metrics": 3,
                "missing_metrics": [],
                "coverage_ratio": 0.2,
                "flags": [],
            },
        }
    ]

    with ExitStack() as stack:
        stack.enter_context(patch.object(main_module, "get_company_regulated_bank_financials", lambda *_args, **_kwargs: []))
        stack.enter_context(patch.object(main_module, "search_company_snapshots", lambda *_args, **_kwargs: [snapshot]))
        stack.enter_context(patch.object(main_module, "get_company_snapshot", lambda *_args, **_kwargs: snapshot))
        stack.enter_context(patch.object(main_module, "get_company_snapshot_by_cik", lambda *_args, **_kwargs: snapshot))
        stack.enter_context(patch.object(main_module, "_trigger_refresh", _fresh_trigger))
        stack.enter_context(patch.object(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot))
        stack.enter_context(patch.object(main_module, "get_company_financials", lambda *_args, **_kwargs: [financial_statement]))
        stack.enter_context(patch.object(main_module, "get_company_price_history", lambda *_args, **_kwargs: [price_point]))
        stack.enter_context(
            patch.object(
                main_module,
                "get_company_price_cache_status",
                lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"),
            )
        )
        stack.enter_context(patch.object(main_module, "_refresh_for_financial_page", _fresh_refresh_for_snapshot))
        stack.enter_context(patch.object(main_module, "_refresh_for_snapshot", _fresh_refresh_for_snapshot))
        stack.enter_context(
            patch.object(
                main_module.ModelEngine,
                "compute_models",
                lambda *_args, **_kwargs: [SimpleNamespace(cached=True)],
            )
        )
        stack.enter_context(patch.object(main_module, "get_company_models", lambda *_args, **_kwargs: [model_payload]))
        stack.enter_context(patch.object(main_module, "build_peer_comparison", lambda *_args, **_kwargs: peer_payload))
        stack.enter_context(patch.object(main_module, "build_metrics_timeseries", lambda *_args, **_kwargs: metrics_timeseries_payload))
        stack.enter_context(
            patch.object(
                main_module,
                "get_company_research_brief_snapshot",
                lambda *_args, **_kwargs: SimpleNamespace(payload=brief_payload),
            )
        )
        stack.enter_context(patch.object(main_module, "_visible_financials_for_company", lambda *_args, **_kwargs: [financial_statement]))
        stack.enter_context(patch.object(main_module, "_visible_price_history", lambda *_args, **_kwargs: [price_point]))
        stack.enter_context(patch.object(main_module, "_load_company_brief_filing_timeline", lambda *_args, **_kwargs: filing_timeline))
        yield


def _clear_benchmark_caches() -> None:
    main_module._search_response_cache.clear()
    main_module._hot_response_cache.clear()


def _snapshot() -> SimpleNamespace:
    company = SimpleNamespace(
        id=1,
        ticker="AAPL",
        cik="0000320193",
        name="Apple Inc.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Consumer Electronics",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime(2026, 4, 4, tzinfo=timezone.utc))


def _financial_statement() -> SimpleNamespace:
    return SimpleNamespace(
        filing_type="10-K",
        statement_type="canonical_xbrl",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        source="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        last_updated=datetime(2026, 3, 21, tzinfo=timezone.utc),
        last_checked=datetime(2026, 4, 4, tzinfo=timezone.utc),
        data={
            "revenue": 391_000_000_000,
            "net_income": 97_000_000_000,
            "operating_income": 123_000_000_000,
            "free_cash_flow": 110_000_000_000,
            "weighted_average_diluted_shares": 15_400_000_000,
            "segment_breakdown": [{"segment_name": "Products", "share_of_revenue": 0.72}],
        },
    )


def _price_point() -> SimpleNamespace:
    return SimpleNamespace(
        trade_date=date(2026, 3, 21),
        close=190.5,
        volume=10_000_000,
        source="https://finance.yahoo.com/quote/AAPL",
    )


def _filing_timeline_item() -> Any:
    return main_module.FilingTimelineItemPayload(
        date=date(2025, 12, 31),
        form="10-K",
        description="Annual report",
        accession="0000320193-26-000010",
    )


def _model_payload() -> SimpleNamespace:
    return SimpleNamespace(
        model_name="dcf",
        model_version="v2",
        created_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
        input_periods={"period_end": "2025-12-31"},
        result={
            "model_status": "supported",
            "base_period_end": "2025-12-31",
            "fair_value_per_share": 205.0,
            "price_snapshot": {
                "price_date": "2026-03-21",
                "price_source": "yahoo_finance",
            },
            "assumption_provenance": {
                "price_snapshot": {
                    "price_date": "2026-03-21",
                    "price_source": "yahoo_finance",
                },
                "risk_free_rate": {
                    "source_name": "U.S. Treasury Daily Par Yield Curve",
                    "observation_date": "2026-03-20",
                },
            },
        },
    )


def _build_brief_payload(
    snapshot: SimpleNamespace,
    financial_statement: SimpleNamespace,
    price_point: SimpleNamespace,
    filing_timeline: list[Any],
) -> dict[str, Any]:
    with ExitStack() as stack:
        stack.enter_context(patch.object(main_module, "_visible_financials_for_company", lambda *_args, **_kwargs: [financial_statement]))
        stack.enter_context(patch.object(main_module, "_visible_price_history", lambda *_args, **_kwargs: [price_point]))
        stack.enter_context(patch.object(main_module, "_load_company_brief_filing_timeline", lambda *_args, **_kwargs: filing_timeline))
        response = main_module._build_company_brief_bootstrap_for_snapshot(
            object(),
            snapshot,
            refresh=main_module.RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None),
            as_of=None,
        )
    return response.model_dump(mode="json")


def _fresh_trigger(_background_tasks: Any, ticker: str, reason: str) -> Any:
    return main_module.RefreshState(triggered=False, reason="fresh" if reason == "stale" else reason, ticker=ticker, job_id=None)


def _fresh_refresh_for_snapshot(*args: Any, **_kwargs: Any) -> Any:
    snapshot = next((arg for arg in args if hasattr(arg, "company")), None)
    ticker = snapshot.company.ticker if snapshot is not None else "AAPL"
    return main_module.RefreshState(triggered=False, reason="fresh", ticker=ticker, job_id=None)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
