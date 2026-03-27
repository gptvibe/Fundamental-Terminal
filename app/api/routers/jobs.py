from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status
from starlette.responses import StreamingResponse

from app.api.schemas.jobs import RefreshQueuedResponse


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["jobs"])
    router.add_api_route("/health", main_module.healthcheck, methods=["GET"])
    router.add_api_route("/api/internal/cache-metrics", main_module.cache_metrics, methods=["GET"])
    router.add_api_route(
        "/api/jobs/{job_id}/events",
        main_module.stream_job_events,
        methods=["GET"],
        response_class=StreamingResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/refresh",
        main_module.refresh_company,
        methods=["POST"],
        response_model=RefreshQueuedResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    return router
