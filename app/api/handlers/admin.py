from __future__ import annotations

from typing import Any

import app.services.route_timing as _store


def performance_summary() -> dict[str, Any]:
    """Return p50/p95/p99 latency per route for the current process."""
    return {
        "description": "Per-route latency percentiles for the current server process (ring buffer, last 2 000 requests).",
        "record_count": _store.record_count(),
        "routes": _store.get_summary(),
    }


def reset_timing() -> dict[str, Any]:
    """Clear the timing ring buffer."""
    cleared = _store.reset()
    return {"cleared": cleared}


__all__ = ["performance_summary", "reset_timing"]
