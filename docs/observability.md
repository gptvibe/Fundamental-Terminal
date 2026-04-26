# Observability

## What It Covers

The internal observability layer is intentionally lightweight. It is not a full external OpenTelemetry deployment, but it does give the backend enough tracing context to explain why a route or refresh job is slow without reading raw logs.

It tracks:

- route duration
- DB duration and query count
- Redis duration and call count
- cache hit / stale / miss events
- singleflight wait count and total wait time
- upstream request duration and source host counts
- worker job duration
- aggregate failed refresh count

## Main Endpoint

Use:

- `/api/internal/observability`

The response has three top-level sections:

- `requests`: recent request records plus route summaries
- `workers`: recent worker job records plus aggregate failure counters
- `caches`: hot-response-cache and shared-upstream-cache snapshots

The route summaries are sorted by slowest `p95` latency first and include:

- total route latency
- DB duration
- Redis duration
- upstream duration
- serialization duration
- `calculation_ms`

`calculation_ms` is the unattributed remainder of route time after subtracting DB, Redis, upstream, and serialization. In practice, this is the bucket that highlights application-side joins, transformation work, or expensive calculations.

## Enable Or Disable

### Local Development

Enable explicitly:

```bash
set OBSERVABILITY_ENABLED=true
set OBSERVABILITY_MAX_RECORDS=5000
```

Disable explicitly:

```bash
set OBSERVABILITY_ENABLED=false
```

If you still use the legacy request-audit endpoint for route triage, also enable:

```bash
set PERFORMANCE_AUDIT_ENABLED=true
```

### Production

Recommended default:

- keep `OBSERVABILITY_ENABLED=true`
- keep `OBSERVABILITY_MAX_RECORDS` bounded so the in-memory store stays small
- expose `/api/internal/observability` only on trusted internal networks or behind operator auth

If you need to minimize runtime overhead temporarily on a constrained host, set:

```bash
OBSERVABILITY_ENABLED=false
```

That disables the lightweight tracing middleware and stops collecting new request and worker records.

## How To Read Slow Routes

When a route is slow:

1. Check `latency_ms.p95` for the route in `/api/internal/observability`.
2. Compare `db_duration_ms`, `redis_duration_ms`, `upstream_duration_ms`, and `serialization_ms`.
3. If those are low but `calculation_ms` is high, the time is in application-side processing.
4. Check `cache_events` and `singleflight_wait_count` to see whether the route is missing cache, serving stale content, or waiting behind a shared fill.

## Cache Visibility

Cache behavior is visible in two places:

- per-route `cache_events` in the request summaries
- backend-wide cache snapshots in the `caches` section

This is meant to answer whether a route is mostly hitting hot cache, serving stale responses, missing entirely, or waiting behind cache coordination.

## Worker Visibility

The `workers` section shows:

- recent job durations
- failed job counts per worker/job type
- aggregate `failed_refresh_count`

That counter is useful when refresh latency looks normal but refresh reliability is degrading.