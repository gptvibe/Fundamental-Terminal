from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class EarningsModelPoint(Base):
    __tablename__ = "earnings_model_points"
    __table_args__ = (
        UniqueConstraint("company_id", "period_end", name="uq_earnings_model_points_company_period"),
        Index("ix_earnings_model_points_company_id", "company_id"),
        Index("ix_earnings_model_points_company_period_end", "company_id", "period_end"),
        Index("ix_earnings_model_points_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filing_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_drift: Mapped[float | None] = mapped_column(Float, nullable=True)
    earnings_momentum_drift: Mapped[float | None] = mapped_column(Float, nullable=True)
    segment_contribution_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    release_statement_coverage_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    fallback_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    stale_period_warning: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    explainability: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    source_statement_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    source_release_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="earnings_model_points")