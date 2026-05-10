"""Lightweight in-process route timing store.

Always-on and flag-free.  A fixed-size ring buffer (default 2 000 records)
keeps memory usage bounded regardless of traffic volume.

Usage (from middleware or elsewhere)::

    import app.services.route_timing as route_timing

    route_timing.record(
        route="/api/companies/{ticker}/financials",
        method="GET",
        status_code=200,
        duration_ms=42.7,
        cache_hit=True,
        upstream_count=0,
    )

    summary = route_timing.get_summary()
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from threading import Lock
from typing import Any

_MAX_RECORDS = 2_000
_STORE_LOCK = Lock()
_RECORDS: list[dict[str, Any]] = []


def record(
    *,
    route: str,
    method: str,
    status_code: int,
    duration_ms: float,
    cache_hit: bool | None = None,
    upstream_count: int = 0,
) -> None:
    """Append one timing observation to the ring buffer."""
    entry: dict[str, Any] = {
        "route": route,
        "method": method.upper(),
        "status_code": status_code,
        "duration_ms": round(duration_ms, 3),
        "cache_hit": cache_hit,
        "upstream_count": upstream_count,
    }
    with _STORE_LOCK:
        _RECORDS.append(entry)
        if len(_RECORDS) > _MAX_RECORDS:
            del _RECORDS[: len(_RECORDS) - _MAX_RECORDS]


def get_summary() -> list[dict[str, Any]]:
    """Return p50/p95/p99 latency per route/method, sorted by p95 descending."""
    with _STORE_LOCK:
        records = list(_RECORDS)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        grouped[(rec["method"], rec["route"])].append(rec)

    summaries: list[dict[str, Any]] = []
    for (method, route), recs in grouped.items():
        durations = sorted(r["duration_ms"] for r in recs)
        cache_hits = [r["cache_hit"] for r in recs if r["cache_hit"] is not None]
        upstreams = [r["upstream_count"] for r in recs]
        summaries.append(
            {
                "method": method,
                "route": route,
                "count": len(recs),
                "latency_ms": _percentiles(durations),
                "status_codes": _count_values([r["status_code"] for r in recs]),
                "cache_hit_rate": round(sum(cache_hits) / len(cache_hits), 4) if cache_hits else None,
                "avg_upstream_calls": round(sum(upstreams) / len(upstreams), 3) if upstreams else 0.0,
            }
        )

    summaries.sort(key=lambda s: s["latency_ms"]["p95"], reverse=True)
    return summaries


def reset() -> int:
    """Clear the store and return how many records were removed."""
    with _STORE_LOCK:
        cleared = len(_RECORDS)
        _RECORDS.clear()
    return cleared


def record_count() -> int:
    """Return the current number of records in the buffer."""
    with _STORE_LOCK:
        return len(_RECORDS)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _percentiles(sorted_values: list[float]) -> dict[str, float]:
    if not sorted_values:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "p50": round(median(sorted_values), 3),
        "p95": round(_at_quantile(sorted_values, 0.95), 3),
        "p99": round(_at_quantile(sorted_values, 0.99), 3),
        "max": round(sorted_values[-1], 3),
    }


def _at_quantile(sorted_values: list[float], q: float) -> float:
    idx = max(0, min(len(sorted_values) - 1, round((len(sorted_values) - 1) * q)))
    return sorted_values[idx]


def _count_values(values: list[int]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for v in values:
        counts[str(v)] += 1
    return dict(sorted(counts.items()))


__all__ = ["get_summary", "record", "record_count", "reset"]
