from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class Form144Filing(Base):
    __tablename__ = "form144_filings"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "accession_number",
            "transaction_index",
            name="uq_form144_filings_company_accession_index",
        ),
        Index("ix_form144_filings_company_id", "company_id"),
        Index("ix_form144_filings_company_filing_date", "company_id", "filing_date"),
        Index("ix_form144_filings_company_planned_sale_date", "company_id", "planned_sale_date"),
        Index("ix_form144_filings_company_sale_filing_id", "company_id", "planned_sale_date", "filing_date", "id"),
        Index("ix_form144_filings_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    form: Mapped[str] = mapped_column(String(16), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transaction_index: Mapped[int] = mapped_column(Integer, nullable=False)
    filer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relationship_to_issuer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    issuer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    security_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    planned_sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shares_to_be_sold: Mapped[float | None] = mapped_column(Float, nullable=True)
    aggregate_market_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_owned_after_sale: Mapped[float | None] = mapped_column(Float, nullable=True)
    broker_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="form144_filings")
