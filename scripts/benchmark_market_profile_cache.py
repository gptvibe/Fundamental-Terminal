from __future__ import annotations

import argparse
import json
import statistics
import time
from types import SimpleNamespace
from typing import Any

import app.services.market_data as market_data_module


def benchmark_market_profile_cache(*, rounds: int = 200, ttl_seconds: int = 21600) -> dict[str, Any]:
    uncached = _run_scenario(rounds=rounds, ttl_seconds=0)
    cached = _run_scenario(rounds=rounds, ttl_seconds=ttl_seconds)
    return {"rounds": rounds, "ttl_seconds": ttl_seconds, "results": [uncached, cached]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark repeated Yahoo market profile lookups with and without the TTL cache")
    parser.add_argument("--rounds", type=int, default=200, help="Repeated same-ticker lookups per scenario")
    parser.add_argument("--ttl-seconds", type=int, default=21600, help="TTL used for the cached scenario")
    args = parser.parse_args()

    print(json.dumps(benchmark_market_profile_cache(rounds=args.rounds, ttl_seconds=args.ttl_seconds), indent=2))
    return 0


def _run_scenario(*, rounds: int, ttl_seconds: int) -> dict[str, Any]:
    request_count = 0
    timings_ms: list[float] = []
    original_settings = market_data_module.settings
    original_request_with_retries = market_data_module._request_with_retries
    original_monotonic = market_data_module.time.monotonic
    current_time = 100.0

    class _Response:
        def json(self) -> dict[str, object]:
            return {
                "quotes": [
                    {
                        "symbol": "AAPL",
                        "quoteType": "EQUITY",
                        "sectorDisp": "Technology",
                        "industryDisp": "Consumer Electronics",
                    }
                ]
            }

    def _profile_request(*_args, **_kwargs):
        nonlocal request_count
        request_count += 1
        return _Response()

    try:
        market_data_module.settings = SimpleNamespace(
            strict_official_mode=False,
            sec_user_agent="benchmark-agent",
            sec_timeout_seconds=10,
            market_max_retries=1,
            market_retry_backoff_seconds=0.01,
            market_profile_cache_ttl_seconds=ttl_seconds,
        )
        market_data_module._request_with_retries = _profile_request
        market_data_module.time.monotonic = lambda: current_time
        market_data_module._clear_market_profile_cache()

        client = market_data_module.MarketDataClient()
        try:
            for _ in range(rounds):
                started = time.perf_counter()
                client.get_market_profile("AAPL")
                timings_ms.append((time.perf_counter() - started) * 1000.0)
                current_time += 0.001
        finally:
            client.close()
    finally:
        market_data_module._clear_market_profile_cache()
        market_data_module.settings = original_settings
        market_data_module._request_with_retries = original_request_with_retries
        market_data_module.time.monotonic = original_monotonic

    return {
        "name": "cached" if ttl_seconds > 0 else "uncached",
        "request_count": request_count,
        "request_reduction_percent": round(100.0 * (1.0 - (request_count / rounds)), 2),
        "latency_ms": _summarize(timings_ms),
    }


def _summarize(durations_ms: list[float]) -> dict[str, float]:
    ordered = sorted(durations_ms)
    p95_index = min(len(ordered) - 1, max(0, int(round(0.95 * len(ordered))) - 1))
    return {
        "min": round(min(durations_ms), 4),
        "p50": round(statistics.median(durations_ms), 4),
        "p95": round(ordered[p95_index], 4),
        "max": round(max(durations_ms), 4),
        "avg": round(statistics.mean(durations_ms), 4),
    }


if __name__ == "__main__":
    raise SystemExit(main())
