from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from statistics import median
from threading import Lock
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.responses import JSONResponse

from app.config import settings
from app.observability import emit_structured_log


logger = logging.getLogger(__name__)

_SKIPPED_PATH_PREFIXES = (
    "/api/internal/performance-audit",
    "/health",
)

_REQUEST_RECORDS_LOCK = Lock()
_REQUEST_RECORDS: list[dict[str, Any]] = []
_INSTRUMENTED_ENGINES: set[int] = set()
_CURRENT_REQUEST_METRICS: ContextVar[RequestMetrics | None] = ContextVar("performance_audit_request_metrics", default=None)


@dataclass(slots=True)
class RequestMetrics:
    request_id: str
    method: str
    path: str
    query_string: str
    started_at: float
    request_kind: str
    route_path: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    sql_query_count: int = 0
    sql_elapsed_ms: float = 0.0
    serialization_ms: float = 0.0
    response_bytes: int | None = None
    error_type: str | None = None
    notes: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sql_elapsed_ms"] = round(self.sql_elapsed_ms, 3)
        payload["serialization_ms"] = round(self.serialization_ms, 3)
        if self.duration_ms is not None:
            payload["duration_ms"] = round(self.duration_ms, 3)
        return payload


class PerformanceAuditJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        started_at = perf_counter()
        body = super().render(content)
        metrics = _CURRENT_REQUEST_METRICS.get()
        if metrics is not None:
            metrics.serialization_ms += (perf_counter() - started_at) * 1000.0
            metrics.response_bytes = len(body)
        return body


def is_enabled() -> bool:
    return settings.performance_audit_enabled


def should_skip_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _SKIPPED_PATH_PREFIXES)


def begin_request(request: Request) -> tuple[RequestMetrics, object]:
    metrics = RequestMetrics(
        request_id=str(uuid4()),
        method=request.method.upper(),
        path=request.url.path,
        query_string=request.url.query,
        started_at=perf_counter(),
        request_kind=_classify_request_kind(request.method, request.url.path, request.url.query),
    )
    token = _CURRENT_REQUEST_METRICS.set(metrics)
    return metrics, token


def complete_request(request: Request, metrics: RequestMetrics, *, status_code: int | None, error_type: str | None = None) -> None:
    metrics.status_code = status_code
    metrics.error_type = error_type
    route = request.scope.get("route")
    metrics.route_path = getattr(route, "path", None)
    metrics.duration_ms = (perf_counter() - metrics.started_at) * 1000.0

    with _REQUEST_RECORDS_LOCK:
        _REQUEST_RECORDS.append(metrics.to_payload())
        if len(_REQUEST_RECORDS) > settings.performance_audit_max_records:
            del _REQUEST_RECORDS[: len(_REQUEST_RECORDS) - settings.performance_audit_max_records]

    emit_structured_log(
        logger,
        "performance_audit.request",
        request_id=metrics.request_id,
        method=metrics.method,
        path=metrics.path,
        route_path=metrics.route_path,
        query_string=metrics.query_string or None,
        request_kind=metrics.request_kind,
        status_code=metrics.status_code,
        duration_ms=round(metrics.duration_ms or 0.0, 3),
        sql_query_count=metrics.sql_query_count,
        sql_elapsed_ms=round(metrics.sql_elapsed_ms, 3),
        serialization_ms=round(metrics.serialization_ms, 3),
        response_bytes=metrics.response_bytes,
        error_type=metrics.error_type,
    )


def end_request(token: object) -> None:
    _CURRENT_REQUEST_METRICS.reset(token)


def install_sqlalchemy_instrumentation(engine: Engine) -> None:
    if not is_enabled() or id(engine) in _INSTRUMENTED_ENGINES:
        return

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        context._ft_performance_started_at = perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        _record_sql_timing(getattr(context, "_ft_performance_started_at", None))

    @event.listens_for(engine, "handle_error")
    def _handle_error(exception_context: Any) -> None:
        execution_context = getattr(exception_context, "execution_context", None)
        _record_sql_timing(getattr(execution_context, "_ft_performance_started_at", None))

    _INSTRUMENTED_ENGINES.add(id(engine))


def snapshot() -> dict[str, Any]:
    with _REQUEST_RECORDS_LOCK:
        records = [dict(record) for record in _REQUEST_RECORDS]
    return {
        "enabled": is_enabled(),
        "record_count": len(records),
        "records": records,
        "route_summaries": _summarize_routes(records),
    }


def reset() -> dict[str, Any]:
    with _REQUEST_RECORDS_LOCK:
        cleared = len(_REQUEST_RECORDS)
        _REQUEST_RECORDS.clear()
    return {"enabled": is_enabled(), "cleared": cleared}


def _record_sql_timing(started_at: float | None) -> None:
    if started_at is None:
        return
    metrics = _CURRENT_REQUEST_METRICS.get()
    if metrics is None:
        return
    metrics.sql_query_count += 1
    metrics.sql_elapsed_ms += (perf_counter() - started_at) * 1000.0


def _classify_request_kind(method: str, path: str, query_string: str) -> str:
    normalized_method = method.upper()
    normalized_query = query_string.lower()
    if "/refresh" in path or normalized_method != "GET":
        return "refresh"
    if "refresh=true" in normalized_query:
        return "refresh"
    return "read"


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * quantile)))
    return ordered[index]


def _summarize_routes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        route_path = str(record.get("route_path") or record.get("path") or "")
        method = str(record.get("method") or "GET")
        request_kind = str(record.get("request_kind") or "read")
        grouped.setdefault((method, route_path, request_kind), []).append(record)

    summaries: list[dict[str, Any]] = []
    for (method, route_path, request_kind), route_records in grouped.items():
        durations = [float(record.get("duration_ms") or 0.0) for record in route_records]
        sql_counts = [int(record.get("sql_query_count") or 0) for record in route_records]
        sql_elapsed = [float(record.get("sql_elapsed_ms") or 0.0) for record in route_records]
        serialization = [float(record.get("serialization_ms") or 0.0) for record in route_records]
        response_sizes = [int(record.get("response_bytes") or 0) for record in route_records if record.get("response_bytes") is not None]
        summaries.append(
            {
                "method": method,
                "route_path": route_path,
                "request_kind": request_kind,
                "count": len(route_records),
                "latency_ms": {
                    "p50": round(median(durations), 3),
                    "p95": round(_percentile(durations, 0.95), 3),
                    "max": round(max(durations), 3),
                },
                "sql_query_count": {
                    "avg": round(sum(sql_counts) / len(sql_counts), 3),
                    "max": max(sql_counts),
                },
                "sql_elapsed_ms": {
                    "avg": round(sum(sql_elapsed) / len(sql_elapsed), 3),
                    "p95": round(_percentile(sql_elapsed, 0.95), 3),
                },
                "serialization_ms": {
                    "avg": round(sum(serialization) / len(serialization), 3),
                    "p95": round(_percentile(serialization, 0.95), 3),
                },
                "response_bytes": {
                    "avg": round(sum(response_sizes) / len(response_sizes), 3) if response_sizes else 0.0,
                    "max": max(response_sizes) if response_sizes else 0,
                },
            }
        )

    summaries.sort(key=lambda item: (item["latency_ms"]["p95"], item["latency_ms"]["p50"]), reverse=True)
    return summaries