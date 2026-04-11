from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class DerivedMetricPoint(Base):
    __tablename__ = "derived_metric_points"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "period_end",
            "period_type",
            "metric_key",
            name="uq_derived_metric_points_company_period_type_metric",
        ),
        Index("ix_derived_metric_points_company_id", "company_id"),
        Index("ix_derived_metric_points_company_period_end", "company_id", "period_end"),
        Index(
            "ix_derived_metric_points_company_type_period_end",
            "company_id",
            "period_type",
            "period_end",
            "metric_key",
        ),
        Index("ix_derived_metric_points_company_metric", "company_id", "metric_key"),
        Index("ix_derived_metric_points_period_type", "period_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    filing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[float | None] = mapped_column(nullable=True)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_proxy: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    source_statement_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="derived_metric_points")
