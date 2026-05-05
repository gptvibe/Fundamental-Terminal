from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError


@dataclass(slots=True)
class Case:
    name: str
    path: str
    params: dict[str, str]


def build_cases(ticker: str) -> list[Case]:
    normalized_ticker = ticker.upper().strip()
    return [
        Case(name="company_search", path="/api/companies/search", params={"query": normalized_ticker, "refresh": "false"}),
        Case(name="financials_payload", path=f"/api/companies/{normalized_ticker}/financials", params={}),
        Case(
            name="models_payload",
            path=f"/api/companies/{normalized_ticker}/models",
            params={"model": "ratios,dupont,dcf,reverse_dcf,roic,capital_allocation"},
        ),
        Case(name="peers_payload", path=f"/api/companies/{normalized_ticker}/peers", params={}),
        Case(name="metrics_timeseries_payload", path=f"/api/companies/{normalized_ticker}/metrics-timeseries", params={"cadence": "ttm", "max_points": "12"}),
        Case(name="beneficial_ownership_summary", path=f"/api/companies/{normalized_ticker}/beneficial-ownership/summary", params={}),
        Case(name="governance_summary", path=f"/api/companies/{normalized_ticker}/governance/summary", params={}),
        Case(name="filing_events_summary", path=f"/api/companies/{normalized_ticker}/filing-events/summary", params={}),
        Case(name="capital_markets_summary", path=f"/api/companies/{normalized_ticker}/capital-markets/summary", params={}),
        Case(name="earnings_summary", path=f"/api/companies/{normalized_ticker}/earnings/summary", params={}),
        Case(name="metrics_summary", path=f"/api/companies/{normalized_ticker}/metrics/summary", params={"period_type": "ttm"}),
        Case(name="institutional_holdings_summary", path=f"/api/companies/{normalized_ticker}/institutional-holdings/summary", params={}),
    ]


def _run_case(base_url: str, case: Case, *, rounds: int, timeout: float) -> dict[str, Any]:
    durations_ms: list[float] = []
    status_codes: list[int] = []
    bytes_out: list[int] = []

    url = f"{base_url.rstrip('/')}{case.path}"
    if case.params:
        url = f"{url}?{urlencode(case.params)}"

    for _ in range(rounds):
        started = time.perf_counter()
        request = Request(url=url, method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:
                content = response.read()
                status_code = int(response.status)
        except HTTPError as exc:
            content = exc.read()
            status_code = int(exc.code)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        durations_ms.append(elapsed_ms)
        status_codes.append(status_code)
        bytes_out.append(len(content))

    ordered = sorted(durations_ms)
    p95_index = min(len(ordered) - 1, max(0, int(round(0.95 * len(ordered))) - 1))
    return {
        "name": case.name,
        "url": url,
        "rounds": rounds,
        "status_codes": sorted(set(status_codes)),
        "bytes_avg": int(statistics.mean(bytes_out)) if bytes_out else 0,
        "latency_ms": {
            "min": round(min(durations_ms), 2),
            "p50": round(statistics.median(durations_ms), 2),
            "p95": round(ordered[p95_index], 2),
            "max": round(max(durations_ms), 2),
            "avg": round(statistics.mean(durations_ms), 2),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark hot read endpoints for cache-warm behavior")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol to benchmark")
    parser.add_argument("--rounds", type=int, default=20, help="Requests per endpoint")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout seconds")
    args = parser.parse_args()

    ticker = args.ticker.upper().strip()
    cases = build_cases(ticker)

    # Warm-up pass so benchmark emphasizes warm-cache behavior.
    for case in cases:
        warm_url = f"{args.base_url.rstrip('/')}{case.path}" + (f"?{urlencode(case.params)}" if case.params else "")
        request = Request(url=warm_url, method="GET")
        try:
            with urlopen(request, timeout=args.timeout):
                pass
        except HTTPError:
            pass

    results = [_run_case(args.base_url, case, rounds=args.rounds, timeout=args.timeout) for case in cases]
    print(json.dumps({"base_url": args.base_url, "ticker": ticker, "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
