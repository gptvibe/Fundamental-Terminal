from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class FinancialRestatement(Base):
    __tablename__ = "financial_restatements"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "statement_type",
            "accession_number",
            "detection_kind",
            name="uq_financial_restatements_company_statement_accession_kind",
        ),
        Index("ix_financial_restatements_company_id", "company_id"),
        Index("ix_financial_restatements_company_period_end", "company_id", "period_end"),
        Index("ix_financial_restatements_company_filing_date", "company_id", "filing_date"),
        Index("ix_financial_restatements_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    statement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    filing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    form: Mapped[str] = mapped_column(String(32), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_accession_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    previous_filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    filing_acceptance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_filing_acceptance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    previous_source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_amendment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detection_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_metric_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    companyfacts_changes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    normalized_data_changes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    confidence_impact: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="financial_restatements")