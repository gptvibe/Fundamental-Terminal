from __future__ import annotations

from pydantic import BaseModel, Field


class DatabasePoolStatusResponse(BaseModel):
    label: str
    pool_class: str
    pool_size: int = Field(ge=0)
    max_overflow: int
    checked_out: int = Field(ge=0)
    overflow: int = Field(ge=0)
    current_capacity: int = Field(ge=0)
    total_capacity: int | None = Field(default=None, ge=0)
    utilization_ratio: float = Field(ge=0.0)
    queue_wait_time_ms: float = Field(ge=0.0)
    average_queue_wait_time_ms: float = Field(ge=0.0)
    max_queue_wait_time_ms: float = Field(ge=0.0)
    queue_wait_samples: int = Field(ge=0)
    pool_timeout_seconds: int = Field(ge=0)