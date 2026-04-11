from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.beneficial_ownership_party import BeneficialOwnershipParty
    from app.models.company import Company


class BeneficialOwnershipReport(Base):
    __tablename__ = "beneficial_ownership_reports"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "accession_number",
            name="uq_beneficial_ownership_reports_company_accession",
        ),
        Index("ix_beneficial_ownership_reports_company_id", "company_id"),
        Index("ix_beneficial_ownership_reports_company_filing_date", "company_id", "filing_date"),
        Index("ix_beneficial_ownership_reports_company_filing_id", "company_id", "filing_date", "id"),
        Index("ix_beneficial_ownership_reports_company_chain_key", "company_id", "amendment_chain_key"),
        Index("ix_beneficial_ownership_reports_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    form: Mapped[str] = mapped_column(String(16), nullable=False)
    base_form: Mapped[str] = mapped_column(String(8), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_amendment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    primary_document: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_doc_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    amendment_chain_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    previous_accession_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    amendment_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amendment_chain_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="beneficial_ownership_reports")
    parties: Mapped[list["BeneficialOwnershipParty"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )