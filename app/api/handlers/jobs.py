from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
async def healthcheck() -> dict[str, Any]:
    database, database_ok = await _database_health_payload()
    redis, redis_ok = await _redis_health_payload()
    worker, worker_ok = await _worker_health_payload()
    sec_upstream, sec_ok = await _sec_upstream_health_payload()
    sec_upstream.pop("healthy", None)

    uptime_seconds = max(0, int((datetime.now(timezone.utc) - _api_started_at).total_seconds()))
    component_health = {
        "db": database_ok,
        "redis": redis_ok,
        "worker": worker_ok,
        "sec_upstream": sec_ok,
    }
    degraded_components = [name for name, is_ok in component_health.items() if not is_ok]
    overall_status = "ok" if all((database_ok, redis_ok, worker_ok, sec_ok)) else "degraded"
    return {
        "status": "ok",
        "overall_status": overall_status,
        "degraded_components": degraded_components,
        "service": "api",
        "version": "1.1.0",
        "uptime_seconds": uptime_seconds,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "components": {
            "api": {
                "status": "ok",
                "observability_enabled": settings.observability_enabled,
                "performance_audit_enabled": settings.performance_audit_enabled,
                "security_headers_enabled": settings.security_headers_enabled,
                "auth_mode": settings.auth_mode,
                "auth_required_path_prefixes": list(settings.auth_required_path_prefixes),
                "rate_limit": {
                    "enabled": settings.api_rate_limit_enabled,
                    "requests": settings.api_rate_limit_requests,
                    "window_seconds": settings.api_rate_limit_window_seconds,
                    "trust_proxy": settings.api_rate_limit_trust_proxy,
                },
            },
            "db": database,
            "redis": redis,
            "worker": worker,
            "sec_upstream": sec_upstream,
        },
    }


@main_bound
async def readiness_check() -> dict[str, str]:
    try:
        async with _session_scope() as session:
            result = session.execute(select(1))
            if inspect.isawaitable(result):
                await result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database not ready") from exc
    return {"status": "ok"}


@main_bound
async def cache_metrics() -> dict[str, Any]:
    hot_cache_metrics = await shared_hot_response_cache.snapshot_metrics()
    backend_details = hot_cache_metrics.get("backend_details", {})
    return {
        "search_cache": {
            "entries": len(_search_response_cache),
            "ttl_seconds": 0,
        },
        "hot_cache_backend": hot_cache_metrics["backend"],
        "hot_cache_backend_mode": hot_cache_metrics["backend_mode"],
        "hot_cache_status": backend_details.get("status"),
        "hot_cache_scope": backend_details.get("cache_scope"),
        "hot_cache_cross_instance_reuse": backend_details.get("cross_instance_reuse"),
        "hot_cache_operator_summary": backend_details.get("summary"),
        "hot_cache": hot_cache_metrics,
    }


@main_bound
async def invalidate_cache_metrics(
    ticker: str | None = Query(default=None),
    dataset: str | None = Query(default=None),
    schema_version: str | None = Query(default=None),
    as_of: str | None = Query(default=None),
) -> dict[str, Any]:
    normalized_ticker = _normalize_ticker(ticker) if ticker and ticker.strip() else None
    normalized_dataset = dataset.strip().lower() if dataset and dataset.strip() else None
    normalized_schema = schema_version.strip() if schema_version and schema_version.strip() else None
    requested_as_of = (as_of or "").strip()
    normalized_as_of = None
    if as_of is not None:
        normalized_as_of = _normalize_as_of(_validated_as_of(requested_as_of or None)) or "latest"
    try:
        return await shared_hot_response_cache.invalidate(
            ticker=normalized_ticker,
            dataset=normalized_dataset,
            schema_version=normalized_schema,
            as_of=normalized_as_of,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@main_bound
def performance_audit_snapshot() -> dict[str, Any]:
    return snapshot_performance_audit_store()


@main_bound
def reset_performance_audit() -> dict[str, Any]:
    return reset_performance_audit_store()


@main_bound
async def observability_snapshot() -> dict[str, Any]:
    hot_cache_metrics = await shared_hot_response_cache.snapshot_metrics()
    return {
        "enabled": settings.observability_enabled,
        "requests": snapshot_request_observations(),
        "workers": snapshot_worker_observations(),
        "caches": {
            "hot_response": hot_cache_metrics,
            "shared_upstream": shared_upstream_cache.snapshot_metrics(),
        },
    }


@main_bound
def pool_status() -> DatabasePoolStatusResponse:
    snapshot = get_async_pool_status()
    return DatabasePoolStatusResponse.model_validate(snapshot, from_attributes=True)


@main_bound
async def stream_job_events(job_id: str, request: Request) -> StreamingResponse:
    try:
        backlog, queue, unsubscribe = await status_broker.async_subscribe(job_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown job ID")

    async def event_generator():
        try:
            for event in backlog:
                yield status_broker.format_sse(job_id, event)
                if event.status in {"completed", "failed"}:
                    return

            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                yield status_broker.format_sse(job_id, event)
                if event.status in {"completed", "failed"}:
                    break
        finally:
            unsubscribe()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@main_bound
def refresh_company(
    ticker: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    session: Session = Depends(get_db_session),
) -> RefreshQueuedResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    queue_ticker = snapshot.company.ticker if snapshot is not None else normalized_ticker
    job_id = queue_company_refresh(queue_ticker, force=force)
    return RefreshQueuedResponse(
        status="queued",
        ticker=queue_ticker,
        force=force,
        refresh=RefreshState(triggered=True, reason="manual", ticker=queue_ticker, job_id=job_id),
    )


__all__ = [
    "cache_metrics",
    "healthcheck",
    "invalidate_cache_metrics",
    "observability_snapshot",
    "performance_audit_snapshot",
    "pool_status",
    "readiness_check",
    "refresh_company",
    "reset_performance_audit",
    "stream_job_events",
]
