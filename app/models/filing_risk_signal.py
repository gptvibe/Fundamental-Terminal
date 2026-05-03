from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class FilingRiskSignal(Base):
    __tablename__ = "filing_risk_signals"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "accession_number",
            "signal_category",
            name="uq_filing_risk_signals_company_accession_category",
        ),
        Index("ix_filing_risk_signals_company_id", "company_id"),
        Index("ix_filing_risk_signals_company_filed_date", "company_id", "filed_date"),
        Index("ix_filing_risk_signals_company_severity", "company_id", "severity", "filed_date"),
        Index("ix_filing_risk_signals_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    cik: Mapped[str] = mapped_column(String(20), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    form_type: Mapped[str] = mapped_column(String(16), nullable=False)
    filed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    signal_category: Mapped[str] = mapped_column(String(64), nullable=False)
    matched_phrase: Mapped[str] = mapped_column(String(255), nullable=False)
    context_snippet: Mapped[str] = mapped_column(String(1000), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    provenance: Mapped[str] = mapped_column(String(64), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="filing_risk_signals")