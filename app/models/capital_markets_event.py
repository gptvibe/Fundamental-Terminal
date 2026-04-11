from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class CapitalMarketsEvent(Base):
    __tablename__ = "capital_markets_events"
    __table_args__ = (
        UniqueConstraint("company_id", "accession_number", name="uq_capital_markets_events_company_accession"),
        Index("ix_capital_markets_events_company_id", "company_id"),
        Index("ix_capital_markets_events_company_filing_date", "company_id", "filing_date"),
        Index("ix_capital_markets_events_company_filing_id", "company_id", "filing_date", "id"),
        Index("ix_capital_markets_events_company_form", "company_id", "form"),
        Index("ix_capital_markets_events_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    form: Mapped[str] = mapped_column(String(16), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_document: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_doc_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    security_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    offering_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    shelf_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_late_filer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="capital_markets_events")
