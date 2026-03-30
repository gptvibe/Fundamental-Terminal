from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status
from starlette.responses import StreamingResponse

from app.api.source_contracts import add_internal_route, add_user_visible_route
from app.api.schemas.jobs import RefreshQueuedResponse


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["jobs"])
    add_internal_route(router, "/health", main_module.healthcheck, methods=["GET"])
    add_internal_route(router, "/api/internal/cache-metrics", main_module.cache_metrics, methods=["GET"])
    add_user_visible_route(
        router,
        "/api/jobs/{job_id}/events",
        main_module.stream_job_events,
        methods=["GET"],
        response_class=StreamingResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/refresh",
        main_module.refresh_company,
        methods=["POST"],
        response_model=RefreshQueuedResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    return router
