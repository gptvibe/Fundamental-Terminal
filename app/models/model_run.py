from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class ModelRun(Base):
    __tablename__ = "models"
    __table_args__ = (
        Index("ix_models_company_id", "company_id"),
        Index("ix_models_company_name_version", "company_id", "model_name", "model_version"),
        Index("ix_models_company_name_calculation_version", "company_id", "model_name", "calculation_version"),
        Index("ix_models_company_name_created_id", "company_id", "model_name", "created_at", "id"),
        Index("ix_models_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    calculation_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    input_periods: Mapped[list[dict[str, Any]] | dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    company: Mapped["Company"] = relationship(back_populates="model_runs")

