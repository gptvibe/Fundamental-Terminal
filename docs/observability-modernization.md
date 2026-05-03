# Observability Modernization Plan

## Current Custom Observability

`app/observability.py` is a self-contained, zero-dependency observability layer
with the following responsibilities:

| Responsibility | Implementation |
|---|---|
| Structured log emission | `emit_structured_log()` – JSON-serialises key/value fields and writes through Python `logging` |
| Request span lifecycle | `begin_request_observation` / `complete_request_observation` / `end_request_observation` – stores a `RequestObservation` dataclass in a `ContextVar` |
| Span attribute recording | `record_sql_query`, `record_redis_call`, `record_cache_event`, `record_singleflight_wait`, `record_upstream_request` – mutate the active span in-process |
| Context-manager spans | `observe_redis_call`, `observe_upstream_request`, `observe_worker_job` – thin wrappers that start/stop timers and call the recording functions above |
| HTTP auto-instrumentation | `install_httpx_observability()` – monkey-patches `httpx.Client.request` and `httpx.AsyncClient.request` to add upstream timing automatically |
| In-process metric store | Fixed-size circular buffers (`_REQUEST_RECORDS`, `_WORKER_RECORDS`) protected by `threading.Lock`; exposed through `snapshot_*` and `reset_*` helpers |
| Aggregation / summaries | `_summarize_routes`, `_summarize_workers` – compute avg/p50/p95/max latency per route or worker job; consumed by the internal observability API endpoint |

The system surfaces data at `/api/internal/observability` (request records and
summaries) and through structured JSON log lines written to stdout.

## Mapping to OpenTelemetry Concepts

| Current concept | OTel equivalent |
|---|---|
| `RequestObservation` / `WorkerObservation` | `Span` (with attributes and status) |
| `ContextVar[RequestObservation]` | OTel context propagation (`context.attach` / `context.detach`) |
| `record_sql_query` / `record_redis_call` etc. | Span attributes (e.g., `db.duration_ms`) or child span events |
| `observe_redis_call`, `observe_upstream_request` | Child spans created with a `Tracer` |
| `observe_worker_job` | Root span with `SpanKind.INTERNAL` |
| `install_httpx_observability()` | `opentelemetry-instrumentation-httpx` auto-instrumentation |
| `emit_structured_log` | OTel Logs SDK (`LoggerProvider` / `LogRecord`) |
| `_REQUEST_RECORDS` circular buffer | OTLP exporter → collector (Prometheus, Jaeger, Grafana, etc.) |
| `_summarize_routes` p50/p95 aggregation | Prometheus histogram / OTel `Histogram` metric |

## Low-Risk Migration Path

The migration can be done incrementally without touching production behavior at
any single step.

### Phase 1 — Add OTel SDK alongside the existing system (no behavior change)

1. Add `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc` (or
   `otlp-proto-http`) to `requirements.txt`.
2. Configure a `TracerProvider` and `LoggerProvider` at application startup
   (guarded by a feature flag, e.g. `OTEL_ENABLED=false` by default).
3. Keep all existing `observability.py` functions fully operational.
4. Emit a parallel OTel span for each `observe_worker_job` call so that the
   OTel pipeline can be validated in a dev/staging environment without
   affecting production.

### Phase 2 — Replace per-category recording functions

Replace `record_sql_query`, `record_redis_call`, etc. with calls that mutate
both the existing `RequestObservation` (keeping the internal `/observability`
endpoint working) and the active OTel span's attributes.  This is additive and
does not change the API surface.

### Phase 3 — Replace `install_httpx_observability` with the OTel httpx instrumentation

The official `opentelemetry-instrumentation-httpx` package covers both sync and
async clients cleanly.  Once validated, remove the manual monkey-patch from
`observability.py`.

### Phase 4 — Replace `emit_structured_log` with OTel Logs SDK

Route structured log output through an OTel `Logger`.  Keep the JSON-to-stdout
format as a fallback for environments without a collector.

### Phase 5 — Replace in-process metric store with exported metrics

Once an OTLP collector is deployed alongside the backend, the circular buffers
and `_summarize_routes` aggregations can be replaced by OTel `Histogram` and
`Counter` instruments that push to the collector.  Retire the
`/api/internal/observability` endpoint or keep it as a lightweight health
signal.

## Risks and Things Not to Change Yet

- **The `/api/internal/observability` endpoint is the primary debuggability
  tool today.** Do not remove the in-process buffers or the summary aggregation
  until a compatible Grafana/Prometheus dashboard is operational and validated.

- **The `ContextVar` approach is correct and thread-safe for async FastAPI.**
  OTel context propagation also uses `ContextVar` internally; switching should
  be transparent but must be tested against concurrent request scenarios.

- **The monkey-patch in `install_httpx_observability` is called once at
  startup and guarded by `_HTTPX_PATCHED`.** Removing it before the OTel
  replacement is instrumented will silently drop upstream timing data from all
  request observations.

- **Do not add OTel dependencies to production requirements until a collector
  endpoint (`OTEL_EXPORTER_OTLP_ENDPOINT`) is available in the deployment.**
  Without a collector, the OTLP exporter will retry and log errors on every
  span export, adding background noise.

- **`_WORKER_TOTALS["failed_refresh_count"]` is consumed by the `/health`
  endpoint.** Keep it regardless of which path worker timing takes during
  migration.
