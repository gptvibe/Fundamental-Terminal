from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class CommentLetter(Base):
    __tablename__ = "comment_letters"
    __table_args__ = (
        UniqueConstraint("company_id", "accession_number", name="uq_comment_letters_company_accession"),
        Index("ix_comment_letters_company_id", "company_id"),
        Index("ix_comment_letters_company_filing_date", "company_id", "filing_date"),
        Index("ix_comment_letters_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    sec_url: Mapped[str] = mapped_column(String(500), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="comment_letters")
