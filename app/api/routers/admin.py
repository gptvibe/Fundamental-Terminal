from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers import admin as handlers
from app.api.source_contracts import add_internal_route


def build_router() -> APIRouter:
    router = APIRouter(tags=["admin"])
    add_internal_route(router, "/api/admin/performance/summary", handlers.performance_summary, methods=["GET"])
    add_internal_route(router, "/api/admin/performance/reset", handlers.reset_timing, methods=["POST"])
    return router


__all__ = ["build_router"]
