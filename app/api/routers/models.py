from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers import models as handlers
from app.api.source_contracts import add_user_visible_route
from app.api.schemas.model_evaluations import ModelEvaluationResponse
from app.api.schemas.models import CompanyModelsResponse


def build_router() -> APIRouter:
    router = APIRouter(tags=["models"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/models",
        handlers.company_models,
        methods=["GET"],
        response_model=CompanyModelsResponse,
    )
    add_user_visible_route(
        router,
        "/api/model-evaluations/latest",
        handlers.latest_model_evaluation,
        methods=["GET"],
        response_model=ModelEvaluationResponse,
    )
    return router
