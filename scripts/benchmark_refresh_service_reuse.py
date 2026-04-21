from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Any

from app.services.sec_edgar import EdgarIngestionService


def benchmark_refresh_service_reuse(*, rounds: int = 200) -> dict[str, Any]:
    fresh_per_job_times: list[float] = []
    for _ in range(rounds):
        started = time.perf_counter()
        service = EdgarIngestionService()
        service.close()
        fresh_per_job_times.append((time.perf_counter() - started) * 1000.0)

    started = time.perf_counter()
    service = EdgarIngestionService()
    try:
        for _ in range(rounds):
            pass
    finally:
        service.close()
    reused_total_ms = (time.perf_counter() - started) * 1000.0

    return {
        "rounds": rounds,
        "results": [
            {
                "name": "fresh_service_per_job",
                "service_constructions": rounds,
                "latency_ms": _summarize(fresh_per_job_times),
                "total_ms": round(sum(fresh_per_job_times), 4),
            },
            {
                "name": "reused_service_for_burst",
                "service_constructions": 1,
                "latency_ms_per_job_equivalent": round(reused_total_ms / rounds, 4),
                "total_ms": round(reused_total_ms, 4),
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark refresh service lifecycle churn with and without worker-scope reuse")
    parser.add_argument("--rounds", type=int, default=200, help="Synthetic jobs per scenario")
    args = parser.parse_args()

    print(json.dumps(benchmark_refresh_service_reuse(rounds=args.rounds), indent=2))
    return 0


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
