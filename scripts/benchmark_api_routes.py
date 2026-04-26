from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TRACKED_CACHE_HEADERS = (
    "cache-control",
    "cache-status",
    "age",
    "etag",
    "last-modified",
    "x-cache",
    "x-cache-status",
    "x-cache-result",
    "cf-cache-status",
    "x-vercel-cache",
    "x-nextjs-cache",
    "x-cache-hit",
    "x-cache-state",
    "x-ft-cache-status",
    "x-ft-cache-state",
    "x-hot-cache-status",
)

STATE_HINT_HEADERS = {
    "cache-status",
    "x-cache",
    "x-cache-status",
    "x-cache-result",
    "cf-cache-status",
    "x-vercel-cache",
    "x-nextjs-cache",
    "x-cache-hit",
    "x-cache-state",
    "x-ft-cache-status",
    "x-ft-cache-state",
    "x-hot-cache-status",
}


@dataclass(slots=True)
class BenchmarkCase:
    name: str
    method: str
    path: str
    params: dict[str, str]
    json_body: dict[str, Any] | None = None


def build_focus_cases(ticker: str, compare_tickers: str) -> list[BenchmarkCase]:
    normalized_ticker = ticker.upper().strip()
    normalized_compare = ",".join(
        item.strip().upper()
        for item in compare_tickers.split(",")
        if item.strip()
    )
    if not normalized_compare:
        normalized_compare = normalized_ticker

    return [
        BenchmarkCase(
            name="company_overview",
            method="GET",
            path=f"/api/companies/{normalized_ticker}/overview",
            params={},
        ),
        BenchmarkCase(
            name="company_financials",
            method="GET",
            path=f"/api/companies/{normalized_ticker}/financials",
            params={},
        ),
        BenchmarkCase(
            name="company_charts",
            method="GET",
            path=f"/api/companies/{normalized_ticker}/charts",
            params={},
        ),
        BenchmarkCase(
            name="derived_metrics",
            method="GET",
            path=f"/api/companies/{normalized_ticker}/metrics",
            params={},
        ),
        BenchmarkCase(
            name="company_models",
            method="GET",
            path=f"/api/companies/{normalized_ticker}/models",
            params={"model": "ratios,dupont,dcf,reverse_dcf,roic,capital_allocation"},
        ),
        BenchmarkCase(
            name="company_compare",
            method="GET",
            path="/api/companies/compare",
            params={"tickers": normalized_compare},
        ),
        BenchmarkCase(
            name="screener_search",
            method="POST",
            path="/api/screener/search",
            params={},
            json_body={
                "period_type": "ttm",
                "filters": {"revenue_growth_min": 0.1},
                "sort": {"field": "revenue_growth", "direction": "desc"},
                "limit": 25,
                "offset": 0,
            },
        ),
        BenchmarkCase(
            name="source_registry",
            method="GET",
            path="/api/source-registry",
            params={},
        ),
        BenchmarkCase(
            name="source_registry_status",
            method="GET",
            path="/api/internal/cache-metrics",
            params={},
        ),
    ]


def _build_url(
    base_url: str,
    case: BenchmarkCase,
    *,
    cache_mode: str,
    nonce: str | None,
) -> str:
    query = dict(case.params)
    if cache_mode == "cold" and nonce:
        query["__bench_nonce"] = nonce

    url = f"{base_url.rstrip('/')}{case.path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def _build_request(
    url: str,
    case: BenchmarkCase,
    *,
    cache_mode: str,
) -> Request:
    body = None
    headers = {
        "Accept": "application/json",
    }
    if cache_mode == "cold":
        headers["Cache-Control"] = "no-cache"
        headers["Pragma"] = "no-cache"
    if case.json_body is not None:
        body = json.dumps(case.json_body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    return Request(url=url, method=case.method.upper(), data=body, headers=headers)


def _extract_cache_headers(headers: Any) -> dict[str, str]:
    extracted: dict[str, str] = {}
    for header_name in TRACKED_CACHE_HEADERS:
        value = headers.get(header_name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            extracted[header_name] = text
    return extracted


def _infer_cache_states(headers: dict[str, str]) -> set[str]:
    states: set[str] = set()
    for header_name, header_value in headers.items():
        if header_name not in STATE_HINT_HEADERS:
            continue
        lowered = header_value.lower()
        if "hit" in lowered:
            states.add("hit")
        if "stale" in lowered:
            states.add("stale")
        if "fresh" in lowered:
            states.add("fresh")
    return states


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * quantile)))
    return ordered[index]


def _summarize_case(
    *,
    case: BenchmarkCase,
    cache_mode: str,
    rounds: int,
    responses: list[dict[str, Any]],
) -> dict[str, Any]:
    durations_ms = [float(item["duration_ms"]) for item in responses]
    payload_sizes = [int(item["payload_bytes"]) for item in responses]

    status_code_counts: dict[str, int] = {}
    cache_header_presence: dict[str, int] = {}
    cache_header_values: dict[str, dict[str, int]] = {}
    cache_state_counts = {"hit": 0, "stale": 0, "fresh": 0}

    for item in responses:
        status_key = str(item["status_code"])
        status_code_counts[status_key] = status_code_counts.get(status_key, 0) + 1

        observed_headers: dict[str, str] = item["cache_headers"]
        for name, value in observed_headers.items():
            cache_header_presence[name] = cache_header_presence.get(name, 0) + 1
            bucket = cache_header_values.setdefault(name, {})
            bucket[value] = bucket.get(value, 0) + 1

        for state in item["cache_states"]:
            cache_state_counts[state] += 1

    return {
        "name": case.name,
        "method": case.method,
        "path": case.path,
        "cache_mode": cache_mode,
        "rounds": rounds,
        "status_codes": sorted(int(item) for item in status_code_counts.keys()),
        "status_code_counts": status_code_counts,
        "payload_bytes": {
            "min": min(payload_sizes),
            "avg": round(statistics.fmean(payload_sizes), 2),
            "max": max(payload_sizes),
        },
        "latency_ms": {
            "min": round(min(durations_ms), 2),
            "p50": round(_percentile(durations_ms, 0.50), 2),
            "p95": round(_percentile(durations_ms, 0.95), 2),
            "p99": round(_percentile(durations_ms, 0.99), 2),
            "max": round(max(durations_ms), 2),
            "avg": round(statistics.fmean(durations_ms), 2),
        },
        "cache_headers": {
            "present_counts": cache_header_presence,
            "value_counts": cache_header_values,
            "state_counts": cache_state_counts,
        },
    }


def run_case(
    *,
    base_url: str,
    case: BenchmarkCase,
    rounds: int,
    timeout: float,
    cache_mode: str,
) -> dict[str, Any]:
    if cache_mode not in {"warm", "cold"}:
        raise ValueError(f"Unsupported cache mode: {cache_mode}")

    if cache_mode == "warm":
        warm_url = _build_url(base_url, case, cache_mode=cache_mode, nonce=None)
        warm_request = _build_request(warm_url, case, cache_mode=cache_mode)
        try:
            with urlopen(warm_request, timeout=timeout):
                pass
        except HTTPError:
            pass
        except URLError as exc:
            raise RuntimeError(f"Warm-up request failed for {case.name} ({warm_url}): {exc}") from exc

    samples: list[dict[str, Any]] = []
    for index in range(rounds):
        nonce = f"{int(time.time() * 1000)}-{index}" if cache_mode == "cold" else None
        url = _build_url(base_url, case, cache_mode=cache_mode, nonce=nonce)
        request = _build_request(url, case, cache_mode=cache_mode)

        started = time.perf_counter()
        try:
            with urlopen(request, timeout=timeout) as response:
                content = response.read()
                status_code = int(response.status)
                response_headers = response.headers
        except HTTPError as exc:
            content = exc.read()
            status_code = int(exc.code)
            response_headers = exc.headers
        except URLError as exc:
            raise RuntimeError(f"Benchmark request failed for {case.name} ({url}): {exc}") from exc
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        observed_cache_headers = _extract_cache_headers(response_headers)
        samples.append(
            {
                "duration_ms": elapsed_ms,
                "status_code": status_code,
                "payload_bytes": len(content),
                "cache_headers": observed_cache_headers,
                "cache_states": sorted(_infer_cache_states(observed_cache_headers)),
            }
        )

    return _summarize_case(case=case, cache_mode=cache_mode, rounds=rounds, responses=samples)


def run_benchmark(
    *,
    base_url: str,
    ticker: str,
    compare_tickers: str,
    rounds: int,
    timeout: float,
    cache_modes: list[str],
) -> dict[str, Any]:
    cases = build_focus_cases(ticker, compare_tickers)
    suites: list[dict[str, Any]] = []

    for cache_mode in cache_modes:
        results: list[dict[str, Any]] = []
        for case in cases:
            results.append(
                run_case(
                    base_url=base_url,
                    case=case,
                    rounds=rounds,
                    timeout=timeout,
                    cache_mode=cache_mode,
                )
            )
        suites.append(
            {
                "cache_mode": cache_mode,
                "rounds": rounds,
                "results": results,
            }
        )

    return {
        "schema_version": "api_route_benchmark_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "ticker": ticker.upper().strip(),
        "compare_tickers": [item.strip().upper() for item in compare_tickers.split(",") if item.strip()],
        "rounds": rounds,
        "timeout_seconds": timeout,
        "cache_modes": cache_modes,
        "routes": [
            {
                "name": case.name,
                "method": case.method,
                "path": case.path,
            }
            for case in cases
        ],
        "suites": suites,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark core API routes with warm/cold cache modes and CI-friendly JSON output")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol for company-scoped routes")
    parser.add_argument("--compare-tickers", default="AAPL,MSFT", help="Comma-separated tickers for compare route")
    parser.add_argument("--rounds", type=int, default=12, help="Requests per route for each cache mode")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--cache-mode",
        choices=("warm", "cold", "both"),
        default="both",
        help="Run warm-cache suite, cold-cache suite, or both",
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Optional path to write benchmark JSON output for CI artifact comparison",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cache_modes = ["warm", "cold"] if args.cache_mode == "both" else [args.cache_mode]

    payload = run_benchmark(
        base_url=args.base_url,
        ticker=args.ticker,
        compare_tickers=args.compare_tickers,
        rounds=args.rounds,
        timeout=args.timeout,
        cache_modes=cache_modes,
    )

    if args.json_out:
        _write_json(Path(args.json_out), payload)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())