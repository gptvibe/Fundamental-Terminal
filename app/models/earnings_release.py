from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class EarningsRelease(Base):
    __tablename__ = "earnings_releases"
    __table_args__ = (
        UniqueConstraint("company_id", "accession_number", name="uq_earnings_releases_company_accession"),
        Index("ix_earnings_releases_company_id", "company_id"),
        Index("ix_earnings_releases_company_filing_date", "company_id", "filing_date"),
        Index("ix_earnings_releases_company_report_date", "company_id", "reported_period_end"),
        Index("ix_earnings_releases_company_filing_reported_id", "company_id", "filing_date", "reported_period_end", "id"),
        Index("ix_earnings_releases_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    form: Mapped[str] = mapped_column(String(16), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    primary_document: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exhibit_document: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exhibit_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reported_period_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reported_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    diluted_eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_guidance_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_guidance_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_guidance_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_guidance_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    share_repurchase_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_per_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    highlights: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    parse_state: Mapped[str] = mapped_column(String(32), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    filing_acceptance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetch_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="earnings_releases")
