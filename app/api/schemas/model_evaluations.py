from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.api.schemas.common import Number, ProvenanceEnvelope


class ModelEvaluationMetricDeltaPayload(BaseModel):
    calibration: Number = None
    stability: Number = None
    mean_absolute_error: Number = None
    root_mean_square_error: Number = None
    mean_signed_error: Number = None
    sample_count: Number = None


class ModelEvaluationMetricPayload(BaseModel):
    model_name: str
    sample_count: int = 0
    calibration: Number = None
    stability: Number = None
    mean_absolute_error: Number = None
    root_mean_square_error: Number = None
    mean_signed_error: Number = None
    status: str = "no_samples"
    delta: ModelEvaluationMetricDeltaPayload = Field(default_factory=ModelEvaluationMetricDeltaPayload)


class ModelEvaluationRunPayload(BaseModel):
    id: int | None = None
    suite_key: str
    candidate_label: str
    baseline_label: str | None = None
    status: str
    completed_at: datetime | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    models: list[ModelEvaluationMetricPayload] = Field(default_factory=list)
    deltas_present: bool = False


class ModelEvaluationResponse(ProvenanceEnvelope):
    run: ModelEvaluationRunPayload | None = None
