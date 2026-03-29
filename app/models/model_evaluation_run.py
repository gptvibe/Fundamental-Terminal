from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelEvaluationRun(Base):
    __tablename__ = "model_evaluation_runs"
    __table_args__ = (
        Index("ix_model_evaluation_runs_suite_key", "suite_key", "created_at"),
        Index("ix_model_evaluation_runs_status", "status", "created_at"),
        Index("ix_model_evaluation_runs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    suite_key: Mapped[str] = mapped_column(String(120), nullable=False)
    candidate_label: Mapped[str] = mapped_column(String(120), nullable=False)
    baseline_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    model_names: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    deltas: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    artifacts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
