from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.schemas.models import CompanyModelsResponse


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["models"])
    router.add_api_route(
        "/api/companies/{ticker}/models",
        main_module.company_models,
        methods=["GET"],
        response_model=CompanyModelsResponse,
    )
    return router
