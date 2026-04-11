from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class CapitalStructureSnapshot(Base):
    __tablename__ = "capital_structure_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "period_end",
            "filing_type",
            name="uq_capital_structure_snapshots_company_period_filing",
        ),
        Index("ix_capital_structure_snapshots_company_id", "company_id"),
        Index("ix_capital_structure_snapshots_company_period_end", "company_id", "period_end"),
        Index(
            "ix_capital_structure_snapshots_company_period_updated_id",
            "company_id",
            "period_end",
            "last_updated",
            "id",
        ),
        Index("ix_capital_structure_snapshots_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    accession_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    statement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    filing_acceptance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    source_statement_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="capital_structure_snapshots")
