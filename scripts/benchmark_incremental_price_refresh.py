from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from app.services.market_data import (
    PriceBar,
    build_price_history_payload_hash,
    price_bar_windows_match,
    touch_company_price_history,
    upsert_price_history,
)


class _FakeExecuteResult:
    def scalar_one_or_none(self) -> None:
        return None


class _FakeSession:
    def __init__(self) -> None:
        self.execute_count = 0
        self.info: dict[str, object] = {}

    def execute(self, _statement):
        self.execute_count += 1
        return _FakeExecuteResult()


def benchmark_incremental_price_refresh(*, rounds: int = 200, bar_count: int = 8) -> dict[str, Any]:
    company = SimpleNamespace(id=7)
    checked_at = datetime(2026, 4, 21, tzinfo=timezone.utc)
    stored_tail = _build_price_bars(bar_count)
    unchanged_tail = list(stored_tail)
    changed_tail = list(stored_tail[:-1]) + [
        PriceBar(
            trade_date=stored_tail[-1].trade_date,
            close=stored_tail[-1].close + 1.0,
            volume=stored_tail[-1].volume,
        )
    ]

    scenarios = [
        ("always_write_unchanged_tail", unchanged_tail, True),
        ("no_op_unchanged_tail", unchanged_tail, False),
        ("changed_tail_write", changed_tail, False),
    ]
    results = [_run_scenario(name, company, bars, checked_at, stored_tail, rounds=rounds, force_write=force_write) for name, bars, force_write in scenarios]
    return {"rounds": rounds, "bar_count": bar_count, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark unchanged incremental price refresh writes vs the no-op fast path")
    parser.add_argument("--rounds", type=int, default=200, help="Benchmark rounds per scenario")
    parser.add_argument("--bar-count", type=int, default=8, help="Synthetic overlapping bars per scenario")
    args = parser.parse_args()

    print(json.dumps(benchmark_incremental_price_refresh(rounds=args.rounds, bar_count=args.bar_count), indent=2))
    return 0


def _run_scenario(
    name: str,
    company: SimpleNamespace,
    bars: list[PriceBar],
    checked_at: datetime,
    stored_tail: list[PriceBar],
    *,
    rounds: int,
    force_write: bool,
) -> dict[str, Any]:
    durations_ms: list[float] = []
    execute_counts: list[int] = []

    for _ in range(rounds):
        session = _FakeSession()
        started = time.perf_counter()
        payload_version_hash = build_price_history_payload_hash(bars)
        if not force_write and price_bar_windows_match(bars, stored_tail):
            touch_company_price_history(
                session,
                company.id,
                checked_at,
                payload_version_hash=payload_version_hash,
                touch_rows=False,
                invalidate_hot_cache=False,
            )
        else:
            upsert_price_history(
                session=session,
                company=company,
                price_bars=bars,
                checked_at=checked_at,
            )
            touch_company_price_history(
                session,
                company.id,
                checked_at,
                payload_version_hash=payload_version_hash,
            )
        durations_ms.append((time.perf_counter() - started) * 1000.0)
        execute_counts.append(session.execute_count)

    return {
        "name": name,
        "latency_ms": _summarize(durations_ms),
        "execute_count": {
            "min": min(execute_counts),
            "max": max(execute_counts),
            "avg": round(statistics.mean(execute_counts), 2),
        },
    }


def _build_price_bars(bar_count: int) -> list[PriceBar]:
    anchor = date(2026, 4, 21)
    start = anchor - timedelta(days=bar_count - 1)
    return [
        PriceBar(
            trade_date=start + timedelta(days=index),
            close=100.0 + index,
            volume=1_000 + (index * 10),
        )
        for index in range(bar_count)
    ]


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
