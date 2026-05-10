# Performance Profiling Baseline

This document explains the lightweight, always-on performance instrumentation
built into the Fundamental Terminal backend and how to read its results.

---

## Overview

Every HTTP request that hits a product API route is timed by a thin Starlette
middleware (`app/middleware/route_timing.py`).  Timing data is kept in a
fixed-size in-process ring buffer (`app/services/route_timing.py`, 2 000-record
cap) so memory usage stays flat regardless of traffic volume.  No external
services, no feature flags — it works in every environment including local dev.

---

## Reading the summary

### Endpoint

```
GET /api/admin/performance/summary
```

Returns the current p50 / p95 / p99 / max latency by route for the lifetime
of the current server process (or since the last reset).

**Example response**

```json
{
  "description": "Per-route latency percentiles for the current server process (ring buffer, last 2 000 requests).",
  "record_count": 312,
  "routes": [
    {
      "method": "GET",
      "route": "/api/companies/{ticker}/financials",
      "count": 84,
      "latency_ms": {
        "p50": 38.4,
        "p95": 210.7,
        "p99": 480.1,
        "max": 612.3
      },
      "status_codes": { "200": 82, "404": 2 },
      "cache_hit_rate": 0.8095,
      "avg_upstream_calls": 0.19
    },
    ...
  ]
}
```

Routes are sorted by **p95 descending** so the slowest routes appear first.

### Field reference

| Field | Description |
|---|---|
| `record_count` | Total observations in the current ring buffer |
| `route` | FastAPI route template (e.g. `/api/companies/{ticker}/financials`) |
| `count` | Number of requests observed for this route |
| `latency_ms.p50` | Median end-to-end response time in milliseconds |
| `latency_ms.p95` | 95th-percentile response time — the primary slowness indicator |
| `latency_ms.p99` | 99th-percentile response time — tail latency |
| `latency_ms.max` | Worst single request observed |
| `status_codes` | Map of HTTP status code (as string) → observation count |
| `cache_hit_rate` | Fraction of requests where `X-Cache-Status: hit` was returned; `null` if no cache header was observed |
| `avg_upstream_calls` | Average number of outbound SEC/market upstream calls per request (requires observability context) |

---

## Clearing the buffer

```
POST /api/admin/performance/reset
```

Returns `{ "cleared": <n> }`.  Useful when you want to measure a clean
baseline after a server warm-up period.

---

## What is timed

The middleware measures **end-to-end wall-clock time from when the request
enters the process to when the response object is ready**.  This includes:

- Routing and dependency injection
- Database queries (SQLAlchemy, via connection pool)
- Redis calls
- Outbound SEC or market upstream HTTP calls
- JSON serialization

It does **not** include network transit time between client and server.

---

## What is excluded from the buffer

The following paths are excluded to avoid self-instrumentation noise:

- `/health`
- `/readyz`
- `/api/admin/performance/*` (this endpoint itself)
- `/api/internal/performance-audit/*`
- `/api/internal/observability`
- `/api/internal/cache-metrics`

---

## Cache hit detection

When a response carries the `X-Cache-Status` header with value `hit`, the
request is counted as a cache hit.  The `cache_hit_rate` in the summary is the
fraction `hits / (hits + misses)` across all requests that carried the header.
Requests without the header are excluded from the rate calculation.

---

## Ring buffer size

The ring buffer holds the **last 2 000 requests** per process worker.  When the
buffer is full, older records are dropped from the front.  If you run multiple
Uvicorn workers (`--workers N`), each worker maintains its own independent
buffer; the admin endpoint only reflects the worker that handled the request.

For multi-worker aggregation during a load test, call the endpoint on each
worker via its local port or use a load-balancer sticky session.

---

## Integration with the existing performance-audit system

The route timing store described here is separate from (but complementary to)
the full performance-audit system at `/api/internal/performance-audit`.

| Feature | Route timing (`/api/admin/performance/summary`) | Full audit (`/api/internal/performance-audit`) |
|---|---|---|
| Always-on | ✅ | Off by default (`PERFORMANCE_AUDIT_ENABLED=true`) |
| p50 / p95 / p99 per route | ✅ | ✅ (avg / p50 / p95 / max) |
| Per-request detail | ❌ | ✅ |
| SQL / Redis / serialization breakdown | ❌ | ✅ |
| Memory per observation | ~6 fields | ~20+ fields |

Use the route timing summary for quick health checks and regression spotting.
Use the full performance-audit system when you need to diagnose which layer
(DB, Redis, serialization, upstream) is causing a slowdown.

---

## Local dev workflow

```bash
# Start the server
uvicorn app.main:app --reload

# Run a few requests against a route you care about, then:
curl http://localhost:8000/api/admin/performance/summary | python -m json.tool

# Clear and re-measure after a code change:
curl -X POST http://localhost:8000/api/admin/performance/reset
```
