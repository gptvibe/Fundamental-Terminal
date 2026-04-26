from __future__ import annotations

import json
import logging
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from statistics import median
from threading import Lock
from time import perf_counter
from typing import Any

from app.config import settings

try:
    import httpx
except Exception:  # pragma: no cover - optional during bootstrap
    httpx = None


def emit_structured_log(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    payload = {"event": event}
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    logger.log(level, json.dumps(payload, default=_json_default, sort_keys=True, separators=(",", ":")))


@dataclass(slots=True)
class RequestObservation:
    request_id: str
    method: str
    path: str
    query_string: str
    started_at: float
    request_kind: str
    route_path: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    db_query_count: int = 0
    db_duration_ms: float = 0.0
    redis_call_count: int = 0
    redis_duration_ms: float = 0.0
    cache_events: dict[str, dict[str, int]] = field(default_factory=dict)
    singleflight_wait_count: int = 0
    singleflight_wait_ms: float = 0.0
    upstream_request_count: int = 0
    upstream_duration_ms: float = 0.0
    upstream_sources: dict[str, int] = field(default_factory=dict)
    serialization_ms: float = 0.0
    response_bytes: int | None = None
    error_type: str | None = None

    @property
    def calculation_ms(self) -> float:
        duration_ms = float(self.duration_ms or 0.0)
        attributed_ms = self.db_duration_ms + self.redis_duration_ms + self.upstream_duration_ms + self.serialization_ms
        return max(duration_ms - attributed_ms, 0.0)

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["db_duration_ms"] = round(self.db_duration_ms, 3)
        payload["redis_duration_ms"] = round(self.redis_duration_ms, 3)
        payload["singleflight_wait_ms"] = round(self.singleflight_wait_ms, 3)
        payload["upstream_duration_ms"] = round(self.upstream_duration_ms, 3)
        payload["serialization_ms"] = round(self.serialization_ms, 3)
        payload["calculation_ms"] = round(self.calculation_ms, 3)
        if self.duration_ms is not None:
            payload["duration_ms"] = round(self.duration_ms, 3)
        payload["cache_events"] = {
            cache_name: dict(sorted(outcomes.items()))
            for cache_name, outcomes in sorted(self.cache_events.items())
        }
        payload["upstream_sources"] = dict(sorted(self.upstream_sources.items()))
        return payload


@dataclass(slots=True)
class WorkerObservation:
    trace_id: str
    worker_kind: str
    job_name: str
    ticker: str | None
    started_at: float
    status: str = "running"
    duration_ms: float | None = None
    error_type: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.duration_ms is not None:
            payload["duration_ms"] = round(self.duration_ms, 3)
        return payload


_REQUEST_RECORDS_LOCK = Lock()
_REQUEST_RECORDS: list[dict[str, Any]] = []
_WORKER_RECORDS_LOCK = Lock()
_WORKER_RECORDS: list[dict[str, Any]] = []
_WORKER_TOTALS_LOCK = Lock()
_WORKER_TOTALS: dict[str, int] = {"failed_refresh_count": 0}
_CURRENT_REQUEST: ContextVar[RequestObservation | None] = ContextVar("observability_request", default=None)
_HTTPX_PATCH_LOCK = Lock()
_HTTPX_PATCHED = False


def observability_enabled() -> bool:
    return settings.observability_enabled


def begin_request_observation(
    *,
    request_id: str,
    method: str,
    path: str,
    query_string: str,
    request_kind: str,
) -> tuple[RequestObservation, object]:
    observation = RequestObservation(
        request_id=request_id,
        method=method,
        path=path,
        query_string=query_string,
        started_at=perf_counter(),
        request_kind=request_kind,
    )
    token = _CURRENT_REQUEST.set(observation)
    return observation, token


def current_request_observation() -> RequestObservation | None:
    return _CURRENT_REQUEST.get()


def complete_request_observation(
    observation: RequestObservation,
    *,
    route_path: str | None,
    status_code: int | None,
    error_type: str | None = None,
) -> None:
    observation.route_path = route_path
    observation.status_code = status_code
    observation.error_type = error_type
    observation.duration_ms = (perf_counter() - observation.started_at) * 1000.0

    with _REQUEST_RECORDS_LOCK:
        _REQUEST_RECORDS.append(observation.to_payload())
        if len(_REQUEST_RECORDS) > settings.observability_max_records:
            del _REQUEST_RECORDS[: len(_REQUEST_RECORDS) - settings.observability_max_records]


def end_request_observation(token: object) -> None:
    _CURRENT_REQUEST.reset(token)


def record_sql_query(duration_ms: float) -> None:
    observation = current_request_observation()
    if observation is None:
        return
    observation.db_query_count += 1
    observation.db_duration_ms += max(duration_ms, 0.0)


def record_redis_call(duration_ms: float) -> None:
    observation = current_request_observation()
    if observation is None:
        return
    observation.redis_call_count += 1
    observation.redis_duration_ms += max(duration_ms, 0.0)


def record_cache_event(cache_name: str, outcome: str) -> None:
    observation = current_request_observation()
    if observation is None:
        return
    normalized_cache_name = str(cache_name or "cache").strip() or "cache"
    normalized_outcome = str(outcome or "unknown").strip() or "unknown"
    cache_events = observation.cache_events.setdefault(normalized_cache_name, {})
    cache_events[normalized_outcome] = int(cache_events.get(normalized_outcome, 0)) + 1


def record_singleflight_wait(duration_ms: float) -> None:
    observation = current_request_observation()
    if observation is None:
        return
    observation.singleflight_wait_count += 1
    observation.singleflight_wait_ms += max(duration_ms, 0.0)


def record_upstream_request(duration_ms: float, *, source: str) -> None:
    observation = current_request_observation()
    if observation is None:
        return
    normalized_source = str(source or "upstream").strip() or "upstream"
    observation.upstream_request_count += 1
    observation.upstream_duration_ms += max(duration_ms, 0.0)
    observation.upstream_sources[normalized_source] = int(observation.upstream_sources.get(normalized_source, 0)) + 1


@contextmanager
def observe_redis_call() -> Any:
    started_at = perf_counter()
    try:
        yield
    finally:
        record_redis_call((perf_counter() - started_at) * 1000.0)


@contextmanager
def observe_upstream_request(*, source: str) -> Any:
    started_at = perf_counter()
    try:
        yield
    finally:
        record_upstream_request((perf_counter() - started_at) * 1000.0, source=source)


@contextmanager
def observe_worker_job(
    *,
    worker_kind: str,
    job_name: str,
    trace_id: str,
    ticker: str | None = None,
    count_refresh_failure: bool = False,
) -> Any:
    observation = WorkerObservation(
        trace_id=trace_id,
        worker_kind=worker_kind,
        job_name=job_name,
        ticker=ticker,
        started_at=perf_counter(),
    )
    try:
        yield observation
        observation.status = "completed"
    except Exception as exc:
        observation.status = "failed"
        observation.error_type = type(exc).__name__
        if count_refresh_failure:
            with _WORKER_TOTALS_LOCK:
                _WORKER_TOTALS["failed_refresh_count"] = int(_WORKER_TOTALS.get("failed_refresh_count", 0)) + 1
        raise
    finally:
        observation.duration_ms = (perf_counter() - observation.started_at) * 1000.0
        with _WORKER_RECORDS_LOCK:
            _WORKER_RECORDS.append(observation.to_payload())
            if len(_WORKER_RECORDS) > settings.observability_max_records:
                del _WORKER_RECORDS[: len(_WORKER_RECORDS) - settings.observability_max_records]


def snapshot_request_observations() -> dict[str, Any]:
    with _REQUEST_RECORDS_LOCK:
        records = [dict(record) for record in _REQUEST_RECORDS]
    return {
        "record_count": len(records),
        "records": records,
        "route_summaries": _summarize_routes(records),
    }


def snapshot_worker_observations() -> dict[str, Any]:
    with _WORKER_RECORDS_LOCK:
        records = [dict(record) for record in _WORKER_RECORDS]
    with _WORKER_TOTALS_LOCK:
        totals = dict(_WORKER_TOTALS)
    return {
        "record_count": len(records),
        "records": records,
        "totals": totals,
        "job_summaries": _summarize_workers(records),
    }


def reset_request_observations() -> dict[str, int]:
    with _REQUEST_RECORDS_LOCK:
        cleared = len(_REQUEST_RECORDS)
        _REQUEST_RECORDS.clear()
    return {"cleared": cleared}


def reset_worker_observations() -> dict[str, int]:
    with _WORKER_RECORDS_LOCK:
        cleared = len(_WORKER_RECORDS)
        _WORKER_RECORDS.clear()
    with _WORKER_TOTALS_LOCK:
        _WORKER_TOTALS["failed_refresh_count"] = 0
    return {"cleared": cleared}


def install_httpx_observability() -> None:
    global _HTTPX_PATCHED

    if httpx is None:
        return

    with _HTTPX_PATCH_LOCK:
        if _HTTPX_PATCHED:
            return

        original_client_request = httpx.Client.request

        def _instrumented_client_request(self, method: str, url: Any, *args: Any, **kwargs: Any):
            with observe_upstream_request(source=_httpx_source_label(url)):
                return original_client_request(self, method, url, *args, **kwargs)

        httpx.Client.request = _instrumented_client_request

        if hasattr(httpx, "AsyncClient"):
            original_async_request = httpx.AsyncClient.request

            async def _instrumented_async_request(self, method: str, url: Any, *args: Any, **kwargs: Any):
                started_at = perf_counter()
                try:
                    return await original_async_request(self, method, url, *args, **kwargs)
                finally:
                    record_upstream_request((perf_counter() - started_at) * 1000.0, source=_httpx_source_label(url))

            httpx.AsyncClient.request = _instrumented_async_request

        _HTTPX_PATCHED = True


def _httpx_source_label(url: Any) -> str:
    host = getattr(url, "host", None)
    if isinstance(host, str) and host.strip():
        return host.strip()

    text = str(url or "").strip()
    if not text:
        return "upstream"
    if "://" in text:
        return text.split("://", 1)[1].split("/", 1)[0] or "upstream"
    return text.split("/", 1)[0] or "upstream"


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * quantile)))
    return ordered[index]


def _summarize_routes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        route_path = str(record.get("route_path") or record.get("path") or "")
        grouped[(str(record.get("method") or "GET"), route_path, str(record.get("request_kind") or "read"))].append(record)

    summaries: list[dict[str, Any]] = []
    for (method, route_path, request_kind), route_records in grouped.items():
        durations = [float(record.get("duration_ms") or 0.0) for record in route_records]
        db_durations = [float(record.get("db_duration_ms") or 0.0) for record in route_records]
        redis_durations = [float(record.get("redis_duration_ms") or 0.0) for record in route_records]
        upstream_durations = [float(record.get("upstream_duration_ms") or 0.0) for record in route_records]
        serialization = [float(record.get("serialization_ms") or 0.0) for record in route_records]
        calculation = [float(record.get("calculation_ms") or 0.0) for record in route_records]
        db_counts = [int(record.get("db_query_count") or 0) for record in route_records]
        redis_counts = [int(record.get("redis_call_count") or 0) for record in route_records]
        upstream_counts = [int(record.get("upstream_request_count") or 0) for record in route_records]
        singleflight_counts = [int(record.get("singleflight_wait_count") or 0) for record in route_records]
        cache_totals: dict[str, int] = defaultdict(int)
        for record in route_records:
            for outcomes in (record.get("cache_events") or {}).values():
                if not isinstance(outcomes, dict):
                    continue
                for outcome, count in outcomes.items():
                    cache_totals[str(outcome)] += int(count or 0)

        summaries.append(
            {
                "method": method,
                "route_path": route_path,
                "request_kind": request_kind,
                "count": len(route_records),
                "latency_ms": _summary_stats(durations),
                "db_duration_ms": _summary_stats(db_durations),
                "redis_duration_ms": _summary_stats(redis_durations),
                "upstream_duration_ms": _summary_stats(upstream_durations),
                "serialization_ms": _summary_stats(serialization),
                "calculation_ms": _summary_stats(calculation),
                "db_query_count": _count_stats(db_counts),
                "redis_call_count": _count_stats(redis_counts),
                "upstream_request_count": _count_stats(upstream_counts),
                "singleflight_wait_count": _count_stats(singleflight_counts),
                "cache_events": dict(sorted(cache_totals.items())),
            }
        )

    summaries.sort(key=lambda item: (item["latency_ms"]["p95"], item["latency_ms"]["p50"]), reverse=True)
    return summaries


def _summary_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "avg": round(sum(values) / len(values), 3),
        "p50": round(median(values), 3),
        "p95": round(_percentile(values, 0.95), 3),
        "max": round(max(values), 3),
    }


def _count_stats(values: list[int]) -> dict[str, float]:
    if not values:
        return {"avg": 0.0, "max": 0}
    return {
        "avg": round(sum(values) / len(values), 3),
        "max": max(values),
    }


def _summarize_workers(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(str(record.get("worker_kind") or "worker"), str(record.get("job_name") or "job"))].append(record)

    summaries: list[dict[str, Any]] = []
    for (worker_kind, job_name), job_records in grouped.items():
        durations = [float(record.get("duration_ms") or 0.0) for record in job_records]
        failed_count = sum(1 for record in job_records if record.get("status") == "failed")
        summaries.append(
            {
                "worker_kind": worker_kind,
                "job_name": job_name,
                "count": len(job_records),
                "failed_count": failed_count,
                "duration_ms": _summary_stats(durations),
            }
        )

    summaries.sort(key=lambda item: (item["failed_count"], item["duration_ms"]["p95"]), reverse=True)
    return summaries


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


install_httpx_observability()