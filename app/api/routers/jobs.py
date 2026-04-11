from __future__ import annotations

from fastapi import APIRouter, status
from starlette.responses import StreamingResponse

from app.api.handlers import jobs as handlers
from app.api.schemas.health import DatabasePoolStatusResponse
from app.api.source_contracts import add_internal_route, add_user_visible_route
from app.api.schemas.jobs import RefreshQueuedResponse


def build_router() -> APIRouter:
    router = APIRouter(tags=["jobs"])
    add_internal_route(router, "/health", handlers.healthcheck, methods=["GET"])
    add_internal_route(router, "/api/internal/cache-metrics", handlers.cache_metrics, methods=["GET"])
    add_internal_route(router, "/api/internal/cache-metrics/invalidate", handlers.invalidate_cache_metrics, methods=["POST"])
    add_internal_route(router, "/api/internal/performance-audit", handlers.performance_audit_snapshot, methods=["GET"])
    add_internal_route(router, "/api/internal/performance-audit/reset", handlers.reset_performance_audit, methods=["POST"])
    add_user_visible_route(
        router,
        "/api/health/pool-status",
        handlers.pool_status,
        methods=["GET"],
        response_model=DatabasePoolStatusResponse,
    )
    add_user_visible_route(
        router,
        "/api/jobs/{job_id}/events",
        handlers.stream_job_events,
        methods=["GET"],
        response_class=StreamingResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/refresh",
        handlers.refresh_company,
        methods=["POST"],
        response_model=RefreshQueuedResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    return router
