from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, ProvenanceEnvelope, RefreshState


class ModelPayload(BaseModel):
    schema_version: str = "2.0"
    model_name: str
    model_version: str
    created_at: datetime
    input_periods: dict[str, Any] | list[dict[str, Any]] | None = None
    result: dict[str, Any]


class CompanyModelsResponse(ProvenanceEnvelope):
    company: CompanyPayload | None
    requested_models: list[str]
    models: list[ModelPayload]
    refresh: RefreshState
    diagnostics: DataQualityDiagnosticsPayload = Field(default_factory=DataQualityDiagnosticsPayload)
