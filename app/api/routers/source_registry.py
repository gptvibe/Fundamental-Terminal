from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers import source_registry as handlers
from app.api.schemas.source_registry import SourceRegistryResponse
from app.api.source_contracts import add_user_visible_route


def build_router() -> APIRouter:
    router = APIRouter(tags=["source-registry"])
    add_user_visible_route(
        router,
        "/api/source-registry",
        handlers.source_registry,
        methods=["GET"],
        response_model=SourceRegistryResponse,
    )
    return router