from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from threading import Lock
from time import perf_counter
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.responses import JSONResponse

from app.config import settings
from app.observability import (
    RequestObservation,
    begin_request_observation,
    complete_request_observation,
    current_request_observation,
    emit_structured_log,
    end_request_observation,
    observability_enabled,
    record_sql_query,
    reset_request_observations,
    snapshot_request_observations,
)

try:
    import orjson
except Exception:  # pragma: no cover - optional dependency during bootstrap
    orjson = None


logger = logging.getLogger(__name__)

_SKIPPED_PATH_PREFIXES = (
    "/api/internal/performance-audit",
    "/api/internal/observability",
    "/health",
)
_QUERY_PARAM_VALUE_ALLOWLIST = frozenset(
    {
        "cadence",
        "dupont_mode",
        "expand",
        "max_periods",
        "max_points",
        "model",
        "refresh",
    }
)
_REDACTED_QUERY_VALUE = "REDACTED"

_REQUEST_RECORDS_LOCK = Lock()
_INSTRUMENTED_ENGINES: set[int] = set()


@dataclass(slots=True)
class RequestMetrics(RequestObservation):
    @property
    def sql_query_count(self) -> int:
        return self.db_query_count

    @property
    def sql_elapsed_ms(self) -> float:
        return self.db_duration_ms


class PerformanceAuditJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        started_at = perf_counter()
        if content is None:
            body = b"null"
        elif orjson is not None:
            body = orjson.dumps(content)
        else:
            body = json.dumps(content, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        metrics = current_request_observation()
        if metrics is not None:
            metrics.serialization_ms += (perf_counter() - started_at) * 1000.0
            metrics.response_bytes = len(body)
        return body


def is_enabled() -> bool:
    return settings.performance_audit_enabled


def should_skip_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _SKIPPED_PATH_PREFIXES)


def begin_request(request: Request) -> tuple[RequestMetrics, object]:
    raw_query_string = request.url.query
    metrics, token = begin_request_observation(
        request_id=str(uuid4()),
        method=request.method.upper(),
        path=request.url.path,
        query_string=_sanitize_query_string(request),
        request_kind=_classify_request_kind(request.method, request.url.path, raw_query_string),
    )
    return RequestMetrics(
        request_id=metrics.request_id,
        method=metrics.method,
        path=metrics.path,
        query_string=metrics.query_string,
        started_at=metrics.started_at,
        request_kind=metrics.request_kind,
        route_path=metrics.route_path,
        status_code=metrics.status_code,
        duration_ms=metrics.duration_ms,
        db_query_count=metrics.db_query_count,
        db_duration_ms=metrics.db_duration_ms,
        redis_call_count=metrics.redis_call_count,
        redis_duration_ms=metrics.redis_duration_ms,
        cache_events=dict(metrics.cache_events),
        singleflight_wait_count=metrics.singleflight_wait_count,
        singleflight_wait_ms=metrics.singleflight_wait_ms,
        upstream_request_count=metrics.upstream_request_count,
        upstream_duration_ms=metrics.upstream_duration_ms,
        upstream_sources=dict(metrics.upstream_sources),
        serialization_ms=metrics.serialization_ms,
        response_bytes=metrics.response_bytes,
        error_type=metrics.error_type,
    ), token


def complete_request(request: Request, metrics: RequestMetrics, *, status_code: int | None, error_type: str | None = None) -> None:
    route = request.scope.get("route")
    complete_request_observation(
        metrics,
        route_path=getattr(route, "path", None),
        status_code=status_code,
        error_type=error_type,
    )

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
        sql_query_count=metrics.db_query_count,
        sql_elapsed_ms=round(metrics.db_duration_ms, 3),
        redis_call_count=metrics.redis_call_count,
        redis_duration_ms=round(metrics.redis_duration_ms, 3),
        singleflight_wait_count=metrics.singleflight_wait_count,
        singleflight_wait_ms=round(metrics.singleflight_wait_ms, 3),
        upstream_request_count=metrics.upstream_request_count,
        upstream_duration_ms=round(metrics.upstream_duration_ms, 3),
        serialization_ms=round(metrics.serialization_ms, 3),
        calculation_ms=round(metrics.calculation_ms, 3),
        cache_events=metrics.cache_events,
        response_bytes=metrics.response_bytes,
        error_type=metrics.error_type,
    )


def end_request(token: object) -> None:
    end_request_observation(token)


def install_sqlalchemy_instrumentation(engine: Engine) -> None:
    if not (is_enabled() or observability_enabled()) or id(engine) in _INSTRUMENTED_ENGINES:
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
    request_snapshot = snapshot_request_observations()
    return {
        "enabled": is_enabled(),
        "observability_enabled": observability_enabled(),
        "record_count": request_snapshot["record_count"],
        "records": request_snapshot["records"],
        "route_summaries": request_snapshot["route_summaries"],
    }


def reset() -> dict[str, Any]:
    reset_payload = reset_request_observations()
    return {"enabled": is_enabled(), "cleared": reset_payload["cleared"]}


def _record_sql_timing(started_at: float | None) -> None:
    if started_at is None:
        return
    record_sql_query((perf_counter() - started_at) * 1000.0)


def _sanitize_query_string(request: Request) -> str:
    sanitized_items: list[tuple[str, str]] = []
    for key, value in request.query_params.multi_items():
        if key.lower() in _QUERY_PARAM_VALUE_ALLOWLIST:
            sanitized_value = value
        else:
            sanitized_value = _REDACTED_QUERY_VALUE
        sanitized_items.append((key, sanitized_value))

    sanitized_items.sort(key=lambda item: (item[0], item[1]))
    return urlencode(sanitized_items, doseq=True)


def _classify_request_kind(method: str, path: str, query_string: str) -> str:
    normalized_method = method.upper()
    normalized_query = query_string.lower()
    if "/refresh" in path or normalized_method != "GET":
        return "refresh"
    if "refresh=true" in normalized_query:
        return "refresh"
    return "read"
